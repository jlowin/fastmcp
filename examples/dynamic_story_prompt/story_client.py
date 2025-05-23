import asyncio
import json

from fastmcp import Client

SERVER_SCRIPT_PATH = __file__.replace("client", "server")


async def main():
    print(f"Attempting to connect to server script: {SERVER_SCRIPT_PATH}\n")
    client = Client(SERVER_SCRIPT_PATH)

    async with client:
        print("Successfully connected to server!")

        # 1. Define the complex data for the prompt
        character_data = {
            "name": "Elara",
            "archetype": "Reluctant Oracle",
            "quirky_trait": "habit of humming ancient, forgotten tunes when nervous",
        }

        objects_data = [
            "a tarnished silver locket that refuses to open",
            "a smooth, obsidian sphere that whispers secrets in the dark",
            "a single, petrified rose that blooms only in moonlight",
        ]

        laws_data = {
            "time": "flows like molasses uphill on Tuesdays",
            "shadows": "have a mind of their own and occasionally steal small, shiny objects",
            "laughter": "can briefly mend broken things",
        }

        # 2. Prepare arguments for the client, serializing complex types to JSON strings
        prompt_args = {
            # 'character_details' expects a Character Pydantic model
            "character_details": json.dumps(character_data),
            # 'mysterious_objects' expects a list[str]
            "mysterious_objects": json.dumps(objects_data),
            # 'world_laws' expects a dict[str, str]
            "world_laws": json.dumps(laws_data),
        }

        print("--- Sending to server: ---")
        for key, value in prompt_args.items():
            print(f"  {key}: {value}")
        print("--------------------------\n")

        try:
            # 3. Call the prompt
            results_iterable = await client.get_prompt(
                "generate_dynamic_story_prompt", arguments=prompt_args
            )

            print("--- Generated Story Prompt from Server: ---")

            # The client.get_prompt() seems to return an iterable of (key, value) pairs
            # from the GetPromptResult model. We need to find the 'messages' key.
            prompt_messages_list = None
            if results_iterable:
                for key, value in results_iterable:
                    if key == "messages":
                        prompt_messages_list = value
                        break  # Found the messages list

            if prompt_messages_list:
                for message in (
                    prompt_messages_list
                ):  # This should be a list of PromptMessage objects
                    if (
                        hasattr(message, "content")
                        and hasattr(message.content, "text")
                        and message.content.text is not None
                    ):
                        print(message.content.text)
                    else:
                        print(
                            f"(Received message with unexpected content structure: {message!r})"
                        )
            else:
                print(
                    "(Could not find 'messages' in the prompt result or result was empty)"
                )

            print("-----------------------------------------")

        except Exception as e:
            print(f"Error calling prompt: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
