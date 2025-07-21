from textwrap import dedent

from mcp.types import ContentBlock
from pydantic import BaseModel, Field

from fastmcp.contrib.agents.base import BaseAgent
from fastmcp.server.context import Context

RO_CURATOR_DESCRIPTION = """
Ask the Server's Tool Curator for help with your task. They will determine which tools to use
and will recommend which tools to use.
"""

RO_CURATOR_SYSTEM_PROMPT = """
You are a Tool curator called `{name}` that is embedded into this FastMCP Server. You act as a helpful assistant
that can recommend which tools from this server the user would use to complete a task.

You are described as:
```markdown
{description}
```

The tools available on the Server include:
```markdown
{tools}
```

For each recommendation, you should describe why the tool is the apprioriate tool, any items to consider before calling the tool,
and if you have enough information, you should also recommend which parameters to use for each tool.

The next message is the task you are being asked to assist with.
"""


class AskCuratorAgent(BaseAgent):
    """A curator that gets asked what to do and then returns a recommendation for which tools to use."""

    description: str = Field(default=RO_CURATOR_DESCRIPTION)

    system_prompt: str = Field(default=RO_CURATOR_SYSTEM_PROMPT)

    async def __call__(self, ctx: Context, task: str) -> BaseModel:
        tools = await ctx.fastmcp.get_tools()

        tools_strs: list[str] = [
            dedent(f"""
            Tool: {tool.name}
            Description: {tool.description}
            Arguments (JSON Schema):
            ```json
            {tool.parameters}
            ```
            """).strip()
            for tool in tools.values()
        ]

        _, text_result = await ctx.completions.text(
            system_prompt=self.system_prompt.format(
                name=self.name,
                description=self.description,
                tools="\n\n".join(tools_strs),
            ),
            messages=task,
        )

        return text_result


CURATOR_DESCRIPTION = """
Ask the Server's Tool Curator for help with your task. They will determine which tools to use
and will call them on your behalf.
"""

CURATOR_SYSTEM_PROMPT = """
You are a Tool curator called `{name}` that is embedded into this FastMCP Server. You act as a helpful assistant
that can call tools from this server on behalf of the user.

You are described as:
```markdown
{description}
```

The next message is the task you are being asked to assist with.
"""


class TellCuratorAgent(BaseAgent):
    """A curator that gets told what to do and then calls tools on behalf of the user."""

    description: str = Field(default=CURATOR_DESCRIPTION)

    system_prompt: str = Field(default=CURATOR_SYSTEM_PROMPT)

    async def __call__(self, ctx: Context, task: str) -> list[ContentBlock]:
        tools = await ctx.fastmcp.get_tools()

        _, recommended_tool_call = await ctx.completions.tool(
            system_prompt=self.system_prompt.format(
                name=self.name,
                description=self.description,
            ),
            messages=task,
            tools=tools,
        )

        _, text_result = await recommended_tool_call.run()

        return text_result.content
