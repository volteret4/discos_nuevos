#!/usr/bin/env python
"""
Google Calendar MuSpy Integration - ERROR 404 FIXED
Actualizar Google Calendar con los nuevos discos que ofrece el RSS de MuSpy
🔧 SOLUCIONA: HttpError 404 por usar OAuth Client ID en lugar de Calendar ID

Author: Based on volteret4's CalDAV script
Fixed: Calendar ID issue that caused 404 errors
"""

import requests
import feedparser
import re
import os
import argparse
import logging
from datetime import datetime, timezone, date, timedelta
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendarMuSpySyncFixed:
    def __init__(self, calendar_id=None):
        """
        🔧 VERSIÓN CORREGIDA - Soluciona error 404 de Calendar ID

        Args:
            calendar_id: ID del calendario específico. Si None, auto-detecta el correcto
        """
        self.service = None
        self.calendar_id = calendar_id
        self.setup_service()

    def authenticate(self):
        """Autenticación OAuth2 (mismo patrón que ya funciona)"""
        creds = None

        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=8080, access_type='offline')

            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        return creds

    def setup_service(self):
        """Configurar servicio de Google Calendar con detección automática de Calendar ID correcto"""
        try:
            creds = self.authenticate()
            self.service = build('calendar', 'v3', credentials=creds)

            # 🔧 CORRECCIÓN: Auto-detectar Calendar ID correcto si no se especificó
            if not self.calendar_id:
                self.calendar_id = self._get_correct_calendar_id()

            # 🔧 VALIDACIÓN: Verificar que el Calendar ID es válido
            self._validate_calendar_id()

            logger.info(f"✅ Google Calendar service initialized")
            logger.info(f"📅 Using calendar ID: {self.calendar_id}")

        except Exception as e:
            logger.error(f"❌ Failed to setup Google Calendar service: {e}")
            raise

    def _get_correct_calendar_id(self):
        """
        🔧 CORRECCIÓN PRINCIPAL: Obtener el Calendar ID correcto, no el OAuth Client ID
        """
        try:
            logger.info("🔍 Auto-detecting correct Calendar ID...")

            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            if not calendars:
                raise Exception("No calendars found in account")

            # 1. Buscar calendario principal primero
            for calendar in calendars:
                if calendar.get('primary', False):
                    calendar_id = calendar['id']
                    calendar_name = calendar['summary']
                    logger.info(f"📅 Found primary calendar: {calendar_name}")
                    logger.info(f"   📧 Calendar ID: {calendar_id}")

                    # 🔧 VALIDACIÓN: Verificar que NO es un OAuth Client ID
                    if '.apps.googleusercontent.com' in calendar_id:
                        logger.error(f"❌ DETECTED OAUTH CLIENT ID AS CALENDAR ID!")
                        logger.error(f"   Wrong ID: {calendar_id}")
                        logger.error(f"   This is why you got 404 errors!")
                        continue  # Buscar otro calendario

                    return calendar_id

            # 2. Si no hay principal, usar el primero que NO sea OAuth Client ID
            for calendar in calendars:
                calendar_id = calendar['id']
                if '.apps.googleusercontent.com' not in calendar_id:
                    calendar_name = calendar['summary']
                    logger.warning(f"⚠️  No primary calendar found, using: {calendar_name}")
                    logger.info(f"   📧 Calendar ID: {calendar_id}")
                    return calendar_id

            # 3. Si todos son OAuth Client IDs, hay un problema grave
            logger.error("❌ ALL CALENDAR IDS LOOK LIKE OAUTH CLIENT IDS!")
            logger.error("   This should not happen. Check your Google account setup.")
            raise Exception("No valid Calendar IDs found")

        except Exception as e:
            logger.error(f"❌ Error auto-detecting calendar: {e}")
            raise

    def _validate_calendar_id(self):
        """
        🔧 VALIDACIÓN: Verificar que el Calendar ID es correcto y accesible
        """
        try:
            # Test 1: Verificar que NO es un OAuth Client ID
            if '.apps.googleusercontent.com' in self.calendar_id:
                logger.error(f"❌ INVALID CALENDAR ID DETECTED!")
                logger.error(f"   You provided: {self.calendar_id}")
                logger.error(f"   This is an OAuth Client ID, NOT a Calendar ID!")
                logger.error(f"   ℹ️  Calendar IDs look like: your-email@gmail.com")
                logger.error(f"   🔧 Run: python google_calendar_id_finder.py")
                raise Exception("Invalid Calendar ID - This is an OAuth Client ID")

            # Test 2: Intentar acceder al calendario
            calendar_info = self.service.calendars().get(calendarId=self.calendar_id).execute()
            logger.info(f"✅ Calendar validated: {calendar_info['summary']}")

        except HttpError as e:
            if e.resp.status == 404:
                logger.error(f"❌ Calendar not found: {self.calendar_id}")
                logger.error("💡 Possible causes:")
                logger.error("   1. Wrong Calendar ID (most likely)")
                logger.error("   2. Calendar was deleted")
                logger.error("   3. No permission to access this calendar")
                logger.error("🔧 Solution: Run python google_calendar_id_finder.py")
                raise Exception(f"Calendar not found: {self.calendar_id}")
            else:
                logger.error(f"❌ Calendar validation failed: {e}")
                raise
        except Exception as e:
            logger.error(f"❌ Calendar validation error: {e}")
            raise

    def list_available_calendars(self):
        """Listar calendarios disponibles con IDs correctos"""
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])

            print(f"\n📅 YOUR AVAILABLE CALENDARS:")
            print("=" * 70)

            for i, calendar in enumerate(calendars, 1):
                calendar_id = calendar['id']
                summary = calendar['summary']
                primary = " ⭐ (PRIMARY)" if calendar.get('primary') else ""
                access = calendar.get('accessRole', 'unknown')

                # 🔧 INDICAR si el ID es válido o problemático
                id_status = "✅ VALID" if '.apps.googleusercontent.com' not in calendar_id else "❌ INVALID (OAuth Client ID)"

                print(f"{i}. {summary}{primary}")
                print(f"   📧 ID: {calendar_id}")
                print(f"   🔐 Access: {access}")
                print(f"   🆔 Status: {id_status}")
                print()

            return calendars

        except Exception as e:
            logger.error(f"❌ Error listing calendars: {e}")
            return []

    def determine_release_type(self, title):
        """Determinar si es álbum o EP basado en el título"""
        title_lower = title.lower()

        # Indicadores comunes de EP
        ep_indicators = ['ep', ' - ep', 'extended play', 'mini album', 'single']

        for indicator in ep_indicators:
            if indicator in title_lower:
                return "EP"

        return "Album"

    def parse_atom_feed(self, feed_url):
        """Parsear el feed Atom de MuSpy"""
        try:
            logger.info(f"📡 Parsing MuSpy feed: {feed_url}")
            feed = feedparser.parse(feed_url)

            if feed.bozo:
                raise ValueError("Invalid feed format or malformed XML.")

            releases = []
            date_pattern = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

            for entry in feed.entries:
                title = entry.title.strip()
                content = entry.summary

                # Buscar fecha en el contenido
                match = date_pattern.search(content)
                if not match:
                    logger.debug(f"Skipping entry with invalid date: {content}")
                    continue

                release_date_str = match.group()
                try:
                    release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
                except ValueError:
                    logger.debug(f"Skipping entry with unparsable date: {release_date_str}")
                    continue

                # Determinar tipo de release y añadir emoji apropiado
                release_type = self.determine_release_type(title)
                if release_type == "EP":
                    formatted_title = f"🎤 {title}"
                else:
                    formatted_title = f"💿 {title}"

                releases.append({
                    "title": formatted_title,
                    "release_date": release_date,
                    "original_title": title,
                    "type": release_type
                })

            logger.info(f"📀 Found {len(releases)} releases in feed")
            return releases

        except Exception as e:
            logger.error(f"❌ Error parsing feed: {e}")
            raise

    def get_existing_events(self, days_range=60):
        """Obtener eventos existentes para evitar duplicados"""
        try:
            now = datetime.now()
            time_min = (now - timedelta(days=days_range)).isoformat() + 'Z'
            time_max = (now + timedelta(days=days_range)).isoformat() + 'Z'

            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            existing_events = set()

            for event in events:
                summary = event.get('summary', '').strip()

                start = event.get('start', {})
                if 'date' in start:
                    event_date = datetime.strptime(start['date'], '%Y-%m-%d').date()
                elif 'dateTime' in start:
                    event_date = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00')).date()
                else:
                    continue

                existing_events.add((summary, event_date))

            logger.info(f"📋 Found {len(existing_events)} existing events in range")
            return existing_events

        except Exception as e:
            logger.error(f"❌ Error getting existing events: {e}")
            return set()

    def create_music_events(self, event_data, dry_run=False):
        """
        🔧 CORRECCIÓN: Crear eventos usando Calendar ID correcto
        """
        logger.info(f"🎵 Processing {len(event_data)} music releases...")

        # Verificar una vez más que el Calendar ID es correcto
        logger.info(f"📧 Using Calendar ID: {self.calendar_id}")
        if '.apps.googleusercontent.com' in self.calendar_id:
            logger.error("❌ STOP! Calendar ID is still an OAuth Client ID!")
            logger.error("   This will cause 404 errors. Fix Calendar ID first.")
            raise Exception("Invalid Calendar ID detected")

        existing_events = self.get_existing_events()

        stats = {
            'total': len(event_data),
            'created': 0,
            'skipped': 0,
            'failed': 0
        }

        for event in event_data:
            event_title = event["title"].strip()
            event_date = event["release_date"]

            # Verificar duplicados
            if (event_title, event_date) in existing_events:
                logger.info(f"⏭️  Skipping duplicate: {event_title} ({event_date})")
                stats['skipped'] += 1
                continue

            if dry_run:
                print(f"[DRY RUN] Would create: {event_title} on {event_date}")
                stats['created'] += 1
                continue

            # 🔧 CREAR EVENTO CON CALENDAR ID CORRECTO
            google_event = {
                'summary': event_title,
                'description': f"Music Release\n\nRelease Date: {event_date}\nType: {event.get('type', 'Album')}\nSource: MuSpy",
                'start': {
                    'date': event_date.strftime('%Y-%m-%d'),
                },
                'end': {
                    'date': event_date.strftime('%Y-%m-%d'),
                },
                'colorId': '10',  # Verde para releases musicales
            }

            try:
                # 🔧 ESTO ERA LO QUE FALLABA ANTES - Calendar ID incorrecto
                created_event = self.service.events().insert(
                    calendarId=self.calendar_id,  # ✅ Ahora usa Calendar ID correcto
                    body=google_event
                ).execute()

                logger.info(f"✅ Created: {event_title} ({event_date})")
                stats['created'] += 1

            except HttpError as e:
                if e.resp.status == 404:
                    logger.error(f"❌ 404 Error - Calendar ID still wrong: {self.calendar_id}")
                    logger.error("🔧 Run: python google_calendar_id_finder.py")
                    stats['failed'] += 1
                    break
                else:
                    logger.error(f"❌ HTTP Error creating '{event_title}': {e}")
                    stats['failed'] += 1

            except Exception as e:
                logger.error(f"❌ Error creating '{event_title}': {e}")
                stats['failed'] += 1

        # Mostrar resumen
        print(f"\n📊 SYNC SUMMARY:")
        print(f"   📧 Calendar ID used: {self.calendar_id}")
        print(f"   📀 Total releases: {stats['total']}")
        print(f"   ✅ Created: {stats['created']}")
        print(f"   ⏭️  Skipped (duplicates): {stats['skipped']}")
        print(f"   ❌ Failed: {stats['failed']}")

        if stats['failed'] > 0:
            print(f"\n🔧 If you got 404 errors:")
            print(f"   1. Run: python google_calendar_id_finder.py")
            print(f"   2. Copy the correct Calendar ID")
            print(f"   3. Use --calendar-id flag or set GOOGLE_CALENDAR_ID env var")

        return stats

