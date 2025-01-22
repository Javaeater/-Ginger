import asyncio
import os
from dotenv import load_dotenv
from capture_audio import VoiceListeningAssistant
from ProcessAgent import CommandProcessor, integrate_with_voice_assistant
from hue_agent import HueAgent

# Load environment variables
load_dotenv()

# Define available agents with detailed command parameters
AGENTS = [
    (
        "weather",
        "Get weather information for your location",
        [
            {
                "name": "get_weather_today",
                "description": "Get the weather from a specific location",
                "parameters": {
                    "location": "Location where weather is wanted"
                }
            },
        ]
    ),
    (
        "lights",
        "Control Philips Hue lights with advanced features",
        [
            {
                "name": "control_light",
                "description": "Turn lights on or off in a specific room",
                "parameters": {
                    "room": "The room name (e.g., living room, kitchen, bedroom)",
                    "state": "Either 'on' or 'off'"
                }
            },
            {
                "name": "set_color",
                "description": "Change light color in a specific room",
                "parameters": {
                    "room": "The room name",
                    "color": "Color name (red, green, blue, yellow, purple, cyan, orange, pink, warm, cool, neutral, daylight)"
                }
            },
            {
                "name": "set_brightness",
                "description": "Set light brightness in a specific room",
                "parameters": {
                    "room": "The room name",
                    "brightness": "Brightness level (0-100)"
                }
            },
            {
                "name": "set_mood",
                "description": "Set predefined mood lighting in a specific room",
                "parameters": {
                    "room": "The room name",
                    "mood": "Mood name"
                }
            },
            {
                "name": "get_light_status",
                "description": "Get the current status of lights",
                "parameters": {
                    "room": "(Optional) Room name to check specific light status"
                }
            }
        ]
    ),
]

async def main():
    # Get configuration from environment variables
    openai_api_key = os.getenv('OPENAI_API_KEY')
    ha_host = os.getenv('HA_HOST')
    ha_token = os.getenv('HA_TOKEN')
    porcupine_key = os.getenv('PORCUPINE_ACCESS_KEY')

    # Validate required environment variables
    required_vars = {
        'OPENAI_API_KEY': openai_api_key,
        'HA_HOST': ha_host,
        'HA_TOKEN': ha_token,
        'PORCUPINE_ACCESS_KEY': porcupine_key
    }

    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Create command processor
    processor = CommandProcessor(
        openai_api_key=openai_api_key,
        agents=AGENTS,
        personality="Fiji nani",
        mood="Welcoming"
    )

    # Initialize HueAgent
    processor.agent_instances["lights"] = HueAgent(
        host=ha_host,
        token=ha_token,
        openai_api_key=openai_api_key
    )

    # Create and configure voice assistant
    assistant = VoiceListeningAssistant(
        openai_api_key=openai_api_key,
        porcupine_access_key=porcupine_key
    )

    # Integrate command processor
    integrate_with_voice_assistant(assistant, processor)

    # Start the system
    try:
        print("\nStarting voice assistant system...")
        await assistant.start_listening()
    except KeyboardInterrupt:
        print("\nShutting down voice assistant system...")
    except Exception as e:
        print(f"\nError in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())