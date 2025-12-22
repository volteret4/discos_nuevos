#!/usr/bin/env python
"""
Google Calendar ID Finder
Encuentra los calendar IDs correctos y soluciona el error 404
"""

import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate_google_calendar():
    """Autenticación OAuth2 (mismo código que funciona)"""
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

def list_available_calendars():
    """
    Lista todos los calendarios disponibles con sus IDs correctos
    """
    try:
        creds = authenticate_google_calendar()
        service = build('calendar', 'v3', credentials=creds)

        print("🔍 FINDING YOUR CALENDAR IDs...")
        print("=" * 60)

        # Obtener lista de calendarios
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get('items', [])

        if not calendars:
            print("❌ No calendars found!")
            return None, None

        print(f"📅 Found {len(calendars)} calendar(s):\n")

        primary_calendar = None

        for i, calendar in enumerate(calendars, 1):
            calendar_id = calendar['id']
            summary = calendar['summary']
            access_role = calendar.get('accessRole', 'unknown')
            is_primary = calendar.get('primary', False)

            # Marcar calendario principal
            primary_marker = " ⭐ (PRIMARY)" if is_primary else ""

            print(f"{i}. {summary}{primary_marker}")
            print(f"   📧 Calendar ID: {calendar_id}")
            print(f"   🔐 Access: {access_role}")
            print(f"   🎨 Background: {calendar.get('backgroundColor', 'default')}")
            print()

            if is_primary:
                primary_calendar = calendar_id

        return service, calendars, primary_calendar

    except Exception as e:
        logger.error(f"❌ Error listing calendars: {e}")
        return None, None, None

