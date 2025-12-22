#!/usr/bin/env python
#
# Script Name: add_release_calendar.py
# Description: Actualizar calendario caldav con los nuevos discos que ofrece el rss de muspy
# Author: volteret4
# Repository: https://github.com/volteret4/
# License:
# Notes:
#   Dependencies:  - python3, caldav, dotenv, feedparser
#

import requests
import feedparser
import re
from datetime import datetime, timezone, date
from caldav import DAVClient
from icalendar import Event, Calendar
from dotenv import load_dotenv
import os
import getpass
import argparse


def parse_command_line():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='🎵 CalDAV Music Release Calendar Updater',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --caldav-url https://server.com/cal/ --username user --password pass --calendar-name music --atom-feed-url https://muspy.com/feed?id=123
  %(prog)s --help
        """
    )

    parser.add_argument(
        '--caldav-url',
        help='CalDAV server URL',
        metavar='URL'
    )

    parser.add_argument(
        '--username',
        help='CalDAV username',
        metavar='USER'
    )

    parser.add_argument(
        '--password',
        help='CalDAV password',
        metavar='PASS'
    )

    parser.add_argument(
        '--calendar-name',
        help='Calendar name',
        metavar='NAME'
    )

    parser.add_argument(
        '--atom-feed-url',
        help='MuSpy Atom feed URL',
        metavar='URL'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='CalDAV Music Calendar v2.0'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Run in quiet mode (minimal output)'
    )

    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip duplicate cleanup phase'
    )

    return parser.parse_args()


def get_credentials():
    """
    Get credentials using a fallback system:
    1. Command line arguments
    2. Environment variables
    3. .env file (using python-dotenv)
    4. Interactive prompts

    Returns a dictionary with all required credentials.
    """
    credentials = {}

    # Parse command line arguments first
    args = parse_command_line()

    # Definir las credenciales necesarias con sus nombres de variables de entorno
    required_credentials = {
        'caldav_url': 'CALDAV_URL',
        'username': 'CALDAV_USERNAME',
        'password': 'CALDAV_PASSWORD',
        'calendar_name': 'CALENDAR_NAME',
        'atom_feed_url': 'ATOM_FEED_URL'
    }

    # Store additional options
    credentials['quiet'] = args.quiet
    credentials['no_cleanup'] = args.no_cleanup

    # Check command line arguments first
    print("Checking command line arguments...")
    cmd_args = {
        'caldav_url': args.caldav_url,
        'username': args.username,
        'password': args.password,
        'calendar_name': args.calendar_name,
        'atom_feed_url': args.atom_feed_url
    }

    for key, value in cmd_args.items():
        if value:
            credentials[key] = value
            print(f"  ✓ {key} loaded from command line argument")

    # Intentar cargar desde variables de entorno para las que faltan
    missing_credentials = [k for k in required_credentials.keys() if k not in credentials]
    if missing_credentials:
        print("\nChecking environment variables...")
        for key in missing_credentials:
            env_var = required_credentials[key]
            value = os.getenv(env_var)
            if value:
                credentials[key] = value
                print(f"  ✓ {key} loaded from environment variable {env_var}")

    # Si faltan credenciales, intentar cargar desde .env
    missing_credentials = [k for k in required_credentials.keys() if k not in credentials]
    if missing_credentials:
        print("\nSome credentials missing, attempting to load .env file...")
        try:
            load_dotenv()
            for key in missing_credentials:
                env_var = required_credentials[key]
                value = os.getenv(env_var)
                if value:
                    credentials[key] = value
                    print(f"  ✓ {key} loaded from .env file")
        except Exception as e:
            print(f"  Warning: Could not load .env file: {e}")

    # Para las credenciales que aún faltan, preguntar interactivamente
    still_missing = [k for k in required_credentials.keys() if k not in credentials]
    if still_missing:
        print("\nSome credentials still missing. Please provide them interactively:")

        for key in still_missing:
            prompt_messages = {
                'caldav_url': 'CalDAV Server URL (e.g., https://your-server.com/path/): ',
                'username': 'CalDAV Username: ',
                'password': 'CalDAV Password: ',
                'calendar_name': 'Calendar Name: ',
                'atom_feed_url': 'Atom Feed URL: '
            }

            if key == 'password':
                # Usar getpass para ocultar la contraseña
                credentials[key] = getpass.getpass(prompt_messages[key])
            else:
                credentials[key] = input(prompt_messages[key]).strip()

            if credentials[key]:
                print(f"  ✓ {key} provided interactively")
            else:
                print(f"  ✗ {key} cannot be empty!")
                raise ValueError(f"Required credential '{key}' was not provided")

    if not credentials.get('quiet'):
        print("\n✅ All credentials loaded successfully!\n")

    return credentials


def save_credentials_template():
    """
    Create a .env template file with all required variables.
    """
    template_content = """# CalDAV Server Configuration
