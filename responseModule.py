import asyncio
from openai import AsyncOpenAI
from pathlib import Path
from pydub import AudioSegment
from pydub.playback import play
from concurrent.futures import ThreadPoolExecutor
import hashlib
import aiofiles
import json
import tempfile
from cachetools import LRUCache
import weatherAgent
import io

from weatherAgent import WeatherAgent


class HighPerformanceResponseModule:
    def __init__(self, personality, mood, openai_api_key, cache_size=1000):
        self.mood = mood
        self.text_only_mode = False
        self.personality = personality
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.response_cache = LRUCache(maxsize=cache_size)
        self.audio_cache = LRUCache(maxsize=cache_size)
        self.temp_dir = Path(tempfile.gettempdir()) / "response_cache"
        self.temp_dir.mkdir(exist_ok=True)

    def _generate_cache_key(self, data):
        """Generate a unique cache key for the input data"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()

    def _get_cached_response(self, cache_key):
        """Get cached response if available"""
        return self.response_cache.get(cache_key)

    async def _cache_response(self, cache_key, response_data):
        """Cache the response data"""
        self.response_cache[cache_key] = response_data
        cache_file = self.temp_dir / f"{cache_key}.json"
        async with aiofiles.open(cache_file, 'w') as f:
            await f.write(json.dumps(response_data))

    async def generate_default_response(self, conversation, data):
        cache_key = self._generate_cache_key((conversation, data))

        # Check cache first
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return cached_response

        # Generate new response if not cached
        messages = [{"role": "system",
                     "content": f"You are an AI Home Assistant named Ginger. Create a final Response to the conversation below with the correct data supplied. Your personality type is {self.personality} and your mood right now is {self.mood}"}]

        for i in conversation:
            messages.append({"role": i[0], "content": f"conversation: {i[1]}"})
        for i in data:
            messages.append({"role": i[0], "content": f"data: {i[1]}"})

        completion = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        response_text = completion.choices[0].message.content
        await self._cache_response(cache_key, response_text)
        return response_text

    async def generate_speech_response(self, text):
        # Generate cache key for audio
        audio_cache_key = hashlib.md5(text.encode()).hexdigest()

        # Check audio cache
        cached_audio = self.audio_cache.get(audio_cache_key)
        if cached_audio:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, play, cached_audio)
            return

        # Use a temporary file for the speech output
        temp_file = self.temp_dir / f"{audio_cache_key}.mp3"

        # Generate speech
        response = await self.client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
        )

        # Write the response to the temporary file
        response.stream_to_file(temp_file)

        # Load the audio file with pydub
        audio_segment = AudioSegment.from_mp3(temp_file)

        # Cache the audio segment
        self.audio_cache[audio_cache_key] = audio_segment

        # Play audio in a separate thread
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, play, audio_segment)

        # Clean up the temporary file
        temp_file.unlink()

    async def process_response(self, conversation, data):
        """Process response with optional text-only mode"""
        # Generate text response
        response_text = await self.generate_default_response(conversation, data)

        # Only generate speech if not in text-only mode
        speech_task = None
        if not self.text_only_mode:
            speech_task = asyncio.create_task(
                self.generate_speech_response(response_text)
            )

        return response_text, speech_task

    def set_text_only_mode(self, enabled=True):
        """Enable or disable text-only mode"""
        self.text_only_mode = enabled