def test_calendar_access(service, calendar_id, calendar_name):
    """
    Test si podemos acceder al calendario y crear eventos
    """
    try:
        print(f"🧪 Testing access to: {calendar_name}")
        print(f"   Calendar ID: {calendar_id}")

        # Test 1: Obtener calendario específico
        calendar_info = service.calendars().get(calendarId=calendar_id).execute()
        print(f"   ✅ Calendar accessible: {calendar_info['summary']}")

        # Test 2: Listar eventos recientes (solo lectura)
        from datetime import datetime, timedelta

        time_min = (datetime.now() - timedelta(days=7)).isoformat() + 'Z'
        time_max = (datetime.now() + timedelta(days=7)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print(f"   ✅ Can read events: {len(events)} events in last/next 7 days")

        return True

    except Exception as e:
        print(f"   ❌ Cannot access calendar: {e}")
        return False

def create_test_music_event(service, calendar_id):
    """
    Crear evento de prueba para música
    """
    try:
        from datetime import datetime, timedelta

        # Evento para mañana
        tomorrow = datetime.now() + timedelta(days=1)

        # Evento de día completo (como los releases de música)
        event = {
            'summary': '💿 Test Music Release',
            'description': 'Test event created by MuSpy Calendar integration\n\nArtist: Test Artist\nAlbum: Test Album\nGenre: Test Genre',
            'start': {
                'date': tomorrow.strftime('%Y-%m-%d'),  # Fecha sin hora = todo el día
            },
            'end': {
                'date': tomorrow.strftime('%Y-%m-%d'),
            },
            'colorId': '10',  # Verde para releases
        }

        print(f"🎵 Creating test music event...")
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()

        print(f"   ✅ Event created successfully!")
        print(f"   📅 Event: {created_event['summary']}")
        print(f"   📅 Date: {tomorrow.strftime('%Y-%m-%d')}")
        print(f"   🆔 Event ID: {created_event['id']}")

        if 'htmlLink' in created_event:
            print(f"   🔗 Link: {created_event['htmlLink']}")

        return created_event['id']

    except Exception as e:
        print(f"   ❌ Failed to create event: {e}")
        return None

def delete_test_event(service, calendar_id, event_id):
    """
    Eliminar evento de prueba
    """
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        print(f"   🗑️  Test event deleted")
        return True
    except Exception as e:
        print(f"   ❌ Error deleting event: {e}")
        return False

def show_calendar_usage_example(calendar_id):
    """
    Mostrar código de ejemplo con el calendar ID correcto
    """
    print(f"\n" + "="*60)
    print("📝 CODE EXAMPLE WITH CORRECT CALENDAR ID")
    print("="*60)

    code_example = f'''
# Ejemplo corregido para crear eventos de música
def create_music_release_event(service, release_info):
    """Crear evento de release musical"""

    # CALENDAR ID CORRECTO:
    calendar_id = "{calendar_id}"  # ✅ Este es el correcto!

    event = {{
        'summary': f"💿 {{release_info['artist']}} - {{release_info['album']}}",
        'description': f"New music release\\n\\nArtist: {{release_info['artist']}}\\nAlbum: {{release_info['album']}}\\nSource: MuSpy",
        'start': {{
            'date': release_info['date'],  # Formato: YYYY-MM-DD
        }},
        'end': {{
            'date': release_info['date'],
        }},
        'colorId': '10',  # Verde para releases
    }}

    try:
        created_event = service.events().insert(
            calendarId=calendar_id,  # ✅ Usar este ID
            body=event
        ).execute()

        print(f"✅ Created: {{created_event['summary']}}")
        return created_event

    except Exception as e:
        print(f"❌ Error: {{e}}")
        return None

# Ejemplo de uso:
release = {{
    'artist': 'Aidan Baker',
    'album': 'Trzecia (Drugi)',
    'date': '2024-12-23'
}}

create_music_release_event(service, release)
'''

    print(code_example)

    # También mostrar como variable de entorno
    print(f"\n💡 TIP: Save this Calendar ID as environment variable:")
    print(f"   export GOOGLE_CALENDAR_ID='{calendar_id}'")
    print(f"   # Or add to .env file:")
    print(f"   GOOGLE_CALENDAR_ID={calendar_id}")

def main():
    """
    Función principal para identificar calendarios y solucionar el error 404
    """
    print("🗓️  Google Calendar ID Finder & 404 Error Fixer")
    print("="*55)

    # Verificar archivos necesarios
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found!")
        return

    # Listar calendarios disponibles
    result = list_available_calendars()
    if not result[0]:
        return

    service, calendars, primary_calendar = result

    # Si solo hay un calendario, usar ese
    if len(calendars) == 1:
        selected_calendar = calendars[0]
        print(f"📌 Using only available calendar: {selected_calendar['summary']}")
    else:
        # Preguntar qué calendario usar
        print(f"🎯 Which calendar do you want to use for music releases?")

        # Sugerir el calendario principal por defecto
        default_choice = 1
        for i, cal in enumerate(calendars, 1):
            if cal.get('primary'):
                default_choice = i
                break

        while True:
            try:
                choice = input(f"\nSelect calendar (1-{len(calendars)}, default {default_choice}): ").strip()

                if not choice:
                    choice = default_choice
                else:
                    choice = int(choice)

                if 1 <= choice <= len(calendars):
                    selected_calendar = calendars[choice - 1]
                    break
                else:
                    print(f"❌ Please enter a number between 1 and {len(calendars)}")
            except ValueError:
                print("❌ Please enter a valid number")

    calendar_id = selected_calendar['id']
    calendar_name = selected_calendar['summary']

    print(f"\n🎯 SELECTED CALENDAR:")
    print(f"   Name: {calendar_name}")
    print(f"   ID: {calendar_id}")

    # Test de acceso
    print(f"\n🧪 TESTING CALENDAR ACCESS:")
    access_ok = test_calendar_access(service, calendar_id, calendar_name)

    if not access_ok:
        print("\n❌ Cannot access the selected calendar!")
        return

    # Test de creación de evento
    print(f"\n🎵 TESTING EVENT CREATION:")

    create_test = input("Create a test music event? (Y/n): ").lower()
    if not create_test.startswith('n'):
        event_id = create_test_music_event(service, calendar_id)

        if event_id:
            delete_test = input("\nDelete test event? (Y/n): ").lower()
            if not delete_test.startswith('n'):
                delete_test_event(service, calendar_id, event_id)

    # Mostrar código de ejemplo
    show_calendar_usage_example(calendar_id)

    print(f"\n🎉 SUCCESS! Use this Calendar ID in your scripts:")
    print(f"   📧 {calendar_id}")

if __name__ == "__main__":
    main()
