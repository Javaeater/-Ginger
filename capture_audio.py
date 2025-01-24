import speech_recognition as sr
import asyncio
from openai import OpenAI
import wave
import os
import pvporcupine
import pyaudio
import struct
import threading
import time
import aioconsole


class VoiceListeningAssistant:
    def __init__(self, openai_api_key, porcupine_access_key):
        self.text_mode = False
        self.text_to_speech_mode = False  # New mode for text-to-speech

        # Initialize Whisper components
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 25
        self.recognizer.pause_threshold = 1.5
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.non_speaking_duration = 1.5
        self.recognizer.dynamic_energy_adjustment_ratio = 1.5

        self.client = OpenAI(api_key=openai_api_key)

        self.porcupine = pvporcupine.create(
            access_key=porcupine_access_key,
            #keyword_paths=["Hey-Ginger_en_mac_v3_0_0.ppn"]
            keyword_paths=["Hey-Ginger_en_windows_v3_0_0.ppn"]
        )

        self.audio_queue = asyncio.Queue()
        self.pa = pyaudio.PyAudio()
        self.listening_for_command = False
        self.stop_listening_event = asyncio.Event()
        self.command_timeout = 15

        self.conversation_mode = False
        self.conversation_timeout = 30
        self.last_interaction = time.time()
        self.conversation_timer = None

    async def start_text_mode(self):
        """Start text mode listening with optional text-to-speech"""
        print("Entering text mode. Type your commands (type 'exit' to quit)...")
        self.text_mode = True
        self.loop = asyncio.get_running_loop()

        try:
            while not self.stop_listening_event.is_set() and self.text_mode:
                try:
                    user_input = await aioconsole.ainput("> ")

                    if user_input.lower() == 'exit':
                        print("Exiting text mode...")
                        self.text_mode = False
                        break
                    elif user_input.lower() == 'tts on':
                        print("Enabling text-to-speech mode...")
                        self.text_to_speech_mode = True
                        continue
                    elif user_input.lower() == 'tts off':
                        print("Disabling text-to-speech mode...")
                        self.text_to_speech_mode = False
                        continue

                    if user_input:
                        result = await self.process_command(user_input)
                        print(f"\nResponse: {result}")

                except Exception as e:
                    print(f"Error processing text input: {e}")

        except KeyboardInterrupt:
            print("\nStopping text mode...")
        finally:
            self.text_mode = False
            self.text_to_speech_mode = False

    async def process_command(self, command: str):
        """Process command using the appropriate mode"""
        if self.text_to_speech_mode:
            # If in text-to-speech mode, use process_text_input instead
            if hasattr(self, 'response_module'):
                response_text, speech_task = await self.response_module.process_text_input(command)
                if speech_task:
                    await speech_task
                return response_text
            else:
                return f"Processed with TTS: {command}"
        else:
            return f"Processed: {command}"

    def prepare_audio_file(self, audio_data):
        temp_wav = "temp_audio.wav"
        with wave.open(temp_wav, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(32000)
            wav_file.writeframes(audio_data.get_raw_data())
        return temp_wav

    def transcribe_with_whisper(self, audio_data):
        try:
            temp_wav = self.prepare_audio_file(audio_data)
            with open(temp_wav, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text"
                )
            os.remove(temp_wav)
            return transcript.strip()
        except Exception as e:
            print(f"Error in Whisper transcription: {e}")
            return None

    async def process_command(self, command: str):
        """Placeholder for command processing - will be overridden"""
        print(f"Base process_command called with: {command}")
        return f"Processed: {command}"

    def check_conversation_timeout(self):
        """Check if conversation mode should timeout due to inactivity"""
        if time.time() - self.last_interaction > self.conversation_timeout:
            print("\nConversation mode timed out due to inactivity")
            self.exit_conversation_mode()
        else:
            # Reset timer for next check
            self.conversation_timer = threading.Timer(
                self.conversation_timeout,
                self.check_conversation_timeout
            )
            self.conversation_timer.start()

    def enter_conversation_mode(self):
        """Enter conversation mode"""
        self.conversation_mode = True
        self.last_interaction = time.time()
        print("\nEntering conversation mode. You can speak without using the wake word.")
        print("Say 'exit conversation' to end conversation mode.")

        # Start conversation timeout checker
        self.conversation_timer = threading.Timer(
            self.conversation_timeout,
            self.check_conversation_timeout
        )
        self.conversation_timer.start()

        # Start continuous listening
        threading.Thread(target=self.continuous_command_capture).start()

    def exit_conversation_mode(self):
        """Exit conversation mode"""
        self.conversation_mode = False
        if self.conversation_timer:
            self.conversation_timer.cancel()
        print("\nExiting conversation mode. Wake word required for next command.")

    def continuous_command_capture(self):
        """Continuously capture commands in conversation mode"""
        try:
            with sr.Microphone(sample_rate=32000) as source:
                while self.conversation_mode and not self.stop_listening_event.is_set():
                    print("\nListening for next command...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

                    try:
                        audio = self.recognizer.listen(
                            source,
                            timeout=5.0,
                            phrase_time_limit=self.command_timeout
                        )

                        if hasattr(self, 'loop'):
                            asyncio.run_coroutine_threadsafe(
                                self.audio_queue.put(audio),
                                self.loop
                            )
                            self.last_interaction = time.time()

                    except sr.WaitTimeoutError:
                        continue

        except Exception as e:
            print(f"Error in continuous capture: {e}")
            self.exit_conversation_mode()

    def porcupine_audio_callback(self, in_data, frame_count, time_info, status):
        """Process audio chunk with Porcupine"""
        if self.stop_listening_event.is_set():
            return (None, pyaudio.paComplete)

        pcm = struct.unpack_from("h" * self.porcupine.frame_length, in_data)

        # Check for wake word only if not in conversation mode
        if not self.conversation_mode:
            keyword_idx = self.porcupine.process(pcm)
            if keyword_idx >= 0 and not self.listening_for_command:
                print("\nWake word detected! Listening for command...")
                self.listening_for_command = True
                threading.Thread(target=self.start_command_capture).start()

        return (in_data, pyaudio.paContinue)

    def start_command_capture(self):
        """Capture command after wake word detection with improved settings"""
        try:
            if hasattr(self, 'wake_stream'):
                self.wake_stream.stop_stream()

            with sr.Microphone(sample_rate=32000) as source:
                print("\nListening for command...")
                # Shorter ambient noise adjustment
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)

                # Temporarily adjust energy threshold for this capture
                original_threshold = self.recognizer.energy_threshold
                self.recognizer.energy_threshold = max(original_threshold * 0.8, 200)

                try:
                    audio = self.recognizer.listen(
                        source,
                        timeout=3.0,  # Reduced timeout for faster response
                        phrase_time_limit=self.command_timeout,
                        snowboy_configuration=None  # Disable snowboy detection if present
                    )

                    if hasattr(self, 'loop'):
                        asyncio.run_coroutine_threadsafe(
                            self.audio_queue.put(audio),
                            self.loop
                        )
                except sr.WaitTimeoutError:
                    print("\nNo command detected. Ready for wake word...")
                finally:
                    # Restore original energy threshold
                    self.recognizer.energy_threshold = original_threshold

        except Exception as e:
            print(f"Error capturing command: {e}")
        finally:
            if hasattr(self, 'wake_stream'):
                self.wake_stream.start_stream()
            self.listening_for_command = False

    def continuous_command_capture(self):
        """Continuously capture commands in conversation mode with improved settings"""
        try:
            with sr.Microphone(sample_rate=32000) as source:
                while self.conversation_mode and not self.stop_listening_event.is_set():
                    print("\nListening for next command...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.2)

                    # Temporarily lower energy threshold for better sensitivity
                    original_threshold = self.recognizer.energy_threshold
                    self.recognizer.energy_threshold = max(original_threshold * 0.8, 200)

                    try:
                        audio = self.recognizer.listen(
                            source,
                            timeout=3.0,
                            phrase_time_limit=self.command_timeout
                        )

                        if hasattr(self, 'loop'):
                            asyncio.run_coroutine_threadsafe(
                                self.audio_queue.put(audio),
                                self.loop
                            )
                            self.last_interaction = time.time()

                    except sr.WaitTimeoutError:
                        continue
                    finally:
                        # Restore original energy threshold
                        self.recognizer.energy_threshold = original_threshold

        except Exception as e:
            print(f"Error in continuous capture: {e}")
            self.exit_conversation_mode()

    async def process_audio(self):
        """Process commands from the queue"""
        while not self.stop_listening_event.is_set():
            try:
                if not self.audio_queue.empty():
                    audio = await self.audio_queue.get()
                    transcript = self.transcribe_with_whisper(audio)

                    if transcript:
                        print(f"\nCommand: {transcript}")

                        # Check for conversation mode commands
                        lower_transcript = transcript.lower()
                        if "enter conversation" in lower_transcript:
                            self.enter_conversation_mode()
                            continue
                        elif "exit conversation" in lower_transcript and self.conversation_mode:
                            self.exit_conversation_mode()
                            continue

                        try:
                            result = await self.process_command(transcript)
                            print(f"\nCommand result: {result}")
                        except Exception as e:
                            print(f"\nError processing command: {e}")

                    if not self.conversation_mode:
                        print("\nReady for wake word...")

                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"\nError in audio processing: {e}")
                self.listening_for_command = False

    async def start_listening(self):
        """Modified to check for text mode command"""
        print("Starting up the voice assistant...")
        self.loop = asyncio.get_running_loop()

        if not self.text_mode:
            self.wake_stream = self.pa.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length,
                stream_callback=self.porcupine_audio_callback
            )

            self.wake_stream.start_stream()
            print("Ready! Say 'Hey Ginger' to start or 'enter conversation' for conversation mode...")

            try:
                await self.process_audio()
            except KeyboardInterrupt:
                print("\nStopping voice assistant...")
            finally:
                self.wake_stream.stop_stream()
                self.wake_stream.close()
                self.porcupine.delete()
                self.pa.terminate()
        else:
            await self.start_text_mode()

    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'porcupine'):
            self.porcupine.delete()
        if hasattr(self, 'pa'):
            self.pa.terminate()