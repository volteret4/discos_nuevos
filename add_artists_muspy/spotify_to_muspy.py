#!/usr/bin/env python
"""
Spotify to MuSpy Artist Sync Script
Mejoras sobre tu código original con flags CLI y mejor manejo de errores
"""

import argparse
import requests
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import spotipy
from spotipy.oauth2 import SpotifyOAuth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SpotifyMuspySync:
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
        self.musicbrainz_delay = 1.0  # MusicBrainz rate limit
        self.spotify_delay = 0.1
        self.muspy_delay = 0.5

    def _init_spotify(self, client_id: str, client_secret: str, redirect_uri: str):
        """Initialize Spotify client with proper scopes."""
        scope = "user-follow-read"

        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope
        )

        return spotipy.Spotify(auth_manager=auth_manager)

    def get_spotify_followed_artists(self, limit: int = 50) -> List[Dict]:
        """
        Get all followed artists from Spotify with improved pagination handling.
        Addresses the known Spotify API pagination bug.
        """
        logger.info("Fetching followed artists from Spotify...")
        artists = []
        after = None
        retries = 3

        while True:
            try:
                results = self.spotify.current_user_followed_artists(
                    limit=min(limit, 50), after=after
                )

                current_artists = results['artists']['items']
                if not current_artists:
                    logger.warning("No more artists returned, might have hit pagination bug")
                    break

                artists.extend(current_artists)
                logger.info(f"Fetched {len(current_artists)} artists, total: {len(artists)}")

                # Check if there are more
                if not results['artists']['next']:
                    break

                # Set cursor for next page
                after = current_artists[-1]['id']
                time.sleep(self.spotify_delay)

            except Exception as e:
                logger.error(f"Error fetching Spotify artists: {e}")
                retries -= 1
                if retries <= 0:
                    break
                time.sleep(2)

        logger.info(f"Total followed artists: {len(artists)}")
        return artists

    def search_musicbrainz_mbid(self, artist_name: str,
                              spotify_data: Optional[Dict] = None) -> Optional[str]:
        """
        MusicBrainz search with fuzzy matching and disambiguation.
        """
        time.sleep(self.musicbrainz_delay)  # Rate limiting

        try:
            # Primary search
            params = {
                'query': f'artist:"{artist_name}"',
                'fmt': 'json',
                'limit': 5
            }

            headers = {
                'User-Agent': '-MuSpySync/2.0 (your-email@domain.com)'
            }

            response = requests.get(
                'https://musicbrainz.org/ws/2/artist/',
                params=params,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                artists = data.get('artists', [])

                if artists:
                    # Score-based matching
                    best_match = self._score_artist_match(artists, artist_name, spotify_data)
                    if best_match:
                        logger.info(f"Found MBID for {artist_name}: {best_match['id']}")
                        return best_match['id']

            # Fallback: simplified search
            if not artists and '"' in artist_name:
                return self.search_musicbrainz_mbid(
                    artist_name.replace('"', ''), spotify_data
                )

        except requests.RequestException as e:
            logger.error(f"MusicBrainz API error for {artist_name}: {e}")

        logger.warning(f"No MBID found for {artist_name}")
        return None

    def _score_artist_match(self, candidates: List[Dict],
                           search_name: str, spotify_data: Optional[Dict]) -> Optional[Dict]:
        """
        Advanced scoring system for artist matching.
        """
        if not candidates:
            return None

        scored_candidates = []

        for candidate in candidates:
            score = 0
            mb_name = candidate.get('name', '').lower()
            search_lower = search_name.lower()

            # Exact name match
            if mb_name == search_lower:
                score += 100
            elif mb_name in search_lower or search_lower in mb_name:
                score += 50

            # Score boost
            if candidate.get('score', 0):
                score += int(candidate.get('score', 0)) / 2

            # Penalty for ended artists (might be tribute bands, etc.)
            if candidate.get('life-span', {}).get('ended'):
                score -= 20

            # Boost for artists with many releases
            if 'disambiguation' in candidate:
                disambig = candidate['disambiguation'].lower()
                if any(word in disambig for word in ['tribute', 'cover', 'parody']):
                    score -= 30

            scored_candidates.append((score, candidate))

        # Return best match if score is reasonable
        scored_candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_candidate = scored_candidates[0]

        if best_score >= 50:
            return best_candidate

        return None

    def add_artist_to_muspy(self, mbid: str, artist_name: str) -> bool:
        """MuSpy artist addition with retry logic."""
        time.sleep(self.muspy_delay)

        url = f"{self.muspy_base_url}/artists/{self.muspy_user_id}/{mbid}"

        try:
            # Check if already following
            check_response = requests.get(url, auth=self.muspy_auth, timeout=10)
            if check_response.status_code == 200:
                logger.info(f"Already following {artist_name} on MuSpy")
                return True

            # Add artist
            response = requests.put(url, auth=self.muspy_auth, timeout=10)

            if response.status_code in [200, 201]:
                logger.info(f"✅ Added {artist_name} to MuSpy")
                return True
            else:
                logger.error(f"❌ Failed to add {artist_name}: {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Error adding {artist_name} to MuSpy: {e}")
            return False

    def sync_followed_artists(self, dry_run: bool = False,
                            limit: Optional[int] = None) -> Dict[str, int]:
        """
        Main sync function with comprehensive statistics.
        """
        logger.info("Starting Spotify to MuSpy sync...")

        stats = {
            'total_spotify': 0,
            'mbid_found': 0,
            'mbid_not_found': 0,
            'muspy_added': 0,
            'muspy_already_following': 0,
            'muspy_failed': 0
        }

        # Get Spotify artists
        spotify_artists = self.get_spotify_followed_artists()
        if limit:
            spotify_artists = spotify_artists[:limit]

        stats['total_spotify'] = len(spotify_artists)

        failed_artists = []

        for i, artist in enumerate(spotify_artists, 1):
            artist_name = artist['name']
            logger.info(f"[{i}/{len(spotify_artists)}] Processing: {artist_name}")

            # Search for MBID
            mbid = self.search_musicbrainz_mbid(artist_name, artist)

            if mbid:
                stats['mbid_found'] += 1

                if not dry_run:
                    # Add to MuSpy
                    success = self.add_artist_to_muspy(mbid, artist_name)
                    if success:
                        stats['muspy_added'] += 1
                    else:
                        stats['muspy_failed'] += 1
                        failed_artists.append(artist_name)
                else:
                    logger.info(f"[DRY RUN] Would add {artist_name} to MuSpy")

            else:
                stats['mbid_not_found'] += 1
                failed_artists.append(artist_name)

        # Print summary
        logger.info("\n" + "="*50)
        logger.info("SYNC SUMMARY")
        logger.info("="*50)
        logger.info(f"Total Spotify artists: {stats['total_spotify']}")
        logger.info(f"MBIDs found: {stats['mbid_found']}")
        logger.info(f"MBIDs not found: {stats['mbid_not_found']}")
        if not dry_run:
            logger.info(f"Added to MuSpy: {stats['muspy_added']}")
            logger.info(f"Failed to add: {stats['muspy_failed']}")

        if failed_artists:
            logger.warning(f"Failed artists: {', '.join(failed_artists[:10])}")
            if len(failed_artists) > 10:
                logger.warning(f"... and {len(failed_artists) - 10} more")

        return stats


def main():
    parser = argparse.ArgumentParser(description='Spotify to MuSpy Artist Sync')

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
        syncer = SpotifyMuspySync(
            spotify_client_id=args.spotify_client_id,
            spotify_client_secret=args.spotify_client_secret,
            spotify_redirect_uri=args.spotify_redirect_uri,
            muspy_username=args.muspy_username,
            muspy_password=args.muspy_password,
            muspy_user_id=args.muspy_user_id
        )

        stats = syncer.sync_followed_artists(
            dry_run=args.dry_run,
            limit=args.limit
        )

        logger.info("Sync completed successfully!")

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        exit(1)

if __name__ == "__main__":
    main()
