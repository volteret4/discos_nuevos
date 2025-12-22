#!/usr/bin/env python
#
# Script Name: add_releases_ics.py
# Description: Crear archivo ICS con los nuevos discos que ofrece el rss de muspy
# Author: volteret4
# Repository: https://github.com/volteret4/
# License:
# Notes:
#   Dependencies:  - python3, icalendar, dotenv, feedparser
#

import requests
import feedparser
import re
from datetime import datetime, timezone, date
from icalendar import Event, Calendar
from dotenv import load_dotenv
import os
import getpass
import argparse


def parse_command_line():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='🎵 Music Release ICS Calendar Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --atom-feed-url https://muspy.com/feed?id=123 --output-filename releases.ics
  %(prog)s --atom-feed-url https://muspy.com/feed?id=123
  %(prog)s --help
        """
    )

    parser.add_argument(
        '--atom-feed-url',
        help='MuSpy Atom feed URL',
        metavar='URL'
    )

    parser.add_argument(
        '--output-filename',
        help='Output ICS filename (default: music_releases.ics)',
        metavar='FILENAME',
        default='music_releases.ics'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='ICS Music Calendar v2.0'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Run in quiet mode (minimal output)'
    )

    parser.add_argument(
        '--calendar-name',
        help='Calendar name for the ICS file (default: Music Releases)',
        default='Music Releases',
        metavar='NAME'
    )

    parser.add_argument(
        '--overwrite', '-f',
        action='store_true',
        help='Overwrite output file if it exists'
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
        'atom_feed_url': 'ATOM_FEED_URL',
        'output_filename': 'ICS_OUTPUT_FILENAME'
    }

    # Store additional options
    credentials['quiet'] = args.quiet
    credentials['calendar_name'] = args.calendar_name
    credentials['overwrite'] = args.overwrite

    # Check command line arguments first
    if not args.quiet:
        print("Checking command line arguments...")
    cmd_args = {
        'atom_feed_url': args.atom_feed_url,
        'output_filename': args.output_filename
    }

    for key, value in cmd_args.items():
        if value and value != 'music_releases.ics':  # Don't count default value
            credentials[key] = value
            if not args.quiet:
                print(f"  ✓ {key} loaded from command line argument")
        elif key == 'output_filename' and value:
            credentials[key] = value  # Use default value

    # Intentar cargar desde variables de entorno para las que faltan
    missing_credentials = [k for k in required_credentials.keys() if k not in credentials]
    if missing_credentials and not args.quiet:
        print("\nChecking environment variables...")

    for key in missing_credentials:
        env_var = required_credentials[key]
        value = os.getenv(env_var)
        if value:
            credentials[key] = value
            if not args.quiet:
                print(f"  ✓ {key} loaded from environment variable {env_var}")

    # Si faltan credenciales, intentar cargar desde .env
    missing_credentials = [k for k in required_credentials.keys() if k not in credentials]
    if missing_credentials:
        if not args.quiet:
            print("\nSome credentials missing, attempting to load .env file...")
        try:
            load_dotenv()
            for key in missing_credentials:
                env_var = required_credentials[key]
                value = os.getenv(env_var)
                if value:
                    credentials[key] = value
                    if not args.quiet:
                        print(f"  ✓ {key} loaded from .env file")
        except Exception as e:
            if not args.quiet:
                print(f"  Warning: Could not load .env file: {e}")

    # Para las credenciales que aún faltan, usar valores por defecto o preguntar interactivamente
    still_missing = [k for k in required_credentials.keys() if k not in credentials]
    if still_missing:
        if not args.quiet:
            print("\nSome credentials still missing. Using defaults or asking interactively:")

        for key in still_missing:
            if key == 'output_filename':
                # Valor por defecto para el archivo de salida
                credentials[key] = "music_releases.ics"
                if not args.quiet:
                    print(f"  ✓ {key} set to default: {credentials[key]}")
            elif key == 'atom_feed_url':
                # Preguntar por el feed URL
                credentials[key] = input('Atom Feed URL: ').strip()
                if credentials[key]:
                    if not args.quiet:
                        print(f"  ✓ {key} provided interactively")
                else:
                    print(f"  ✗ {key} cannot be empty!")
                    raise ValueError(f"Required credential '{key}' was not provided")

    if not args.quiet:
        print("\n✅ All credentials loaded successfully!\n")

    return credentials


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
            formatted_title = f"🎤 {title}"
        else:  # Album
            formatted_title = f"💿 {title}"

        releases.append({
            "title": formatted_title,
            "release_date": release_date,
            "original_title": title,
            "release_type": release_type
        })

    return releases


def create_ics_file(releases, output_filename, calendar_name='Music Releases', quiet=False, overwrite=False):
    """Create an ICS file with all the release events."""

    # Check if file exists and overwrite flag
    if os.path.exists(output_filename) and not overwrite:
        if not quiet:
            print(f"⚠️  File '{output_filename}' already exists. Use --overwrite to overwrite.")
        response = input("Overwrite existing file? [y/N]: ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Operation cancelled")
            return False

    # Crear el calendario
    calendar = Calendar()
    calendar.add('prodid', '-//Music Releases Calendar//volteret4//EN')
    calendar.add('version', '2.0')
    calendar.add('calscale', 'GREGORIAN')
    calendar.add('method', 'PUBLISH')
    calendar.add('x-wr-calname', calendar_name)
    calendar.add('x-wr-caldesc', f'Calendar of music album and EP releases from MuSpy - {calendar_name}')

    # Contador de eventos añadidos
    events_added = 0

    for release in releases:
        # Crear evento
        event = Event()
        event.add('summary', release["title"])

        # Para eventos de todo el día, usar solo la fecha
        event.add('dtstart', release["release_date"])
        event.add('dtend', release["release_date"])

        # Marcar como evento de todo el día
        event['dtstart'].params['VALUE'] = 'DATE'
        event['dtend'].params['VALUE'] = 'DATE'

        # Añadir descripción
        description = f"Release Date for {release['original_title']} ({release['release_type']})"
        event.add('description', description)

        # Añadir UID único
        uid = f"music-release-{release['release_date']}-{hash(release['original_title'])}@volteret4"
        event.add('uid', uid)

        # Añadir timestamp de creación
        event.add('dtstamp', datetime.now(timezone.utc))

        # Añadir categorías
        event.add('categories', f'Music,{release["release_type"]}')

        # Añadir al calendario
        calendar.add_component(event)
        events_added += 1
        if not quiet:
            print(f"Added event: {release['title']} ({release['release_date']})")

    # Guardar el archivo ICS
    try:
        with open(output_filename, 'wb') as f:
            f.write(calendar.to_ical())
        if not quiet:
            print(f"\n✅ Successfully created ICS file: {output_filename}")
            print(f"📊 Total events added: {events_added}")
        return True
    except Exception as e:
        print(f"❌ Error creating ICS file: {e}")
        return False


def save_credentials_template():
    """
    Create a .env template file with all required variables for ICS version.
    """
    template_content = """# ICS File Configuration
