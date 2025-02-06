import asyncio
import time
from typing import List, Tuple, Dict, Any, Optional
from weatherAgent import WeatherAgent
from responseModule import HighPerformanceResponseModule
import openai
from dataclasses import dataclass
import json
from functools import lru_cache
import hashlib


@dataclass
class SuggestedAction:
    agent_name: str
    function_name: str
    parameters: Dict[str, Any]
    suggestion_context: str


@dataclass
class AgentCommand:
    agent_name: str
    function_name: str
    parameters: Dict[str, Any]


class CommandCache:
    def __init__(self, max_size=1000):
        self.cache = {}
        self.max_size = max_size

    def _generate_key(self, command: str, recent_context: str) -> str:
        combined = f"{command.lower().strip()}:{recent_context}"
        return hashlib.md5(combined.encode()).hexdigest()

    def get(self, command: str, recent_context: str) -> Dict:
        key = self._generate_key(command, recent_context)
        return self.cache.get(key)

    def set(self, command: str, recent_context: str, value: Dict):
        key = self._generate_key(command, recent_context)
        if len(self.cache) >= self.max_size:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = value


class CommandProcessor:
    def __init__(self, openai_api_key: str, agents: List[Tuple[str, str, List[Dict[str, Any]]]],
                 personality: str = "Friendly", mood: str = "Happy"):
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.agents = agents
        self.agent_instances = {}
        self.response_module = HighPerformanceResponseModule(
            personality=personality,
            mood=mood,
            openai_api_key=openai_api_key
        )
        self.conversation_history = []
        self.command_cache = CommandCache()
        self.suggestion_cache = {}
        self.pending_suggestion: Optional[SuggestedAction] = None
        self.last_suggestion_time = 0
        self.suggestion_cooldown = 30  # seconds
        self._initialize_agents()

    async def process_command(self, command: str) -> str:
        """Process command with improved context flow and suggestion handling."""
        print(f"\nProcessing command: {command}")
        self.conversation_history.append(("user", command))

        try:
            # Check if this is a confirmation of a pending suggestion
            if self.pending_suggestion and await self._is_confirmation(command):
                return await self._execute_suggested_action()

            # Regular command processing flow
            command_context = await self._extract_command_context(command)
            if not command_context:
                return "Could not understand command"

            agent_command = await self._create_agent_command(command_context)
            if not agent_command:
                return "Could not create agent command"

            execution_result = await self._execute_agent_command(agent_command, command_context)
            response = await self._generate_contextual_response(command, command_context, execution_result)

            return response

        except Exception as e:
            error_message = f"Error processing command: {str(e)}"
            print(f"\nError: {error_message}")
            self.conversation_history.append(("system", error_message))
            return error_message

    async def _is_confirmation(self, command: str) -> bool:
        """Cost-optimized confirmation check."""
        if not self.pending_suggestion:
            return False

        # First try simple keyword matching to avoid API call
        positive_keywords = {'yes', 'sure', 'okay', 'ok', 'yep', 'yeah', 'go ahead', 'sounds good', 'awesome'}
        if any(keyword in command.lower() for keyword in positive_keywords):
            return True

        # Only use GPT API for ambiguous cases
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Determine if this is a confirmation. Return only 'yes' or 'no'."},
                    {"role": "user", "content": f"Is this confirming or agreeing: {command}"}
                ],
                temperature=0.3,
                max_tokens=5  # Minimal tokens needed
            )
            return "yes" in response.choices[0].message.content.lower()
        except Exception as e:
            print(f"Error checking confirmation: {e}")
            return False

    async def _execute_suggested_action(self) -> str:
        """Execute a previously suggested action with explicit tracking."""
        if not self.pending_suggestion:
            return "No pending suggestion to execute"

        try:
            print(f"\nExecuting suggested action: {self.pending_suggestion}")

            # Create command with exact parameters from suggestion
            agent_command = AgentCommand(
                agent_name=self.pending_suggestion.agent_name,
                function_name=self.pending_suggestion.function_name,
                parameters=self.pending_suggestion.parameters
            )

            # Add suggestion context to execution
            execution_context = {
                "suggestion_execution": True,
                "original_suggestion": self.pending_suggestion.suggestion_context,
                "exact_parameters": self.pending_suggestion.parameters
            }

            execution_result = await self._execute_agent_command(
                agent_command,
                execution_context
            )

            # Store suggestion before clearing it
            executed_suggestion = self.pending_suggestion
            self.pending_suggestion = None

            # Generate response with explicit reference to executed suggestion
            response = await self._generate_contextual_response(
                f"Executing suggested action: {executed_suggestion.suggestion_context}",
                execution_context,
                execution_result
            )

            return response

        except Exception as e:
            self.pending_suggestion = None
            return f"Error executing suggested action: {str(e)}"

    async def _validate_and_refine_command(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and refines command parameters using conversation context."""
        print("Validating Data")
        try:
            agent = next((a for a in self.agents if a[0] == command_data["agent_name"]), None)
            if not agent:
                return command_data

            func_def = next(
                (cmd for cmd in agent[2]
                 if isinstance(cmd, dict) and cmd["name"] == command_data["function_name"]),
                None
            )
            if not func_def:
                return command_data

            recent_messages = self.conversation_history[-5:]
            context_text = "\n".join([f"{role}: {content}" for role, content in recent_messages])

            param_info = {}
            if func_def and "parameters" in func_def:
                params_spec = func_def["parameters"]
                if isinstance(params_spec, dict):
                    for param_name, param_spec in params_spec.items():
                        if isinstance(param_spec, dict):
                            param_info[param_name] = {
                                "type": param_spec.get("type", "string"),
                                "description": param_spec.get("description", ""),
                                "required": param_spec.get("required", True),
                                "current_value": command_data["parameters"].get(param_name)
                            }
                            print(param_info[param_name])
                        else:
                            param_info[param_name] = {
                                "type": "string",
                                "description": str(param_spec),
                                "required": True,
                                "current_value": command_data["parameters"].get(param_name)
                            }
                            print(param_info[param_name])
                            print(command_data["parameters"])
                elif isinstance(params_spec, list):
                    for param_name in params_spec:
                        param_info[param_name] = {
                            "type": "string",
                            "description": f"Parameter: {param_name}",
                            "required": True,
                            "current_value": command_data["parameters"].get(param_name)
                        }

            validation_prompt = f"""Given the following conversation context and parameter requirements, validate and refine the command parameters.

Recent Conversation:
{context_text}

Command: {command_data['agent_name']}.{command_data['function_name']}

Parameter Requirements:
{json.dumps(param_info, indent=2)}

Current Parameter Values:
{json.dumps(command_data['parameters'], indent=2)}

Return only a JSON object with the refined parameters."""

            try:
                print("Validating Now")
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system",
                         "content": "You are a parameter validation assistant. Return only valid JSON."},
                        {"role": "user", "content": validation_prompt}
                    ],
                    temperature=0.3
                )
                refined_params = json.loads(response.choices[0].message.content)
            except Exception:
                print("\nFallback to simpler validation...")
                refined_params = command_data["parameters"]

            command_data["parameters"] = refined_params
            return command_data

        except Exception as e:
            print(f"Error in parameter validation: {e}")
            return command_data

    async def _should_suggest_alternative(self, command: str, execution_result: Dict[str, Any],
                                          recent_history: List[Tuple[str, str]]) -> bool:
        """Cost-optimized suggestion check."""
        current_time = time.time()
        if current_time - self.last_suggestion_time < self.suggestion_cooldown:
            return False

        # Quick checks first to avoid API call
        if "error" not in execution_result and "suggestion" not in execution_result:
            return False

        try:
            history_text = "\n".join(
                [f"{role}: {msg}" for role, msg in recent_history[-3:]])  # Only use last 3 messages

            prompt = f"""Given the context, should we suggest an alternative action? Consider:
1. Was the original command unsuccessful?
2. Was there a clear alternative mentioned?
3. Did the user express interest in an alternative?

Command: {command}
Result: {json.dumps(execution_result.get('error', ''), indent=2)}
History: {history_text}

Return only 'yes' or 'no'."""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system",
                           "content": "You determine if alternatives should be suggested. Return only 'yes' or 'no'."},
                          {"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=5
            )

            should_suggest = "yes" in response.choices[0].message.content.lower()
            if should_suggest:
                self.last_suggestion_time = current_time
            return should_suggest

        except Exception as e:
            print(f"Error in should_suggest_alternative: {e}")
            return False

    async def _generate_suggestion(self, command: str, execution_result: Dict[str, Any],
                                   recent_history: List[Tuple[str, str]]) -> Optional[SuggestedAction]:
        """Generate a suggestion with caching and explicit parameter tracking."""
        try:
            # Check cache first
            cache_key = f"{command}:{execution_result.get('error', '')}"
            if cache_key in self.suggestion_cache:
                return self.suggestion_cache[cache_key]

            history_text = "\n".join([f"{role}: {msg}" for role, msg in recent_history[-3:]])

            agent_descriptions = []
            for name, desc, commands in self.agents:
                if isinstance(commands[0], dict):
                    command_details = [f"{cmd['name']}({','.join(cmd['parameters'].keys())})"
                                       for cmd in commands]
                    agent_descriptions.append(f"{name}: {', '.join(command_details)}")
                else:
                    agent_descriptions.append(f"{name}: {', '.join(commands)}")

            prompt = f"""Given the context, suggest an alternative action.
Important: When suggesting songs or media, be EXACT with artist names and titles.

Available Agents:
{json.dumps(agent_descriptions, indent=2)}

Command: {command}
Result: {json.dumps(execution_result, indent=2)}
History:
{history_text}

Return a JSON object with:
1. agent_name: name of the agent
2. function_name: name of the function
3. parameters: dictionary with EXACT values (e.g., precise song title and artist)
4. suggestion_context: natural language description that includes the EXACT title and artist

Example for music:
{{
    "agent_name": "music",
    "function_name": "play",
    "parameters": {{
        "song_name": "Yesterday",
        "artist": "The Beatles"
    }},
    "suggestion_context": "Let's play 'Yesterday' by The Beatles"
}}"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Using 3.5 instead of 4 for cost optimization
                messages=[
                    {"role": "system", "content": "You suggest alternative actions. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )

            suggestion_data = json.loads(response.choices[0].message.content)
            suggestion = SuggestedAction(
                agent_name=suggestion_data["agent_name"],
                function_name=suggestion_data["function_name"],
                parameters=suggestion_data["parameters"],
                suggestion_context=suggestion_data["suggestion_context"]
            )

            self.suggestion_cache[cache_key] = suggestion
            return suggestion

        except Exception as e:
            print(f"Error generating suggestion: {e}")
            return None

    async def _extract_command_context(self, command: str) -> Dict[str, Any]:
        """Extract context from command and conversation history."""
        try:
            recent_context = self._get_recent_context()

            # Try cache first
            cached_result = self.command_cache.get(command, recent_context)
            if cached_result:
                return cached_result

            # Create context-aware prompt
            prompt = self._create_agent_prompt(command)

            # Parse with GPT
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system",
                     "content": "Parse natural language commands into structured format with context."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )

            # Parse command data
            command_data = json.loads(response.choices[0].message.content)

            # Enhance with emotional and contextual information
            if hasattr(self.response_module, 'detect_emotion'):
                emotion, intensity = self.response_module.detect_emotion(command)
                command_data['emotional_context'] = {
                    'emotion': emotion,
                    'intensity': intensity
                }

            # Add conversation context
            command_data['conversation_context'] = {
                'recent_history': self.conversation_history[-5:],
                'topics': self.response_module.context_memory['topics'][-3:] if hasattr(self.response_module,
                                                                                        'context_memory') else []
            }

            # Cache the result
            self.command_cache.set(command, recent_context, command_data)

            return command_data

        except Exception as e:
            print(f"Error extracting context: {e}")
            return None

    async def _create_agent_command(self, command_context: Dict[str, Any]) -> Optional[AgentCommand]:
        """Create agent command with context."""
        try:
            # Validate and refine command with context
            refined_command = await self._validate_and_refine_command(command_context)

            # Create agent command
            return AgentCommand(
                agent_name=refined_command["agent_name"],
                function_name=refined_command["function_name"],
                parameters=refined_command["parameters"]
            )

        except Exception as e:
            print(f"Error creating agent command: {e}")
            return None

    async def _execute_agent_command(self, agent_command: AgentCommand, command_context: Dict[str, Any]) -> Dict[
        str, Any]:
        """Execute agent command and append result to conversation history."""
        try:
            agent = self.agent_instances.get(agent_command.agent_name)
            if not agent:
                error_msg = f"Agent '{agent_command.agent_name}' not found"
                system_msg = {
                    "status": "error",
                    "agent": agent_command.agent_name,
                    "function": agent_command.function_name,
                    "parameters": agent_command.parameters,
                    "error": error_msg,
                    "context": command_context
                }
                self.conversation_history.append(("system", json.dumps(system_msg, indent=2)))
                return {"error": error_msg, "context": command_context}

            # Get the agent function
            func = getattr(agent, agent_command.function_name, None)
            if not func:
                error_msg = f"Function '{agent_command.function_name}' not found"
                system_msg = {
                    "status": "error",
                    "agent": agent_command.agent_name,
                    "function": agent_command.function_name,
                    "parameters": agent_command.parameters,
                    "error": error_msg,
                    "context": command_context
                }
                self.conversation_history.append(("system", json.dumps(system_msg, indent=2)))
                return {"error": error_msg, "context": command_context}

            # Execute function with context
            if asyncio.iscoroutinefunction(func):
                result = await func(**agent_command.parameters)
            else:
                result = func(**agent_command.parameters)

            # Create and append system message for successful execution
            system_msg = {
                "status": "success",
                "agent": agent_command.agent_name,
                "function": agent_command.function_name,
                "parameters": agent_command.parameters,
                "result": result,
                "context": command_context
            }
            self.conversation_history.append(("system", json.dumps(system_msg, indent=2)))

            return {"result": result, "context": command_context}

        except Exception as e:
            error_msg = str(e)
            system_msg = {
                "status": "error",
                "agent": agent_command.agent_name,
                "function": agent_command.function_name,
                "parameters": agent_command.parameters,
                "error": error_msg,
                "context": command_context
            }
            self.conversation_history.append(("system", json.dumps(system_msg, indent=2)))
            return {"error": error_msg, "context": command_context}

    def _get_recent_context(self, num_messages=5) -> str:
        """Get recent context in a compressed format"""
        recent = self.conversation_history[-num_messages:]
        return " | ".join(f"{role}:{content}" for role, content in recent)

    @lru_cache(maxsize=100)
    def _extract_context_from_history(self, missing_param: str, command_signature: str) -> str:
        """Extract context with caching and optimized prompt"""
        recent_history = self.conversation_history[-5:]  # Reduced from 10 to 5

        # Create a minimal context string
        history_text = "\n".join(f"{role}: {content}" for role, content in recent_history)

        try:
            # Use GPT-3.5 first for simple context extraction
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system",
                     "content": "Extract the most recent value for the missing parameter from the conversation. Return only the value or 'null' if not found."},
                    {"role": "user", "content": f"Parameter: {missing_param}\nHistory:\n{history_text}"}
                ],
                temperature=0.3
            )

            value = response.choices[0].message.content.strip()

            # If GPT-3.5 couldn't find it, try GPT-4 with more context
            if value.lower() == "null":
                response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system",
                         "content": "Extract the most recent value for the missing parameter from the conversation. Return only the value or 'null' if not found."},
                        {"role": "user", "content": f"Parameter: {missing_param}\nHistory:\n{history_text}"}
                    ],
                    temperature=0.3
                )
                value = response.choices[0].message.content.strip()

            return None if value.lower() == "null" else value

        except Exception as e:
            print(f"Error extracting context: {e}")
            return None

    def _create_agent_prompt(self, command: str) -> str:
        """Create an optimized prompt for command parsing"""
        # Build minimal agent descriptions
        agent_descriptions = []
        for name, desc, commands in self.agents:
            if isinstance(commands[0], dict):
                command_details = [
                    f"{cmd['name']}({','.join(cmd['parameters'].keys())})"
                    for cmd in commands
                ]
                agent_descriptions.append(f"{name}: {', '.join(command_details)}")
            else:
                agent_descriptions.append(f"{name}: {', '.join(commands)}")

        # Include minimal context
        recent_context = " | ".join([
            f"{content}" for _, content in self.conversation_history[-3:]
        ])

        return f"""Agents: {' | '.join(agent_descriptions)}
Context: {recent_context}
Command: "{command}"

Return JSON:
{{"agent_name": "X", "function_name": "Y", "parameters": {{...}}}}
Or for chat: {{"agent_name": "conversation", "function_name": "chat", "parameters": {{"message": "Z"}}}}"""

    async def _generate_contextual_response(self, original_command: str,
                                      command_context: Dict[str, Any],
                                      execution_result: Dict[str, Any]) -> str:
        """Generate response with suggestion capability."""
        try:
            data = []
            if "result" in execution_result:
                data.append(("assistant", execution_result["result"]))
                if hasattr(self.response_module, 'context_memory'):
                    self.response_module.context_memory.update({
                        'command_context': command_context
                    })
            else:
                data.append(("system", execution_result["error"]))

            should_suggest = await self._should_suggest_alternative(
                original_command,
                execution_result,
                self.conversation_history[-5:]
            )

            if should_suggest:
                suggestion = await self._generate_suggestion(
                    original_command,
                    execution_result,
                    self.conversation_history[-5:]
                )
                if suggestion:
                    self.pending_suggestion = suggestion
                    data.append(("system", suggestion.suggestion_context))

            response_text, speech_task = await self.response_module.process_response(
                self.conversation_history,
                data
            )

            self.conversation_history.append(("assistant", response_text))

            if speech_task:
                await speech_task

            return response_text

        except Exception as e:
            return f"Error generating response: {str(e)}"

    def _initialize_agents(self):
        """Initialize agent instances"""
        print("\nInitializing agents...")
        for agent_name, _, _ in self.agents:
            if agent_name == "weather":
                self.agent_instances[agent_name] = WeatherAgent()
                print(f"Initialized {agent_name} agent")

    def set_response_mode(self, mode: str):
        """Set the response mode for the response module"""
        self.response_module.set_response_mode(mode)


def integrate_with_voice_assistant(voice_assistant, processor):
    """Integrate command processor with voice assistant"""

    async def process_voice_command(command: str):
        print(f"\nProcessing voice command: {command}")
        processor.set_response_mode(
            "text_to_speech" if voice_assistant.text_to_speech_mode else
            "text" if voice_assistant.text_mode else "voice"
        )
        return await processor.process_command(command)

    voice_assistant.process_command = process_voice_command
    voice_assistant.response_module = processor.response_module