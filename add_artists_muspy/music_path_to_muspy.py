#!/usr/bin/env python
"""
Music Files to MuSpy Script (Album-based)
Escanea archivos de música agrupándolos por álbum, encuentra el artista principal
del álbum usando album_artist o analizando todos los archivos, y los añade a MuSpy
"""

import argparse
import requests
import time
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter
from dotenv import load_dotenv
import musicbrainzngs

# Audio libraries for tag reading
try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3NoHeaderError
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    logger_mutagen = logging.getLogger(__name__)
    logger_mutagen.warning("Mutagen not available. Install with: pip install mutagen")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Silenciar los logs molestos de musicbrainzngs
logging.getLogger('musicbrainzngs').setLevel(logging.ERROR)

# También silenciar logs de mutagen si son molestos
logging.getLogger('mutagen').setLevel(logging.WARNING)

# Silenciar requests/urllib3 si es muy verboso
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

class AlbumBasedMusicToMuSpy:
    def __init__(self, muspy_username: str, muspy_password: str, muspy_user_id: str):
        self.muspy_auth = (muspy_username, muspy_password)
        self.muspy_user_id = muspy_user_id
        self.muspy_base_url = "https://muspy.com/api/1"

        # Configurar MusicBrainz NGS
        musicbrainzngs.set_useragent(
            "AlbumBasedMusicToMuSpy",
            "1.1",
            "https://github.com/tu-usuario/repo"
        )
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0)

        # Rate limiting
        self.muspy_delay = 0.5

        # Cache to avoid duplicate searches
        self.mbid_cache = {}
        self.processed_artists = set()  # Track artists we've already processed

        # Supported audio formats
        self.supported_formats = {
            '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.oga', '.wav',
            '.wv', '.ape', '.aif', '.aiff', '.opus', '.mp4', '.m4p',
            '.wma', '.asf', '.dsf', '.dff'
        }

        if not MUTAGEN_AVAILABLE:
            logger.error("Mutagen library is required. Install with: pip install mutagen")
            raise ImportError("Mutagen library not found")

    def scan_music_files(self, directory: str, recursive: bool = True) -> List[Path]:
        """Scan directory for music files."""
        directory = Path(directory)

        if not directory.exists():
            logger.error(f"Directory does not exist: {directory}")
            return []

        if not directory.is_dir():
            logger.error(f"Path is not a directory: {directory}")
            return []

        logger.info(f"Scanning {'recursively' if recursive else 'non-recursively'} in: {directory}")

        music_files = []

        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        for file_path in directory.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                music_files.append(file_path)

        logger.info(f"Found {len(music_files)} music files")
        return sorted(music_files)

    def extract_tags_from_file(self, file_path: Path) -> Optional[Dict]:
        """Extract relevant tags from music file."""
        try:
            audio_file = MutagenFile(str(file_path))

            if audio_file is None:
                logger.debug(f"Could not read tags from: {file_path}")
                return None

            # Debug: mostrar todos los tags disponibles para el primer archivo
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Available tags in {file_path.name}: {list(audio_file.keys())}")

            # Initialize result dictionary
            tags = {
                'artist': None,
                'artistsort': None,
                'albumartist': None,
                'albumartistsort': None,
                'artist_mbid': None,
                'albumartist_mbid': None,
                'album': None,
                'album_mbid': None,
                'title': None,
                'recording_mbid': None,
                'release_group_mbid': None,
                'date': None,
                'year': None,
                'track': None,
                'disc': None
            }

            # Define tag mappings for different formats (FLAC/Vorbis first, then ID3, then MP4)
            tag_mappings = {
                # Artist information - FLAC/Vorbis tags first
                'artist': ['ARTIST', 'TPE1', '\xa9ART', 'Artist'],
                'artistsort': ['ARTISTSORT', 'TSOP', 'soar', 'ArtistSort'],
                'albumartist': ['ALBUMARTIST', 'TPE2', 'aART', 'AlbumArtist'],
                'albumartistsort': ['ALBUMARTISTSORT', 'TSO2', 'soaa', 'AlbumArtistSort'],

                # MusicBrainz IDs - FLAC/Vorbis style first (como los pone Picard)
                'artist_mbid': [
                    'MUSICBRAINZ_ARTISTID',
                    'TXXX:MusicBrainz Artist Id',
                    '----:com.apple.iTunes:MusicBrainz Artist Id'
                ],
                'albumartist_mbid': [
                    'MUSICBRAINZ_ALBUMARTISTID',
                    'TXXX:MusicBrainz Album Artist Id',
                    '----:com.apple.iTunes:MusicBrainz Album Artist Id'
                ],
                'album_mbid': [
                    'MUSICBRAINZ_ALBUMID',
                    'TXXX:MusicBrainz Album Id',
                    '----:com.apple.iTunes:MusicBrainz Album Id'
                ],
                'recording_mbid': [
                    'MUSICBRAINZ_TRACKID',
                    'MUSICBRAINZ_RECORDINGID',  # Picard usa este también
                    'UFID:http://musicbrainz.org',
                    '----:com.apple.iTunes:MusicBrainz Track Id'
                ],
                'release_group_mbid': [
                    'MUSICBRAINZ_RELEASEGROUPID',
                    'TXXX:MusicBrainz Release Group Id',
                    '----:com.apple.iTunes:MusicBrainz Release Group Id'
                ],

                # Additional info - FLAC/Vorbis first
                'album': ['ALBUM', 'TALB', '\xa9alb', 'Album'],
                'title': ['TITLE', 'TIT2', '\xa9nam', 'Title'],
                'date': ['DATE', 'TDRC', '\xa9day', 'Date'],
                'year': ['DATE', 'YEAR', 'TYER', '\xa9day', 'Year'],  # En FLAC, DATE contiene el año
                'track': ['TRACKNUMBER', 'TRCK', 'trkn', 'Track'],
                'disc': ['DISCNUMBER', 'TPOS', 'disk', 'Disc']
            }

            # Extract values based on tag mappings
            for key, possible_tags in tag_mappings.items():
                for tag in possible_tags:
                    if tag in audio_file:
                        value = audio_file[tag]
                        if isinstance(value, list) and value:
                            value = value[0]
                        if isinstance(value, bytes):
                            value = value.decode('utf-8', errors='ignore')
                        if value:
                            tags[key] = str(value).strip()
                            break

            # Debug: mostrar qué tags se extrajeron
            if logger.isEnabledFor(logging.DEBUG):
                extracted_tags = {k: v for k, v in tags.items() if v is not None}
                if extracted_tags:
                    logger.debug(f"Extracted tags from {file_path.name}: {extracted_tags}")

            return tags

        except ID3NoHeaderError:
            logger.debug(f"No ID3 header in file: {file_path}")
            return None
        except Exception as e:
            logger.debug(f"Error reading tags from {file_path}: {e}")
            return None

    def group_files_by_album(self, music_files: List[Path]) -> Dict[str, List[Dict]]:
        """Group music files by album, extracting tags from each."""
        albums = defaultdict(list)

        for i, file_path in enumerate(music_files):
            logger.debug(f"Processing file {i+1}/{len(music_files)}: {file_path.name}")

            tags = self.extract_tags_from_file(file_path)
            if not tags:
                logger.debug(f"No tags found in {file_path.name}")
                continue

            # Create album key - try multiple strategies
            album_key = self._create_album_key(tags, file_path)

            file_info = {
                'file_path': file_path,
                'tags': tags
            }

            albums[album_key].append(file_info)
            logger.debug(f"Added {file_path.name} to album: {album_key}")

        logger.info(f"Grouped {len(music_files)} files into {len(albums)} albums")

        # En modo debug, mostrar información de álbumes encontrados
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Albums found:")
            for album_key, files in albums.items():
                logger.debug(f"  {album_key}: {len(files)} files")
                # Mostrar algunos tags del primer archivo como ejemplo
                if files and files[0]['tags']:
                    sample_tags = {k: v for k, v in files[0]['tags'].items() if v is not None}
                    logger.debug(f"    Sample tags: {sample_tags}")

        return dict(albums)

    def _create_album_key(self, tags: Dict, file_path: Path) -> str:
        """Create a unique key for grouping files by album."""
        # Strategy 1: Use album + albumartist (preferred for Picard-tagged files)
        album = tags.get('album', '').strip()
        album_artist = tags.get('albumartist', '').strip()

        if album and album_artist:
            return f"{album_artist} - {album}"

        # Strategy 2: Use album + artist
        artist = tags.get('artist', '').strip()
        if album and artist:
            # Clean artist name to avoid featuring issues
            clean_artist = self._clean_artist_name(artist)
            if clean_artist and clean_artist != artist:
                return f"{clean_artist} - {album}"
            return f"{artist} - {album}"

        # Strategy 3: Use directory structure (common for well-organized libraries)
        parent_dir = file_path.parent.name
        grandparent_dir = file_path.parent.parent.name

        # Try to detect "Artist - Album" directory structure
        if " - " in parent_dir:
            return parent_dir

        # Try "Artist/Album" structure
        if album_artist:
            return f"{album_artist} - {parent_dir}"
        elif artist:
            clean_artist = self._clean_artist_name(artist)
            return f"{clean_artist} - {parent_dir}"

        # Strategy 4: Just use directory with some intelligence
        if album:
            return f"Unknown Artist - {album}"

        return f"Unknown Artist - {parent_dir}"

    def analyze_album_artist(self, album_files: List[Dict]) -> Tuple[Optional[str], Optional[str], Dict]:
        """
        Analyze files in an album to determine the main artist.
        Returns (artist_name, artist_mbid, analysis_info)
        """
        analysis = {
            'strategy_used': None,
            'album_name': None,
            'total_files': len(album_files),
            'artists_found': [],
            'confidence': 0
        }

        if not album_files:
            return None, None, analysis

        # Get album name
        album_names = [f['tags'].get('album', '') for f in album_files if f['tags'].get('album')]
        if album_names:
            analysis['album_name'] = Counter(album_names).most_common(1)[0][0]

        logger.debug(f"Analyzing album with {len(album_files)} files, album name: {analysis['album_name']}")

        # Strategy 1: Use albumartist if consistently present
        album_artists = []
        album_artist_mbids = []

        for file_info in album_files:
            tags = file_info['tags']
            if tags.get('albumartist'):
                album_artists.append(tags['albumartist'])
                logger.debug(f"Found albumartist: {tags['albumartist']} in {file_info['file_path'].name}")
            if tags.get('albumartist_mbid'):
                album_artist_mbids.append(tags['albumartist_mbid'])
                logger.debug(f"Found albumartist_mbid: {tags['albumartist_mbid']} in {file_info['file_path'].name}")

        # Check if albumartist is consistent
        if album_artists:
            artist_counter = Counter(album_artists)
            most_common_artist, artist_count = artist_counter.most_common(1)[0]

            logger.debug(f"Album artists found: {dict(artist_counter)}")

            # If albumartist appears in majority of files
            if artist_count >= len(album_files) * 0.7:  # 70% threshold
                analysis['strategy_used'] = 'albumartist_tag'
                analysis['confidence'] = (artist_count / len(album_files)) * 100
                analysis['artists_found'] = [most_common_artist]

                # Try to find corresponding MBID
                mbid = None
                if album_artist_mbids:
                    mbid_counter = Counter(album_artist_mbids)
                    most_common_mbid = mbid_counter.most_common(1)[0][0]
                    if mbid_counter[most_common_mbid] >= artist_count * 0.8:
                        mbid = most_common_mbid
                        logger.debug(f"Found matching MBID: {mbid}")

                logger.debug(f"Strategy 1 successful: {most_common_artist} with {analysis['confidence']:.0f}% confidence")
                return most_common_artist, mbid, analysis

        # Strategy 2: Analyze track artists and filter collaborations
        track_artists = []
        track_artist_mbids = []

        for file_info in album_files:
            tags = file_info['tags']
            if tags.get('artist'):
                # Clean artist name - remove featuring, feat, etc.
                clean_artist = self._clean_artist_name(tags['artist'])
                if clean_artist:
                    track_artists.append(clean_artist)
                    logger.debug(f"Found cleaned artist: {clean_artist} (from {tags['artist']}) in {file_info['file_path'].name}")
            if tags.get('artist_mbid'):
                track_artist_mbids.append(tags['artist_mbid'])

        if track_artists:
            # Find the most common artist (should be the album artist)
            artist_counter = Counter(track_artists)
            analysis['artists_found'] = [name for name, count in artist_counter.most_common(5)]

            logger.debug(f"Track artists found: {dict(artist_counter)}")

            most_common_artist, artist_count = artist_counter.most_common(1)[0]

            # Check if this artist appears in majority of tracks
            if artist_count >= len(album_files) * 0.6:  # 60% threshold
                analysis['strategy_used'] = 'cleaned_track_artists'
                analysis['confidence'] = (artist_count / len(album_files)) * 100

                # Try to find corresponding MBID
                mbid = None
                if track_artist_mbids:
                    mbid_counter = Counter(track_artist_mbids)
                    most_common_mbid = mbid_counter.most_common(1)[0][0]
                    if mbid_counter[most_common_mbid] >= artist_count * 0.8:
                        mbid = most_common_mbid
                        logger.debug(f"Found matching MBID: {mbid}")

                logger.debug(f"Strategy 2 successful: {most_common_artist} with {analysis['confidence']:.0f}% confidence")
                return most_common_artist, mbid, analysis

        # Strategy 3: Use MusicBrainz album lookup if we have album MBID
        album_mbids = [f['tags'].get('album_mbid') for f in album_files if f['tags'].get('album_mbid')]
        if album_mbids:
            mbid_counter = Counter(album_mbids)
            most_common_album_mbid = mbid_counter.most_common(1)[0][0]

            logger.debug(f"Found album MBID: {most_common_album_mbid}, trying MusicBrainz lookup")

            artist_info = self._lookup_album_artist_by_mbid(most_common_album_mbid)
            if artist_info:
                analysis['strategy_used'] = 'musicbrainz_album_lookup'
                analysis['confidence'] = 90
                logger.debug(f"Strategy 3 successful: {artist_info['name']} via MusicBrainz album lookup")
                return artist_info['name'], artist_info['mbid'], analysis

        # Strategy 4: Fallback - just use the most common artist without cleaning
        if track_artists:
            raw_artists = [f['tags'].get('artist', '') for f in album_files if f['tags'].get('artist')]
            if raw_artists:
                artist_counter = Counter(raw_artists)
                most_common_artist = artist_counter.most_common(1)[0][0]
                analysis['strategy_used'] = 'fallback_most_common'
                analysis['confidence'] = 30
                logger.debug(f"Strategy 4 fallback: {most_common_artist}")
                return most_common_artist, None, analysis

        analysis['strategy_used'] = 'failed'
        logger.debug("All strategies failed to find album artist")
        return None, None, analysis

    def _clean_artist_name(self, artist_name: str) -> str:
        """Remove featuring, collaborations, etc. from artist name."""
        if not artist_name:
            return ""

        # Patterns to remove featuring and collaborations
        featuring_patterns = [
            r'\s+feat\.\s+.*',
            r'\s+ft\.\s+.*',
            r'\s+featuring\s+.*',
            r'\s+ft\s+.*',
            r'\s+feat\s+.*',
            r'\s+with\s+.*',
            r'\s+vs\.\s+.*',
            r'\s+vs\s+.*',
            r'\s+x\s+.*',
            r'\s+&\s+.*',
            r'\s+and\s+.*'
        ]

        cleaned = artist_name.strip()

        for pattern in featuring_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _lookup_album_artist_by_mbid(self, album_mbid: str) -> Optional[Dict]:
        """Look up album artist using MusicBrainz album MBID."""
        try:
            result = musicbrainzngs.get_release_by_id(album_mbid, includes=['artist-credits'])

            artist_credit = result.get('release', {}).get('artist-credit', [])
            if artist_credit and len(artist_credit) > 0:
                main_artist = artist_credit[0]
                if 'artist' in main_artist:
                    return {
                        'name': main_artist['artist']['name'],
                        'mbid': main_artist['artist']['id']
                    }
        except Exception as e:
            logger.debug(f"Error looking up album MBID {album_mbid}: {e}")

        return None

    def search_musicbrainz_mbid(self, artist_name: str) -> Optional[Dict]:
        """Search for MBID on MusicBrainz using musicbrainzngs."""
        cache_key = artist_name.lower()
        if cache_key in self.mbid_cache:
            return self.mbid_cache[cache_key]

        try:
            result = musicbrainzngs.search_artists(artist=artist_name, limit=10)
            artist_list = result.get('artist-list', [])

            if artist_list:
                best_match = self._find_best_artist_match(artist_list, artist_name)
                if best_match:
                    info = {
                        'mbid': best_match['id'],
                        'name': best_match.get('name', ''),
                        'disambiguation': best_match.get('disambiguation', ''),
                        'score': int(best_match.get('ext:score', 0)),
                        'url': f"https://musicbrainz.org/artist/{best_match['id']}",
                        'type': best_match.get('type', ''),
                        'country': best_match.get('area', {}).get('name', '') if best_match.get('area') else ''
                    }
                    self.mbid_cache[cache_key] = info
                    return info
        except Exception as e:
            logger.debug(f"MusicBrainz search error for {artist_name}: {e}")

        self.mbid_cache[cache_key] = None
        return None

    def _find_best_artist_match(self, candidates: List[Dict], search_name: str) -> Optional[Dict]:
        """Find best artist match from MusicBrainz candidates."""
        if not candidates:
            return None

        search_lower = search_name.lower()
        scored_candidates = []

        for candidate in candidates:
            score = 0
            mb_name = candidate.get('name', '').lower()
            mb_score = int(candidate.get('ext:score', 0))

            # Base score from MusicBrainz
            score += mb_score / 2

            # Exact name match
            if mb_name == search_lower:
                score += 150
            elif mb_name in search_lower or search_lower in mb_name:
                score += 80

            # Type bonuses
            artist_type = candidate.get('type', '')
            if artist_type == 'Person':
                score += 15
            elif artist_type == 'Group':
                score += 20

            # Penalty for tributes and covers
            disambiguation = candidate.get('disambiguation', '').lower()
            if any(word in disambiguation for word in ['tribute', 'cover', 'parody', 'karaoke']):
                score -= 100

            # Prefer active artists
            life_span = candidate.get('life-span', {})
            if not life_span.get('ended'):
                score += 10

            scored_candidates.append((score, candidate))

        scored_candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_candidate = scored_candidates[0]

        return best_candidate if best_score >= 70 else None

    def add_artist_to_muspy(self, mbid: str, artist_name: str) -> Tuple[bool, str]:
        """Add artist to MuSpy."""
        time.sleep(self.muspy_delay)
        url = f"{self.muspy_base_url}/artists/{self.muspy_user_id}/{mbid}"

        try:
            # Check if already following
            check_response = requests.get(url, auth=self.muspy_auth, timeout=10)
            if check_response.status_code == 200:
                return True, "already_following"

            # Add artist
            response = requests.put(url, auth=self.muspy_auth, timeout=10)
            if response.status_code in [200, 201]:
                return True, "added"
            else:
                return False, f"http_error_{response.status_code}"

        except Exception as e:
            logger.error(f"Error adding {artist_name} to MuSpy: {e}")
            return False, f"exception_{type(e).__name__}"

    def process_music_files(self, directory: str, recursive: bool = True,
                           dry_run: bool = False, limit: Optional[int] = None) -> Dict[str, int]:
        """Process music files by album and add artists to MuSpy."""
        logger.info(f"Processing music files from {directory} (album-based)")

        # Scan for music files
        music_files = self.scan_music_files(directory, recursive)

        if not music_files:
            logger.error("No music files found")
            return {}

        # Group files by album
        albums = self.group_files_by_album(music_files)

        if limit:
            album_keys = list(albums.keys())[:limit]
            albums = {k: albums[k] for k in album_keys}
            logger.info(f"Limited to first {limit} albums")

        stats = {
            'total_files': len(music_files),
            'total_albums': len(albums),
            'albums_with_artist': 0,
            'albums_without_artist': 0,
            'unique_artists_found': 0,
            'artists_added_to_muspy': 0,
            'artists_already_following': 0,
            'artists_failed': 0,
            'strategy_breakdown': defaultdict(int)
        }

        processed_albums = []
        failed_albums = []

        for i, (album_key, album_files) in enumerate(albums.items(), 1):
            logger.info(f"[{i}/{len(albums)}] Analyzing album: {album_key}")

            # Analyze album to find main artist
            artist_name, artist_mbid, analysis = self.analyze_album_artist(album_files)

            album_info = {
                'album_key': album_key,
                'file_count': len(album_files),
                'analysis': analysis
            }

            if artist_name:
                stats['albums_with_artist'] += 1
                stats['strategy_breakdown'][analysis['strategy_used']] += 1

                # Skip if we already processed this artist
                artist_key = artist_name.lower()
                if artist_key in self.processed_artists:
                    logger.info(f"  ⏭️  Skipping {artist_name} (already processed)")
                    continue

                self.processed_artists.add(artist_key)
                stats['unique_artists_found'] += 1

                # Get or search for MBID
                final_mbid = artist_mbid
                final_name = artist_name

                if not final_mbid:
                    logger.debug(f"  🔍 Searching MusicBrainz for: {artist_name}")
                    mb_info = self.search_musicbrainz_mbid(artist_name)
                    if mb_info:
                        final_mbid = mb_info['mbid']
                        final_name = mb_info['name']

                if final_mbid:
                    album_info.update({
                        'artist_name': final_name,
                        'mbid': final_mbid,
                        'source_mbid': 'tags' if artist_mbid else 'search'
                    })

                    if dry_run:
                        strategy = analysis['strategy_used']
                        confidence = analysis.get('confidence', 0)

                        print(f"  ✅ Album: {analysis.get('album_name', 'Unknown')}")
                        print(f"     Artist: {final_name}")
                        print(f"     MBID: {final_mbid}")
                        print(f"     Strategy: {strategy} ({confidence:.0f}% confidence)")
                        print(f"     Files: {len(album_files)}")
                        if analysis.get('artists_found'):
                            print(f"     Artists found: {', '.join(analysis['artists_found'][:3])}")
                        print()

                        processed_albums.append(album_info)
                    else:
                        success, status = self.add_artist_to_muspy(final_mbid, final_name)
                        if success:
                            if status == "added":
                                stats['artists_added_to_muspy'] += 1
                                logger.info(f"  ✅ Added {final_name} to MuSpy")
                            else:
                                stats['artists_already_following'] += 1
                                logger.info(f"  ℹ️  Already following {final_name}")

                            album_info['muspy_status'] = status
                            processed_albums.append(album_info)
                        else:
                            stats['artists_failed'] += 1
                            album_info['muspy_status'] = status
                            failed_albums.append(album_info)
                            logger.error(f"  ❌ Failed to add {final_name} to MuSpy")
                else:
                    stats['albums_without_artist'] += 1
                    album_info['error'] = 'no_mbid_found'
                    failed_albums.append(album_info)
                    logger.warning(f"  ❌ No MBID found for {artist_name}")
            else:
                stats['albums_without_artist'] += 1
                album_info['error'] = 'no_artist_found'
                failed_albums.append(album_info)
                logger.warning(f"  ❌ Could not determine artist for album")

        # Print summary
        self._print_summary(stats, failed_albums, processed_albums, dry_run)

        return stats

    def _print_summary(self, stats: Dict, failed_albums: List[Dict],
                      processed_albums: List[Dict], dry_run: bool):
        """Print processing summary."""
        print("\n" + "="*70)
        print("ALBUM-BASED MUSIC PROCESSING SUMMARY")
        print("="*70)
        print(f"Total files scanned: {stats['total_files']}")
        print(f"Total albums found: {stats['total_albums']}")
        print(f"Albums with artist identified: {stats['albums_with_artist']}")
        print(f"Albums without artist: {stats['albums_without_artist']}")
        print(f"Unique artists discovered: {stats['unique_artists_found']}")

        if not dry_run:
            print(f"Artists added to MuSpy: {stats['artists_added_to_muspy']}")
            print(f"Artists already following: {stats['artists_already_following']}")
            print(f"Failed to add: {stats['artists_failed']}")

        # Strategy breakdown
        if stats['strategy_breakdown']:
            print(f"\n📊 Artist Detection Strategy Breakdown:")
            for strategy, count in stats['strategy_breakdown'].items():
                strategy_names = {
                    'albumartist_tag': 'Album Artist Tag',
                    'cleaned_track_artists': 'Cleaned Track Artists',
                    'musicbrainz_album_lookup': 'MusicBrainz Album Lookup',
                    'fallback_most_common': 'Fallback Most Common'
                }
                strategy_display = strategy_names.get(strategy, strategy)
                print(f"  {strategy_display}: {count}")

        # Show failed albums
        if failed_albums:
            print(f"\n❌ Problematic albums (showing up to 10):")
            for album in failed_albums[:10]:
                error = album.get('error', album.get('muspy_status', 'unknown'))
                print(f"  • {album['album_key']} - {error}")
            if len(failed_albums) > 10:
                print(f"  ... and {len(failed_albums) - 10} more")

        # Success rates
        if stats['total_albums'] > 0:
            success_rate = stats['albums_with_artist'] / stats['total_albums'] * 100
            print(f"\n📈 Artist Detection Rate: {success_rate:.1f}%")

        # Show some successful albums
        if processed_albums:
            print(f"\n✅ Some successfully processed albums:")
            for album in processed_albums[:5]:
                strategy = album['analysis']['strategy_used']
                confidence = album['analysis'].get('confidence', 0)
                artist = album.get('artist_name', 'Unknown')
                print(f"  • {album['album_key']} → {artist} ({strategy}, {confidence:.0f}%)")


