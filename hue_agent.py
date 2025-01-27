import requests
from typing import Dict, Optional, Union, List
import json
from openai import OpenAI
import random

class HueAgent:
    def __init__(self, host: str, token: str, openai_api_key: str, port: int = 8123):
        """Initialize the Home Assistant light control agent."""
        self.base_url = f"http://{host}:{port}/api"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # Predefined moods/scenes with their colors and brightness
        self.moods = {
            "relax": {
                "description": "Warm, cozy lighting for relaxation",
                "palette": ["peach", "coral", "orange", "cream"],
                "brightness_range": (30, 50)
            },
            "focus": {
                "description": "Bright, cool light for concentration",
                "palette": ["skyblue", "white", "powder", "mint"],
                "brightness_range": (80, 100)
            },
            "energize": {
                "description": "Dynamic daylight for energy",
                "palette": ["yellow", "white", "skyblue", "mint"],
                "brightness_range": (90, 100)
            },
            "reading": {
                "description": "Comfortable lighting for reading",
                "palette": ["cream", "white", "peach"],
                "brightness_range": (70, 90)
            },
            "movie": {
                "description": "Dim, atmospheric light for watching movies",
                "palette": ["navy", "purple", "blue", "steelblue"],
                "brightness_range": (10, 30)
            },
            "sunset": {
                "description": "Warm sunset glow",
                "palette": ["orange", "coral", "pink", "gold"],
                "brightness_range": (40, 70)
            },
            "ocean": {
                "description": "Calming ocean vibes",
                "palette": ["blue", "turquoise", "teal", "aquamarine"],
                "brightness_range": (50, 80)
            },
            "forest": {
                "description": "Natural forest ambient",
                "palette": ["forest", "sage", "mint", "olive"],
                "brightness_range": (40, 70)
            }
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
            "mintgreen": (152, 255, 152),
            "seagreen": (46, 139, 87),
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
        """Cache available lights from Home Assistant"""
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
        
        example_format = {
            "description": "Mood description",
            "palette": ["color1", "color2", "color3", "color4"],
            "brightness_range": [40, 80]
        }
        
        prompt = f"""Create a lighting mood setting called "{mood_name}".
        Available colors are: {', '.join(sorted(self.colors.keys()))}
        
        Follow these rules EXACTLY:
        1. Choose 3-4 complementary colors from the available colors list that together create the desired mood
        2. Set an appropriate brightness range (min and max, between 0-100) for the mood
        3. Write a brief description of what the mood feels like
        4. Return ONLY a JSON object matching this exact format:
        {json.dumps(example_format, indent=2)}
        
        All colors MUST be from the available colors list. DO NOT use any other colors."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
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
                temperature=0.7
            )
            
            mood_data = json.loads(response.choices[0].message.content.strip())
            
            # Validate the response
            if not isinstance(mood_data, dict):
                raise ValueError("GPT response is not a dictionary")

            # Validate required fields
            required_fields = ["description", "palette", "brightness_range"]
            missing_fields = [field for field in required_fields if field not in mood_data]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")

            # Validate colors
            palette = [color.lower() for color in mood_data["palette"]]
            invalid_colors = [color for color in palette if color not in self.colors]
            if invalid_colors:
                raise ValueError(f"Invalid colors in palette: {invalid_colors}")

            # Validate brightness range
            brightness_range = mood_data["brightness_range"]
            if not isinstance(brightness_range, list) or len(brightness_range) != 2:
                raise ValueError("Invalid brightness range format")
            if not all(isinstance(b, (int, float)) and 0 <= b <= 100 for b in brightness_range):
                raise ValueError("Invalid brightness values")

            # Create the validated mood
            validated_mood = {
                "description": str(mood_data["description"]),
                "palette": palette,
                "brightness_range": tuple(sorted(brightness_range))
            }

            # Add to our moods dictionary
            self.moods[mood_name] = validated_mood
            return validated_mood
            
        except Exception as e:
            print(f"Error generating mood: {str(e)}")
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
            
            if isinstance(entity_ids, list):
                response = requests.post(
                    f"{self.base_url}/services/light/{service}",
                    headers=self.headers,
                    json={"entity_id": entity_ids}
                )
                response.raise_for_status()
                return f"Turned {state} all lights"
            else:
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
            
            if isinstance(entity_ids, list):
                response = requests.post(
                    f"{self.base_url}/services/light/turn_on",
                    headers=self.headers,
                    json={
                        "entity_id": entity_ids,
                        "rgb_color": list(rgb)
                    }
                )
                response.raise_for_status()
                return f"Set all lights to {color}"
            else:
                response = requests.post(
                    f"{self.base_url}/services/light/turn_on",
                    headers=self.headers,
                    json={
                        "entity_id": entity_ids,
                        "rgb_color": list(rgb)
                    }
                )
                response.raise_for_status()
                return f"Set {room} light to {color}"
                    
        except Exception as e:
            error_msg = f"Error setting color: {str(e)}"
            print(error_msg)
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
            
            if isinstance(entity_ids, list):
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
            else:
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
        """Set mood lighting with different colors for each light"""
        try:
            mood = mood.lower()
            print(f"\nSetting mood: {mood} for {'all lights' if room.lower() == 'all' else room}")
            
            # Generate new mood if it doesn't exist
            if mood not in self.moods:
                try:
                    new_mood = self._generate_mood(mood)
                    result_msg = f"Created new mood '{mood}': {new_mood['description']}\n"
                except ValueError as e:
                    return f"Failed to generate mood: {str(e)}"
            else:
                result_msg = ""
                new_mood = self.moods[mood]
                
            entity_ids = self._find_light(room)
            if not entity_ids:
                return f"No lights found for room '{room}'"

            if not isinstance(entity_ids, list):
                entity_ids = [entity_ids]

            success_messages = []
            for entity_id in entity_ids:
                try:
                    # Randomly select color and brightness from mood's palette and range
                    color = random.choice(new_mood["palette"])
                    brightness = random.randint(
                        int(new_mood["brightness_range"][0]),
                        int(new_mood["brightness_range"][1])
                    )

                    # Set light with random color from palette and brightness
                    data = {
                        "entity_id": entity_id,
                        "rgb_color": list(self.colors[color]),
                        "brightness": int(brightness * 2.55)
                    }
                    
                    response = requests.post(
                        f"{self.base_url}/services/light/turn_on",
                        headers=self.headers,
                        json=data
                    )
                    response.raise_for_status()
                    success_messages.append(f"Set {entity_id.replace('light.', '')} to {color}")

                except requests.exceptions.RequestException as e:
                    print(f"Error setting light {entity_id}: {str(e)}")
                    continue

            return result_msg + " and ".join(success_messages) if success_messages else f"Failed to set mood for any lights"
                
        except Exception as e:
            error_msg = f"Error setting mood: {str(e)}"
            print(error_msg)
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
                        "color": entity["attributes"].get("rgb_color", ["unknown"])[0] if "rgb_color" in entity["attributes"] else "unknown"
                    }
                    states[name] = state_info
            
            if room and room.lower() != 'all':
                room = room.lower().strip()
                for light_name, state in states.items():
                    if room in light_name.lower():
                        return f"The {light_name} light is {state['power']}, brightness: {state['brightness']}, color: {state['color']}"
                return f"No light found for room '{room}'"
            
            return "\n".join([
                f"{name}: {state['power']}, brightness: {state['brightness']}, color: {state['color']}"
                for name, state in states.items()
            ])
            
        except requests.exceptions.RequestException as e:
            return f"Error getting light status: {str(e)}"