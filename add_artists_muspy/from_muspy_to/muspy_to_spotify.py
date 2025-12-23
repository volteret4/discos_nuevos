#!/usr/bin/env python
"""
MuSpy to Spotify Artist Sync Script
Sincroniza artistas seguidos en MuSpy hacia Spotify
"""

import argparse
import requests
import json
import time
import logging
from typing import Dict, List, Optional
import spotipy
from spotipy.oauth2 import SpotifyOAuth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MuspyToSpotifySync:
    def __init__(self, spotify_client_id: str, spotify_client_secret: str,
                 spotify_redirect_uri: str, muspy_username: str,
                 muspy_password: str, muspy_user_id: str):

        self.spotify = self._init_spotify(
            spotify_client_id, spotify_client_secret, spotify_redirect_uri
        )
        self.muspy_auth = (muspy_username, muspy_password)
        self.muspy_user_id = muspy_user_id
        self.muspy_base_url = "https://muspy.com/api/1"

        # Rate limiting
        self.musicbrainz_delay = 1.0
        self.spotify_delay = 0.1

    def _init_spotify(self, client_id: str, client_secret: str, redirect_uri: str):
        """Initialize Spotify client with follow permissions."""
        scope = "user-follow-modify user-follow-read"

        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope
        )

        return spotipy.Spotify(auth_manager=auth_manager)

    def get_muspy_followed_artists(self) -> List[Dict]:
        """Get all artists followed on MuSpy."""
        logger.info("Fetching followed artists from MuSpy...")

        try:
            url = f"{self.muspy_base_url}/artists/{self.muspy_user_id}"
            response = requests.get(url, auth=self.muspy_auth, timeout=10)

            if response.status_code == 200:
                artists = response.json()
                logger.info(f"Found {len(artists)} artists on MuSpy")
                return artists
            else:
                logger.error(f"Failed to get MuSpy artists: {response.status_code}")
                return []

        except requests.RequestException as e:
            logger.error(f"Error fetching MuSpy artists: {e}")
            return []

    def get_artist_info_from_musicbrainz(self, mbid: str) -> Optional[Dict]:
        """Get artist information from MusicBrainz using MBID."""
        time.sleep(self.musicbrainz_delay)

        try:
            url = f"https://musicbrainz.org/ws/2/artist/{mbid}"
            params = {
                'fmt': 'json',
                'inc': 'url-rels'  # Include URL relationships (Spotify links)
            }
            headers = {
                'User-Agent': 'MuspySpotifySync/2.0 (your-email@domain.com)'
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"MusicBrainz lookup failed for {mbid}: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"MusicBrainz API error for {mbid}: {e}")
            return None

    def extract_spotify_id_from_musicbrainz(self, mb_data: Dict) -> Optional[str]:
        """Extract Spotify ID from MusicBrainz relations."""
        if not mb_data or 'relations' not in mb_data:
            return None

        for relation in mb_data.get('relations', []):
            if relation.get('type') == 'streaming music' and 'url' in relation:
                url = relation['url'].get('resource', '')
                if 'spotify.com/artist/' in url:
                    # Extract Spotify ID from URL
                    spotify_id = url.split('spotify.com/artist/')[-1].split('?')[0]
                    return spotify_id

        return None

    def search_artist_on_spotify(self, artist_name: str) -> Optional[str]:
        """Search for artist on Spotify by name and return Spotify ID."""
        try:
            time.sleep(self.spotify_delay)

            results = self.spotify.search(
                q=f'artist:"{artist_name}"',
                type='artist',
                limit=1
            )

            if results['artists']['items']:
                artist = results['artists']['items'][0]
                return artist['id']

            return None

        except Exception as e:
            logger.error(f"Error searching for {artist_name} on Spotify: {e}")
            return None

    def follow_artist_on_spotify(self, spotify_id: str, artist_name: str) -> bool:
        """Follow an artist on Spotify."""
        try:
            # Check if already following
            is_following = self.spotify.current_user_following_artists([spotify_id])

            if is_following and is_following[0]:
                logger.info(f"Already following {artist_name} on Spotify")
                return True

            # Follow the artist
            self.spotify.user_follow_artists([spotify_id])
            logger.info(f"✅ Followed {artist_name} on Spotify")
            return True

        except Exception as e:
            logger.error(f"Error following {artist_name} on Spotify: {e}")
            return False

    def sync_to_spotify(self, dry_run: bool = False, limit: Optional[int] = None) -> Dict[str, int]:
        """
        Main sync function from MuSpy to Spotify.
        """
        logger.info("Starting MuSpy to Spotify sync...")

        stats = {
            'total_muspy': 0,
            'spotify_id_from_mb': 0,
            'spotify_id_from_search': 0,
            'spotify_id_not_found': 0,
            'spotify_followed': 0,
            'spotify_already_following': 0,
            'spotify_failed': 0
        }

        # Get MuSpy artists
        muspy_artists = self.get_muspy_followed_artists()
        if limit:
            muspy_artists = muspy_artists[:limit]

        stats['total_muspy'] = len(muspy_artists)
        failed_artists = []

        for i, artist in enumerate(muspy_artists, 1):
            mbid = artist.get('mbid')
            artist_name = artist.get('name', 'Unknown')

            logger.info(f"[{i}/{len(muspy_artists)}] Processing: {artist_name}")

            if not mbid:
                logger.warning(f"No MBID for {artist_name}")
                continue

            spotify_id = None

            # Step 1: Try to get Spotify ID from MusicBrainz relations
            mb_data = self.get_artist_info_from_musicbrainz(mbid)
            if mb_data:
                spotify_id = self.extract_spotify_id_from_musicbrainz(mb_data)
                if spotify_id:
                    stats['spotify_id_from_mb'] += 1
                    logger.debug(f"Found Spotify ID via MusicBrainz relations: {spotify_id}")

            # Step 2: Fall back to Spotify search by name
            if not spotify_id:
                spotify_id = self.search_artist_on_spotify(artist_name)
                if spotify_id:
                    stats['spotify_id_from_search'] += 1
                    logger.debug(f"Found Spotify ID via search: {spotify_id}")

            if spotify_id:
                if not dry_run:
                    # Follow on Spotify
                    success = self.follow_artist_on_spotify(spotify_id, artist_name)
                    if success:
                        stats['spotify_followed'] += 1
                    else:
                        stats['spotify_failed'] += 1
                        failed_artists.append(artist_name)
                else:
                    logger.info(f"[DRY RUN] Would follow {artist_name} on Spotify")
            else:
                stats['spotify_id_not_found'] += 1
                failed_artists.append(artist_name)
                logger.warning(f"Could not find {artist_name} on Spotify")

        # Print summary
        logger.info("\n" + "="*50)
        logger.info("SYNC SUMMARY")
        logger.info("="*50)
        logger.info(f"Total MuSpy artists: {stats['total_muspy']}")
        logger.info(f"Spotify IDs via MusicBrainz: {stats['spotify_id_from_mb']}")
        logger.info(f"Spotify IDs via search: {stats['spotify_id_from_search']}")
        logger.info(f"Not found on Spotify: {stats['spotify_id_not_found']}")

        if not dry_run:
            logger.info(f"Followed on Spotify: {stats['spotify_followed']}")
            logger.info(f"Failed to follow: {stats['spotify_failed']}")

        if failed_artists:
            logger.warning(f"Failed artists: {', '.join(failed_artists[:10])}")
            if len(failed_artists) > 10:
                logger.warning(f"... and {len(failed_artists) - 10} more")

        return stats


def main():
    parser = argparse.ArgumentParser(description='MuSpy to Spotify Artist Sync')

    # Required arguments
    parser.add_argument('--spotify-client-id', required=True,
                       help='Spotify API Client ID')
    parser.add_argument('--spotify-client-secret', required=True,
                       help='Spotify API Client Secret')
    parser.add_argument('--spotify-redirect-uri',
                       default='http://localhost:8080/callback',
                       help='Spotify OAuth Redirect URI')
    parser.add_argument('--muspy-username', required=True,
                       help='MuSpy username')
    parser.add_argument('--muspy-password', required=True,
                       help='MuSpy password')
    parser.add_argument('--muspy-user-id', required=True,
                       help='MuSpy user ID')

    # Optional arguments
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int,
                       help='Limit number of artists to process (for testing)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        syncer = MuspyToSpotifySync(
            spotify_client_id=args.spotify_client_id,
            spotify_client_secret=args.spotify_client_secret,
            spotify_redirect_uri=args.spotify_redirect_uri,
            muspy_username=args.muspy_username,
            muspy_password=args.muspy_password,
            muspy_user_id=args.muspy_user_id
        )

        stats = syncer.sync_to_spotify(
            dry_run=args.dry_run,
            limit=args.limit
        )

        logger.info("Sync completed successfully!")

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
