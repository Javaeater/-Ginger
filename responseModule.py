import asyncio
from openai import AsyncOpenAI
from pathlib import Path
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
import hashlib
import aiofiles
import json
import tempfile
from cachetools import LRUCache
import time
from typing import Optional, Tuple, List, Dict, Any
import gc
import pygame
import io


class HighPerformanceResponseModule:
    def __init__(self, personality: str, mood: str, openai_api_key: str, cache_size: int = 1000):
        # Response modes
        self.TEXT_MODE = "text"
        self.VOICE_MODE = "voice"
        self.TEXT_TO_SPEECH_MODE = "text_to_speech"
        self.current_mode = self.VOICE_MODE

        self.mood = mood
        self.personality = personality
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.response_cache = LRUCache(maxsize=cache_size)
        self.audio_cache = LRUCache(maxsize=cache_size)
        self.temp_dir = Path(tempfile.gettempdir()) / "response_cache"
        self.temp_dir.mkdir(exist_ok=True)

        # Voice settings based on personality
        self.voice_personalities = {
            "friendly": "nova",  # Warm and approachable
            "professional": "onyx",  # Clear and authoritative
            "energetic": "fable",  # Bright and dynamic
            "calming": "echo",  # Soft and soothing
            "wise": "alloy",  # Balanced and mature
            "playful": "shimmer"  # Light and cheerful
        }
        self.base_speech_speed = 1.0

        # Set voice based on personality
        personality_lower = personality.lower()
        self.current_voice = self.voice_personalities.get(
            personality_lower,
            self.voice_personalities["friendly"]  # Default to friendly
        )

        # Initialize pygame mixer for audio playback
        pygame.mixer.init()

        # Enhanced emotion detection with intensity levels
        self.emotion_patterns = {
            "joy": {
                "patterns": ["😊", "great", "wonderful", "happy", "excited", "fantastic"],
                "intensity_modifiers": {
                    "very": 2.0,
                    "so": 1.8,
                    "really": 1.5,
                    "quite": 1.3
                }
            },
            "sadness": {
                "patterns": ["😢", "sorry", "unfortunately", "sad", "regret", "apologies"],
                "intensity_modifiers": {
                    "very": 2.0,
                    "so": 1.8,
                    "really": 1.5,
                    "deeply": 2.0
                }
            },
            "concern": {
                "patterns": ["😕", "warning", "careful", "caution", "worried", "concerned"],
                "intensity_modifiers": {
                    "very": 1.5,
                    "extremely": 2.0,
                    "highly": 1.8
                }
            },
            "enthusiasm": {
                "patterns": ["🎉", "amazing", "awesome", "wow", "incredible", "excellent"],
                "intensity_modifiers": {
                    "absolutely": 2.0,
                    "totally": 1.5,
                    "super": 1.8
                }
            }
        }

    def _generate_cache_key(self, data: Tuple) -> str:
        """Generate a unique cache key for the input data"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()

    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response if available"""
        cached = self.response_cache.get(cache_key)
        if cached:
            if time.time() - cached.get('timestamp', 0) > 3600:
                return None
            return cached.get('response')
        return None

    async def _cache_response(self, cache_key: str, response_data: str):
        """Cache the response data with timestamp"""
        cache_data = {
            'response': response_data,
            'timestamp': time.time()
        }
        self.response_cache[cache_key] = cache_data
        cache_file = self.temp_dir / f"{cache_key}.json"
        async with aiofiles.open(cache_file, 'w') as f:
            await f.write(json.dumps(cache_data))

    def detect_emotion(self, text: str) -> Tuple[str, float]:
        """
        Detect emotion and its intensity from text
        Returns: Tuple of (emotion, intensity)
        """
        text_lower = text.lower()
        words = text_lower.split()

        # First, find the primary emotion
        max_matches = 0
        detected_emotion = "neutral"
        for emotion, data in self.emotion_patterns.items():
            matches = sum(1 for pattern in data["patterns"]
                          if pattern.lower() in text_lower)
            if matches > max_matches:
                max_matches = matches
                detected_emotion = emotion

        # Then determine intensity
        intensity = 1.0  # Default intensity
        if detected_emotion != "neutral":
            # Check for intensity modifiers
            modifiers = self.emotion_patterns[detected_emotion]["intensity_modifiers"]
            for word in words:
                if word in modifiers:
                    intensity = modifiers[word]
                    break

            # Adjust intensity based on punctuation and repetition
            if "!" in text:
                intensity *= 1.2
            if "!!" in text:
                intensity *= 1.3
            if any(char * 3 in text for char in "!?."):
                intensity *= 1.2

        return detected_emotion, min(intensity, 2.0)  # Cap intensity at 2.0

    def adjust_voice_parameters(self, text: str) -> Dict[str, Any]:
        """
        Adjust voice parameters based on detected emotion and intensity
        Maintains personality-based voice while subtly adjusting other parameters
        """
        emotion, intensity = self.detect_emotion(text)

        # Start with base parameters
        params = {
            "voice": self.current_voice,
            "speed": self.base_speech_speed
        }

        # Subtle speed adjustments based on emotion and intensity
        if emotion == "joy":
            # Slightly faster for joy, scaled by intensity
            params["speed"] *= 1.0 + (0.1 * intensity)
        elif emotion == "sadness":
            # Slightly slower for sadness
            params["speed"] *= 1.0 - (0.1 * intensity)
        elif emotion == "concern":
            # Slightly slower and more measured for concern
            params["speed"] *= 1.0 - (0.05 * intensity)
        elif emotion == "enthusiasm":
            # Slightly faster for enthusiasm
            params["speed"] *= 1.0 + (0.15 * intensity)

        # Ensure speed stays within reasonable bounds
        params["speed"] = max(0.8, min(1.2, params["speed"]))

        return params

    async def generate_default_response(self, conversation: List[Tuple[str, str]], data: List[Tuple[str, str]]) -> str:
        """Generate text response"""
        cache_key = self._generate_cache_key((conversation, data))

        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return cached_response

        messages = [{
            "role": "system",
            "content": f"""You are an AI Home Assistant named Ginger. Your personality type is {self.personality} and your current mood is {self.mood}.

Key traits:
- You're helpful and efficient while maintaining a natural, conversational tone
- You use emojis occasionally when appropriate to convey emotion
- You acknowledge past interactions when relevant
- You avoid repetitive phrases and vary your responses
- You maintain context from previous messages

Please respond naturally to the conversation, incorporating any provided data."""
        }]

        for role, content in conversation:
            messages.append({"role": role, "content": content})

        for role, content in data:
            if role == "system":
                messages.append({"role": role, "content": f"[System Info: {content}]"})
            else:
                messages.append({"role": role, "content": content})

        try:
            completion = await self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7
            )

            response_text = completion.choices[0].message.content
            await self._cache_response(cache_key, response_text)
            return response_text
        except Exception as e:
            print(f"Error generating response: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"

    async def play_audio_safe(self, audio_segment):
        """Safely play audio using pygame"""
        try:
            # Export audio segment to an in-memory file
            audio_data = io.BytesIO()
            audio_segment.export(audio_data, format='wav')
            audio_data.seek(0)

            # Load and play with pygame
            pygame.mixer.music.load(audio_data)
            pygame.mixer.music.play()

            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error playing audio: {e}")
        finally:
            # Clean up
            pygame.mixer.music.unload()
            audio_data.close()
            gc.collect()

    async def generate_speech_response(self, text: str):
        """Generate and play speech response with improved error handling"""
        try:
            audio_cache_key = hashlib.md5(f"{text}_{self.current_voice}_{self.base_speech_speed}".encode()).hexdigest()

            cached_audio = self.audio_cache.get(audio_cache_key)
            if cached_audio:
                await self.play_audio_safe(cached_audio)
                return

            voice_params = self.adjust_voice_parameters(text)
            temp_file = self.temp_dir / f"{audio_cache_key}.mp3"

            try:
                response = await self.client.audio.speech.create(
                    model="tts-1",
                    voice=voice_params["voice"],
                    input=text,
                    speed=voice_params["speed"]
                )

                response.stream_to_file(str(temp_file))

                # Load audio with pydub
                audio_segment = AudioSegment.from_mp3(temp_file)

                # Cache and play
                self.audio_cache[audio_cache_key] = audio_segment
                await self.play_audio_safe(audio_segment)

            finally:
                # Clean up temporary file
                if temp_file.exists():
                    temp_file.unlink()

        except Exception as e:
            print(f"Error in speech generation: {e}")
        finally:
            gc.collect()

    async def process_response(self, conversation: List[Tuple[str, str]], data: List[Tuple[str, str]]) -> Tuple[
        str, Optional[asyncio.Task]]:
        """Process response with improved error handling"""
        try:
            response_text = await self.generate_default_response(conversation, data)

            speech_task = None
            if self.current_mode in [self.VOICE_MODE, self.TEXT_TO_SPEECH_MODE]:
                speech_task = asyncio.create_task(self.generate_speech_response(response_text))

            return response_text, speech_task

        except Exception as e:
            print(f"Error in response processing: {e}")
            return f"I apologize, but I encountered an error: {str(e)}", None

    async def process_text_input(self, text: str) -> Tuple[str, Optional[asyncio.Task]]:
        """Process text input and generate voice response if in text-to-speech mode"""
        conversation = [("user", text)]
        data = []

        response_text = await self.generate_default_response(conversation, data)

        speech_task = None
        if self.current_mode == self.TEXT_TO_SPEECH_MODE:
            speech_task = asyncio.create_task(
                self.generate_speech_response(response_text)
            )

        return response_text, speech_task

    def set_response_mode(self, mode: str):
        """Set the response mode"""
        valid_modes = [self.TEXT_MODE, self.VOICE_MODE, self.TEXT_TO_SPEECH_MODE]
        if mode.lower() not in valid_modes:
            raise ValueError(f"Invalid mode. Must be one of: {valid_modes}")

        self.current_mode = mode.lower()
        self.text_only_mode = (mode == self.TEXT_MODE)

    def __del__(self):
        """Cleanup resources"""
        try:
            self.executor.shutdown(wait=False)
            pygame.mixer.quit()
        except:
            pass