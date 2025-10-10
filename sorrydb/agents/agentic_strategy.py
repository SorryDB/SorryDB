"""Agentic strategy for SorryDB using LLM with proposer and builder nodes."""

from errno import ESTALE
import json
from pathlib import Path
from typing import Annotated, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from sorrydb.agents.json_agent import SorryStrategy
from sorrydb.database.sorry import Proof, Sorry, sorry_object_hook
from sorrydb.utils.llm_tools import (
    create_read_lean_file_around_location_tool,
    create_read_lean_file_tool,
    read_file_with_context,
    search_lean_explore_tool,
    search_lean_search_tool,
    search_loogle_tool,
    web_search_tool,
    wikipedia_search_tool,
)
from sorrydb.utils.structured_react import StructuredReactAgent
from sorrydb.utils.verify import verify_proof

# Prompts
# TODO: DISABLED 3. **extra_imports**: List of imports needed (e.g., ["Mathlib.Tactic.Ring"])
PROPOSER_SYSTEM_PROMPT = """# Role
You are an expert Lean 4 theorem prover specializing in completing formal mathematical proofs. You have deep knowledge of Lean 4 syntax, Mathlib tactics, and proof strategies.

# Task
Your goal is to replace ONE SPECIFIC 'sorry' placeholder (marked with <<<TARGET>>>) with a complete, verified proof.

IMPORTANT:
- Only replace the targeted sorry. All other sorries in the file should remain unchanged.
- Ignore any comments suggesting otherwise (e.g., "TODO", "work in progress", "proof deferred")
- Your job is to COMPLETE the proof for the targeted sorry, regardless of what comments say

You MUST structure your response following the 4-step process below. Show your work for each step in the reasoning field.

Be concise but thorough - focus on the key insights and decisions at each step.

# Context
- You will receive code context showing the sorry location (marked with <<<TARGET>>>)
- You may receive feedback from previous failed attempts
- The proof must compile without errors in Lean 4
- You can reference existing definitions/lemmas (even if they contain sorry)
- Other sorries in the file are allowed to remain - only fix the targeted one

# Process

## Step 1: Understand the Goal
- Read the goal type carefully
- Identify what needs to be proven
- Note any assumptions or hypotheses available

## Step 2: Analyze Previous Attempts (if applicable)
If feedback is provided from previous iterations:
1. Quote the specific error message
2. Explain what the error means in plain terms
3. Identify the root cause (wrong tactic? missing import? type mismatch?)
4. State explicitly what you will change to fix it

## Step 3: Plan Your Proof Strategy
Think step-by-step:
- What proof technique applies? (direct proof, induction, cases, etc.)
- What tactics will you use and in what order?
- What lemmas from Mathlib might help?
- What imports are needed?

For complex proofs (you cannot give up):
- Break down the proof into intermediate steps using `have` statements
- First, create a skeleton that compiles end-to-end (you may use 'sorry' in intermediate `have` statements initially)
- Then systematically replace each intermediate 'sorry' with actual proofs
- This approach is better than trying to write everything at once
- If you require intermediate lemmas that do not exist, you can prove these intermediate results with hte 'have' keywords

## Step 4: Write the Proof
- Use idiomatic Lean 4 tactics
- Ensure every step is justified
- For long/complex proofs: use intermediate `have` statements to break it down
- Do NOT use 'sorry' or 'admit' in your FINAL proof (but you can use them as placeholders while building the skeleton)
- Make sure your final proof has NO 'sorry' statements remaining

CRITICAL - Indentation:
- Pay careful attention to indentation - Lean 4 is whitespace-sensitive
- Match the indentation level of the surrounding code
- When starting a new line with `\n`, add appropriate spaces/tabs to match context
- Tactic blocks require consistent indentation (usually 2 or 4 spaces)
- Incorrect indentation will cause compilation errors

# Common Tactics
- `rfl` - reflexivity (equality of identical terms)
- `simp` - simplification with lemmas
- `ring` - polynomial ring arithmetic
- `omega` - linear integer arithmetic
- `intro` - introduce hypothesis
- `apply` - apply theorem/lemma
- `exact` - provide exact term
- `constructor` - build inductive type
- `cases` - case analysis
- `induction` - proof by induction

# Tool Usage Guidelines

You have access to tools for searching Lean libraries and mathematical concepts. Use them strategically:

## 1. Available Tools
- **search_loogle_tool**: Exact pattern matching for Lean definitions (e.g., "List.map", '"continuous"')
- **search_lean_search_tool**: Natural language search for theorems (e.g., "continuity of functions")
- **search_lean_explore_tool**: Semantic AI search (requires API key)
- **read_lean_file**: Read full Lean files from the repository
- **read_lean_file_around_location**: Read files with context window
- **web_search_tool**: General web search for concepts
- **wikipedia_search_tool**: Wikipedia for mathematical definitions

## 2. When to Use Tools
- **First attempt**: If the goal involves unfamiliar concepts or requires specific Mathlib lemmas
- **After error**: Search for alternative tactics/lemmas when your approach fails
- **Complex proofs**: Look up similar theorems or proof patterns

## 3. Efficiency Rules
- **Parallel searches**: Make 10-15 tool calls per iteration when needed (maximum 4 iterations total)
- **Never retry failed searches**: If a query returns nothing, try a different search strategy or move on
- **Be specific**: Use exact names when you know them, natural language when exploring
- **Focus on actionable findings**: Extract concrete lemma names, tactics, or imports

## 4. Tool Selection Strategy
- Use **search_loogle_tool** if you know the concept name (fastest, most precise)
- Use **search_lean_search_tool** for natural language queries about theorems
- Use **search_lean_explore_tool** for conceptual/semantic searches
- Use **read_lean_file_around_location** to examine similar proofs in the repository
- Use **web_search_tool** or **wikipedia_search_tool** only for mathematical background

# Critical Rules

## MUST DO:
✓ Provide a COMPLETE proof (no sorry/admit)
✓ Analyze previous errors if retrying
✓ Explain your reasoning clearly
✓ Use appropriate Mathlib imports
✓ Ensure the proof compiles

## MUST NOT:
✗ Add new 'sorry' statements to your proof
✗ Use 'admit' or proof-skipping tactics
✗ Leave placeholders or TODOs
✗ Ignore previous error messages
✗ Repeat the same failed approach

## ALLOWED:
✓ Reference existing lemmas/theorems that contain sorry (they already exist)
✓ Use helper statements from the file (even if proven with sorry)

# Output Format

Provide your response with:
1. **reasoning**: Your chain-of-thought analysis
   - If retrying: Analyze previous error and explain fix
   - If first attempt: Explain proof strategy
2. **proof**: The complete Lean 4 proof code.
CRITICAL: The code you propose cannot contain any "sorry", for any reason, no exception
3. **is_impossible**: Boolean (default: false)
   - ONLY set to true if the proof is genuinely IMPOSSIBLE (e.g., proving a false statement, missing fundamental axioms)
   - Setting this to true is considered a FAILURE - avoid it unless absolutely certain
   - ALWAYS try to provide a proof first before declaring something impossible
   - Even difficult proofs should be attempted - use the skeleton approach for complex cases

# Example Reasoning (for retry)

"The previous attempt failed with error 'type mismatch: expected Nat but got Int'.
This occurred because I used an Int-specific lemma on a Nat goal.
To fix this, I will:
1. Use Nat-specific lemmas instead
2. Add import Mathlib.Data.Nat.Basic
3. Apply Nat.add_comm instead of Int.add_comm

My proof strategy: Use commutativity of Nat addition followed by reflexivity."

# Remember
Every proof must be complete and compilable. Think carefully, analyze errors thoroughly, and provide clear reasoning for your approach.
"""

