from datetime import datetime, date
from zoneinfo import ZoneInfo
from django.utils.timezone import is_aware

MX_TZ = ZoneInfo("America/Mexico_City")

def compose_aware_dt(d, hour=0, minute=0, second=0, tz=MX_TZ):
    """
    d puede ser str 'YYYY-MM-DD', date o datetime.
    Devuelve un datetime *aware* en la zona 'tz' con la hora fija indicada.
    """
    if isinstance(d, str):
        d = datetime.strptime(d, "%Y-%m-%d").date()
    if isinstance(d, date) and not isinstance(d, datetime):
        dt = datetime(d.year, d.month, d.day, hour, minute, second)
    elif isinstance(d, datetime):
        dt = d.replace(hour=hour, minute=minute, second=second, microsecond=0)
    else:
        raise ValueError("Fecha inválida")

    if not is_aware(dt):
        dt = dt.replace(tzinfo=tz)
    return dt