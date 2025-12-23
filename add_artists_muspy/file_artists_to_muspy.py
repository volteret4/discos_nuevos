#!/usr/bin/env python
"""
Artist List to MuSpy Script
Lee un archivo txt con artistas (uno por línea) y los añade a MuSpy
"""

import argparse
import requests
import time
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
import musicbrainzngs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Silenciar los logs molestos de musicbrainzngs
logging.getLogger('musicbrainzngs').setLevel(logging.ERROR)

# Silenciar requests/urllib3 si es muy verboso
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

class ArtistListToMuSpy:
    def __init__(self, muspy_username: str, muspy_password: str, muspy_user_id: str):
        self.muspy_auth = (muspy_username, muspy_password)
        self.muspy_user_id = muspy_user_id
        self.muspy_base_url = "https://muspy.com/api/1"

        # Configurar MusicBrainz NGS
        musicbrainzngs.set_useragent(
            "ArtistListToMuSpy",
            "1.1",
            "https://github.com/tu-usuario/repo"
        )
        # Opcional: si tienes muchos artistas, MusicBrainz permite 1 req/sec
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0)

        self.muspy_delay = 0.5
        self.mbid_cache = {}

    def read_artist_file(self, file_path: str) -> List[str]:
        """Lee nombres de artistas desde un archivo txt."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                artists = [line.strip() for line in f if line.strip()]
            unique_artists = list(dict.fromkeys(artists))  # Preserva orden
            logger.info(f"Leídos {len(unique_artists)} artistas únicos.")
            return unique_artists
        except Exception as e:
            logger.error(f"Error leyendo archivo: {e}")
            return []

    def search_musicbrainz_mbid(self, artist_name: str) -> Optional[Dict]:
        """Busca el MBID usando musicbrainzngs con lógica mejorada."""
        cache_key = artist_name.lower()
        if cache_key in self.mbid_cache:
            return self.mbid_cache[cache_key]

        try:
            # Búsqueda usando la librería NGS
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
        except musicbrainzngs.MusicBrainzError as e:
            logger.error(f"Error en MusicBrainz para {artist_name}: {e}")
        except Exception as e:
            logger.debug(f"Error inesperado buscando {artist_name}: {e}")

        self.mbid_cache[cache_key] = None
        return None

    def _find_best_artist_match(self, candidates: List[Dict], search_name: str) -> Optional[Dict]:
        """Lógica mejorada para encontrar el mejor match."""
        if not candidates:
            return None

        search_lower = search_name.lower()
        scored_candidates = []

        for candidate in candidates:
            score = 0
            mb_name = candidate.get('name', '').lower()
            mb_score = int(candidate.get('ext:score', 0))

            # Base score de MusicBrainz
            score += mb_score / 2

            # Match exacto del nombre
            if mb_name == search_lower:
                score += 150
            elif mb_name in search_lower or search_lower in mb_name:
                score += 80

            # Bonificación por tipo de artista
            artist_type = candidate.get('type', '')
            if artist_type == 'Person':
                score += 15
            elif artist_type == 'Group':
                score += 20

            # Penalización por tributes y covers
            disambiguation = candidate.get('disambiguation', '').lower()
            if any(word in disambiguation for word in ['tribute', 'cover', 'parody', 'karaoke']):
                score -= 100

            # Bonificación por artistas activos
            life_span = candidate.get('life-span', {})
            if not life_span.get('ended'):
                score += 10

            # Penalización por artistas muy viejos sin actividad
            if life_span.get('ended') and 'begin' in life_span:
                try:
                    begin_year = int(life_span['begin'][:4])
                    if begin_year < 1950:
                        score -= 20
                except (ValueError, TypeError):
                    pass

            scored_candidates.append((score, candidate))

        # Ordenar por score y devolver el mejor
        scored_candidates.sort(reverse=True, key=lambda x: x[0])
        best_score, best_candidate = scored_candidates[0]

        # Solo devolver si el score es razonablemente alto
        return best_candidate if best_score >= 70 else None

    def add_artist_to_muspy(self, mbid: str, artist_name: str) -> Tuple[bool, str]:
        """Añade el artista a MuSpy via API."""
        time.sleep(self.muspy_delay)
        url = f"{self.muspy_base_url}/artists/{self.muspy_user_id}/{mbid}"

        try:
            # Primero verificar si ya existe
            check_response = requests.get(url, auth=self.muspy_auth, timeout=10)
            if check_response.status_code == 200:
                return True, "already_following"

            # Si no existe, añadir con PUT
            response = requests.put(url, auth=self.muspy_auth, timeout=10)
            if response.status_code in [200, 201]:
                return True, "added"
            else:
                logger.warning(f"Error HTTP {response.status_code} para {artist_name}")
                return False, f"http_error_{response.status_code}"

        except Exception as e:
            logger.error(f"Error en MuSpy para {artist_name}: {e}")
            return False, f"exception_{type(e).__name__}"

    def process_artist_list(self, file_path: str, dry_run: bool = False, limit: Optional[int] = None) -> Dict:
        """Procesa la lista de artistas desde el archivo."""
        logger.info(f"Procesando artistas desde: {file_path}")

        # Leer artistas del archivo
        artists = self.read_artist_file(file_path)
        if not artists:
            return {'error': 'No se pudieron leer artistas del archivo'}

        # Aplicar límite si se especifica
        if limit and limit > 0:
            artists = artists[:limit]
            logger.info(f"Limitado a los primeros {limit} artistas")

        # Estadísticas
        stats = {
            'total_artists': len(artists),
            'mbid_found': 0,
            'mbid_not_found': 0,
            'added_to_muspy': 0,
            'already_following': 0,
            'failed_muspy': 0,
            'processed_artists': [],
            'failed_artists': []
        }

        for i, artist_name in enumerate(artists, 1):
            logger.info(f"[{i}/{len(artists)}] Procesando: {artist_name}")

            # Buscar MBID
            mb_info = self.search_musicbrainz_mbid(artist_name)

            if mb_info:
                stats['mbid_found'] += 1
                artist_info = {
                    'original_name': artist_name,
                    'mb_name': mb_info['name'],
                    'mbid': mb_info['mbid'],
                    'disambiguation': mb_info['disambiguation'],
                    'score': mb_info['score'],
                    'type': mb_info['type'],
                    'country': mb_info['country'],
                    'url': mb_info['url']
                }

                if dry_run:
                    disambiguation = f" ({mb_info['disambiguation']})" if mb_info['disambiguation'] else ""
                    country = f" [{mb_info['country']}]" if mb_info['country'] else ""
                    artist_type = f" ({mb_info['type']})" if mb_info['type'] else ""

                    print(f"  ✅ {mb_info['name']}{disambiguation}{country}{artist_type}")
                    print(f"     Original: {artist_name}")
                    print(f"     MBID: {mb_info['mbid']}")
                    print(f"     Score: {mb_info['score']}")
                    print(f"     URL: {mb_info['url']}")
                    print()
                    stats['processed_artists'].append(artist_info)
                else:
                    # Añadir a MuSpy
                    success, status = self.add_artist_to_muspy(mb_info['mbid'], mb_info['name'])

                    if success:
                        if status == "added":
                            stats['added_to_muspy'] += 1
                            logger.info(f"✅ Añadido: {mb_info['name']}")
                        else:  # already_following
                            stats['already_following'] += 1
                            logger.info(f"ℹ️  Ya sigues a: {mb_info['name']}")

                        artist_info['muspy_status'] = status
                        stats['processed_artists'].append(artist_info)
                    else:
                        stats['failed_muspy'] += 1
                        artist_info['muspy_status'] = status
                        stats['failed_artists'].append(artist_info)
                        logger.error(f"❌ Falló añadir a MuSpy: {mb_info['name']} ({status})")
            else:
                stats['mbid_not_found'] += 1
                failed_info = {
                    'original_name': artist_name,
                    'error': 'no_mbid_found'
                }
                stats['failed_artists'].append(failed_info)
                logger.warning(f"❌ No se encontró MBID para: {artist_name}")

        # Mostrar resumen
        self._print_summary(stats, dry_run)
        return stats

    def _print_summary(self, stats: Dict, dry_run: bool):
        """Imprime resumen de procesamiento."""
        print("\n" + "="*70)
        print("RESUMEN DE PROCESAMIENTO")
        print("="*70)
        print(f"Total de artistas: {stats['total_artists']}")
        print(f"MBID encontrados: {stats['mbid_found']}")
        print(f"MBID no encontrados: {stats['mbid_not_found']}")

        if not dry_run:
            print(f"Añadidos a MuSpy: {stats['added_to_muspy']}")
            print(f"Ya seguías: {stats['already_following']}")
            print(f"Fallos en MuSpy: {stats['failed_muspy']}")

        # Tasa de éxito
        if stats['total_artists'] > 0:
            mbid_rate = (stats['mbid_found'] / stats['total_artists']) * 100
            print(f"Tasa de búsqueda MBID: {mbid_rate:.1f}%")

            if not dry_run and stats['mbid_found'] > 0:
                muspy_rate = ((stats['added_to_muspy'] + stats['already_following']) / stats['mbid_found']) * 100
                print(f"Tasa de éxito MuSpy: {muspy_rate:.1f}%")

        # Mostrar algunos fallos
        if stats['failed_artists']:
            print(f"\n❌ Artistas problemáticos (mostrando hasta 10):")
            for failed in stats['failed_artists'][:10]:
                if 'error' in failed:
                    print(f"  • {failed['original_name']} - {failed['error']}")
                else:
                    print(f"  • {failed['original_name']} - {failed.get('muspy_status', 'unknown_error')}")

            if len(stats['failed_artists']) > 10:
                print(f"  ... y {len(stats['failed_artists']) - 10} más")

        # Mostrar algunos éxitos
        if stats['processed_artists']:
            print(f"\n✅ Algunos artistas procesados exitosamente:")
            for success in stats['processed_artists'][:5]:
                status = success.get('muspy_status', 'found')
                disambiguation = f" ({success['disambiguation']})" if success['disambiguation'] else ""
                print(f"  • {success['mb_name']}{disambiguation} - {status}")

    # Método legacy para compatibilidad
    def process(self, file_path: str, dry_run: bool = False):
        """Método legacy - usa process_artist_list."""
        return self.process_artist_list(file_path, dry_run)


def load_env_config() -> Dict[str, str]:
    """Load configuration from environment variables or .env file."""
    config = {}

    # Try to load from .env file
    load_dotenv()

    env_vars = ['MUSPY_USERNAME', 'MUSPY_PASSWORD', 'MUSPY_USER_ID']

    for var in env_vars:
        if var in os.environ:
            config[var] = os.environ[var]

    return config


def main():
    parser = argparse.ArgumentParser(
        description='🎵 Artist List to MuSpy - Add artists from text file to MuSpy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s artists.txt
  %(prog)s artists.txt --dry-run
  %(prog)s artists.txt --limit 10 --muspy-username user --muspy-password pass

File format:
  One artist name per line:
    Radiohead
    The Beatles
    Pink Floyd

Environment variables:
  MUSPY_USERNAME, MUSPY_PASSWORD, MUSPY_USER_ID
        """
    )

    # Required arguments
    parser.add_argument('file_path', help='Path to text file with artist names (one per line)')

    # Optional MuSpy arguments
    parser.add_argument('--muspy-username', help='MuSpy username')
    parser.add_argument('--muspy-password', help='MuSpy password')
    parser.add_argument('--muspy-user-id', help='MuSpy user ID')

    # Processing options
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int,
                       help='Limit number of artists to process (for testing)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

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

    # Validate file path
    if not Path(args.file_path).exists():
        logger.error(f"File not found: {args.file_path}")
        return

    try:
        # Initialize processor
        processor = ArtistListToMuSpy(**required_config)

        # Process artist list
        stats = processor.process_artist_list(
            args.file_path,
            dry_run=args.dry_run,
            limit=args.limit
        )

        if stats.get('mbid_found', 0) > 0:
            logger.info("🎉 Processing completed successfully!")
        else:
            logger.warning("⚠️  No artists found with MBIDs")

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
