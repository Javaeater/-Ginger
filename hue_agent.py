import requests
from typing import Dict, Optional, Union, List
import colorsys
import json
from openai import OpenAI

class HueAgent:
    def __init__(self, host: str, token: str, openai_api_key: str, port: int = 8123):
        """Initialize the Hue light control agent."""
        self.base_url = f"http://{host}:{port}/api"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # Predefined moods/scenes with their colors and brightness
        self.moods = {
            "relax": {"color_name": "peach", "brightness": 40, "description": "Warm, cozy lighting for relaxation"},
            "focus": {"color_name": "skyBlue", "brightness": 100, "description": "Bright, cool light for concentration"},
            "energize": {"color_name": "white", "brightness": 100, "description": "Bright daylight for energy"},
            "reading": {"color_name": "cream", "brightness": 80, "description": "Comfortable lighting for reading"},
            "movie": {"color_name": "coral", "brightness": 20, "description": "Dim, warm light for watching movies"},
            "sunset": {"color_name": "orange", "brightness": 60, "description": "Warm orange glow like a sunset"},
            "ocean": {"color_name": "blue", "brightness": 70, "description": "Calming blue ocean vibes"},
            "forest": {"color_name": "green", "brightness": 60, "description": "Natural green forest ambient"},
        }
        
        # Color name to RGB mapping
        self.colors = {
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "yellow": (255, 255, 0),
            "purple": (255, 0, 255),
            "cyan": (0, 255, 255),
            "orange": (255, 165, 0),
            "pink": (255, 192, 203),
            "coral": (255, 127, 80),
            "salmon": (250, 128, 114),
            "peach": (255, 218, 185),
            "gold": (255, 215, 0),
            "bronze": (205, 127, 50),
            "copper": (184, 115, 51),
            "rust": (183, 65, 14),
            "brown": (165, 42, 42),
            "skyblue": (135, 206, 235),
            "steelblue": (70, 130, 180),
            "navy": (0, 0, 128),
            "turquoise": (64, 224, 208),
            "teal": (0, 128, 128),
            "aquamarine": (127, 255, 212),
            "mintbreen": (152, 255, 152),
            "seabreen": (46, 139, 87),
            "khaki": (240, 230, 140),
            "beige": (245, 245, 220),
            "tan": (210, 180, 140),
            "olive": (128, 128, 0),
            "sage": (176, 208, 176),
            "forest": (34, 139, 34),
            "sienna": (160, 82, 45),
            "chocolate": (210, 105, 30),
            "white": (255, 255, 255),
            "silver": (192, 192, 192),
            "gray": (128, 128, 128),
            "charcoal": (54, 69, 79),
            "black": (0, 0, 0),
            "lavender": (230, 230, 250),
            "rose": (255, 228, 225),
            "mint": (245, 255, 250),
            "powder": (176, 224, 230),
            "cream": (255, 253, 208)
        }
        self._cache_lights()

    def _cache_lights(self) -> None:
        """Cache available lights and their states"""
        response = requests.get(
            f"{self.base_url}/states",
            headers=self.headers
        )
        response.raise_for_status()
        
        self.lights = {}
        for entity in response.json():
            if entity["entity_id"].startswith("light."):
                name = entity["entity_id"][6:].replace('_', ' ')
                self.lights[name] = entity["entity_id"]

    def _find_light(self, room: str) -> Union[str, List[str], None]:
        """Find light entity IDs by room name. Returns all lights if room is 'all'."""
        room = room.lower().strip()
        
        if room == 'all':
            return list(self.lights.values())
            
        for light_name, light_id in self.lights.items():
            if room in light_name.lower():
                return light_id
        return None

    def _generate_mood(self, mood_name: str) -> Dict:
        """Generate a new mood setting using GPT"""
        print(f"\nGenerating new mood: {mood_name}")
        
        # Create an example format to guide the response
        example_format = {
            "color_name": "blue",
            "brightness": 70,
            "description": "Example mood description"
        }
        
        prompt = f"""Create a lighting mood setting called "{mood_name}".
        Available colors are: {', '.join(sorted(self.colors.keys()))}
        
        Follow these rules EXACTLY:
        1. Choose a color from the available colors list that best matches the mood
        2. Set an appropriate brightness (0-100) for the mood
        3. Write a brief description of what the mood feels like
        4. Return ONLY a JSON object matching this exact format:
        {json.dumps(example_format, indent=2)}
        
        The color_name MUST be one from the available colors list. DO NOT use any other colors."""

        try:
            print("Sending request to GPT...")
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",  # Using 3.5-turbo for faster responses
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a lighting design expert. You must respond with ONLY a valid JSON object."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.7  # Add some creativity while keeping responses focused
            )
            
            response_text = response.choices[0].message.content.strip()
            print(f"GPT Response: {response_text}")
            
            # Extract JSON
            try:
                # Find the first { and last } to extract JSON
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start != -1 and end != 0:
                    json_str = response_text[start:end]
                    mood_data = json.loads(json_str)
                else:
                    raise ValueError("No JSON object found in response")
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {str(e)}")
                raise ValueError("Failed to parse GPT response as JSON")

            # Validate the response
            if not isinstance(mood_data, dict):
                raise ValueError("GPT response is not a dictionary")

            # Check required fields
            required_fields = ["color_name", "brightness", "description"]
            missing_fields = [field for field in required_fields if field not in mood_data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")

            # Validate color name
            color_name = mood_data["color_name"].lower()
            if color_name not in self.colors:
                raise ValueError(f"Invalid color name: {color_name}")

            # Validate brightness
            brightness = mood_data["brightness"]
            if not isinstance(brightness, (int, float)) or not 0 <= brightness <= 100:
                raise ValueError(f"Invalid brightness value: {brightness}")

            # Create the validated mood
            validated_mood = {
                "color_name": color_name,
                "brightness": float(brightness),
                "description": str(mood_data["description"])
            }

            # Add to our moods dictionary
            self.moods[mood_name] = validated_mood
            
            print(f"Successfully created mood: {validated_mood}")
            return validated_mood
            
        except Exception as e:
            print(f"Error generating mood: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise ValueError(f"Failed to generate mood: {str(e)}")

    def control_light(self, room: str, state: str) -> str:
        """Basic light control - on/off"""
        room = room.lower().strip()
        state = state.lower().strip()
        
        if state not in ['on', 'off']:
            return f"Invalid state '{state}'. Use 'on' or 'off'."
        
        entity_ids = self._find_light(room)
        if not entity_ids:
            return f"No light found for room '{room}'"
        
        try:
            service = "turn_on" if state == "on" else "turn_off"
            if isinstance(entity_ids, list):  # For 'all' lights
                response = requests.post(
                    f"{self.base_url}/services/light/{service}",
                    headers=self.headers,
                    json={"entity_id": entity_ids}
                )
                response.raise_for_status()
                return f"Turned {state} all lights"
            else:  # For single light
                response = requests.post(
                    f"{self.base_url}/services/light/{service}",
                    headers=self.headers,
                    json={"entity_id": entity_ids}
                )
                response.raise_for_status()
                return f"Turned {state} the {room} light"
            
        except requests.exceptions.RequestException as e:
            return f"Error controlling light(s): {str(e)}"

    def set_color(self, room: str, color: str) -> str:
        """Set light color by name"""
        if color.lower() not in self.colors:
            return f"Unknown color '{color}'. Available colors: {', '.join(self.colors.keys())}"
        
        entity_ids = self._find_light(room)
        if not entity_ids:
            return f"No light found for room '{room}'"
        
        try:
            rgb = self.colors[color.lower()]
            print(f"Setting color for {'all lights' if isinstance(entity_ids, list) else room}")
            print(f"Entity IDs: {entity_ids}")
            print(f"RGB Color: {rgb}")
            
            data = {
                "entity_id": entity_ids,
                "rgb_color": list(rgb)
            }
            print(f"Request data: {json.dumps(data, indent=2)}")
            
            try:
                response = requests.post(
                    f"{self.base_url}/services/light/turn_on",
                    headers=self.headers,
                    json=data
                )
                print(f"Response status code: {response.status_code}")
                print(f"Response content: {response.text}")
                response.raise_for_status()
                
                if isinstance(entity_ids, list):
                    return f"Set all lights to {color}"
                else:
                    return f"Set {room} light to {color}"
                    
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {str(e)}")
                if hasattr(e.response, 'text'):
                    print(f"Error response: {e.response.text}")
                raise
                
        except Exception as e:
            error_msg = f"Error setting color: {str(e)}"
            print(error_msg)
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return error_msg

    def set_brightness(self, room: str, brightness: Union[int, str]) -> str:
        """Set light brightness (0-100)"""
        try:
            # Convert brightness to integer if it's a string
            if isinstance(brightness, str):
                brightness = int(brightness.rstrip('%'))
            
            if not 0 <= brightness <= 100:
                return "Brightness must be between 0 and 100"
            
            entity_ids = self._find_light(room)
            if not entity_ids:
                return f"No light found for room '{room}'"
            
            # Convert 0-100 to 0-255 range
            brightness_255 = int(brightness * 2.55)
            
            if isinstance(entity_ids, list):  # For 'all' lights
                response = requests.post(
                    f"{self.base_url}/services/light/turn_on",
                    headers=self.headers,
                    json={
                        "entity_id": entity_ids,
                        "brightness": brightness_255
                    }
                )
                response.raise_for_status()
                return f"Set all lights brightness to {brightness}%"
            else:  # For single light
                response = requests.post(
                    f"{self.base_url}/services/light/turn_on",
                    headers=self.headers,
                    json={
                        "entity_id": entity_ids,
                        "brightness": brightness_255
                    }
                )
                response.raise_for_status()
                return f"Set {room} light brightness to {brightness}%"
            
        except ValueError:
            return "Invalid brightness value"
        except requests.exceptions.RequestException as e:
            return f"Error setting brightness: {str(e)}"

    def set_mood(self, room: str, mood: str) -> str:
        """Set predefined mood lighting or generate a new one"""
        try:
            mood = mood.lower()
            print(f"\nSetting mood: {mood} for {'all lights' if room.lower() == 'all' else room}")
            
            # Generate new mood if it doesn't exist
            if mood not in self.moods:
                try:
                    new_mood = self._generate_mood(mood)
                    result_msg = f"Created new mood '{mood}': {new_mood['description']}\n"
                except ValueError as e:
                    print(f"Failed to generate mood: {str(e)}")
                    return f"Failed to generate mood: {str(e)}"
            else:
                result_msg = ""
                new_mood = self.moods[mood]
                
            print(f"Mood settings: {json.dumps(new_mood, indent=2)}")
            
            entity_ids = self._find_light(room)
            if not entity_ids:
                return f"No light found for room '{room}'"
                
            print(f"Entity IDs: {entity_ids}")
            
            # Prepare light settings
            data = {
                "entity_id": entity_ids,
                "brightness": int(new_mood["brightness"] * 2.55)
            }
            
            # Add color
            if "color_name" in new_mood:
                rgb = self.colors[new_mood["color_name"]]
                data["rgb_color"] = list(rgb)
                
            print(f"Request data: {json.dumps(data, indent=2)}")
            
            try:
                response = requests.post(
                    f"{self.base_url}/services/light/turn_on",
                    headers=self.headers,
                    json=data
                )
                print(f"Response status code: {response.status_code}")
                print(f"Response content: {response.text}")
                response.raise_for_status()
                
                if isinstance(entity_ids, list):
                    return result_msg + f"Set all lights to {mood} mood"
                else:
                    return result_msg + f"Set {room} light to {mood} mood"
                    
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {str(e)}")
                if hasattr(e.response, 'text'):
                    print(f"Error response: {e.response.text}")
                raise
                
        except Exception as e:
            error_msg = f"Error setting mood: {str(e)}"
            print(error_msg)
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return error_msg

    def get_light_status(self, room: Optional[str] = None) -> str:
        """Get detailed light status"""
        try:
            response = requests.get(
                f"{self.base_url}/states",
                headers=self.headers
            )
            response.raise_for_status()
            
            states = {}
            for entity in response.json():
                if entity["entity_id"].startswith("light."):
                    name = entity["entity_id"][6:].replace('_', ' ')
                    state_info = {
                        "power": entity["state"],
                        "brightness": f"{int(entity['attributes'].get('brightness', 0) / 2.55)}%" if "brightness" in entity["attributes"] else "unknown",
                    }
                    states[name] = state_info
            
            if room and room.lower() != 'all':
                room = room.lower().strip()
                for light_name, state in states.items():
                    if room in light_name.lower():
                        return f"The {light_name} light is {state['power']}, brightness: {state['brightness']}"
                return f"No light found for room '{room}'"
            
            return "\n".join([
                f"{name}: {state['power']}, brightness: {state['brightness']}"
                for name, state in states.items()
            ])
            
        except requests.exceptions.RequestException as e:
            return f"Error getting light status: {str(e)}"