# Copy this file to .env and fill in your values

# Atom Feed URL from MuSpy
ATOM_FEED_URL=https://muspy.com/feed?id=your_feed_id_here

# Output ICS filename (optional, defaults to music_releases.ics)
ICS_OUTPUT_FILENAME=music_releases.ics
"""

    try:
        with open('.env.template.ics', 'w', encoding='utf-8') as f:
            f.write(template_content)
        print("📝 Created .env.template.ics file with required variables")
        return True
    except Exception as e:
        print(f"Warning: Could not create .env.template.ics: {e}")
        return False


if __name__ == "__main__":
    try:
        # Obtener credenciales usando el sistema de fallback
        creds = get_credentials()

        quiet_mode = creds.get('quiet', False)
        calendar_name = creds.get('calendar_name', 'Music Releases')
        overwrite = creds.get('overwrite', False)

        # Extraer las credenciales del diccionario
        atom_feed_url = creds['atom_feed_url']
        output_filename = creds['output_filename']

        if not quiet_mode:
            print("🎵 Music Release ICS Calendar Generator")
            print("=" * 50)

            # Mostrar configuración
            print("📋 Configuration:")
            print(f"  • Atom Feed URL: {atom_feed_url}")
            print(f"  • Output File: {output_filename}")
            print(f"  • Calendar Name: {calendar_name}")
            if overwrite:
                print("  • Overwrite: Enabled")
            print()

        # Parsear el feed Atom
        if not quiet_mode:
            print("📡 Parsing Atom feed...")
        releases = parse_atom_feed(atom_feed_url)
        if not quiet_mode:
            print(f"Found {len(releases)} releases to process")

        if not releases:
            message = "⚠️ No releases found in the feed."
            if quiet_mode:
                print("No releases found")
            else:
                print(message)
            exit(0)

        # Crear archivo ICS
        if not quiet_mode:
            print("\n📅 Creating ICS calendar file...")
        success = create_ics_file(releases, output_filename, calendar_name, quiet_mode, overwrite)

        if success:
            if not quiet_mode:
                print(f"\n🎉 ICS file created successfully!")
                print(f"📁 You can import '{output_filename}' into any calendar application")
                print("   (Google Calendar, Apple Calendar, Outlook, Thunderbird, etc.)")
            else:
                print(f"✅ Created {output_filename} with {len(releases)} releases")
        else:
            print("\n❌ Failed to create ICS file")
            exit(1)

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("\n💡 Tip: You can use command line arguments or set up a .env file.")
        print("💡 Use --help for more information about available arguments.")
        save_credentials_template()
        exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        exit(1)
