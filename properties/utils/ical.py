# properties/utils/ical.py
import requests
from icalendar import Calendar, Event
from datetime import datetime, timedelta, date
from django.utils.timezone import make_aware, now, is_aware
from urllib.parse import urlparse
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Configuración de seguridad para fetch de iCal
ICAL_REQUEST_TIMEOUT = getattr(settings, 'ICAL_REQUEST_TIMEOUT', 10)  # segundos
ICAL_MAX_SIZE = getattr(settings, 'ICAL_MAX_SIZE', 5 * 1024 * 1024)  # 5 MB
ICAL_ALLOWED_HOSTS = getattr(settings, 'ICAL_ALLOWED_HOSTS', [
    'airbnb.com',
    'airbnb.es',
    'airbnb.mx',
    'calendar.google.com',
    'booking.com',
    'vrbo.com',
    'homeaway.com',
])

def fetch_ical_bookings(ical_url):
    """
    Obtiene reservas de un calendario iCal externo de forma segura.

    Protecciones implementadas:
    - Validación de URL (solo HTTP/HTTPS)
    - Whitelist de hosts permitidos
    - Timeout de conexión
    - Límite de tamaño de respuesta
    - Logging de errores

    Args:
        ical_url: URL del calendario iCal

    Returns:
        list: Lista de tuplas (start_date, end_date)

    Raises:
        ValueError: Si la URL es inválida o el host no está permitido
        requests.exceptions.RequestException: Si hay error en la petición
    """
    # 1. Validar que sea una URL válida
    try:
        parsed_url = urlparse(ical_url)
    except Exception as e:
        logger.error(f"Invalid URL format: {ical_url[:100]}, error: {e}")
        raise ValueError(f"Formato de URL inválido: {e}")

    # 2. Validar esquema (solo http/https)
    if parsed_url.scheme not in ['http', 'https']:
        logger.warning(f"Invalid URL scheme: {parsed_url.scheme} for URL: {ical_url[:100]}")
        raise ValueError(f"El esquema de URL debe ser http o https, no '{parsed_url.scheme}'")

    # 3. Validar que el host esté en la whitelist
    host = parsed_url.netloc.lower()
    if not host:
        raise ValueError("URL sin host válido")

    # Verificar si el host o alguno de sus dominios padre está en la whitelist
    host_allowed = False
    for allowed_host in ICAL_ALLOWED_HOSTS:
        if host == allowed_host or host.endswith('.' + allowed_host):
            host_allowed = True
            break

    if not host_allowed:
        logger.warning(f"Host not in whitelist: {host} for URL: {ical_url[:100]}")
        raise ValueError(
            f"El host '{host}' no está en la lista de proveedores permitidos. "
            f"Hosts permitidos: {', '.join(ICAL_ALLOWED_HOSTS)}"
        )

    # 4. Hacer la petición con protecciones
    try:
        logger.info(f"Fetching iCal from {host}: {ical_url[:100]}...")

        response = requests.get(
            ical_url,
            timeout=ICAL_REQUEST_TIMEOUT,
            stream=True,  # Stream para verificar tamaño antes de descargar todo
            headers={
                'User-Agent': 'ReyesEstancias/1.0 (Calendar Sync)',
                'Accept': 'text/calendar, application/octet-stream, */*',
            },
            allow_redirects=True,  # Permite redirects (max 30 por defecto)
            max_redirects=5,  # Limitar redirects
        )
        response.raise_for_status()

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching iCal from {host}: {ical_url[:100]}")
        raise ValueError(f"Timeout al obtener el calendario de {host} (>{ICAL_REQUEST_TIMEOUT}s)")

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error fetching iCal from {host}: {e}")
        raise ValueError(f"Error de conexión al obtener el calendario de {host}")

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error fetching iCal from {host}: {e.response.status_code}")
        raise ValueError(f"Error HTTP {e.response.status_code} al obtener el calendario")

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching iCal from {host}: {e}")
        raise ValueError(f"Error al obtener el calendario: {e}")

    # 5. Verificar tamaño del contenido
    content_length = response.headers.get('content-length')
    if content_length and int(content_length) > ICAL_MAX_SIZE:
        logger.warning(f"iCal file too large: {content_length} bytes from {host}")
        raise ValueError(
            f"El archivo de calendario es demasiado grande "
            f"({int(content_length) / 1024 / 1024:.1f} MB, máximo {ICAL_MAX_SIZE / 1024 / 1024} MB)"
        )

    # 6. Leer contenido con límite
    try:
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > ICAL_MAX_SIZE:
                logger.warning(f"iCal content exceeded max size while reading from {host}")
                raise ValueError(
                    f"El archivo de calendario excede el tamaño máximo permitido "
                    f"({ICAL_MAX_SIZE / 1024 / 1024} MB)"
                )
    finally:
        response.close()

    # 7. Parsear el calendario
    try:
        calendar = Calendar.from_ical(content)
    except Exception as e:
        logger.error(f"Error parsing iCal from {host}: {e}")
        raise ValueError(f"Error al parsear el calendario: formato inválido")

    # 8. Extraer reservas
    bookings = []
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue

        try:
            start = component.get("dtstart").dt
            end = component.get("dtend").dt

            # Convertir datetime a date si es necesario
            if isinstance(start, datetime):
                if not is_aware(start):
                    start = make_aware(start)
                start = start.date()
            elif not isinstance(start, date):
                logger.warning(f"Invalid start date type: {type(start)}")
                continue

            if isinstance(end, datetime):
                if not is_aware(end):
                    end = make_aware(end)
                end = end.date()
            elif not isinstance(end, date):
                logger.warning(f"Invalid end date type: {type(end)}")
                continue

            bookings.append((start, end))

        except Exception as e:
            # Si un evento individual falla, log y continuar
            logger.warning(f"Error parsing iCal event from {host}: {e}")
            continue

    logger.info(f"Successfully fetched {len(bookings)} bookings from {host}")
    return bookings

def get_blocked_dates(ical_url):
    ranges = fetch_ical_bookings(ical_url)
    blocked = set()

    for start, end in ranges:
        current = start
        while current < end:
            blocked.add(current)
            current += timedelta(days=1)

    return sorted(blocked)

def generate_ical_for_property(property_obj):
    """
    Genera un calendario iCal con las reservas confirmadas de una propiedad.

    Args:
        property_obj: Instancia de Property

    Returns:
        Calendar: Objeto icalendar.Calendar listo para serializar
    """
    # Crear calendario
    cal = Calendar()
    cal.add('prodid', '-//Reyes Estancias//Calendario de Reservas//ES')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', f'Reservas - {property_obj.name}')
    cal.add('x-wr-timezone', 'America/Mexico_City')

    # Obtener reservas confirmadas
    confirmed_bookings = property_obj.bookings.filter(status='confirmed').order_by('arrival')

    # Crear eventos para cada reserva
    for booking in confirmed_bookings:
        event = Event()

        # Campos obligatorios
        event.add('dtstart', booking.arrival)
        event.add('dtend', booking.departure)
        event.add('dtstamp', now())
        event.add('summary', 'Reservado')
        event.add('uid', f'booking_{booking.id}@reyesestancias.com')

        # Campos opcionales pero recomendados
        event.add('status', 'CONFIRMED')
        event.add('transp', 'OPAQUE')  # Marca como ocupado
        event.add('description', f'Reserva confirmada para {booking.person_num} persona(s)')

        cal.add_component(event)

    return cal
