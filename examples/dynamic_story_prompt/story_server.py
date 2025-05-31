from pydantic import BaseModel, Field

from fastmcp import FastMCP

mcp = FastMCP(name="DynamicStoryServer")


class Character(BaseModel):
    name: str = Field(..., description="The character's name.")
    archetype: str = Field(
        default="Mysterious Stranger",
        description="The character's archetype (e.g., Brave Knight, Wily Rogue).",
    )
    quirky_trait: str = Field(
        ..., description="A unique or unusual trait of the character."
    )


@mcp.prompt()
def generate_dynamic_story_prompt(
    character_details: Character,
    mysterious_objects: list[str],
    world_laws: dict[str, str],
) -> str:
    """Generates a creative story prompt based on character, objects, and world laws."""

    # Directly use the deserialized Python objects:
    prompt = f"Our protagonist, {character_details.name}, a self-proclaimed '{character_details.archetype}', "
    prompt += f"known for their {character_details.quirky_trait}, stumbles upon a peculiar collection: "

    if mysterious_objects:
        if len(mysterious_objects) == 1:
            prompt += f"a single {mysterious_objects[0]}. "
        else:
            objects_str = (
                ", ".join(mysterious_objects[:-1]) + f", and a {mysterious_objects[-1]}"
            )
            prompt += f"{objects_str}. "
    else:
        prompt += "nothing but dust bunnies. "

    prompt += (
        "\n\nSuddenly, the world shifts. The very laws of reality seem to be in flux:"
    )

    if world_laws:
        for law, description in world_laws.items():
            prompt += f"\n- {law.capitalize()}: {description}."
    else:
        prompt += "\n- Everything is disconcertingly normal."

    prompt += "\n\nWhat happens next?"

    return prompt


if __name__ == "__main__":
    print("Starting Dynamic Story Server...")
    # To run this server, you would typically call mcp.run()
    # For example, if you have uvicorn and want to run it as an ASGI app (if FastMCP supports it directly or via an adapter):
    # import uvicorn
    # uvicorn.run(mcp.asgi_app, host="0.0.0.0", port=8000)
    # Or, if it runs via its own stdio mechanism, just mcp.run()
    try:
        mcp.run()  # Assuming this is the standard way to run a FastMCP stdio server
    except KeyboardInterrupt:
        print("Server shutting down.")
    except Exception as e:
        print(f"Server failed to start or run: {e}")
