"""Agentic strategy for SorryDB using LangGraph with Anthropic extended thinking."""

import logging
from pathlib import Path
from typing import Annotated, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from sorrydb.database.sorry import Sorry
from sorrydb.runners.json_runner import SorryStrategy
from sorrydb.utils.llm_tools import (
    create_grep_tool,
    search_lean_search_tool,
    search_loogle_tool,
    web_search_tool,
    wikipedia_search_tool,
)
from sorrydb.utils.sorry_extraction import extract_proof_from_diff
from sorrydb.utils.verify_lean_interact import verify_lean_interact

logger = logging.getLogger(__name__)

PROMPT = """You are an advanced AI that has studied all known mathematics and world expert in Lean4 theorem proving.
Consider the following Lean code:
<context>
```lean
{context}
```
</context>

Its proof goal is
<proof_goal>
```lean
{goal}
```
</proof_goal>

Target sorry is the following:
<target_sorry>
The given file contains a sorry on the last line, column {column}.
</target_sorry>

You already tried proving the theorem a few times and got the following feedback:
<feedback>
{feedback}
</feedback>
If there is feedback, start by mentioning why the previous attempt failed and how to fix the error.


Replace the target sorry on the last line with a valid proof.
Write a short, simple and elegant proof.
Output the ENTIRE code block inside a ```lean block with ONLY the sorry replaced.
If the file is long you should not output again the entire file, but just the last code block that is relevant.
Do not modify anything else - no formatting changes, no whitespace changes, no other edits.
Do not replace other sorries apart from the target one on the last line of the context.
You cannot import any additional libraries.
DO NOT WRITE COMMENTS OR EXPLANATIONS! Just output the modified code block.
If there are other thoughts or explanations, the last code block will be considered as the answer.
"""

TOOLS_PROMPT = """
<tool-use>
You have access to search tools if you need to find specific lemmas or tactics:
- grep: Search for text patterns in Lean files within the repository
- search_loogle: Exact pattern matching for Lean definitions
- search_lean_search: Natural language search for theorems
- web_search: General web search for concepts
- wikipedia_search: Search Wikipedia for mathematical concepts

Make as many parallel tool calls as possible to reduce iterations.
If you need to search for multiple terms or concepts, call all the relevant tools at once rather than one at a time.
</tool-use>
"""


