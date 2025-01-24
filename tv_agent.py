import requests
from typing import Dict, Optional, Union, List
import time

class TVAgent:
    def __init__(self, host: str, token: str, port: int = 8123):
        """Initialize TV Agent with Home Assistant connection details"""
        self.base_url = f"http://{host}:{port}/api"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.tv_entity = None
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
            
            # First try to find a TV-like entity
            tv_keywords = ["tv", "android", "television", "smart_tv", "smarttv", "bravia"]
            for entity_id in media_players:
                if any(keyword in entity_id.lower() for keyword in tv_keywords):
                    self.tv_entity = entity_id
                    print(f"\nFound TV entity: {entity_id}")
                    return
            
            # If no TV entity found, use the first media_player
            if media_players:
                self.tv_entity = media_players[0]
                print(f"\nNo specific TV entity found. Using first media_player: {self.tv_entity}")
                return
                
            raise ValueError("No media_player entities found in Home Assistant")
            
        except Exception as e:
            print(f"\nError accessing Home Assistant: {str(e)}")
            raise

    def _get_app_launch_intent(self, app_name: str) -> Optional[str]:
        """Get the launch intent for streaming apps on BRAVIA TV"""
        app_intents = {
            "Netflix": "com.netflix.ninja",
            "Disney+": "com.disney.disneyplus",
            "Hulu": "com.hulu.livingroomplus",
            "Prime Video": "com.amazon.amazonvideo.livingroom",
            "Max": "com.wbd.stream",
            "Apple TV": "com.apple.atve.androidtv.appletv",
            "YouTube": "com.google.android.youtube.tv",
            "YouTube TV": "com.google.android.youtube.tvunplugged",
            "Spotify": "com.spotify.tv.android",
            "Plex": "com.plexapp.android"
        }
        return app_intents.get(app_name)

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
        """Launch a specific app on BRAVIA Android TV"""
        try:
            print(f"\nAttempting to launch {app_name}")
            
            # Normalize app name
            normalized_app_name = self._normalize_app_name(app_name)
            print(f"Normalized app name: {normalized_app_name}")
            
            # First ensure TV is on
            power_result = self.power_control("on")
            print(f"Power control result: {power_result}")
            time.sleep(2)  # Wait for TV to be fully on
            
            # Get app package name
            app_package = self._get_app_launch_intent(normalized_app_name)
            if not app_package:
                return f"App {normalized_app_name} not supported"

            print(f"\nAttempting to launch package: {app_package}")
            
            # Method 1: Try using media_player service
            try:
                print("\nTrying media_player service...")
                response = requests.post(
                    f"{self.base_url}/services/media_player/play_media",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "media_content_id": app_package,
                        "media_content_type": "app"
                    }
                )
                print(f"Media player response: {response.status_code}")
                print(f"Response content: {response.text}")
                
                if response.status_code == 200:
                    return f"Launched {app_name} using media_player service"
                
            except Exception as e:
                print(f"Media player method failed: {str(e)}")

            # Method 2: Try using androidtv service
            try:
                print("\nTrying androidtv service...")
                response = requests.post(
                    f"{self.base_url}/services/androidtv/adb_command",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "command": "monkey",
                        "args": ["-p", app_package, "1"]
                    }
                )
                print(f"ADB response: {response.status_code}")
                print(f"Response content: {response.text}")
                
                if response.status_code == 200:
                    return f"Launched {app_name} using ADB"
                    
            except Exception as e:
                print(f"ADB method failed: {str(e)}")

            # Method 3: Try direct am start command
            try:
                print("\nTrying direct am start command...")
                response = requests.post(
                    f"{self.base_url}/services/androidtv/adb_command",
                    headers=self.headers,
                    json={
                        "entity_id": self.tv_entity,
                        "command": "am",
                        "args": ["start", "-n", f"{app_package}/.MainActivity"]
                    }
                )
                print(f"AM start response: {response.status_code}")
                print(f"Response content: {response.text}")
                
                if response.status_code == 200:
                    return f"Launched {app_name} using am start"
                    
            except Exception as e:
                print(f"AM start method failed: {str(e)}")

            return f"Failed to launch {app_name}. Please check Android TV integration in Home Assistant"
            
        except Exception as e:
            error_msg = f"Error launching app: {str(e)}"
            print(f"\nDetailed error: {error_msg}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return error_msg

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

    def play_content(self, title: str, service: str) -> str:
        """Play specific content on a streaming service"""
        try:
            print(f"\nAttempting to play {title} on {service}")
            
            # First launch the streaming service
            launch_result = self.launch_app(service)
            print(f"Service launch result: {launch_result}")
            
            # Wait for app to load
            time.sleep(10)  # Give Netflix more time to fully load
            
            # Use ADB input commands for more reliable control
            commands = [
                # Press search button (keycode 84)
                ["input", "keyevent", "84"],
                ["sleep", "2"],
                
                # Input the search text
                ["input", "text", title.replace(" ", "%s")],
                ["sleep", "2"],
                
                # Press enter to search
                ["input", "keyevent", "66"],
                ["sleep", "3"],
                
                # Press enter again to select first result
                ["input", "keyevent", "66"],
                ["sleep", "2"],
                
                # Press enter one more time to start playback
                ["input", "keyevent", "66"]
            ]
            
            print("\nExecuting ADB commands...")
            for cmd in commands:
                try:
                    if cmd[0] == "sleep":
                        time.sleep(float(cmd[1]))
                        continue
                        
                    response = requests.post(
                        f"{self.base_url}/services/androidtv/adb_command",
                        headers=self.headers,
                        json={
                            "entity_id": self.tv_entity,
                            "command": cmd[0],
                            "args": cmd[1:]
                        }
                    )
                    print(f"ADB command {cmd} response: {response.status_code}")
                    
                except Exception as e:
                    print(f"ADB command failed: {e}")
            
            return f"Attempting to play {title} on {service}"
            
        except Exception as e:
            error_msg = f"Error playing content: {str(e)}"
            print(f"\nDetailed error: {error_msg}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return error_msg

    def _send_bravia_command(self, command: str) -> None:
        """Send a command to the BRAVIA TV"""
        try:
            response = requests.post(
                f"{self.base_url}/services/media_player/play_media",
                headers=self.headers,
                json={
                    "entity_id": self.tv_entity,
                    "media_content_id": f"button://{command}",
                    "media_content_type": "command"
                }
            )
            print(f"Command {command} response: {response.status_code}")
        except Exception as e:
            print(f"Error sending command {command}: {e}")

    def _simulate_keyboard_input(self, text: str) -> None:
        """Simulate keyboard input for search"""
        for char in text:
            # First navigate to the character on the virtual keyboard
            # This is a simplified version - might need adjustment
            self._send_bravia_command("Confirm")  # Select character
            time.sleep(0.5)

            
        try:
            if action.lower() in ['play', 'pause']:
                service = "media_play" if action.lower() == "play" else "media_pause"
            else:
                service = "media_next_track" if action.lower() == "next" else "media_previous_track"
                
            response = requests.post(
                f"{self.base_url}/services/media_player/{service}",
                headers=self.headers,
                json={"entity_id": self.tv_entity}
            )
            response.raise_for_status()
            return f"Media {action} command sent"
        except Exception as e:
            return f"Error controlling media: {str(e)}"

    def media_control(self, action: str) -> str:
        """Control media playback - play/pause/next/previous"""
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