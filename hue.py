import requests
import json
from typing import Optional

class HomeAssistantHue:
    def __init__(self, host: str, token: str, port: int = 8123):
        """
        Initialize the Home Assistant Hue controller.
        
        Args:
            host: Home Assistant host address (e.g., '192.168.1.100' or 'homeassistant.local')
            token: Long-lived access token from Home Assistant
            port: Home Assistant port (default: 8123)
        """
        self.base_url = f"http://{host}:{port}/api"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    
    def get_lights(self) -> dict:
        """Get all available lights from Home Assistant."""
        response = requests.get(
            f"{self.base_url}/states",
            headers=self.headers
        )
        response.raise_for_status()
        
        # Filter for light entities
        lights = {}
        for entity in response.json():
            if entity["entity_id"].startswith("light."):
                lights[entity["entity_id"]] = entity["state"]
        
        return lights
    
    def control_light(self, entity_id: str, state: bool) -> None:
        """
        Control a specific light.
        
        Args:
            entity_id: The entity ID of the light (e.g., 'light.living_room')
            state: True to turn on, False to turn off
        """
        service = "turn_on" if state else "turn_off"
        
        response = requests.post(
            f"{self.base_url}/services/light/{service}",
            headers=self.headers,
            json={"entity_id": entity_id}
        )
        response.raise_for_status()

def main():
    # Configuration
    HOST = "172.19.200.212"  # Replace with your Home Assistant IP
    TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxYjQ0Yzk2NGRjZGM0NDZmYThiNTNjNWJkYzE0YTAzYyIsImlhdCI6MTczNzQ5OTg1NiwiZXhwIjoyMDUyODU5ODU2fQ.9WOZsQTeEKhx-TA6CBG-AvXETJtDsbP4VMaNHjYaAmw"  # Replace with your token  # Replace with your token
    
    try:
        # Initialize the controller
        hue = HomeAssistantHue(HOST, TOKEN)
        
        # Get all available lights
        lights = hue.get_lights()
        print("\nAvailable lights:")
        for light, state in lights.items():
            print(f"{light}: {state}")
        
        # Example: Control a specific light
        while True:
            print("\nEnter a command (or 'q' to quit)")
            print("Format: <entity_id> <on/off>")
            command = input("> ").strip()
            
            if command.lower() == 'q':
                break
            
            try:
                entity_id, state = command.split()
                if not entity_id.startswith("light."):
                    entity_id = f"light.{entity_id}"
                
                state = state.lower() == "on"
                hue.control_light(entity_id, state)
                print(f"Changed {entity_id} to {'on' if state else 'off'}")
            except ValueError:
                print("Invalid command format. Use: <entity_id> <on/off>")
            except requests.exceptions.RequestException as e:
                print(f"Error controlling light: {e}")
    
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Home Assistant: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")

if __name__ == "__main__":
    main()