class AgenticState(BaseModel):
    """State for the agentic prover workflow."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    sorry: Sorry
    repo_path: Path
    iteration: int = 0
    proof: str | None = None
    approved: bool = False


class AgenticStrategy(SorryStrategy):
    """
    An agentic proof strategy using LangGraph with Anthropic extended thinking.

    Workflow:
    START -> proposer -> builder -> decision (retry proposer or END)
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        max_iterations: int = 5,
        max_tokens: int = 16000,
        enable_tools: bool = True,
        enable_thinking: bool = True,
        thinking_budget: int = 10000,
        max_tool_calls_per_iteration: int = 5,
    ):
        """
        Initialize the agentic strategy.

        Args:
            model: The Anthropic model to use
            max_iterations: Maximum number of proof attempts
            max_tokens: Maximum tokens for response
            enable_tools: Whether to enable tools for the proposer
            enable_thinking: Whether to enable extended thinking
            thinking_budget: Token budget for thinking (when enabled)
            max_tool_calls_per_iteration: Maximum tool call rounds per proposer iteration
        """
        self.model = model
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.enable_tools = enable_tools
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget
        self.max_tool_calls_per_iteration = max_tool_calls_per_iteration

        # Build model kwargs with Anthropic beta flags
        model_kwargs = {}
        if self.enable_thinking:
            model_kwargs["betas"] = ["interleaved-thinking-2025-05-14"]
            model_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        self.llm = ChatAnthropic(
            model=self.model,
            max_tokens=self.max_tokens,
            **model_kwargs,
        )

        # Tools
        self.tools = [
            search_loogle_tool,
            search_lean_search_tool,
            web_search_tool,
            wikipedia_search_tool,
        ]

        # Build the LangGraph workflow
        self.app = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build and compile the LangGraph workflow."""
        workflow = StateGraph(AgenticState)

        workflow.add_node("proposer", self._proposer_node)
        workflow.add_node("builder", self._builder_node)

        workflow.add_edge(START, "proposer")
        workflow.add_edge("proposer", "builder")

        workflow.add_conditional_edges(
            "builder", self._build_decision, {"retry": "proposer", "done": END}
        )

        return workflow.compile()

    def _get_context(self, repo_path: Path, sorry: Sorry) -> str:
        """Get the context (file content up to the sorry line)."""
        loc = sorry.location
        file_path = repo_path / loc.path
        file_text = file_path.read_text()
        context_lines = file_text.splitlines()[: loc.start_line]
        return "\n".join(context_lines)

    def _proposer_node(self, state: AgenticState) -> dict:
        """Proposer node: Generate proof proposal using LLM with tools."""
        sorry = state.sorry
        iteration = state.iteration

        logger.info(
            f"[Iteration {iteration + 1}] Proposer: Generating proof proposal..."
        )

        # Get context
        context = self._get_context(state.repo_path, sorry)

        # Format feedback from previous attempts (show last 3 attempts)
        feedback = ""
        if state.messages:
            # Collect attempts as (proposal, error) pairs
            attempts: list[tuple[str, str]] = []
            current_proposal = None
            for msg in state.messages:
                if isinstance(msg, AIMessage):
                    current_proposal = msg.content
                elif isinstance(msg, HumanMessage) and current_proposal is not None:
                    attempts.append((current_proposal, msg.content))
                    current_proposal = None

            # Show last 3 attempts with age info
            if attempts:
                feedback = "Previous attempts failed. Here is the feedback:\n"
                total_attempts = len(attempts)
                recent_attempts = attempts[-3:]  # Last 3 attempts
                for i, (proposal, error) in enumerate(recent_attempts):
                    attempt_num = total_attempts - len(recent_attempts) + i + 1
                    age = total_attempts - attempt_num  # 0 = most recent
                    age_str = "most recent" if age == 0 else f"{age} attempt(s) ago"
                    feedback += f"\n<attempt iteration=\"{attempt_num}\" age=\"{age_str}\">\n"
                    feedback += f"<proposed_code>\n{proposal}\n</proposed_code>\n"
                    feedback += f"<error>\n{error}\n</error>\n"
                    feedback += "</attempt>\n"

        # Create prompt
        base_prompt = PROMPT.format(
            context=context,
            goal=sorry.debug_info.goal,
            column=sorry.location.start_column,
            feedback=feedback,
        )
        prompt = base_prompt + TOOLS_PROMPT if self.enable_tools else base_prompt

        # Create messages
        messages = [HumanMessage(content=prompt)]

        # Bind tools if enabled
        if self.enable_tools:
            tools = self.tools + [create_grep_tool(str(state.repo_path))]
            llm = self.llm.bind_tools(tools)
        else:
            llm = self.llm
            tools = []

        # Call LLM
        response = llm.invoke(messages)
        new_messages = [response]

        # Handle tool calls in a loop with iteration limit
        tool_call_count = 0
        while response.tool_calls:
            tool_node = ToolNode(tools)
            tool_result = tool_node.invoke({"messages": messages + new_messages})
            new_messages.extend(tool_result["messages"])
            tool_call_count += 1

            # Check if we've hit the tool call limit
            if tool_call_count >= self.max_tool_calls_per_iteration:
                # Force final response without tools
                response = self.llm.invoke(
                    messages + new_messages + [HumanMessage(content="NO MORE TOOL CALLS ALLOWED. Provide your final answer now.")]
                )
            else:
                response = llm.invoke(messages + new_messages)
            new_messages.append(response)

        # Extract text and thinking using LangChain properties
        text_response = response.text

        # Log thinking if present
        for block in response.content_blocks:
            if block.get("type") == "reasoning":
                thinking = block.get("reasoning", "")
                if thinking:
                    logger.info(
                        f"[Iteration {iteration + 1}] Thinking: {thinking[:500]}..."
                    )

        logger.info(f"[Iteration {iteration + 1}] LLM response:\n{text_response}")

        # Extract proof using diff
        proof = extract_proof_from_diff(context, text_response, sorry.location)
        logger.info(f"[Iteration {iteration + 1}] Extracted proof:\n{proof}")

        # Add response to message history
        proposal_message = AIMessage(content=text_response)

        return {
            "proof": proof,
            "iteration": iteration + 1,
            "messages": [proposal_message],
        }

    def _builder_node(self, state: AgenticState) -> dict:
        """Builder node: Verify the proposed proof."""
        sorry = state.sorry
        proof = state.proof
        iteration = state.iteration

        logger.info(f"[Iteration {iteration}] Builder: Verifying proof...")

        if proof is None:
            error_msg = "No proof could be extracted from LLM response"
            logger.info(f"[Iteration {iteration}] ✗ {error_msg}")
            error_msg_human = HumanMessage(content=f"✗ {error_msg}")
            return {"approved": False, "messages": [error_msg_human]}

        # Verify the proof
        try:
            success, error_message = verify_lean_interact(
                repo_dir=state.repo_path, location=sorry.location, proof=proof
            )

            if success:
                logger.info(f"[Iteration {iteration}] ✓ Proof verified successfully!")
                success_message = HumanMessage(content="✓ Proof verified successfully!")
                return {"approved": True, "messages": [success_message]}
            else:
                logger.info(
                    f"[Iteration {iteration}] ✗ Verification failed: {error_message}"
                )
                error_msg_human = HumanMessage(
                    content=f"✗ Verification failed:\n{error_message}"
                )
                return {"approved": False, "messages": [error_msg_human]}

        except Exception as e:
            error_msg = f"Exception during verification: {str(e)}"
            logger.info(f"[Iteration {iteration}] ✗ {error_msg}")
            error_msg_human = HumanMessage(content=f"✗ {error_msg}")
            return {"approved": False, "messages": [error_msg_human]}

    def _build_decision(self, state: AgenticState) -> Literal["retry", "done"]:
        """Decision function: Determine if we should retry or finish."""
        if state.approved:
            return "done"

        if state.iteration >= self.max_iterations:
            logger.info(f"Max iterations ({self.max_iterations}) reached. Giving up.")
            return "done"

        return "retry"

    def prove_sorry(self, repo_path: Path, sorry: Sorry) -> str | None:
        """
        Attempt to prove a sorry using the LangGraph workflow.

        Args:
            repo_path: Path to the repository
            sorry: The Sorry object to prove

        Returns:
            Proof string if successful, None otherwise
        """
        # Initialize state
        initial_state = AgenticState(
            messages=[],
            sorry=sorry,
            repo_path=repo_path,
        )

        try:
            # Build a concise run name for LangSmith
            repo_name = sorry.repo.remote.rstrip("/").split("/")[-1].removesuffix(".git")
            file_name = Path(sorry.location.path).stem
            run_name = f"{repo_name}>{file_name}:L{sorry.location.start_line}"

            config = {
                "run_name": run_name,
                "tags": ["agentic-prover", file_name],
                "metadata": {
                    "sorry_id": sorry.id,
                    "repo_remote": sorry.repo.remote,
                    "lean_version": sorry.repo.lean_version,
                    "file_path": sorry.location.path,
                    "goal": sorry.debug_info.goal,
                },
            }
            final_state = AgenticState(**self.app.invoke(initial_state, config))

            if final_state.approved and final_state.proof is not None:
                logger.info("✓ Successfully proved sorry!")
                return final_state.proof
            else:
                logger.info(
                    f"✗ Failed to prove sorry after {final_state.iteration} iterations"
                )
                return None

        except Exception as e:
            logger.info(f"✗ Error during proof workflow: {e}")
            return None
