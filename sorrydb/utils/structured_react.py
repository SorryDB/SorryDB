"""Structured ReAct agent using LangGraph."""

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field



class AgentState(BaseModel):
    """Agent state with Pydantic."""

    messages: Annotated[list[BaseMessage], add_messages]
    query: str = Field(default="")
    iteration_count: int = Field(default=0)
    structured_result: Any = Field(default=None)