import asyncio
from typing import List, Tuple, Dict, Any
from weatherAgent import WeatherAgent
from responseModule import HighPerformanceResponseModule
import openai
from dataclasses import dataclass
import json


@dataclass
class AgentCommand:
    agent_name: str
    function_name: str
    parameters: Dict[str, Any]


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
        self._initialize_agents()

    def _extract_context_from_history(self, missing_param: str, current_command: Dict) -> str:
        """Extract context for a missing parameter from conversation history"""
        history_text = "\n".join([f"{role}: {content}" for role, content in self.conversation_history[-5:]])
        
        prompt = f"""
            Given this conversation history:
            {history_text}
            Current command parameters: {json.dumps(current_command)}
            Find the most relevant value for the missing parameter: "{missing_param}"
            Return ONLY the value, no explanation. If no relevant value is found, return null.
            """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a context analyzer that extracts relevant parameter values from conversation history."},
                    {"role": "user", "content": prompt}
                ]
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
        """Create a detailed prompt for command parsing"""
        # Build agent descriptions with parameter details
        agent_descriptions = []
        for name, desc, commands in self.agents:
            if isinstance(commands[0], dict):
                command_details = []
                for cmd in commands:
                    params = "\n          ".join(
                        f"{param}: {desc}"
                        for param, desc in cmd["parameters"].items()
                    )
                    command_details.append(f"""
            Command: {cmd['name']}
            Description: {cmd['description']}
            Parameters:
            {params}""")
                agent_descriptions.append(f"""
    Agent: {name}
    Description: {desc}
    Available Commands:{' '.join(command_details)}""")
            else:
                agent_descriptions.append(f"""
    Agent: {name}
    Description: {desc}
    Commands: {', '.join(commands)}""")

        # Include recent conversation history for context
        history_context = "\n".join([
            f"{role}: {content}"
            for role, content in self.conversation_history[-5:]
        ])

        # Create the prompt
        prompt = f"""Given these agents and their commands:
{' '.join(agent_descriptions)}

Recent conversation history:
{history_context}

Your task is to parse this command: "{command}"

If this is a general conversation or greeting (like "hello", "how are you", etc.), respond with:
{{
    "agent_name": "conversation",
    "function_name": "chat",
    "parameters": {{
        "message": "<the user's message>"
    }}
}}

For agent-specific commands, you must identify one of the exact commands listed above and return a JSON object with this structure:
{{
    "agent_name": "<agent name>",
    "function_name": "<function to call>",
    "parameters": {{
        // parameters matching the command definition exactly
    }}
}}

For the "lights" agent:
- set_mood requires both "room" and "mood" parameters
- control_light requires both "room" and "state" parameters
- set_color requires both "room" and "color" parameters
- set_brightness requires both "room" and "brightness" parameters"""

        return prompt

    def set_response_mode(self, mode: str):
        """Set the response mode for the response module"""
        self.response_module.set_response_mode(mode)

    async def process_command(self, command: str) -> str:
        """Process command and return response"""
        print(f"\nProcessing command: {command}")

        self.conversation_history.append(("user", command))

        try:
            print("\nSending to GPT for parsing...")
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system",
                     "content": "You are a command parser that converts natural language commands into structured agent commands."},
                    {"role": "user", "content": self._create_agent_prompt(command)}
                ],
                temperature=0.7
            )

            parsed_command = response.choices[0].message.content
            print(f"\nParsed command: {parsed_command}")

            data = []

            if parsed_command.lower() == "null":
                print("\nNo matching agent found for command")
                data.append(("system", "Could not understand command"))
            elif "conversation" in parsed_command.lower():
                print("\nHandling general conversation")
                data.append(("assistant", "I'm doing well! How can I help you today?"))
            else:
                try:
                    print("\nParsing command data...")
                    command_data = json.loads(parsed_command)
                    print(f"Command data: {command_data}")

                    # Check for missing parameters and try to fill them from context
                    agent = next((a for a in self.agents if a[0] == command_data["agent_name"]), None)
                    if agent:
                        expected_params = next(
                            (cmd["parameters"].keys()
                             for cmd in agent[2]
                             if isinstance(cmd, dict) and cmd["name"] == command_data["function_name"]),
                            []
                        )

                        for param in expected_params:
                            if param not in command_data["parameters"] or not command_data["parameters"][param]:
                                context_value = self._extract_context_from_history(param, command_data)
                                if context_value:
                                    command_data["parameters"][param] = context_value
                                    print(f"Filled missing parameter {param} with value: {context_value}")

                    agent_command = AgentCommand(
                        agent_name=command_data["agent_name"],
                        function_name=command_data["function_name"],
                        parameters=command_data["parameters"]
                    )

                    print(f"\nLooking for agent: {agent_command.agent_name}")
                    print(f"Available agents: {list(self.agent_instances.keys())}")
                    agent = self.agent_instances.get(agent_command.agent_name)

                    if not agent:
                        print(f"Agent '{agent_command.agent_name}' not found in instances")
                        data.append(("system", f"Agent '{agent_command.agent_name}' not found."))
                    else:
                        print(f"\nFound agent: {type(agent)}")
                        print(f"Looking for function: {agent_command.function_name}")
                        print(f"Available functions: {[f for f in dir(agent) if not f.startswith('_')]}")
                        
                        func = getattr(agent, agent_command.function_name, None)
                        if not func:
                            print(f"Function '{agent_command.function_name}' not found in agent")
                            data.append(("system", f"Function '{agent_command.function_name}' not found."))
                        else:
                            print(f"\nExecuting {agent_command.agent_name}.{agent_command.function_name}")
                            print(f"Parameters: {agent_command.parameters}")
                            if asyncio.iscoroutinefunction(func):
                                print("Executing async function...")
                                result = await func(**agent_command.parameters)
                            else:
                                print("Executing sync function...")
                                result = func(**agent_command.parameters)
                            print(f"Execution result: {result}")
                            data.append(("assistant", f"Result: {result}"))

                except json.JSONDecodeError as e:
                    print(f"\nError parsing command JSON: {e}")
                    data.append(("system", "Error parsing command structure"))
                except Exception as e:
                    print(f"\nError processing command data: {e}")
                    import traceback
                    print(f"Traceback: {traceback.format_exc()}")
                    data.append(("system", f"Error: {str(e)}"))

            # Generate response using response module
            print("\nGenerating response with ResponseModule...")
            response_text, speech_task = await self.response_module.process_response(
                self.conversation_history,
                data
            )

            # Update conversation history
            self.conversation_history.append(("assistant", response_text))

            if speech_task:
                await speech_task

            return response_text

        except Exception as e:
            error_message = f"Error processing command: {str(e)}"
            print(f"\nError: {error_message}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            self.conversation_history.append(("system", error_message))
            return error_message


def integrate_with_voice_assistant(voice_assistant, processor):
    """Integrate command processor with voice assistant"""

    async def process_voice_command(command: str):
        print(f"\nProcessing voice command: {command}")

        # Set response mode based on voice assistant mode
        if voice_assistant.text_to_speech_mode:
            processor.set_response_mode("text_to_speech")
        elif voice_assistant.text_mode:
            processor.set_response_mode("text")
        else:
            processor.set_response_mode("voice")

        return await processor.process_command(command)

    voice_assistant.process_command = process_voice_command
    voice_assistant.response_module = processor.response_module  # Share response module