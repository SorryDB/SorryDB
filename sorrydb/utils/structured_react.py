"""Structured ReAct agent using LangGraph."""

from typing import Annotated, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from .llm_tools import get_logger


class AgentState(BaseModel):
    """Agent state with Pydantic."""

    messages: Annotated[list[BaseMessage], add_messages]
    query: str = Field(default="")
    iteration_count: int = Field(default=0)
    structured_result: Any = Field(default=None)


class StructuredReactAgent:
    """
    A structured ReAct agent that plans, executes tools, and structures output.

    Flow: plan -> tools -> plan -> ... -> structurer -> END
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        system_prompt: str,
        output_schema: type[BaseModel] | None = None,
        max_iterations: int = 10,
    ):
        """
        Initialize the structured ReAct agent.

        Args:
            llm: Language model (ChatAnthropic, ChatOpenAI, etc.)
            tools: List of LangChain tools
            system_prompt: System prompt for the agent
            output_schema: Optional Pydantic schema for structured output
            max_iterations: Maximum planning iterations
        """
        self.logger = get_logger(__name__)
        self.llm: BaseChatModel = llm
        self.llm_with_tools = llm.bind_tools(
            tools, tool_choice="any" if tools else None
        )
        self.tools: list[BaseTool] = tools
        self.system_prompt: str = system_prompt
        self.output_schema: type[BaseModel] | None = output_schema
        self.max_iterations: int = max_iterations

        # Build the graph
        self.app: StateGraph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("tools", self._tool_node)
        workflow.add_node("structurer", self._structurer_node)

        # Route from START based on whether tools are available
        workflow.add_conditional_edges(
            START,
            lambda state: "plan" if self.tools else "structurer",
            {"plan": "plan", "structurer": "structurer"},
        )

        # Add conditional edges from plan
        workflow.add_conditional_edges(
            "plan",
            self._should_continue,
            {"tools": "tools", "structurer": "structurer"},
        )

        # Tools always go back to plan
        workflow.add_edge("tools", "plan")

        # Structurer ends the flow
        workflow.add_edge("structurer", END)

        return workflow.compile()

    def _plan_node(self, state: AgentState) -> dict[str, Any]:
        """Planning node - decides what tools to call."""
        state.iteration_count += 1

        # Build messages with system prompt
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Query: {state.query}"),
        ] + state.messages

        # Get response with potential tool calls
        if state.iteration_count < self.max_iterations:
            response = self.llm_with_tools.invoke(messages)
        else:
            return {}

        return {"messages": response, "iteration_count": state.iteration_count}

    def _tool_node(self, state: AgentState) -> dict[str, Any]:
        """Execute tools."""
        tool_node = ToolNode(self.tools)
        result = tool_node.invoke({"messages": state.messages})
        return result

    def _structurer_node(self, state: AgentState) -> dict[str, Any]:
        """Final synthesis - structures output if schema provided, otherwise synthesizes."""
        self.logger.info("Creating summary..")

        # Create synthesis prompt
        synthesis_prompt = f"""Based on all the research and tool calls performed,
provide a comprehensive answer to the original query.

Original query: {state.query}
"""

        messages = (
            [SystemMessage(content=self.system_prompt)]
            + state.messages
            + [HumanMessage(content=synthesis_prompt)]
        )

        if self.output_schema:
            # Use structured output - returns the Pydantic object directly
            structured_llm = self.llm.with_structured_output(self.output_schema)
            result = structured_llm.invoke(messages)
            # Store the structured result directly in state (not as a message)
            return {"structured_result": result}
        else:
            # Regular synthesis without schema - returns a message
            result = self.llm.invoke(messages)
            return {"messages": result}

    def _should_continue(self, state: AgentState) -> str:
        """Decide next step based on tool calls and iteration count."""

        # Check last message for tool calls
        if state.messages:
            last_message = state.messages[-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"

        # If max iterations reached or no tool calls, go to structurer
        return "structurer"

    def invoke(self, query: str, initial_context: list | None = None) -> Any:
        """
        Execute the agent with a query.

        Args:
            query: The user's query
            initial_context: Optional list of initial messages for context (e.g past history)

        Returns:
            The structured output or final message
        """
        initial_state = AgentState(
            query=query,
            messages=initial_context if initial_context else [],
            iteration_count=0,
        )

        result = self.app.invoke(initial_state)

        self.logger.info(f"Completed in {result['iteration_count']} iterations")

        # Return structured result if using output_schema, otherwise return final message
        if self.output_schema and result.get("structured_result"):
            return result["structured_result"]
        else:
            return result["messages"][-1].content
