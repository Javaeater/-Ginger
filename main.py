import asyncio
import os
from dotenv import load_dotenv
from capture_audio import VoiceListeningAssistant
from ProcessAgent import CommandProcessor, integrate_with_voice_assistant
from spotify_agent import SpotifyAgent
from hue_agent import HueAgent
import aioconsole

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
(
        "spotify",
        "Control Spotify playback with voice commands",
        [
            {
                "name": "play_song",
                "description": "Play a specific song, optionally filtered by artist",
                "parameters": {
                    "song_name": "Name of the song to play",
                    "artist": "(Optional) Name of the artist"
                }
            },
            {
                "name": "play_artist",
                "description": "Play top songs from a specific artist",
                "parameters": {
                    "artist_name": "Name of the artist to play"
                }
            },
            {
                "name": "start_artist_radio",
                "description": "Start a radio station based on an artist",
                "parameters": {
                    "artist_name": "Name of the artist to base radio on"
                }
            },
            {
                "name": "play_liked_songs",
                "description": "Play your liked songs playlist",
                "parameters": {
                    "shuffle": "(Optional) Whether to shuffle the playlist (default: True)"
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
        personality="wise",
        mood="Welcoming"
    )

    processor.agent_instances["spotify"] = SpotifyAgent(
        client_id=os.getenv('SPOTIFY_CLIENT_ID'),
        client_secret=os.getenv('SPOTIFY_CLIENT_SECRET'),
        redirect_uri=os.getenv('SPOTIFY_REDIRECT_URI')
    )

    # Initialize HueAgent
    #processor.agent_instances["lights"] = HueAgent(
    #    host=ha_host,
    #    token=ha_token,
    #    openai_api_key=openai_api_key
    #)

    # Create and configure voice assistant
    assistant = VoiceListeningAssistant(
        openai_api_key=openai_api_key,
        porcupine_access_key=porcupine_key
    )

    # Integrate command processor
    integrate_with_voice_assistant(assistant, processor)

    # Start the system
    try:
        print("\nStarting assistant system...")
        print("Available commands:")
        print("- 'text mode': Enter text-only mode")
        print("- 'voice mode': Enter voice-only mode")
        print("- 'tts on': Enable text-to-speech in text mode")
        print("- 'tts off': Disable text-to-speech in text mode")
        print("- 'exit': Exit the program")

        while True:
            command = await aioconsole.ainput("> ")
            command_lower = command.lower()

            if command_lower == "text mode":
                print("Switching to text mode...")
                assistant.text_mode = True
                processor.set_response_mode("text")
                await assistant.start_text_mode()
            elif command_lower == "voice mode":
                print("Switching to voice mode...")
                assistant.text_mode = False
                assistant.text_to_speech_mode = False
                processor.set_response_mode("voice")
                await assistant.start_listening()
            elif command_lower == "tts on":
                if assistant.text_mode:
                    print("Enabling text-to-speech mode...")
                    assistant.text_to_speech_mode = True
                    processor.set_response_mode("text_to_speech")
                else:
                    print("Text-to-speech mode can only be enabled in text mode")
            elif command_lower == "tts off":
                if assistant.text_mode:
                    print("Disabling text-to-speech mode...")
                    assistant.text_to_speech_mode = False
                    processor.set_response_mode("text")
                else:
                    print("Already in voice mode")
            elif command_lower == "exit":
                break
            else:
                await assistant.start_listening()

    except KeyboardInterrupt:
        print("\nShutting down assistant system...")
    except Exception as e:
        print(f"\nError in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())