import asyncio
from openai import AsyncOpenAI
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import tempfile
from typing import Optional, Tuple, List, Dict, Any
import pygame
import pygame.mixer
import time
import os


class HighPerformanceResponseModule:
    def __init__(self, personality: str, mood: str, openai_api_key: str, assistant_history: List):
        # Response modes
        self.TEXT_MODE = "text"
        self.VOICE_MODE = "voice"
        self.TEXT_TO_SPEECH_MODE = "text_to_speech"
        self.current_mode = self.VOICE_MODE

        self.mood = mood
        self.personality = personality
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.temp_dir = Path(tempfile.gettempdir()) / "response_temp"
        self.temp_dir.mkdir(exist_ok=True)
        self.assistant_history = assistant_history

        # Voice settings based on personality
        self.voice_personalities = {
            "friendly": "nova",  # Warm and approachable
            "professional": "onyx",  # Clear and authoritative
            "energetic": "fable",  # Bright and dynamic
            "calming": "echo",  # Soft and soothing
            "wise": "alloy",  # Balanced and mature
            "playful": "shimmer"  # Light and cheerful
        }
        # Set voice based on personality
        personality_lower = personality.lower()
        self.current_voice = self.voice_personalities.get(
            personality_lower,
            self.voice_personalities["friendly"]  # Default to friendly
        )

        # Initialize pygame mixer for audio playback
        pygame.mixer.init()

    def update_history(self, new_history):
        self.assistant_history = new_history

    def adjust_voice_parameters(self, text: str) -> Dict[str, Any]:
        """Adjust voice parameters based on emotion and context"""
        # Start with base parameters
        params = {
            "voice": self.current_voice,
        }
        return params

    async def generate_default_response(self) -> str:
        """Generate varied responses with enhanced context awareness"""
        # Update context memory
        self.assistant_history = self.assistant_history[-10:]
        print(f"Context History: {self.assistant_history}")

        messages = [{
            "role": "system",
            "content": f"""You are an AI Home Assistant named Ginger. Please respond to only the last user message based on any info given by the system or assistant. If successful the system messages will tell you the result of what was completed if not they will tell you the error
Personality: {self.personality}
Current Mood: {self.mood}"""
        }]

        # Add recent conversation history
        for message in self.assistant_history[-5:]:  # Limit context window
            messages.append({"role": message[0], "content": message[1]})

        try:
            completion = await self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.8  # Slightly increased for more variety
            )

            response_text = completion.choices[0].message.content

            return response_text

        except Exception as e:
            print(f"Error generating response: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"

    async def generate_speech_response(self, text: str):
        """Generate and play speech response with improved Raspberry Pi compatibility"""
        temp_file = None
        try:
            # Get voice parameters
            voice_params = self.adjust_voice_parameters(text)

            # Create unique temp file
            timestamp = int(time.time() * 1000)
            temp_file = self.temp_dir / f"temp_audio_{timestamp}.mp3"

            # Generate speech
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice=voice_params["voice"],
                input=text,
            )

            # Stream to file with explicit close
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_bytes(chunk_size=4096):
                    f.write(chunk)

            # Ensure file exists and has content
            if not temp_file.exists() or temp_file.stat().st_size == 0:
                raise Exception("Audio file was not created successfully")

            # Load and play with extra error checking
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)

                pygame.mixer.music.load(str(temp_file))
                pygame.mixer.music.play()

                # Wait for playback with timeout
                start_time = time.time()
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
                    if time.time() - start_time > 30:  # 30 second timeout
                        pygame.mixer.music.stop()
                        break

            except Exception as audio_error:
                print(f"Playback error: {audio_error}")
                # Try to reinitialize mixer
                pygame.mixer.quit()
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                raise

        except Exception as e:
            print(f"Error in speech generation: {e}")
            self.current_mode = self.TEXT_MODE  # Fallback to text mode
            raise

        finally:
            # Cleanup
            try:
                pygame.mixer.music.unload()
            except:
                pass

            # Remove temp file
            if temp_file and temp_file.exists():
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"Error removing temp file: {e}")

    async def process_response(self) -> Tuple[
        str, Optional[asyncio.Task]]:
        """Process response with improved context handling and error recovery"""
        try:
            #print(f"Current Convo for testing: {conversation}")
            # Generate text response with context
            response_text = await self.generate_default_response()

            speech_task = None
            if self.current_mode in [self.VOICE_MODE, self.TEXT_TO_SPEECH_MODE]:
                speech_task = asyncio.create_task(self.generate_speech_response(response_text))

            return response_text, speech_task

        except Exception as e:
            print(f"Error in response processing: {e}")
            error_response = f"I apologize, but I encountered an error: {str(e)}"

            # Attempt basic error recovery
            try:
                if self.current_mode in [self.VOICE_MODE, self.TEXT_TO_SPEECH_MODE]:
                    speech_task = asyncio.create_task(self.generate_speech_response(error_response))
                    return error_response, speech_task
            except:
                pass

            return error_response, None

    async def process_text_input(self, text: str) -> Tuple[str, Optional[asyncio.Task]]:
        """Process text input with context awareness"""
        conversation = [("user", text)]
        data = []

        response_text = await self.generate_default_response()

        speech_task = None
        if self.current_mode == self.TEXT_TO_SPEECH_MODE:
            speech_task = asyncio.create_task(
                self.generate_speech_response(response_text)
            )

        return response_text, speech_task

    def set_response_mode(self, mode: str):
        """Set the response mode with validation"""
        valid_modes = [self.TEXT_MODE, self.VOICE_MODE, self.TEXT_TO_SPEECH_MODE]
        if mode.lower() not in valid_modes:
            raise ValueError(f"Invalid mode. Must be one of: {valid_modes}")

        self.current_mode = mode.lower()
        self.text_only_mode = (mode == self.TEXT_MODE)

    def __del__(self):
        """Cleanup resources safely"""
        try:
            self.executor.shutdown(wait=False)
            pygame.mixer.quit()
        except:
            pass