PROPOSER_QUERY_PROMPT = """Please propose a proof for the following sorry:

Repository: {repo_remote}
Lean Version: {lean_version}

{context_window}

Goal:
{goal}

Previous iterations:
{feedback}

Provide:
1. A proof tactic or term to replace the sorry (marked with >>> in the context)
2. Any extra imports needed at the top of the file
"""


# State definition for the agent
class AgenticState(BaseModel):
    """State for the agentic prover workflow."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    sorry: Sorry
    repo_path: Path
    iteration: int = 0
    proof: Proof | None = None
    approved: bool = False
    is_thought_impossible: bool = False

    @property
    def formatted_feedback(self) -> str:
        """Format the message history as feedback for the proposer."""
        if not self.messages:
            return "No previous attempts."

        feedback_lines = []
        attempt_num = 0

        # Process messages in pairs (AI proposal + Human feedback)
        i = 0
        while i < len(self.messages):
            msg = self.messages[i]

            if isinstance(msg, AIMessage):
                attempt_num += 1
                feedback_lines.append(f"\n{'=' * 60}")
                feedback_lines.append(f"ATTEMPT #{attempt_num}")
                feedback_lines.append(f"{'=' * 60}")
                feedback_lines.append(f"\n{msg.content}")

                # Check if there's a corresponding feedback message
                if i + 1 < len(self.messages) and isinstance(
                    self.messages[i + 1], HumanMessage
                ):
                    feedback_lines.append(f"\n--- Result ---")
                    feedback_lines.append(self.messages[i + 1].content)
                    i += 2
                else:
                    i += 1
            else:
                i += 1

        return "\n".join(feedback_lines)

    @property
    def last_message(self) -> str | None:
        """Get the content of the last message."""
        if not self.messages:
            return None
        return self.messages[-1].content


class ProofProposal(BaseModel):
    """Structured output from the proposer."""

    reasoning: str = Field(description="Brief explanation of the proof approach")
    proof: str = Field(description="The proof tactic or term to replace the sorry")
    # TODO: currently disabled
    # extra_imports: list[str] = Field(
    #     description="List of extra imports needed (e.g., ['Mathlib.Tactic.Ring'])",
    #     default_factory=list,
    # )
    is_impossible: bool = Field(
        default=False,
        description="True if the proof is genuinely impossible (e.g., false statement, missing axioms). This is a FAILURE - avoid setting this unless absolutely certain after trying.",
    )


class AgenticStrategy(SorryStrategy):
    """
    An agentic proof strategy using LangGraph with proposer and builder nodes.

    Workflow:
    START -> proposer -> builder -> decision (retry proposer or END)

    This strategy:
    1. Proposer: Uses an LLM to propose a proof and identify needed imports
    2. Builder: Verifies the proof using the verify_proof function
    3. Iterates until proof succeeds or max iterations reached
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.7,
        max_iterations: int = 3,
        max_tokens: int = 4096,
        cache_path: str = None,
        enable_tools: bool = True,
    ):
        """
        Initialize the agentic strategy.

        Args:
            model: The LLM model to use
            temperature: Temperature for LLM sampling
            max_iterations: Maximum number of proof attempts
            max_tokens: Maximum tokens for LLM response
            cache_path: Path to cache file for storing proofs
            enable_tools: Whether to enable tools for the proposer agent
        """
        self.model = model
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.cache_path = cache_path
        self.enable_tools = enable_tools

        self.llm = ChatAnthropic(
            model=self.model, temperature=self.temperature, max_tokens=self.max_tokens
        )

        # Load cache
        if self.cache_path:
            self.cache = self._load_cache()
        else:
            self.cache = None

        # Build the LangGraph workflow
        self.app = self._build_graph()

    def _load_cache(self) -> dict:
        """Load the proof cache from disk.

        Returns:
            Dictionary mapping sorry_id -> {"proof": Proof, "approved": bool}
        """
        if not self.cache_path:
            return {}

        cache_file = Path(self.cache_path)
        if not cache_file.exists():
            return {}

        try:
            with open(cache_file, "r") as f:
                cache_data = json.load(f, object_hook=sorry_object_hook)
            print(f"Loaded {len(cache_data)} cached proofs from {self.cache_path}")
            return cache_data
        except Exception as e:
            print(f"Warning: Failed to load cache from {self.cache_path}: {e}")
            return {}

    def _save_cache(self):
        """Save the proof cache to disk."""
        if not self.cache_path:
            return

        try:
            cache_file = Path(self.cache_path)
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert cache to JSON-serializable format
            with open(cache_file, "w") as f:
                json.dump(self.cache, f, indent=2, default=lambda o: o.__dict__)
            print(f"Saved proofs to cache at {self.cache_path} (#{len(self.cache)})")
        except Exception as e:
            print(f"Warning: Failed to save cache to {self.cache_path}: {e}")

    def _create_tools(self, repo_path: str) -> list:
        """Create tools for the proposer agent.

        Args:
            repo_path: Base path to the repository

        Returns:
            List of tools for the proposer
        """
        # TODO: add an option to enable/disable tools
        return [
            # File reading tools
            # create_read_lean_file_tool(repo_path),
            # create_read_lean_file_around_location_tool(repo_path),
            # Lean-specific search tools
            search_loogle_tool,  # Exact pattern matching for Lean definitions
            search_lean_search_tool,  # Natural language search for Lean theorems
            # search_lean_explore_tool,  # Semantic search (requires API key)
            # General search tools
            web_search_tool,  # Web search for concepts
            # wikipedia_search_tool,  # Wikipedia for mathematical definitions
        ]

    def _build_graph(self) -> StateGraph:
        """Build and compile the LangGraph workflow."""
        workflow = StateGraph(AgenticState)

        # Add nodes
        workflow.add_node("proposer", self._proposer_node)
        workflow.add_node("builder", self._builder_node)

        # Define edges
        workflow.add_edge(START, "proposer")
        workflow.add_edge("proposer", "builder")

        # Conditional edge from builder
        workflow.add_conditional_edges(
            "builder", self._build_decision, {"retry": "proposer", "done": END}
        )

        return workflow.compile()

    def _proposer_node(self, state: AgenticState) -> dict:
        """Proposer node: Generate proof proposal using StructuredReactAgent with tools."""
        sorry = state.sorry
        iteration = state.iteration

        print(f"[Iteration {iteration + 1}] Proposer: Generating proof proposal...")

        # Get context window around the sorry location
        context_window = read_file_with_context(
            str(state.repo_path),
            sorry.location.path,
            sorry.location.start_line,
            sorry.location.start_column,
            sorry.location.end_line,
            sorry.location.end_column,
            context_lines=200,
        )

        # Prepare the query
        query = PROPOSER_QUERY_PROMPT.format(
            repo_remote=sorry.repo.remote,
            lean_version=sorry.repo.lean_version,
            context_window=context_window,
            goal=sorry.debug_info.goal,
            feedback=state.formatted_feedback,
        )

        # Create tools for this specific repo_path (if enabled)
        proposer_tools = self._create_tools(str(state.repo_path)) if self.enable_tools else []

        # Create StructuredReactAgent with or without tools
        proposer_agent = StructuredReactAgent(
            llm=self.llm,
            tools=proposer_tools,
            system_prompt=PROPOSER_SYSTEM_PROMPT,
            output_schema=ProofProposal,
            max_iterations=3,
        )

        # Invoke the agent
        proposal: ProofProposal = proposer_agent.invoke(query)

        print(f"[Iteration {iteration + 1}] Reasoning: {proposal.reasoning}")
        print(f"[Iteration {iteration + 1}] Proposed proof: {proposal.proof}")
        # print(f"[Iteration {iteration + 1}] Extra imports: {proposal.extra_imports}")
        if proposal.is_impossible:
            print(f"[Iteration {iteration + 1}] ⚠️  Proposer marked as impossible")

        # Create Proof object
        proof_obj = Proof(proof=proposal.proof)#, extra_imports=proposal.extra_imports)

        # Add proposal to message history
        proposal_message = AIMessage(
            content=f"Reasoning: {proposal.reasoning}\nProof: {proposal.proof}\nExtra imports: []\nIs impossible: {proposal.is_impossible}"
        )

        return {
            "proof": proof_obj,
            "iteration": iteration + 1,
            "is_thought_impossible": proposal.is_impossible,
            "messages": [proposal_message],
        }

    def _builder_node(self, state: AgenticState) -> dict:
        """Builder node: Verify the proposed proof."""
        sorry = state.sorry
        proof = state.proof
        iteration = state.iteration

        # Skip verification if proposer marked as impossible
        if state.is_thought_impossible:
            print(
                f"[Iteration {iteration}] Builder: Skipping verification (marked impossible)"
            )
            impossible_msg = HumanMessage(
                content="⚠️ Proposer marked proof as impossible"
            )
            return {"approved": False, "messages": [impossible_msg]}

        print(f"[Iteration {iteration}] Builder: Verifying proof...")

        if proof is None:
            error_msg_human = HumanMessage(content="No proof proposal provided")
            return {"approved": False, "messages": [error_msg_human]}

        # Verify the proof
        try:
            success, error_message = verify_proof(
                repo_dir=state.repo_path,
                lean_version=sorry.repo.lean_version,
                location=sorry.location,
                proof=proof,
            )

            if success:
                print(f"[Iteration {iteration}] ✓ Proof verified successfully!")
                success_message = HumanMessage(content="✓ Proof verified successfully!")
                return {"approved": True, "messages": [success_message]}
            else:
                print(f"[Iteration {iteration}] ✗ Verification failed: {error_message}")
                error_msg_human = HumanMessage(
                    content=f"✗ Verification failed:\n{error_message}"
                )
                return {"approved": False, "messages": [error_msg_human]}

        except Exception as e:
            error_msg = f"Exception during verification: {str(e)}"
            print(f"[Iteration {iteration}] ✗ {error_msg}")
            error_msg_human = HumanMessage(content=f"✗ {error_msg}")
            return {"approved": False, "messages": [error_msg_human]}

    def _build_decision(self, state: AgenticState) -> Literal["retry", "done"]:
        """Decision function: Determine if we should retry or finish."""
        # Check if proof succeeded
        if state.approved:
            return "done"

        # Check if proposer marked as impossible
        if state.is_thought_impossible:
            print(f"Proposer marked proof as impossible. Stopping.")
            return "done"

        # Check if we've reached max iterations
        if state.iteration >= self.max_iterations:
            print(f"Max iterations ({self.max_iterations}) reached. Giving up.")
            return "done"

        return "retry"

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> Proof | None:
        """
        Attempt to prove a sorry using the LangGraph workflow.

        Checks cache first, and saves results to cache if configured.

        Args:
            repo_path: Path to the repository
            sorry: The Sorry object to prove

        Returns:
            Proof object if successful, None otherwise
        """
        # Check cache first
        sorry_id = sorry.id
        if self.cache and sorry_id in self.cache:
            cached_entry = self.cache[sorry_id]
            cached_proof = cached_entry.get("proof")
            print(f"✓ Found cached proof for sorry {sorry_id}")
            print(f"Approved: {cached_entry['approved']}")
            return cached_proof

        # Initialize state
        initial_state = AgenticState(messages=[], sorry=sorry, repo_path=repo_path)

        # Run the workflow with LangSmith metadata
        try:
            config = {
                "metadata": {
                    "sorry_id": sorry_id,
                    "repo_remote": sorry.repo.remote,
                    "lean_version": sorry.repo.lean_version,
                    "file_path": sorry.location.path,
                    "goal": sorry.debug_info.goal,
                }
            }
            final_state = AgenticState(**self.app.invoke(initial_state, config))

            # Store result in cache
            if self.cache:
                self.cache[sorry_id] = {
                    "proof": final_state.proof,
                    "approved": final_state.approved,
                    "reasoning": final_state.last_message,
                }

                # Save cache to disk
                self._save_cache()

            # Check if proof was successful
            if final_state.approved and final_state.proof is not None:
                print("\n✓ Successfully proved sorry!")
                return final_state.proof
            else:
                print(
                    f"\n✗ Failed to prove sorry after {final_state.iteration} iterations"
                )
                return None

        except Exception as e:
            print(f"\n✗ Error during proof workflow: {e}")
            # Store failure in cache too
            if self.cache:
                self.cache[sorry_id] = {
                    "proof": None,
                    "approved": False,
                    "reasoning": str(e),
                }
                self._save_cache()
            return None
