import spotipy
from spotipy.oauth2 import SpotifyOAuth
from typing import Optional, Dict, Any, List
import random


class SpotifyAgent:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """Initialize Spotify agent with authentication."""
        scope = "user-library-read user-modify-playback-state user-read-playback-state streaming"

        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope
        ))

    def _get_active_device(self) -> Optional[str]:
        """Get the ID of the active Spotify device."""
        try:
            devices = self.sp.devices()
            print("\nAvailable Spotify devices:")
            for device in devices['devices']:
                print(f"- {device['name']} ({device['type']}): Active = {device['is_active']}")

            # First try to find an active device
            active_devices = [d for d in devices['devices'] if d['is_active']]
            if active_devices:
                selected_device = active_devices[0]
                print(f"\nUsing active device: {selected_device['name']}")
                return selected_device['id']

            # If no active device, try to find and activate a suitable one
            available_devices = devices['devices']
            if available_devices:
                # Prefer Spotify app over others
                preferred_device = next(
                    (d for d in available_devices if d['type'].lower() in ['computer', 'smartphone']),
                    available_devices[0]
                )
                print(f"\nNo active device found. Attempting to use: {preferred_device['name']}")

                # Try to activate the device
                try:
                    self.sp.transfer_playback(device_id=preferred_device['id'], force_play=False)
                    print(f"Activated device: {preferred_device['name']}")
                    return preferred_device['id']
                except Exception as e:
                    print(f"Error activating device: {e}")
                    return preferred_device['id']  # Try to use it anyway

            print("\nNo available Spotify devices found!")
            return None

        except Exception as e:
            print(f"Error getting active device: {e}")
            return None

    def play_song(self, song_name: str, artist: Optional[str] = None) -> str:
        """Play a specific song, optionally filtered by artist."""
        try:
            print(f"\nAttempting to play song: {song_name}" + (f" by {artist}" if artist else ""))

            # Build search query
            query = song_name
            if artist:
                query += f" artist:{artist}"

            # Search for the track
            print(f"Searching for: {query}")
            results = self.sp.search(q=query, type='track', limit=1)

            if not results['tracks']['items']:
                return f"Could not find song: {song_name}"

            track_info = results['tracks']['items'][0]
            track_uri = track_info['uri']
            print(f"Found track: {track_info['name']} by {track_info['artists'][0]['name']}")

            # Get active device
            device_id = self._get_active_device()
            if not device_id:
                return "No active Spotify device found. Please open Spotify on your device."

            print("\nAttempting to start playback...")
            try:
                # First, ensure the device is active
                self.sp.transfer_playback(device_id=device_id, force_play=False)

                # Then start playback
                self.sp.start_playback(device_id=device_id, uris=[track_uri])
                print("Playback started successfully")

                return f"Playing {track_info['name']} by {track_info['artists'][0]['name']}"

            except spotipy.exceptions.SpotifyException as e:
                error_msg = str(e)
                if "NO_ACTIVE_DEVICE" in error_msg:
                    return "Please open Spotify on your device and try again"
                elif "PREMIUM_REQUIRED" in error_msg:
                    return "This feature requires Spotify Premium"
                else:
                    print(f"Spotify error: {error_msg}")
                    return f"Error playing track: {error_msg}"

        except Exception as e:
            return f"Error playing song: {str(e)}"

    def play_artist(self, artist_name: str) -> str:
        """Play top songs from a specific artist."""
        try:
            # Search for the artist
            results = self.sp.search(q=artist_name, type='artist', limit=1)

            if not results['artists']['items']:
                return f"Could not find artist: {artist_name}"

            artist_uri = results['artists']['items'][0]['uri']

            # Get artist's top tracks
            top_tracks = self.sp.artist_top_tracks(artist_uri)

            if not top_tracks['tracks']:
                return f"No tracks found for {artist_name}"

            track_uris = [track['uri'] for track in top_tracks['tracks']]
            device_id = self._get_active_device()

            if not device_id:
                return "No active Spotify device found"

            # Start playback
            self.sp.start_playback(device_id=device_id, uris=track_uris)

            return f"Playing top tracks from {artist_name}"

        except Exception as e:
            return f"Error playing artist: {str(e)}"

    def start_artist_radio(self, artist_name: str) -> str:
        """Start a radio station based on an artist."""
        try:
            # Search for the artist
            results = self.sp.search(q=artist_name, type='artist', limit=1)

            if not results['artists']['items']:
                return f"Could not find artist: {artist_name}"

            artist_uri = results['artists']['items'][0]['uri']

            # Get recommendations based on the artist
            recommendations = self.sp.recommendations(
                seed_artists=[artist_uri],
                limit=50
            )

            if not recommendations['tracks']:
                return f"Could not generate radio for {artist_name}"

            track_uris = [track['uri'] for track in recommendations['tracks']]
            device_id = self._get_active_device()

            if not device_id:
                return "No active Spotify device found"

            # Start playback with recommended tracks
            self.sp.start_playback(device_id=device_id, uris=track_uris)

            return f"Started radio based on {artist_name}"

        except Exception as e:
            return f"Error starting artist radio: {str(e)}"

    def play_liked_songs(self, shuffle: bool = True) -> str:
        """Play user's liked songs, optionally shuffled."""
        try:
            # Get user's saved tracks
            saved_tracks = []
            offset = 0
            limit = 50

            # Get first batch of tracks
            results = self.sp.current_user_saved_tracks(limit=limit, offset=offset)
            total_tracks = results['total']

            # Get track URIs from first batch
            track_uris = [item['track']['uri'] for item in results['items']]

            device_id = self._get_active_device()
            if not device_id:
                return "No active Spotify device found"

            if shuffle:
                random.shuffle(track_uris)

            # Start playback
            self.sp.start_playback(device_id=device_id, uris=track_uris)

            mode = "shuffled" if shuffle else "in order"
            return f"Playing your liked songs {mode}"

        except Exception as e:
            return f"Error playing liked songs: {str(e)}"