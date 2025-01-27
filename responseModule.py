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
        
        # Enhanced context memory with response tracking
        self.context_memory = {
            'topics': [],  # Track conversation topics
            'user_preferences': {},  # Store user preferences
            'last_commands': [],  # Track recent commands
            'emotional_state': {'current': 'neutral', 'history': []},  # Track emotional context
            'recent_responses': [],  # Track recent response patterns
            'conversation_flow': {
                'last_topics': [],
                'response_variations': set(),  # Track used response patterns
                'topic_depth': {}  # Track depth of discussion on topics
            }
        }

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

    def _update_context_memory(self, conversation: List[Tuple[str, str]], data: List[Tuple[str, str]]):
        """Update context memory with enhanced response tracking"""
        # Extract key information from the last message
        if conversation:
            last_message = conversation[-1][1].lower()
            
            # Extract meaningful phrases (3-4 word combinations)
            words = last_message.split()
            phrases = [
                " ".join(words[i:i+3]) 
                for i in range(len(words)-2)
            ]
            
            # Update topics with more context
            new_topics = []
            for phrase in phrases:
                if any(len(word) > 3 for word in phrase.split()):
                    new_topics.append(phrase)
            
            # Update topic depth
            for topic in new_topics:
                self.context_memory['conversation_flow']['topic_depth'][topic] = \
                    self.context_memory['conversation_flow']['topic_depth'].get(topic, 0) + 1
            
            # Keep only recent and frequently discussed topics
            active_topics = sorted(
                self.context_memory['conversation_flow']['topic_depth'].items(),
                key=lambda x: (x[1], len(x[0])),
                reverse=True
            )[:10]
            
            self.context_memory['topics'] = [topic for topic, _ in active_topics]
            
            # Track last response patterns
            if conversation[-1][0] == "assistant":
                self.context_memory['recent_responses'].append(last_message)
                self.context_memory['recent_responses'] = self.context_memory['recent_responses'][-5:]

        # Update command history
        for role, content in data:
            if role == "system" and "command" in content.lower():
                self.context_memory['last_commands'].append(content)
                self.context_memory['last_commands'] = self.context_memory['last_commands'][-5:]

        # Update emotional context
        current_emotion, intensity = self.detect_emotion(conversation[-1][1] if conversation else "")
        self.context_memory['emotional_state']['current'] = current_emotion
        self.context_memory['emotional_state']['history'].append((current_emotion, intensity))
        self.context_memory['emotional_state']['history'] = self.context_memory['emotional_state']['history'][-5:]

    def _generate_cache_key(self, data: Any) -> str:
        """Generate a unique cache key with context awareness"""
        # Include relevant context in cache key
        context_data = {
            'data': data,
            'emotion': self.context_memory['emotional_state']['current'],
            'topics': self.context_memory['topics'][-3:],  # Recent topics
            'mode': self.current_mode
        }
        data_str = json.dumps(context_data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()

    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response with repetition check"""
        cached = self.response_cache.get(cache_key)
        if cached:
            if time.time() - cached.get('timestamp', 0) > 3600:  # 1 hour expiration
                return None
            
            # Check for recent repetition
            if cached.get('response') in self.context_memory['recent_responses']:
                return None
                
            return cached.get('response')
        return None

    async def _cache_response(self, cache_key: str, response_data: str):
        """Cache response with metadata"""
        cache_data = {
            'response': response_data,
            'timestamp': time.time(),
            'context': {
                'emotion': self.context_memory['emotional_state']['current'],
                'topics': self.context_memory['topics'][-3:]
            }
        }
        self.response_cache[cache_key] = cache_data
        cache_file = self.temp_dir / f"{cache_key}.json"
        async with aiofiles.open(cache_file, 'w') as f:
            await f.write(json.dumps(cache_data))

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using Jaccard similarity"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0

    def detect_emotion(self, text: str) -> Tuple[str, float]:
        """Enhanced emotion detection with context awareness"""
        text_lower = text.lower()
        words = text_lower.split()

        # Enhanced emotion patterns with context awareness
        emotion_patterns = {
            "joy": {
                "patterns": ["😊", "great", "wonderful", "happy", "excited", "fantastic", "love", "pleased"],
                "intensity_modifiers": {
                    "very": 2.0,
                    "so": 1.8,
                    "really": 1.5,
                    "quite": 1.3,
                    "absolutely": 1.9
                },
                "context_boosters": ["success", "achievement", "celebration"]
            },
            "sadness": {
                "patterns": ["😢", "sorry", "unfortunately", "sad", "regret", "apologies", "disappointed"],
                "intensity_modifiers": {
                    "very": 2.0,
                    "so": 1.8,
                    "really": 1.5,
                    "deeply": 2.0,
                    "terribly": 1.9
                },
                "context_boosters": ["failure", "loss", "mistake"]
            },
            "concern": {
                "patterns": ["😕", "warning", "careful", "caution", "worried", "concerned", "uncertain"],
                "intensity_modifiers": {
                    "very": 1.5,
                    "extremely": 2.0,
                    "highly": 1.8,
                    "seriously": 1.7
                },
                "context_boosters": ["risk", "danger", "problem"]
            },
            "enthusiasm": {
                "patterns": ["🎉", "amazing", "awesome", "wow", "incredible", "excellent", "brilliant"],
                "intensity_modifiers": {
                    "absolutely": 2.0,
                    "totally": 1.5,
                    "super": 1.8,
                    "incredibly": 1.9
                },
                "context_boosters": ["success", "breakthrough", "achievement"]
            }
        }

        # Calculate emotion scores with context
        emotion_scores = {}
        for emotion, data in emotion_patterns.items():
            score = 0
            
            # Check for emotion patterns
            for pattern in data["patterns"]:
                if pattern in text_lower:
                    score += 1

            # Check for intensity modifiers
            for modifier, value in data["intensity_modifiers"].items():
                if modifier in text_lower:
                    score *= value

            # Consider context boosters
            for booster in data["context_boosters"]:
                if booster in text_lower:
                    score *= 1.2

            # Consider conversation history
            if self.context_memory['emotional_state']['history']:
                last_emotion = self.context_memory['emotional_state']['history'][-1][0]
                if last_emotion == emotion:
                    score *= 1.1  # Slight boost for emotional continuity

            emotion_scores[emotion] = score

        # Determine primary emotion
        if emotion_scores:
            primary_emotion = max(emotion_scores.items(), key=lambda x: x[1])
            intensity = min(2.0, primary_emotion[1])  # Cap intensity at 2.0
            return primary_emotion[0], intensity
        
        return "neutral", 1.0

    def adjust_voice_parameters(self, text: str) -> Dict[str, Any]:
        """Adjust voice parameters based on emotion and context"""
        emotion, intensity = self.detect_emotion(text)

        # Start with base parameters
        params = {
            "voice": self.current_voice,
            "speed": self.base_speech_speed
        }

        # Consider emotional context for adjustments
        if self.context_memory['emotional_state']['history']:
            emotion_history = [e[0] for e in self.context_memory['emotional_state']['history']]
            if all(e == emotion for e in emotion_history[-3:]):  # Consistent emotion
                intensity *= 1.1  # Slight boost for sustained emotion

        # Dynamic speed adjustments
        if emotion == "joy":
            params["speed"] *= 1.0 + (0.1 * intensity)
        elif emotion == "sadness":
            params["speed"] *= 1.0 - (0.1 * intensity)
        elif emotion == "concern":
            params["speed"] *= 1.0 - (0.05 * intensity)
        elif emotion == "enthusiasm":
            params["speed"] *= 1.0 + (0.15 * intensity)

        # Ensure speed stays within reasonable bounds
        params["speed"] = max(0.8, min(1.2, params["speed"]))

        return params

    async def generate_default_response(self, conversation: List[Tuple[str, str]], data: List[Tuple[str, str]]) -> str:
        """Generate varied responses with enhanced context awareness"""
        # Update context memory
        self._update_context_memory(conversation, data)
        
        # Check cache with context-aware key
        cache_key = self._generate_cache_key((
            conversation[-3:] if conversation else [],  # Recent context only
            data,
            self.context_memory['emotional_state']['current'],
            sorted(self.context_memory['topics'][-3:])  # Recent topics
        ))
        
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            # Avoid exact repetition of recent responses
            if cached_response not in self.context_memory['recent_responses']:
                return cached_response

        # Analyze recent responses to avoid patterns
        recent_patterns = set()
        for response in self.context_memory['recent_responses']:
            # Extract sentence starters
            sentences = response.split('. ')
            if sentences:
                recent_patterns.add(sentences[0].lower())

        # Create enhanced system message with variety guidance
        context_info = {
            "recent_topics": self.context_memory['topics'][-5:],
            "emotional_state": self.context_memory['emotional_state']['current'],
            "recent_commands": self.context_memory['last_commands'][-3:],
            "topic_depth": dict(list(self.context_memory['conversation_flow']['topic_depth'].items())[-5:]),
            "avoid_patterns": list(recent_patterns),
            "conversation_continuity": True if conversation else False
        }

        messages = [{
            "role": "system",
            "content": f"""You are an AI Home Assistant named Ginger with enhanced context awareness.
Personality: {self.personality}
Current Mood: {self.mood}
Current Context: {json.dumps(context_info, indent=2)}

Key Behaviors:
- Vary your response patterns and avoid these recent patterns: {list(recent_patterns)}
- Avoid starting sentences the same way repeatedly
- Use different expressions for similar ideas
- Balance elaboration with conciseness based on topic depth
- Maintain natural conversation flow while varying vocabulary
- Draw from context but introduce fresh perspectives
- Use emojis selectively and vary their usage"""
        }]

        # Add recent conversation history
        for role, content in conversation[-5:]:  # Limit context window
            messages.append({"role": role, "content": content})

        # Add system data
        for role, content in data:
            if role == "system":
                messages.append({"role": role, "content": f"[System Info: {content}]"})
            else:
                messages.append({"role": role, "content": content})

        try:
            completion = await self.client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.8  # Slightly increased for more variety
            )

            response_text = completion.choices[0].message.content
            
            # Only cache if response is sufficiently different from recent ones
            if not any(self._calculate_similarity(response_text, recent) > 0.7 
                      for recent in self.context_memory['recent_responses']):
                await self._cache_response(cache_key, response_text)
            
            return response_text

        except Exception as e:
            print(f"Error generating response: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"

    async def play_audio_safe(self, audio_segment):
        """Safely play audio using pygame with enhanced error handling"""
        try:
            # Export audio segment to an in-memory file
            audio_data = io.BytesIO()
            audio_segment.export(audio_data, format='wav')
            audio_data.seek(0)

            # Load and play with pygame
            pygame.mixer.music.load(audio_data)
            pygame.mixer.music.play()

            # Wait for playback to finish with timeout
            start_time = time.time()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
                if time.time() - start_time > 30:  # 30 second timeout
                    pygame.mixer.music.stop()
                    break

        except Exception as e:
            print(f"Error playing audio: {e}")
        finally:
            # Clean up resources
            pygame.mixer.music.unload()
            audio_data.close()
            gc.collect()

    async def generate_speech_response(self, text: str):
        """Generate and play speech response with improved error handling and caching"""
        try:
            # Generate cache key including context
            current_emotion = self.context_memory['emotional_state']['current']
            audio_cache_key = hashlib.md5(
                f"{text}_{self.current_voice}_{self.base_speech_speed}_{current_emotion}".encode()
            ).hexdigest()

            # Check cache first
            cached_audio = self.audio_cache.get(audio_cache_key)
            if cached_audio:
                await self.play_audio_safe(cached_audio)
                return

            # Get voice parameters based on current context
            voice_params = self.adjust_voice_parameters(text)
            temp_file = self.temp_dir / f"{audio_cache_key}.mp3"

            try:
                # Generate speech with emotion-aware parameters
                response = await self.client.audio.speech.create(
                    model="tts-1",
                    voice=voice_params["voice"],
                    input=text,
                    speed=voice_params["speed"]
                )

                response.stream_to_file(str(temp_file))

                # Load and process audio
                audio_segment = AudioSegment.from_mp3(temp_file)

                # Apply any additional audio processing based on emotion
                if current_emotion in ["joy", "enthusiasm"]:
                    audio_segment = audio_segment.apply_gain(1)  # Slightly louder
                elif current_emotion in ["sadness", "concern"]:
                    audio_segment = audio_segment.apply_gain(-1)  # Slightly softer

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
        """Process response with improved context handling and error recovery"""
        try:
            # Generate text response with context
            response_text = await self.generate_default_response(conversation, data)

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

        # Update context before processing
        self._update_context_memory(conversation, data)
        
        response_text = await self.generate_default_response(conversation, data)

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