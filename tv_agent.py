import requests
from typing import Dict, Optional, Union, List
import time

class TVAgent:
    def __init__(self, host: str, token: str, port: int = 8123):
        # Keep existing initialization code
        self.base_url = f"http://{host}:{port}/api"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.tv_entity = None
        self.keyboard_position = 0  # Add keyboard position tracking
        self._cache_tv_entity()

    def _cache_tv_entity(self) -> None:
        """Cache the TV entity ID from Home Assistant"""
        try:
            response = requests.get(
                f"{self.base_url}/states",
                headers=self.headers
            )
            response.raise_for_status()
            
            print("\nAvailable media_player entities:")
            media_players = []
            for entity in response.json():
                if entity["entity_id"].startswith("media_player."):
                    print(f"- {entity['entity_id']}")
                    media_players.append(entity["entity_id"])
            
            # Look for Apple TV entities
            apple_tv_keywords = ["apple", "appletv", "apple_tv"]
            for entity_id in media_players:
                if any(keyword in entity_id.lower() for keyword in apple_tv_keywords):
                    self.tv_entity = entity_id
                    print(f"\nFound Apple TV entity: {entity_id}")
                    return
            
            # If no Apple TV entity found, use the first media_player
            if media_players:
                self.tv_entity = media_players[0]
                print(f"\nNo specific Apple TV entity found. Using first media_player: {self.tv_entity}")
                return
                
            raise ValueError("No media_player entities found in Home Assistant")
            
        except Exception as e:
            print(f"\nError accessing Home Assistant: {str(e)}")
            raise

    def _get_app_id(self, app_name: str) -> Optional[str]:
        """Get the bundle ID for Apple TV apps"""
        app_ids = {
            "Netflix": "com.netflix.Netflix",
            "Disney+": "com.disney.disneyplus",
            "Hulu": "com.hulu.plus",
            "Prime Video": "com.amazon.aiv.AIVApp",
            "Max": "com.hbo.hbonow",
            "Apple TV": "com.apple.TVWatchList",
            "YouTube": "com.google.ios.youtube",
            "YouTube TV": "com.google.ios.youtubeunplugged",
            "Spotify": "com.spotify.client",
            "Plex": "com.plexapp.plex"
        }
        return app_ids.get(app_name)

    def _normalize_app_name(self, app_name: str) -> str:
        """Normalize streaming service names to match exact app names"""
        app_mappings = {
            "netflix": "Netflix",
            "hulu": "Hulu",
            "disney+": "Disney+",
            "disney plus": "Disney+",
            "max": "Max",
            "hbo max": "Max",
            "prime": "Prime Video",
            "prime video": "Prime Video",
            "amazon": "Prime Video",
            "apple": "Apple TV",
            "apple tv": "Apple TV",
            "appletv": "Apple TV",
            "youtube": "YouTube",
            "youtube tv": "YouTube TV",
            "spotify": "Spotify",
            "plex": "Plex"
        }
        return app_mappings.get(app_name.lower(), app_name)

    def launch_app(self, app_name: str) -> str:
        """Launch a specific app on Apple TV"""
        try:
            print(f"\nAttempting to launch {app_name}")
            
            # Normalize app name
            normalized_app_name = self._normalize_app_name(app_name)
            print(f"Normalized app name: {normalized_app_name}")
            
            # First ensure TV is on
            power_result = self.power_control("on")
            print(f"Power control result: {power_result}")
            time.sleep(2)  # Wait for TV to be fully on
            
            # Get app bundle ID
            app_id = self._get_app_id(normalized_app_name)
            if not app_id:
                return f"App {normalized_app_name} not supported"

            print(f"\nAttempting to launch app ID: {app_id}")
            
            # Launch app using Apple TV integration
            try:
                response = requests.post(
                    f"{self.base_url}/services/media_player/play_media",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "media_content_id": app_id,
                        "media_content_type": "app"
                    }
                )
                response.raise_for_status()
                return f"Launched {normalized_app_name}"
                
            except Exception as e:
                print(f"App launch failed: {str(e)}")
                return f"Failed to launch {normalized_app_name}"
            
        except Exception as e:
            error_msg = f"Error launching app: {str(e)}"
            print(f"\nDetailed error: {error_msg}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return error_msg

    def _move_to_position(self, target_pos) -> list:
        """Calculate moves needed to reach target position from current position"""
        if self.keyboard_position < target_pos:
            commands = ["right"] * (target_pos - self.keyboard_position)
        else:
            commands = ["left"] * (self.keyboard_position - target_pos)
        self.keyboard_position = target_pos
        return commands

    def _reset_keyboard_prime(self) -> list:
        """Reset keyboard to starting position"""
        commands = ["select","left","up","select","left","left"]  # Go back to main menu
        self.keyboard_position = 0  # Reset position tracker
        response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": ["menu", "menu", "menu", "menu", "menu", "menu"]
                        }
                    )
        response.raise_for_status()
        launch_result = self.launch_app('Prime Video')
        print(f"\nLaunch result: {launch_result}")
        time.sleep(5)  # Wait for app to fully launch
        response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": commands
                        }
                    )
        response.raise_for_status()
        time.sleep(2)
        return commands
    
    def _reset_keyboard_apple(self) -> list:
        """Reset keyboard to starting position"""
        commands = ["up","up","up","up","up","up","up","up","up","up","up","down", "select", "right", "right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select", "left", "left", "left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left"]  # Go back to main menu
        self.keyboard_position = 0  # Reset position tracker
        response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": ["menu", "menu", "menu", "menu", "menu", "menu"]
                        }
                    )
        response.raise_for_status()
        launch_result = self.launch_app('Apple TV')
        print(f"\nLaunch result: {launch_result}")
        time.sleep(5)  # Wait for app to fully launch
        response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": commands
                        }
                    )
        response.raise_for_status()
        time.sleep(2)
        return commands
    
    def _reset_keyboard_netflix(self) -> list:
        """Reset keyboard to starting position"""
        commands = ["up","up","up","up","up","up","up","up","down","down", "select", "up","up","up","up","up","up","up","right", "right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select","select", "left", "left", "left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left","left"]  # Go back to main menu
        self.keyboard_position = 0  # Reset position tracker
        response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": ["menu", "menu", "menu", "menu"]
                        }
                    )
        response.raise_for_status()
        launch_result = self.launch_app('Netflix')
        print(f"\nLaunch result: {launch_result}")
        time.sleep(5)  # Wait for app to fully launch
        response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": commands
                        }
                    )
        response.raise_for_status()
        time.sleep(2)
        return commands

    def _char_to_remote_commands(self, char: str) -> list:
        """Convert a character to remote control commands for Apple TV keyboard"""
        char = char.lower()
        commands = []
        
        if char == ' ':
            # Move to space from current position
            commands = self._move_to_position(1)
            commands.append("select")
            
        elif char.isalpha():
            # Calculate letter position (a=2, b=3, etc.)
            target_pos = ord(char) - ord('a') + 2
            commands = self._move_to_position(target_pos)
            commands.append("select")
            
        elif char.isdigit():
            num = int(char)
            # First move to number selector (position 1)
            commands = self._move_to_position(0)
            commands.append("select")
            # Then select specific number
            if num == 0:
                num = 10
            commands.extend(["right"] * (num - 1) + ["select"])
            # Reset position after number input
            self.keyboard_position = 0
            commands.append("select")
            commands.append("select")
            
        return commands

    def play_content(self, title: str, service: str) -> str:
        """Play specific content using remote controls to search"""
        try:
            # Normalize service name
            service = self._normalize_app_name(service)
            
            # First launch the appropriate app
            launch_result = self.launch_app(service)
            print(f"\nLaunch result: {launch_result}")
            time.sleep(3)  # Wait for app to fully launch
            
            if service == "Netflix":
                try:
                    # Reset keyboard and navigate to search
                    self._reset_keyboard_netflix() 
                    # Input the title character by character
                    for char in title:
                        commands = self._char_to_remote_commands(char)
                        if commands:
                            print(f"Current position: {self.keyboard_position}, Commands for '{char}': {commands}")
                            response = requests.post(
                                f"{self.base_url}/services/remote/send_command",
                                headers=self.headers,
                                json={
                                    "entity_id": self.tv_entity.replace('media_player', 'remote'),
                                    "command": commands
                                }
                            )
                            response.raise_for_status()
                            time.sleep(1)  # Wait between characters
                    
                    # After entering title, wait then select first result
                    time.sleep(3)
                    response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": ["down", "select"]
                        }
                    )
                    return f"Searched for '{title}' on {service}"
                    
                except Exception as e:
                    print(f"Search failed: {str(e)}")
                    return f"Error searching for '{title}' on {service}"
                
            if service == "Prime Video":
                try:
                    # Reset keyboard and navigate to search
                    self._reset_keyboard_prime() 
                    # Input the title character by character
                    for char in title:
                        commands = self._char_to_remote_commands(char)
                        if commands:
                            print(f"Current position: {self.keyboard_position}, Commands for '{char}': {commands}")
                            response = requests.post(
                                f"{self.base_url}/services/remote/send_command",
                                headers=self.headers,
                                json={
                                    "entity_id": self.tv_entity.replace('media_player', 'remote'),
                                    "command": commands
                                }
                            )
                            response.raise_for_status()
                            time.sleep(1)  # Wait between characters
                    
                    # After entering title, wait then select first result
                    time.sleep(3)
                    response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": ["down", "select","down","down","down","select"]
                        }
                    )
                    return f"Searched for '{title}' on {service}"
                    
                except Exception as e:
                    print(f"Search failed: {str(e)}")
                    return f"Error searching for '{title}' on {service}"

        except Exception as e:
            print(f"Error: {str(e)}")
            return f"Failed to play content"
        
        if service == "Apple TV":
                try:
                    # Reset keyboard and navigate to search
                    self._reset_keyboard_apple() 
                    # Input the title character by character
                    for char in title:
                        commands = self._char_to_remote_commands(char)
                        if commands:
                            print(f"Current position: {self.keyboard_position}, Commands for '{char}': {commands}")
                            response = requests.post(
                                f"{self.base_url}/services/remote/send_command",
                                headers=self.headers,
                                json={
                                    "entity_id": self.tv_entity.replace('media_player', 'remote'),
                                    "command": commands
                                }
                            )
                            response.raise_for_status()
                            time.sleep(1)  # Wait between characters
                    
                    # After entering title, wait then select first result
                    time.sleep(3)
                    response = requests.post(
                        f"{self.base_url}/services/remote/send_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity.replace('media_player', 'remote'),
                            "command": ["down","down","select"]
                        }
                    )
                    return f"Searched for '{title}' on {service}"
                    
                except Exception as e:
                    print(f"Search failed: {str(e)}")
                    return f"Error searching for '{title}' on {service}"


    def power_control(self, state: str) -> str:
        """Turn TV on/off"""
        if state.lower() not in ['on', 'off']:
            return "Invalid state. Use 'on' or 'off'"
            
        try:
            service = "turn_on" if state.lower() == "on" else "turn_off"
            response = requests.post(
                f"{self.base_url}/services/media_player/{service}",
                headers=self.headers,
                json={"entity_id": self.tv_entity}
            )
            response.raise_for_status()
            return f"TV turned {state}"
        except Exception as e:
            return f"Error controlling TV power: {str(e)}"

    def volume_control(self, action: str, level: Optional[int] = None) -> str:
        """Control TV volume - up/down/mute/set"""
        try:
            if action.lower() == "mute":
                response = requests.post(
                    f"{self.base_url}/services/media_player/volume_mute",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "is_volume_muted": True
                    }
                )
                return "TV muted"
                
            elif action.lower() == "unmute":
                response = requests.post(
                    f"{self.base_url}/services/media_player/volume_mute",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "is_volume_muted": False
                    }
                )
                return "TV unmuted"
                
            elif action.lower() in ["up", "down"]:
                current_volume = self._get_current_volume()
                new_volume = current_volume + (0.1 if action.lower() == "up" else -0.1)
                new_volume = max(0, min(1, new_volume))  # Keep between 0 and 1
                
                response = requests.post(
                    f"{self.base_url}/services/media_player/volume_set",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "volume_level": new_volume
                    }
                )
                return f"Volume {action.lower()}"
                
            elif action.lower() == "set" and level is not None:
                if not 0 <= level <= 100:
                    return "Volume level must be between 0 and 100"
                    
                response = requests.post(
                    f"{self.base_url}/services/media_player/volume_set",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "volume_level": level / 100
                    }
                )
                return f"Volume set to {level}%"
                
            else:
                return "Invalid volume action"
                
        except Exception as e:
            return f"Error controlling volume: {str(e)}"

    def _get_current_volume(self) -> float:
        """Get current volume level"""
        try:
            response = requests.get(
                f"{self.base_url}/states/{self.tv_entity}",
                headers=self.headers
            )
            response.raise_for_status()
            state = response.json()
            return state.get('attributes', {}).get('volume_level', 0.5)
        except:
            return 0.5

    def get_tv_state(self) -> str:
        """Get current TV state including power, volume, and current app"""
        try:
            response = requests.get(
                f"{self.base_url}/states/{self.tv_entity}",
                headers=self.headers
            )
            response.raise_for_status()
            
            state = response.json()
            status = f"TV is {state['state']}"
            
            if "volume_level" in state["attributes"]:
                status += f", Volume: {int(state['attributes']['volume_level'] * 100)}%"
            if "app_name" in state["attributes"]:
                status += f", Current app: {state['attributes']['app_name']}"
                
            return status
            
        except Exception as e:
            return f"Error getting TV status: {str(e)}"