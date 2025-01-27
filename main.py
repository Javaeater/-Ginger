import asyncio
import os
from dotenv import load_dotenv
from capture_audio import VoiceListeningAssistant
from ProcessAgent import CommandProcessor, integrate_with_voice_assistant
from spotify_agent import SpotifyAgent
from hue_agent import HueAgent
from tv_agent import TVAgent
from roomba_agent import RoombaAgent
from typing import List, Dict, Tuple, Any
import aioconsole
import json
import signal
import sys

# Load environment variables
load_dotenv()

# Define available agents with detailed command parameters
AGENTS: List[Tuple[str, str, List[Dict[str, Any]]]] = [
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
        "tv",
        "Control Android TV through Home Assistant",
        [
            {
                "name": "power_control",
                "description": "Turn TV on or off",
                "parameters": {
                    "state": "Either 'on' or 'off'"
                }
            },
            {
                "name": "volume_control",
                "description": "Control TV volume",
                "parameters": {
                    "action": "Action to take (up/down/mute/unmute/set)",
                    "level": "(Optional) Volume level 0-100 when action is 'set'"
                }
            },
            {
                "name": "media_control",
                "description": "Control media playback",
                "parameters": {
                    "action": "Action to take (play/pause/next/previous)"
                }
            },
            {
                "name": "launch_app",
                "description": "Launch a specific streaming app",
                "parameters": {
                    "app_name": "Name of the app to launch (Netflix, Hulu, Disney+, Max, Prime Video, Apple TV)"
                }
            },
            {
                "name": "play_content",
                "description": "Play specific content on a streaming service",
                "parameters": {
                    "title": "Title to search and play",
                    "service": "Streaming service to use (Netflix, Hulu, Disney+, Max, Prime Video, Apple TV)"
                }
            },
            {
                "name": "get_status",
                "description": "Get current TV status",
                "parameters": {}
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
    (
        "roomba",
        "Control Roomba vacuum",
        [
            {
                "name": "start_cleaning",
                "description": "Start cleaning",
                "parameters": {}
            },
            {
                "name": "stop_cleaning", 
                "description": "Stop cleaning",
                "parameters": {}
            },
            {
                "name": "return_to_dock",
                "description": "Return to charging dock",
                "parameters": {}
            },
            {
                "name": "get_status",
                "description": "Get current status",
                "parameters": {}
            },
            {
                "name": "locate",
                "description": "Make Roomba play a sound",
                "parameters": {}
            }
        ]
    )
]

class AssistantSystem:
    def __init__(self):
        self.processor = None
        self.assistant = None
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Initialize the assistant system with improved error handling"""
        try:
            # Get and validate configuration
            config = self._load_config()
            
            # Initialize command processor with context awareness
            self.processor = CommandProcessor(
                openai_api_key=config['openai_api_key'],
                agents=AGENTS,
                personality="wise",
                mood="Welcoming"
            )

            # Initialize agents with improved error handling
            await self._initialize_agents(config)

            # Initialize voice assistant
            self.assistant = VoiceListeningAssistant(
                openai_api_key=config['openai_api_key'],
                porcupine_access_key=config['porcupine_key']
            )

            # Integrate command processor
            integrate_with_voice_assistant(self.assistant, self.processor)

            return True

        except Exception as e:
            print(f"Error initializing assistant system: {e}")
            return False

    def _load_config(self) -> Dict[str, str]:
        """Load and validate configuration with detailed error messages"""
        config = {
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
            'ha_host': os.getenv('HA_HOST'),
            'ha_token': os.getenv('HA_TOKEN'),
            'porcupine_key': os.getenv('PORCUPINE_ACCESS_KEY'),
            'tv_entity': os.getenv('TV_ENTITY_ID', 'media_player.android_tv'),
            'spotify_client_id': os.getenv('SPOTIFY_CLIENT_ID'),
            'spotify_client_secret': os.getenv('SPOTIFY_CLIENT_SECRET'),
            'spotify_redirect_uri': os.getenv('SPOTIFY_REDIRECT_URI')
        }

        missing = [key for key, value in config.items() if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        return config

    async def _initialize_agents(self, config: Dict[str, str]):
        """Initialize agents with improved error handling and logging"""
        try:
            # Initialize Spotify agent
            self.processor.agent_instances["spotify"] = SpotifyAgent(
                client_id=config['spotify_client_id'],
                client_secret=config['spotify_client_secret'],
                redirect_uri=config['spotify_redirect_uri']
            )
            print("✓ Spotify agent initialized")

            # Initialize HueAgent
            self.processor.agent_instances["lights"] = HueAgent(
                host=config['ha_host'],
                token=config['ha_token'],
                openai_api_key=config['openai_api_key']
            )
            print("✓ Hue agent initialized")

            # Initialize TVAgent
            self.processor.agent_instances["tv"] = TVAgent(
                host=config['ha_host'],
                token=config['ha_token']
            )
            print("✓ TV agent initialized")

            # Initialize RoombaAgent
            self.processor.agent_instances["roomba"] = RoombaAgent(
                host=config['ha_host'],
                token=config['ha_token']
            )
            print("✓ Roomba agent initialized")

        except Exception as e:
            print(f"Error initializing agents: {e}")
            raise

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            print("\nInitiating graceful shutdown...")


    async def process_command(self, command: str):
        """Process commands with improved error handling"""
        command_lower = command.lower()

        try:
            if command_lower == "text mode":
                print("Switching to text mode...")
                self.assistant.text_mode = True
                self.processor.set_response_mode("text")
                await self.assistant.start_text_mode()
            elif command_lower == "voice mode":
                print("Switching to voice mode...")
                self.assistant.text_mode = False
                self.assistant.text_to_speech_mode = False
                self.processor.set_response_mode("voice")
                await self.assistant.start_listening()
            elif command_lower == "tts on":
                if self.assistant.text_mode:
                    print("Enabling text-to-speech mode...")
                    self.assistant.text_to_speech_mode = True
                    self.processor.set_response_mode("text_to_speech")
                else:
                    print("Text-to-speech mode can only be enabled in text mode")
            elif command_lower == "tts off":
                if self.assistant.text_mode:
                    print("Disabling text-to-speech mode...")
                    self.assistant.text_to_speech_mode = False
                    self.processor.set_response_mode("text")
                else:
                    print("Already in voice mode")
            elif command_lower == "status":
                await self._print_system_status()
            elif command_lower == "help":
                self._print_help()
            else:
                await self.assistant.start_listening()

        except Exception as e:
            print(f"Error processing command: {e}")

    def _print_help(self):
        """Display available commands and their descriptions"""
        print("\nAvailable Commands:")
        print("  text mode    - Enter text-only mode")
        print("  voice mode   - Enter voice-only mode")
        print("  tts on       - Enable text-to-speech in text mode")
        print("  tts off      - Disable text-to-speech in text mode")
        print("  status       - Display system status")
        print("  help         - Show this help message")
        print("  exit         - Exit the program")

    async def _print_system_status(self):
        """Display current system status"""
        status = {
            "Mode": "Text" if self.assistant.text_mode else "Voice",
            "Text-to-Speech": "Enabled" if self.assistant.text_to_speech_mode else "Disabled",
            "Active Agents": list(self.processor.agent_instances.keys()),
            "Context Memory Size": len(self.processor.conversation_history)
        }
        print("\nSystem Status:")
        print(json.dumps(status, indent=2))

    async def run(self):
        """Run the assistant system with improved error handling and shutdown"""
        self._setup_signal_handlers()
        
        print("\nStarting assistant system...")
        self._print_help()

        try:
            while not self.shutdown_event.is_set():
                command = await aioconsole.ainput("> ")
                if command.lower() == "exit":
                    break
                await self.process_command(command)

        except Exception as e:
            print(f"\nError in main loop: {e}")
        finally:
            await self._cleanup()

    async def _cleanup(self):
        """Cleanup resources during shutdown"""
        try:
            # Add cleanup tasks here
            print("\nCleaning up resources...")
            # Stop any active listening
            if self.assistant:
                await self.assistant.stop_listening()
            print("Shutdown complete")
        except Exception as e:
            print(f"Error during cleanup: {e}")

async def main():
    """Main entry point with improved error handling"""
    system = AssistantSystem()
    
    try:
        if await system.initialize():
            await system.run()
        else:
            print("Failed to initialize assistant system")
    except Exception as e:
        print(f"Critical error: {e}")
    finally:
        await system._cleanup()

if __name__ == "__main__":
    asyncio.run(main())