import logging
import re
from enum import StrEnum
from pathlib import Path

import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from lean_interact import (
    FileCommand,
    LeanREPLConfig,
    LeanServer,
    LocalProject,
    ProofStep,
)
from lean_interact.interface import LeanError
from lean_interact.interface import Sorry as REPLSorry

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.database.sorry import Sorry

logger = logging.getLogger(__name__)


class StrategyMode(StrEnum):
    """Enumeration of different modes for the TacticByTacticStrategy."""

    INTERACTIVE = "interactive"
    PREDEFINED = "predefined"
    LLM = "llm"


TACTIC_GENERATION_PROMPT = """You are an advanced AI that has studied all known mathematics and Lean 4 tactics.
You are proving a theorem in Lean 4 step by step.

You can choose which proof state to work on at each step.

File context:
```lean4
{file_context}
```

Full proof search history (chronological order):
{search_history}

Generate the next action in the proof search:
1. First choose which proof state ID to work on
2. Then provide a single specific Lean 4 tactic to apply to that state

Only provide the proof state ID and tactic, no explanation. Do NOT use the
tactic `sorry`.
Use this exact format: [state_id] tactic

Examples of good responses:
```
[12] rfl
```

```
[5] intro h
```

```
[8] apply Nat.le_antisymm
```"""