def main():
    """
    Función principal - versión corregida para error 404
    """
    parser = argparse.ArgumentParser(
        description='🔧 Google Calendar MuSpy Sync - FIXED VERSION (Soluciona error 404)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
🔧 FIXES THE 404 ERROR YOU WERE GETTING!

Your error was caused by using OAuth Client ID as Calendar ID:
❌ WRONG: 693512159244-72h4hsiiql72rubp3vhqhk5er8k1kp9j.apps.googleusercontent.com
✅ CORRECT: your-email@gmail.com

Examples:
  %(prog)s                                    # Auto-detect correct calendar
  %(prog)s --calendar-id "your@email.com"    # Use specific calendar
  %(prog)s --dry-run                          # Test without creating events
  %(prog)s --list-calendars                   # Show available calendars

Environment variables:
  MUSPY_FEED_URL          # Your MuSpy RSS feed URL
  GOOGLE_CALENDAR_ID      # Correct calendar ID to use
        """
    )

    parser.add_argument('--calendar-id',
                       help='Correct Google Calendar ID (NOT OAuth Client ID)')
    parser.add_argument('--feed-url',
                       help='MuSpy Atom feed URL')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without creating events')
    parser.add_argument('--list-calendars', action='store_true',
                       help='List available calendars with correct IDs')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Cargar configuración
        feed_url = args.feed_url or os.getenv('MUSPY_FEED_URL', 'https://muspy.com/feed?id=rvy1q943dvxvelrwvmmnxzk6ownko6')
        calendar_id = args.calendar_id or os.getenv('GOOGLE_CALENDAR_ID')

        print("🔧 Google Calendar MuSpy Sync - ERROR 404 FIXED VERSION")
        print("=" * 65)

        # 🔧 VALIDACIÓN PREVIA del Calendar ID si se proporciona
        if calendar_id and '.apps.googleusercontent.com' in calendar_id:
            print(f"❌ ERROR: You provided an OAuth Client ID as Calendar ID!")
            print(f"   Provided: {calendar_id}")
            print(f"   This is what caused your 404 errors!")
            print(f"   ℹ️  Calendar IDs look like: your-email@gmail.com")
            print(f"   🔧 Run: python google_calendar_id_finder.py")
            return

        # Inicializar sincronizador con detección automática
        logger.info("🚀 Initializing Google Calendar sync with auto-detection...")
        syncer = GoogleCalendarMuSpySyncFixed(calendar_id=calendar_id)

        # Listar calendarios si se solicita
        if args.list_calendars:
            syncer.list_available_calendars()
            print(f"\n💡 To use a specific calendar:")
            print(f"   python {parser.prog} --calendar-id 'CALENDAR_ID_FROM_ABOVE'")
            return

        # Parsear feed de MuSpy
        releases = syncer.parse_atom_feed(feed_url)

        if not releases:
            logger.warning("⚠️  No releases found in feed")
            return

        # Crear eventos de música
        stats = syncer.create_music_events(releases, dry_run=args.dry_run)

        if stats['failed'] == 0:
            if args.dry_run:
                logger.info("✅ Dry run completed - no 404 errors detected!")
            else:
                logger.info("✅ Sync completed successfully - 404 error fixed!")
        else:
            logger.warning("⚠️  Some events failed - check Calendar ID if you got 404 errors")

    except KeyboardInterrupt:
        logger.info("\n❌ Sync interrupted by user")
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")

        # Ayuda específica para errores comunes
        if "Invalid Calendar ID" in str(e):
            print(f"\n🔧 SOLUTION FOR YOUR ERROR:")
            print(f"   1. Run: python google_calendar_id_finder.py")
            print(f"   2. Copy the correct Calendar ID from the output")
            print(f"   3. Run this script again with --calendar-id 'CORRECT_ID'")

        if args.verbose:
            import traceback
            traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
