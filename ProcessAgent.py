import asyncio
from typing import List, Tuple, Dict, Any
from weatherAgent import WeatherAgent
from responseModule import HighPerformanceResponseModule
import openai
from dataclasses import dataclass
import json
import re

@dataclass
class AgentCommand:
    agent_name: str
    function_name: str
    parameters: Dict[str, Any]

class CommandProcessor:
    def __init__(self, openai_api_key: str, agents: List[Tuple[str, str, List[str]]], 
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

    def _initialize_agents(self):
        """Initialize agent instances"""
        for agent_name, _, _ in self.agents:
            if agent_name == "weather":
                self.agent_instances[agent_name] = WeatherAgent()

    def _extract_context_from_history(self, missing_param: str, current_command: Dict) -> str:
        """
        Extract context for a missing parameter from conversation history
        """
        # Create a prompt for GPT to find relevant context
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

    def _create_agent_prompt(self, command: str) -> str:
        """Create a detailed prompt for command parsing."""
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
        
        return f"""Given these agents and their commands:
    {' '.join(agent_descriptions)}

Recent conversation history:
{history_context}

Your task is to parse this command: "{command}"

Even if the command contains references like "it", "that", or "what we discussed", try to determine the actual command based on the conversation history.

For commands involving lights and moods, if a specific detail isn't given but was mentioned in the conversation history, use that information.

You must identify one of the exact commands listed above and return a JSON object with this structure:
{{
    "agent_name": "<agent name>",
    "function_name": "<function to call>",
    "parameters": {{
        // parameters matching the command definition exactly
    }}
}}

For example:
- "Set the light mood based on what we talked about" → Look in history for context about a specific mood
- "Turn those lights on" → Look in history for which room was last discussed

Return null ONLY if you absolutely cannot determine a valid command and parameters from the context.

For the "lights" agent:
- set_mood requires both "room" and "mood" parameters
- control_light requires both "room" and "state" parameters
- set_color requires both "room" and "color" parameters
- set_brightness requires both "room" and "brightness" parameters
"""

    async def process_command(self, command: str) -> str:
        """Process command and return response"""
        print(f"\nProcessing command in CommandProcessor: {command}")
        
        # Update conversation history
        self.conversation_history.append(("user", command))
        
        try:
            # Parse command with GPT-4
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """You are a command parser that converts natural language commands into structured agent commands.
Your job is to understand user intent, including contextual references to previous conversation, and map them to specific commands.
Always try to extract a valid command - only return null if you absolutely cannot determine the user's intent."""},
                    {"role": "user", "content": self._create_agent_prompt(command)}
                ],
                temperature=0.7  # Add some creativity for context understanding
            )
            
            parsed_command = response.choices[0].message.content
            print(f"\nParsed command: {parsed_command}")
            
            data = []
            
            if parsed_command.lower() == "null":
                print("\nNo matching agent found for command")
                data.append(("system", "Could not understand command"))
            else:
                # Parse the agent command
                try:
                    command_data = json.loads(parsed_command)
                    
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
                    
                    # Get agent and execute command
                    agent = self.agent_instances.get(agent_command.agent_name)
                    if not agent:
                        data.append(("system", f"Agent '{agent_command.agent_name}' not found."))
                    else:
                        func = getattr(agent, agent_command.function_name, None)
                        if not func:
                            data.append(("system", f"Function '{agent_command.function_name}' not found."))
                        else:
                            print(f"\nExecuting {agent_command.agent_name}.{agent_command.function_name}")
                            if asyncio.iscoroutinefunction(func):
                                result = await func(**agent_command.parameters)
                            else:
                                result = func(**agent_command.parameters)
                            data.append(("assistant", f"Result: {result}"))
                            
                except json.JSONDecodeError as e:
                    print(f"\nError parsing command JSON: {e}")
                    data.append(("system", "Error parsing command structure"))
            
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
            self.conversation_history.append(("system", error_message))
            return error_message

def integrate_with_voice_assistant(voice_assistant, processor):
    """Integrate command processor with voice assistant"""
    async def process_voice_command(command: str):
        print(f"\nProcessing voice command: {command}")
        return await processor.process_command(command)
    
    voice_assistant.process_command = process_voice_command