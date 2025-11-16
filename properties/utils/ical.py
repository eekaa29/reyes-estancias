# properties/utils/ical.py
import requests
from icalendar import Calendar
from datetime import datetime, timedelta, date
from django.utils.timezone import make_aware

def fetch_ical_bookings(ical_url):
    r = requests.get(ical_url)
    r.raise_for_status()

    calendar = Calendar.from_ical(r.content)
    bookings = []

    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        start = component.get("dtstart").dt
        end = component.get("dtend").dt

        if isinstance(start, datetime): start = make_aware(start).date()
        elif isinstance(start, date): start = start

        if isinstance(end, datetime): end = make_aware(end).date()
        elif isinstance(end, date): end = end

        bookings.append((start, end))
    
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
