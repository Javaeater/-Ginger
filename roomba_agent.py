import requests
from typing import Dict, Optional

class RoombaAgent:
    def __init__(self, host: str, token: str, port: int = 8123):
        self.base_url = f"http://{host}:{port}/api"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.device_id = "vacuum.figi_bot"

    def start_cleaning(self, device_name: str = None) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/services/vacuum/start",
                headers=self.headers,
                json={"entity_id": self.device_id}
            )
            response.raise_for_status()
            return "Started cleaning with Figi Bot"
        except Exception as e:
            return f"Error starting cleaning: {str(e)}"

    def stop_cleaning(self, device_name: str = None) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/services/vacuum/stop",
                headers=self.headers,
                json={"entity_id": self.device_id}
            )
            response.raise_for_status()
            return "Stopped cleaning with Figi Bot"
        except Exception as e:
            return f"Error stopping cleaning: {str(e)}"

    def return_to_dock(self, device_name: str = None) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/services/vacuum/return_to_base",
                headers=self.headers,
                json={"entity_id": self.device_id}
            )
            response.raise_for_status()
            return "Sending Figi Bot back to dock"
        except Exception as e:
            return f"Error returning to dock: {str(e)}"

    def get_status(self, device_name: str = None) -> str:
        try:
            response = requests.get(
                f"{self.base_url}/states/{self.device_id}",
                headers=self.headers
            )
            response.raise_for_status()
            
            state_data = response.json()
            status = state_data.get("state", "unknown")
            battery = state_data.get("attributes", {}).get("battery_level", "unknown")
            
            return f"Figi Bot status: {status}, battery: {battery}%"
        except Exception as e:
            return f"Error getting status: {str(e)}"

    def locate(self, device_name: str = None) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/services/vacuum/locate",
                headers=self.headers,
                json={"entity_id": self.device_id}
            )
            response.raise_for_status()
            return "Locating Figi Bot"
        except Exception as e:
            return f"Error locating device: {str(e)}"