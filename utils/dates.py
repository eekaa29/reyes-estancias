from datetime import datetime, time
from django.utils import timezone

CHECKIN_TIME = time(15, 0)   # 15:00
CHECKOUT_TIME = time(12, 0)  # 12:00

def compose_aware_dt(date_obj, clock_time):
    """
    Combina una fecha (date) con una hora (time) y la convierte a datetime 'aware'
    según TIME_ZONE / USE_TZ de Django.
    """
    naive = datetime.combine(date_obj, clock_time)
    return timezone.make_aware(naive, timezone.get_current_timezone())