def load_env_config() -> Dict[str, str]:
    """Load configuration from environment variables or .env file."""
    config = {}
    load_dotenv()

    env_vars = ['MUSPY_USERNAME', 'MUSPY_PASSWORD', 'MUSPY_USER_ID']

    for var in env_vars:
        if var in os.environ:
            config[var] = os.environ[var]

    return config


def main():
    parser = argparse.ArgumentParser(
        description='🎵 Album-based Music Files to MuSpy - Scan music files by album and add artists to MuSpy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/music/library
  %(prog)s /path/to/music --dry-run
  %(prog)s /path/to/music --debug --limit 5
  %(prog)s /path/to/music --no-recursive --limit 10
  %(prog)s /path/to/albums --muspy-username user --muspy-password pass

Features:
  - Groups music files by album automatically
  - Prioritizes album_artist tag over individual track artists
  - Filters out featuring/collaboration artists
  - Uses multiple strategies to find the main album artist
  - Supports MusicBrainz MBID lookup from album metadata
  - Optimized for Picard-tagged FLAC files

Debug mode:
  Use --debug to see detailed information about:
  - All tags found in each file
  - How albums are being grouped
  - Which artist detection strategy is used
  - MusicBrainz search results

Supported formats:
  MP3, FLAC, M4A, AAC, OGG, WAV, WV, APE, AIF, AIFF, OPUS, WMA, DSF, DFF

Environment variables:
  MUSPY_USERNAME, MUSPY_PASSWORD, MUSPY_USER_ID
        """
    )

    # Required arguments
    parser.add_argument('directory', help='Directory to scan for music files')

    # Optional MuSpy arguments
    parser.add_argument('--muspy-username', help='MuSpy username')
    parser.add_argument('--muspy-password', help='MuSpy password')
    parser.add_argument('--muspy-user-id', help='MuSpy user ID')

    # Scanning options
    parser.add_argument('--no-recursive', action='store_true',
                       help='Only scan top level directory (no subdirectories)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int,
                       help='Limit number of albums to process (for testing)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode (shows all tags found in files)')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        # En modo debug, también queremos ver los tags de mutagen
        logging.getLogger('mutagen').setLevel(logging.DEBUG)

    # Check for mutagen
    if not MUTAGEN_AVAILABLE:
        logger.error("Mutagen library is required. Install with: pip install mutagen")
        return

    # Load configuration
    config = load_env_config()

    # Get required config
    required_config = {
        'muspy_username': args.muspy_username or config.get('MUSPY_USERNAME'),
        'muspy_password': args.muspy_password or config.get('MUSPY_PASSWORD'),
        'muspy_user_id': args.muspy_user_id or config.get('MUSPY_USER_ID')
    }

    # Check required config
    missing = [k for k, v in required_config.items() if not v]
    if missing:
        logger.error(f"Missing required configuration: {', '.join(missing)}")
        logger.error("Set via command line arguments or environment variables/.env file")
        return

    # Validate directory
    if not Path(args.directory).exists():
        logger.error(f"Directory not found: {args.directory}")
        return

    try:
        # Initialize processor
        processor = AlbumBasedMusicToMuSpy(**required_config)

        # Process music files
        stats = processor.process_music_files(
            directory=args.directory,
            recursive=not args.no_recursive,
            dry_run=args.dry_run,
            limit=args.limit
        )

        if stats.get('unique_artists_found', 0) > 0:
            logger.info("🎉 Processing completed successfully!")
        else:
            logger.warning("⚠️  No artists found in music files")

    except KeyboardInterrupt:
        logger.info("\n⚡ Processing interrupted by user")
    except Exception as e:
        logger.error(f"⚡ Processing failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
