import asyncio
from typing import List, Tuple, Dict, Any
from weatherAgent import WeatherAgent
from responseModule import HighPerformanceResponseModule
import openai
from dataclasses import dataclass
import json
from functools import lru_cache
import hashlib

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
        # Create a unique key based on command and recent context
        combined = f"{command.lower().strip()}:{recent_context}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get(self, command: str, recent_context: str) -> Dict:
        key = self._generate_key(command, recent_context)
        return self.cache.get(key)
    
    def set(self, command: str, recent_context: str, value: Dict):
        key = self._generate_key(command, recent_context)
        if len(self.cache) >= self.max_size:
            # Remove oldest entry if cache is full
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
        self._initialize_agents()


    async def _validate_and_refine_command(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates and refines command parameters using conversation context.
        
        Args:
            command_data: Dictionary containing agent_name, function_name, and parameters
            
        Returns:
            Updated command data with refined parameters
        """
        try:
            # Get agent definition
            agent = next((a for a in self.agents if a[0] == command_data["agent_name"]), None)
            if not agent:
                return command_data
                
            # Get function definition
            func_def = next(
                (cmd for cmd in agent[2] 
                if isinstance(cmd, dict) and cmd["name"] == command_data["function_name"]),
                None
            )
            if not func_def:
                return command_data

            # Get recent conversation context
            recent_messages = self.conversation_history[-5:]  # Last 5 messages
            context_text = "\n".join([
                f"{role}: {content}" for role, content in recent_messages
            ])

            # Handle different parameter specification formats
            param_info = {}
            if func_def and "parameters" in func_def:
                params_spec = func_def["parameters"]
                if isinstance(params_spec, dict):
                    # Handle dictionary format
                    for param_name, param_spec in params_spec.items():
                        if isinstance(param_spec, dict):
                            param_info[param_name] = {
                                "type": param_spec.get("type", "string"),
                                "description": param_spec.get("description", ""),
                                "required": param_spec.get("required", True),
                                "current_value": command_data["parameters"].get(param_name)
                            }
                        else:
                            # Handle simple string type specification
                            param_info[param_name] = {
                                "type": "string",
                                "description": str(param_spec),
                                "required": True,
                                "current_value": command_data["parameters"].get(param_name)
                            }
                elif isinstance(params_spec, list):
                    # Handle list format
                    for param_name in params_spec:
                        param_info[param_name] = {
                            "type": "string",
                            "description": f"Parameter: {param_name}",
                            "required": True,
                            "current_value": command_data["parameters"].get(param_name)
                        }

            # Create a detailed validation prompt
            validation_prompt = f"""Given the following conversation context and parameter requirements, validate and refine the command parameters.

    Recent Conversation:
    {context_text}

    Command: {command_data['agent_name']}.{command_data['function_name']}

    Parameter Requirements:
    {json.dumps(param_info, indent=2)}

    Current Parameter Values:
    {json.dumps(command_data['parameters'], indent=2)}

    For each parameter:
    1. Check if the value matches expected type/format
    2. If value seems like a description/request, convert to specific value
    3. Use conversation context to resolve ambiguous values
    4. For missing or invalid parameters, infer from context if possible

    Examples:
    - If movie="something like vegas", use context to suggest specific movie
    - If location is missing but mentioned in conversation, use that
    - If time="later", find specific time from context

    Return only a JSON object with the refined parameters. Maintain original values if no refinement needed."""

            # Try GPT-3.5 first
            try:
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a parameter validation assistant that uses conversation context to validate and refine command parameters. Return only valid JSON."},
                        {"role": "user", "content": validation_prompt}
                    ],
                    temperature=0.7
                )
                refined_params = json.loads(response.choices[0].message.content)
            except (json.JSONDecodeError, Exception):
                # Fallback to GPT-4 for complex cases
                print("\nFallback to GPT-4 for complex parameter validation...")
                response = self.client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a parameter validation assistant that uses conversation context to validate and refine command parameters. Return only valid JSON."},
                        {"role": "user", "content": validation_prompt}
                    ],
                    temperature=0.7
                )
                refined_params = json.loads(response.choices[0].message.content)

            # Update parameters with refined values
            command_data["parameters"] = refined_params
            
            # Log parameter changes
            original_params = command_data.get("parameters", {})
            changes = {
                k: (original_params.get(k), refined_params.get(k))
                for k in set(original_params) | set(refined_params)
                if original_params.get(k) != refined_params.get(k)
            }
            if changes:
                print("\nParameter refinements made:")
                for param, (old, new) in changes.items():
                    print(f"- {param}: {old} -> {new}")
            
            return command_data
            
        except Exception as e:
            print(f"Error in parameter validation: {e}")
            return command_data  # Return original if validation fails
        
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
                    {"role": "system", "content": "Extract the most recent value for the missing parameter from the conversation. Return only the value or 'null' if not found."},
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
                        {"role": "system", "content": "Extract the most recent value for the missing parameter from the conversation. Return only the value or 'null' if not found."},
                        {"role": "user", "content": f"Parameter: {missing_param}\nHistory:\n{history_text}"}
                    ],
                    temperature=0.3
                )
                value = response.choices[0].message.content.strip()
            
            return None if value.lower() == "null" else value
            
        except Exception as e:
            print(f"Error extracting context: {e}")
            return None

    def _initialize_agents(self):
        """Initialize agent instances"""
        print("\nInitializing agents...")
        for agent_name, _, _ in self.agents:
            if agent_name == "weather":
                self.agent_instances[agent_name] = WeatherAgent()
                print(f"Initialized {agent_name} agent")

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

    def set_response_mode(self, mode: str):
        """Set the response mode for the response module"""
        self.response_module.set_response_mode(mode)

    async def process_command(self, command: str) -> str:
        """Process a natural language command and route it to appropriate agent."""
        print(f"\nProcessing command: {command}")
        self.conversation_history.append(("user", command))

        try:
            data = []  # Initialize data list for responses

            # First try to get command from cache
            recent_context = self._get_recent_context()
            cached_result = self.command_cache.get(command, recent_context)
            
            if cached_result:
                print("\nUsing cached command parsing")
                command_data = cached_result
            else:
                print("\nParsing command with GPT-3.5...")
                # Try GPT-3.5 first for efficiency
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Parse natural language commands into structured format."},
                        {"role": "user", "content": self._create_agent_prompt(command)}
                    ],
                    temperature=0.7
                )

                try:
                    command_data = json.loads(response.choices[0].message.content)
                except json.JSONDecodeError:
                    print("\nFallback to GPT-4 for complex parsing...")
                    response = self.client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": "Parse natural language commands into structured format."},
                            {"role": "user", "content": self._create_agent_prompt(command)}
                        ],
                        temperature=0.7
                    )
                    command_data = json.loads(response.choices[0].message.content)
                
                # Cache the successful parse
                self.command_cache.set(command, recent_context, command_data)

            if not command_data:
                print("\nNo valid command data found")
                data.append(("system", "Could not understand command"))
            else:
                try:
                    
                    if command_data.get("agent_name") == "conversation":
                        print("\nHandling general conversation")
                        data.append(("assistant", "I'm here to help! What can I do for you?"))
                    else:
                        # Look up agent definition
                        agent = next((a for a in self.agents if a[0] == command_data["agent_name"]), None)
                        if agent:
                            # Extract expected parameters
                            expected_params = next(
                                (cmd["parameters"].keys()
                                for cmd in agent[2]
                                if isinstance(cmd, dict) and cmd["name"] == command_data["function_name"]),
                                []
                            )

                            # Fill in missing parameters from context
                            for param in expected_params:
                                if param not in command_data["parameters"] or not command_data["parameters"][param]:
                                    context_value = self._extract_context_from_history(
                                        param,
                                        f"{command_data['agent_name']}:{command_data['function_name']}"
                                    )
                                    if context_value:
                                        command_data["parameters"][param] = context_value
                                            # Validate and refine command parameters
                        if expected_params:
                            command_data = await self._validate_and_refine_command(command_data)
                        # Create agent command once
                        agent_command = AgentCommand(
                            agent_name=command_data["agent_name"],
                            function_name=command_data["function_name"],
                            parameters=command_data["parameters"]
                        )

                        print(f"\nExecuting command for agent: {agent_command.agent_name}")
                        agent = self.agent_instances.get(agent_command.agent_name)

                        if not agent:
                            data.append(("system", f"Agent '{agent_command.agent_name}' not found."))
                        else:
                            func = getattr(agent, agent_command.function_name, None)
                            
                            if not func:
                                data.append(("system", f"Function '{agent_command.function_name}' not found."))
                            else:
                                # Execute function (handle both async and sync)
                                if asyncio.iscoroutinefunction(func):
                                    result = await func(**agent_command.parameters)
                                else:
                                    result = func(**agent_command.parameters)
                                    
                                data.append(("assistant", f"Result: {result}"))

                except Exception as e:
                    print(f"\nError in command processing: {e}")
                    data.append(("system", f"Error: {str(e)}"))

            # Process response once with the collected data
            response_text, speech_task = await self.response_module.process_response(
                self.conversation_history,
                data
            )

            # Update conversation history once
            self.conversation_history.append(("assistant", response_text))

            if speech_task:
                await speech_task

            return response_text

        except Exception as e:
            error_message = f"Error processing command: {str(e)}"
            print(f"\nError: {error_message}")
            self.conversation_history.append(("system", error_message))
            return error_message

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