# Copy this file to .env and fill in your values

# CalDAV Server URL (e.g., https://your-server.com/path/)
CALDAV_URL=

# CalDAV Username
CALDAV_USERNAME=

# CalDAV Password
CALDAV_PASSWORD=

# Calendar Name
CALENDAR_NAME=

# Atom Feed URL from MuSpy
ATOM_FEED_URL=
"""

    try:
        with open('.env.template', 'w', encoding='utf-8') as f:
            f.write(template_content)
        print("📝 Created .env.template file with all required variables")
        return True
    except Exception as e:
        print(f"Warning: Could not create .env.template: {e}")
        return False

def determine_release_type(title):
    """Determine if the release is an album or EP based on the title."""
    title_lower = title.lower()

    # Common EP indicators
    ep_indicators = ['ep', ' - ep', 'extended play', 'mini album', 'single']

    for indicator in ep_indicators:
        if indicator in title_lower:
            return "EP"

    # Default to album if no EP indicators found
    return "Album"

def parse_atom_feed(feed_url):
    """Parse the Atom feed and extract album release information."""
    feed = feedparser.parse(feed_url)

    if feed.bozo:
        raise ValueError("Invalid feed format or malformed XML.")

    releases = []
    date_pattern = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")  # Match dates in YYYY-MM-DD format

    for entry in feed.entries:
        title = entry.title.strip()  # Limpiar espacios extra
        content = entry.summary

        # Search for date in the content
        match = date_pattern.search(content)
        if not match:
            print(f"Skipping entry with invalid date: {content}")
            continue

        release_date_str = match.group()
        try:
            release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"Skipping entry with unparsable date: {release_date_str}")
            continue

        # Determine release type and add appropriate icon
        release_type = determine_release_type(title)
        if release_type == "EP":
            formatted_title = f"ðŸŽ¤ {title}"
        else:  # Album
            formatted_title = f"ðŸ’¿ {title}"

        releases.append({"title": formatted_title, "release_date": release_date})

    return releases

def get_existing_events(calendar):
    """Retrieve existing events from the calendar to avoid duplicates."""
    existing_events = set()

    for event in calendar.events():
        try:
            cal = Calendar.from_ical(event.data)
            for component in cal.walk():
                if component.name == "VEVENT":
                    summary = str(component.get("SUMMARY")).strip()
                    dtstart = component.get("DTSTART").dt

                    # Convert datetime to date if necessary
                    if isinstance(dtstart, datetime):
                        dtstart = dtstart.date()

                    existing_events.add((summary, dtstart))
        except Exception as e:
            print(f"Error parsing existing event: {e}")

    return existing_events

def create_caldav_event(client_url, username, password, calendar_name, event_data):
    """Connect to CalDAV and create events if they do not already exist."""
    client = DAVClient(client_url, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()

    # Buscar el calendario por nombre
    calendar = next((c for c in calendars if c.name == calendar_name), None)
    if calendar is None:
        print(f"Calendar '{calendar_name}' not found. Creating a new one.")
        calendar = principal.make_calendar(name=calendar_name)

    # Obtener eventos existentes para evitar duplicados
    existing_events = get_existing_events(calendar)

    for event in event_data:
        event_title = event["title"].strip()
        event_date = event["release_date"]

        # Verificar si el evento ya existe
        if (event_title, event_date) in existing_events:
            print(f"Skipping duplicate event: {event_title} ({event_date})")
            continue

        # Crear nuevo evento de todo el dÃ­a
        cal_event = Event()
        cal_event.add("summary", event_title)

        # Para eventos de todo el dÃ­a, usar solo la fecha sin hora ni timezone
        cal_event.add("dtstart", event_date)
        cal_event.add("dtend", event_date)

        # Marcar como evento de todo el dÃ­a
        cal_event['dtstart'].params['VALUE'] = 'DATE'
        cal_event['dtend'].params['VALUE'] = 'DATE'

        cal_event.add("description", f"Release Date for {event_title}")

        calendar.save_event(cal_event.to_ical())
        print(f"Added all-day event: {event_title} ({event_date})")

# ELIMINAR DUPLICADOS
def get_calendar(client_url, username, password, calendar_name):
    """Connect to CalDAV and retrieve the calendar."""
    client = DAVClient(client_url, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()

    # Buscar el calendario por nombre
    calendar = next((c for c in calendars if c.name == calendar_name), None)
    if calendar is None:
        print(f"Calendar '{calendar_name}' not found.")
        return None

    return calendar

def find_duplicate_events(calendar):
    """Find duplicate events in the calendar."""
    events_by_key = {}  # Diccionario para almacenar eventos Ãºnicos (key = (title, date))
    duplicate_events = []  # Lista de eventos duplicados para eliminar

    for event in calendar.events():
        try:
            cal = Calendar.from_ical(event.data)
            for component in cal.walk():
                if component.name == "VEVENT":
                    title = str(component.get("SUMMARY"))
                    dtstart = component.get("DTSTART").dt

                    if isinstance(dtstart, datetime):
                        dtstart = dtstart.date()  # Convertir a objeto date

                    key = (title, dtstart)

                    if key in events_by_key:
                        duplicate_events.append(event)  # Marcar como duplicado
                    else:
                        events_by_key[key] = event  # Guardar como Ãºnico

        except Exception as e:
            print(f"Error parsing event: {e}")

    return duplicate_events

def remove_duplicate_events(calendar):
    """Remove duplicate events from the calendar."""
    duplicate_events = find_duplicate_events(calendar)

    if not duplicate_events:
        print("No duplicate events found.")
        return

    for event in duplicate_events:
        try:
            event.delete()
            print(f"Deleted duplicate event: {event.url}")
        except Exception as e:
            print(f"Error deleting event: {e}")


if __name__ == "__main__":
    try:
        # Obtener credenciales usando el sistema de fallback
        creds = get_credentials()

        quiet_mode = creds.get('quiet', False)
        no_cleanup = creds.get('no_cleanup', False)

        # Extraer las credenciales del diccionario
        atom_feed_url = creds['atom_feed_url']
        caldav_url = creds['caldav_url']
        username = creds['username']
        password = creds['password']
        calendar_name = creds['calendar_name']

        if not quiet_mode:
            print("🎵 CalDAV Music Release Calendar Updater")
            print("=" * 50)

            # Mostrar configuración (ocultando la contraseña)
            print("📋 Configuration:")
            print(f"  • Atom Feed URL: {atom_feed_url}")
            print(f"  • CalDAV URL: {caldav_url}")
            print(f"  • Username: {username}")
            print(f"  • Password: {'*' * len(password)}")
            print(f"  • Calendar Name: {calendar_name}")
            if no_cleanup:
                print("  • Cleanup: Disabled")
            print()

        # Parsear el feed Atom
        if not quiet_mode:
            print("📡 Parsing Atom feed...")
        releases = parse_atom_feed(atom_feed_url)
        if not quiet_mode:
            print(f"Found {len(releases)} releases to process")

        # Conectar a CalDAV y agregar eventos sin duplicados
        if not quiet_mode:
            print("📅 Connecting to CalDAV server...")
        create_caldav_event(caldav_url, username, password, calendar_name, releases)

        if not quiet_mode:
            print("✅ Events successfully processed!")

        # Limpiar duplicados (unless disabled)
        if not no_cleanup:
            if not quiet_mode:
                print("\n🧹 Cleaning up duplicate events...")
            calendar = get_calendar(caldav_url, username, password, calendar_name)

            if calendar:
                remove_duplicate_events(calendar)
                if not quiet_mode:
                    print("✅ Duplicate cleanup completed!")
            else:
                if not quiet_mode:
                    print("⚠️  Could not access calendar for duplicate cleanup")
        elif not quiet_mode:
            print("⏭️  Duplicate cleanup skipped (--no-cleanup flag)")

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\n💡 Tip: You can use command line arguments or set up a .env file.")
        print("💡 Use --help for more information about available arguments.")
        save_credentials_template()
        exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        exit(1)

    if not quiet_mode:
        print("\n🎉 Script completed successfully!")
    elif len(releases) > 0:
        print(f"✅ Processed {len(releases)} releases")
