from fastmcp.tools.tool import FunctionTool
from fastmcp.utilities.components import FastMCPComponent


class BaseAgent(FastMCPComponent):
    """A base class for agents. Define the __call__ method to implement the agent."""

    system_prompt: str

    def to_tool(self) -> "AgentTool":
        return AgentTool.from_agent(agent=self)


class AgentTool(FunctionTool):
    """An agent tool that can be used to run an agent."""

    @classmethod
    def from_agent(cls, agent: BaseAgent) -> "AgentTool":
        if not callable(agent):
            msg = f"Agent {agent.name} does not have a __call__ method."
            raise TypeError(msg)

        return cls.from_function(  # pyright: ignore[reportReturnType]
            fn=agent.__call__,  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            name=agent.name,
            description=agent.description,
            tags=agent.tags,
            enabled=agent.enabled,
        )
