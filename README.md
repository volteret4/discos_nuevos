# discospatitunaitunai

Con estos scripts puedes añadir los discos nuevos de los artistas que sigas en muspy a tu calendario

# Requisitos

- Cuenta en muspy.con
- Calendario en google, caldav o aplicación que acepte `.ics`
- python 3
- Paquetes python

# Preparativos

## Crea una cuenta en muspy

Accede a muspy.com, y una vez obtengas tu cuenta, haz click derecho en el icono RSS y copia el enlace. En este puedes obtener tu id de muspy para usar mas tarde

## Añade artistas

Puedes usar la pagina de muspy para sincronizar una cantidad especifica de tus artistas mas escuchados en lastfm o añadir manualmente

## Credenciales

Tienes varis opciones para pasar las credenciales, `--flags`, variables de entorno o un archivo `.env`. Por ese orden

### Usando `--flags`

#### Caldav

```bash
python add_releases_caldav.py \
    --caldav-url "https://nextcloud.example.com/remote.php/dav/calendars/user/music/" \
    --username "myuser" \
    --password "mypassword" \
    --calendar-name "music_releases" \
    --atom-feed-url "https://muspy.com/feed?id=abcd1234"
# opcionales
    --no-cleanup # sin eliminar duplicados wtf
    --help # i need somebody
    --quiet  # ideal para crontab sin logs
```

#### ICS

```bash
python add_releases_ics.py \
    --atom-feed-url "https://muspy.com/feed?id=abcd1234" \
    --output-filename "my_music_releases.ics" \
    --calendar-name "My Music Calendar"
    # opcionales
    --quiet # ideal para crontab sin logs
    --output-filename "releases_$(date +%Y%m%d_%H%M%S).ics"
```

#### Google

##### Uso básico con OAuth2

```bash
python add_releases_google_calendar.py \
    --atom-feed-url "https://muspy.com/feed?id=abcd1234" \
    --calendar-id "your_email@gmail.com" \
    --auth-method oauth \
    --oauth-credentials-file "credentials.json"
    # opcionales
    --album-color 9 \ # colores personalizados
    --ep-color 10   # colores personalizados
    --quiet # ideal para crontab sin logs
```

##### Con Service Account

```bash
python add_releases_google_calendar.py \
    --atom-feed-url "https://muspy.com/feed?id=xyz" \
    --calendar-id "calendar@gmail.com" \
    --auth-method service_account \
    --service-account-file "service-key.json"
    # opcionales
    --album-color 9 \ # colores personalizados
    --ep-color 10   # colores personalizados
    --quiet # ideal para crontab sin logs
```

### Variables de entorno

```bash
# obligatorio
export ATOM_FEED_URL="https://muspy.com/feed?id=tu_feed_id"
# caldav
export CALDAV_URL="https://tu-servidor.com/path/"
export CALDAV_USERNAME="tu_usuario"
export CALDAV_PASSWORD="tu_password"
export CALENDAR_NAME="discos"
# ics
export ICS_OUTPUT_FILENAME="music_releases.ics"
# google
export GOOGLE_CALENDAR_ID="tu_email@gmail.com"
export GOOGLE_AUTH_METHOD="oauth"  # o "service_account"
export GOOGLE_OAUTH_CREDENTIALS_FILE="path/to/credentials.json"
```

Archivo `.env`

```bash
# obligatorio
ATOM_FEED_URL=
# spotify

# caldav
CALDAV_URL=
CALDAV_USERNAME=
CALDAV_PASSWORD=
CALENDAR_NAME=
# ics
ICS_OUTPUT_FILENAME=
# google
GOOGLE_CALENDAR_ID=
GOOGLE_AUTH_METHOD=
GOOGLE_OAUTH_CREDENTIALS_FILE=
```

# Instalación

Edita el archivo `requirements.txt` según los scripts que vayas a utilizar.

Instala los paquetes elegidos con:

```
pip install -f requirements.txt
```

# Añade discos al calendario

## Crea archivo `.cal`

Con el script `add_releases/add_releases_ics.py` [[Link]](https://github.com/volteret4/discos_nuevos/blob/main/add_releases/add_releases_ics.py)

## Sincroniza con un servidor caldav

Usando el script `add_releases/add_releases_caldav.py` [[Link]](https://github.com/volteret4/discos_nuevos/blob/main/add_releases/add_releases_caldav.py)

## Sincroniza con Google calendars

Si quieres usar el calendario principal de google usa tu dirección de gmail como id `example@gmail.com`.

Si quieres usar otro calendario tendrás que usar el script `add_releases/google/google_cal_id_finder.py` [[Link]](https://github.com/volteret4/discos_nuevos/blob/main/add_releases/google/google_cal_id_finder.py)

Luego puedes usar `add_releases/google/add_releases_google.py`para añadir discos al calendario de google que elijas. [[Link]](https://github.com/volteret4/discos_nuevos/blob/main/add_releases/google/add_releases_google.py)