class TacticByTacticStrategy(SorryStrategy):
    """
    A strategy that attempts to prove a sorry by applying tactics one by one.
    Can use LLMs to generate tactics.
    """

    def __init__(
        self,
        strategy_mode: StrategyMode = StrategyMode.INTERACTIVE,
        model_config: dict | None = None,
        max_consecutive_failures: int = 3,
        max_iterations: int = 10,
        max_context_lines: int | None = None,
    ):
        """
        Initialize the strategy.
        Args:
            strategy_mode: The mode to use for generating tactics:
                           - INTERACTIVE: Prompts user for tactics
                           - PREDEFINED: Uses a predefined tactic
                           - LLM: Uses an LLM to generate tactics
            model_config: Dictionary containing LLM configuration (only used in LLM mode):
                - provider: "anthropic", "openai", or "google"
                - params: Model-specific parameters
            max_consecutive_failures: Maximum allowed consecutive failures before giving up
            max_iterations: Maximum number of iterations to attempt in proof search
            max_context_lines: Maximum number of context lines before the sorry to include (default: None)
        """
        self.strategy_mode = strategy_mode
        self.predefined_tactic_to_try = "rfl"
        self._predefined_attempt_made = False
        self.model_config = None  # Initialize to avoid reference errors
        self.max_context_lines = max_context_lines

        # Count consecutive failures to prevent infinite loops
        self.consecutive_failures = 0
        # Maximum allowed consecutive failures before giving up
        self.max_consecutive_failures = max_consecutive_failures
        # Maximum iterations for proof search
        self.max_iterations = max_iterations

        logger.info("Initialized TacticByTacticStrategy with mode: %s", strategy_mode)

        # Setup LLM if specified
        self.model = None
        if self.strategy_mode == StrategyMode.LLM:
            # Load environment variables for API keys
            dotenv.load_dotenv()

            # Load model config
            if model_config is None:
                logger.error("Model config is required for LLM mode.")
                raise ValueError("Model config is required for LLM mode.")
            self.model_config = model_config

            # Setup LLM
            if model_config["provider"] == "anthropic":
                self.model = ChatAnthropic(**model_config["params"])
            elif model_config["provider"] == "openai":
                self.model = ChatOpenAI(**model_config["params"])
            elif model_config["provider"] == "google":
                self.model = ChatGoogleGenerativeAI(**model_config["params"])
            else:
                raise ValueError(f"Invalid model provider: {model_config['provider']}")
            logger.info(
                "Initialized %s LLM for tactic generation", model_config["provider"]
            )

    def _generate_tactic(
        self, search_history: list[str], file_context: str = ""
    ) -> tuple[int, str] | None:
        """
        Generate the next tactic and proof state to work on.

        In LLM mode: Uses an LLM to generate the tactic
        In INTERACTIVE mode: Prompts the user with the same format as the LLM
        In PREDEFINED mode: Uses a predefined tactic

        Args:
            search_history: List of formatted search history entries in chronological order
            file_context: Context from the Lean file up to the sorry

        Returns:
            Tuple of (proof_state_id, tactic) or None if generation fails
        """
        # Format the prompt with the search history and file context
        prompt = TACTIC_GENERATION_PROMPT.format(
            search_history="\n".join(search_history)
            if search_history
            else "No previous tactics applied yet.",
            file_context=file_context if file_context else "No file context available.",
        )

        # Handle different modes
        response_text = ""
        if self.strategy_mode == StrategyMode.LLM:
            logger.info("Requesting tactic from LLM...")
            try:
                logger.info("Prompting LLM with:\n%s", prompt)
                assert self.model is not None, "Model must be initialized in LLM mode"
                response = self.model.invoke([HumanMessage(content=prompt)])
                assert isinstance(response.content, str), (
                    "LLM response must be a string"
                )
                response_text = response.content.strip()
                logger.info("LLM response: %s", response_text)
            except Exception as e:
                logger.error("Error generating tactic from LLM: %s", e, exc_info=True)
                return None

        elif self.strategy_mode == StrategyMode.INTERACTIVE:
            # Print the prompt for the user, just like we'd send to the LLM
            logger.info("\n" + prompt + "\n")

            # Get user input
            response_text = input(
                "Enter your response (format: [state_id] tactic): "
            ).strip()

        elif self.strategy_mode == StrategyMode.PREDEFINED:
            # In predefined mode, check if we already made an attempt
            if self._predefined_attempt_made:
                logger.info(
                    "Predefined mode: single tactic attempt '%s' already made. Stopping.",
                    self.predefined_tactic_to_try,
                )
                return None

            # Get the first state ID (usually the initial one)
            match = re.search(r"Initial state \(ID: (\d+)\)", search_history[0])
            if not match:
                logger.warning("Could not find initial state ID in search history.")
                return None

            state_id = int(match.group(1))
            logger.info(
                "Predefined mode: attempting tactic '%s' for state %d",
                self.predefined_tactic_to_try,
                state_id,
            )
            self._predefined_attempt_made = True
            return state_id, self.predefined_tactic_to_try

        if not response_text:
            return None

        # Post-process the response to remove code blocks
        if "```" in response_text:
            code_blocks = response_text.split("```")
            extracted_code = []

            for i, block in enumerate(code_blocks):
                if i % 2 == 1:  # This is inside a code block
                    if block.startswith("lean"):
                        block = block[4:]
                    extracted_code.append(block.strip())

            # Use the first code block if any were found
            if extracted_code:
                response_text = extracted_code[0]

        # Parse the state ID and tactic using regex
        match = re.match(r"\[(\d+)\]\s*(.*)", response_text)

        if not match:
            logger.warning("Response doesn't match expected format: %s", response_text)
            return None

        state_id = int(match.group(1))
        tactic = match.group(2).strip()

        logger.info("Generated state ID: %d, tactic: %s", state_id, tactic)
        return state_id, tactic

    def _get_tactic_and_state(
        self,
        all_states: dict[int, list[str]],
        search_history: list[str],
        file_context: str = "",
    ) -> tuple[int, str] | None:
        """
        Generates the next tactic to try and the proof state to apply it to.
        Uses the selected strategy mode to determine how to generate the tactic.

        Args:
            all_states: Dictionary mapping proof state IDs to their lists of goal strings
            search_history: Chronological history of the entire proof search
            file_context: Context from the Lean file up to the sorry

        Returns:
            Tuple of (proof_state_id, tactic) or None if generation fails
        """
        # If we've had too many consecutive failures, give up
        if self.consecutive_failures >= self.max_consecutive_failures:
            logger.warning(
                "Too many consecutive tactic failures (%d). Stopping.",
                self.consecutive_failures,
            )
            return None

        # Generate the tactic and state ID based on the strategy mode
        result = self._generate_tactic(search_history, file_context)

        if result is None:
            return None

        state_id, tactic = result

        # Check if the state ID is valid
        if state_id not in all_states:
            logger.warning(
                "Invalid state ID %d, available states: %s",
                state_id,
                list(all_states.keys()),
            )
            return None

        return state_id, tactic

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """Attempt to prove a sorry using the selected strategy mode.

        Args:
            repo_path: Path to the repository
            sorry: Dictionary containing sorry information

        Returns:
            Proof string or None if no proof was found
        """
        # Load the file and render the prompt
        loc = sorry.location
        file_path = repo_path / loc.path
        file_text = file_path.read_text()

        # Extract the context up to the sorry line, with optional max_context_lines
        if self.max_context_lines is not None and self.max_context_lines > 0:
            start_line = max(0, loc.start_line - self.max_context_lines)
            context_lines = file_text.splitlines()[start_line : loc.start_line]
        else:
            context_lines = file_text.splitlines()[: loc.start_line]
        file_context = "\n".join(context_lines)

        self.consecutive_failures = 0
        self._predefined_attempt_made = False

        # Determine mode for logging
        mode = f"{self.strategy_mode.value} mode"
        if self.strategy_mode == StrategyMode.LLM and self.model_config:
            mode += f" ({self.model_config['provider']})"

        logger.info(
            "Attempting tactic-by-tactic proof for sorry in %s at line %d using %s",
            file_path,
            loc.start_line,
            mode,
        )

        repl_config = LeanREPLConfig(project=LocalProject(str(repo_path)))
        lean_server = LeanServer(config=repl_config)

        # Run file and find the sorry
        logger.info("Loading file %s into Lean server", file_path)
        file_env = lean_server.run(FileCommand(path=str(file_path)))

        if isinstance(file_env, LeanError):
            logger.error(
                "Error loading file %s into Lean server: %s", file_path, file_env
            )
            return None

        live_sorry: REPLSorry | None = None
        for s in file_env.sorries:
            if (
                s.start_pos is not None
                and s.end_pos is not None
                and s.start_pos.line == sorry.location.start_line
                and s.start_pos.column == sorry.location.start_column
                and s.end_pos.line == sorry.location.end_line
                and s.end_pos.column == sorry.location.end_column
            ):
                live_sorry = s
                break
        if live_sorry is None:
            logger.error("Sorry %s not found in Lean server environment.", sorry.id)
            return None

        # Initialize proof state tracking
        initial_state_id = live_sorry.proof_state
        initial_goal = live_sorry.goal

        # Ensure initial_state_id is always int (never None)
        assert isinstance(initial_state_id, int)

        # Track all available proof states and their goals
        # Map of proof_state_id -> goals
        available_states: dict[int, list[str]] = {initial_state_id: [initial_goal]}
        # Track the proof state tree for reconstructing the proof
        # Map of proof_state_id -> (parent_state_id, tactic, goals)
        proof_tree: dict[int, tuple[int | None, str | None, list[str]]] = {
            initial_state_id: (None, None, [initial_goal])
        }

        # Store the chronological history of the proof search
        # Each entry is a formatted string showing the action taken
        search_history = []

        # Add initial state to search history
        search_history.append(
            f"Initial state (ID: {initial_state_id}):\n{self._format_goals([initial_goal])}"
        )

        # Main proof search loop using the configured maximum iterations to prevent infinite loops
        iterations = 0

        while iterations < self.max_iterations and available_states:
            iterations += 1
            logger.info("Proof search iteration %d", iterations)

            # Get the next state ID and tactic to try from the model or user
            result = self._get_tactic_and_state(
                available_states, search_history, file_context
            )

            if result is None:
                logger.info("No tactic provided, stopping.")
                break

            state_id, tactic = result

            # Check if the state ID is valid
            if state_id not in available_states:
                logger.warning(
                    "Invalid state ID %d, available states: %s",
                    state_id,
                    list(available_states.keys()),
                )
                self.consecutive_failures += 1
                search_history.append(f"Invalid state ID {state_id} specified")
                continue

            goals = available_states[state_id]
            logger.info(
                "Working on state %d with goals: %s...",
                state_id,
                self._format_goals(goals),
            )
            logger.info("Applying tactic: %s", tactic)

            # Apply the tactic to the chosen proof state
            try:
                result = lean_server.run(ProofStep(proof_state=state_id, tactic=tactic))
            except Exception as e:
                logger.error("Error running ProofStep: %s", e, exc_info=True)
                self.consecutive_failures += 1
                search_history.append(f"  Result: Error running ProofStep - {str(e)}")
                continue

            logger.info("Result: %s", result)

            # Add this attempt to the search history
            search_history.append(f"State {state_id}: Applied tactic '{tactic}'")

            if isinstance(result, LeanError):
                logger.warning("Tactic failed: %s", tactic)
                logger.warning("Error: %s", result)
                self.consecutive_failures += 1
                search_history[-1] = (
                    f"State {state_id}: Applied tactic '{tactic}' → Failed: {result}"
                )
                continue

            new_state_id = result.proof_state
            new_goals = result.goals

            # Update search history with the new state ID after tactic application
            search_history[-1] = (
                f"State {state_id}: Applied tactic '{tactic}' → State {new_state_id}"
            )

            if result.messages:
                search_history[-1] += f" → Messages: {result.messages}"

            # If there are no more goals, we're done!
            if result.proof_status == "Completed":
                logger.info("Proof completed with tactic: %s", tactic)
                search_history.append("  Result: Success - Proof completed!")

                # Record this final step in the proof tree
                proof_tree[new_state_id] = (state_id, tactic, [])

                # Extract the successful proof branch
                proof_tactics = self._extract_proof_from_tree(proof_tree, new_state_id)

                # Format the tactics into a proof string
                proof_string = self._format_proof(proof_tactics)
                logger.info("Proof string:\n%s", proof_string)
                return proof_string

            # Reset consecutive failures counter
            self.consecutive_failures = 0

            # Add the new goals to the search history
            search_history.append(
                f"Result: New goal(s) (State ID: {new_state_id}):\n{self._format_goals(new_goals)}"
            )

            # Record this step in the proof tree
            if new_goals:
                available_states[new_state_id] = new_goals
                proof_tree[new_state_id] = (state_id, tactic, new_goals)

        if iterations >= self.max_iterations:
            logger.warning(
                "Reached maximum number of iterations (%d) without finding a proof",
                self.max_iterations,
            )

        logger.info("No proof found")
        return None

    def _extract_proof_from_tree(
        self,
        proof_tree: dict[int, tuple[int | None, str | None, list[str]]],
        final_state_id: int,
    ) -> list[str]:
        """Extract the sequence of tactics that led to a successful proof.

        Args:
            proof_tree: Dictionary mapping proof state IDs to (parent_state_id, tactic, goals)
            final_state_id: The ID of the final (successful) proof state

        Returns:
            List of tactics in order of application
        """
        tactics = []
        current_id = final_state_id

        # Trace back from the final state to the initial state
        while current_id in proof_tree:
            parent_id, tactic, _ = proof_tree[current_id]
            if tactic is not None:  # Skip the initial state which has no tactic
                tactics.append(tactic)
            if parent_id is None:  # We've reached the initial state
                break
            current_id = parent_id

        # Reverse to get tactics in order of application
        tactics.reverse()
        return tactics

    def _format_proof(self, tactics: list[str]) -> str:
        """Format a list of tactics into a Lean proof string.

        Args:
            tactics: List of tactics used in the proof

        Returns:
            Formatted proof string
        """
        # Just join the tactics with newlines and proper indentation
        # Hacky, might not work for all cases
        return "\n  ".join(tactics)

    def _format_goals(self, goals: list[str]) -> str:
        """Format a list of goals into a string for display.

        Args:
            goals: List of goal strings

        Returns:
            Formatted string of goals
        """
        if not goals:
            return "No goals."
        return "```\n" + "\n\n".join(goal for goal in goals) + "\n```"
