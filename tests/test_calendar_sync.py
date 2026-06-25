"""
Tests de sincronización bidireccional de calendarios.

Cubre:
  - fetch_ical_bookings: caché, whitelist de hosts, errores HTTP, tamaño
  - generate_ical_for_property: qué reservas se incluyen en el .ics exportado
  - ExportCalendarView: token válido/inválido, contenido del .ics
  - Property.is_available: bloqueo por calendario externo (Airbnb → web)
  - sync_all_property_calendars: tarea Celery de sincronización masiva
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache as django_cache
from django.utils import timezone
from icalendar import Calendar
from model_bakery import baker

from properties.utils.ical import fetch_ical_bookings, generate_ical_for_property


@pytest.fixture(autouse=True)
def _clear_cache():
    """Limpia el caché de Django antes y después de cada test."""
    django_cache.clear()
    yield
    django_cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ical(events: list[tuple[date, date]]) -> bytes:
    """Construye un .ics mínimo con los rangos indicados."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Test//Test//EN",
    ]
    for i, (start, end) in enumerate(events):
        lines += [
            "BEGIN:VEVENT",
            f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
            f"UID:test-event-{i}@test.com",
            "SUMMARY:Reservado",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode()


def _mock_response(body: bytes, status_code: int = 200, content_length: int | None = None):
    """Devuelve un mock de requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {"content-length": str(content_length or len(body))}
    resp.iter_content = lambda chunk_size: iter([body])
    resp.raise_for_status = MagicMock()
    resp.close = MagicMock()
    if status_code >= 400:
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(response=resp)
    return resp


# ---------------------------------------------------------------------------
# fetch_ical_bookings — caché y validación de URL
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFetchIcalBookings:

    VALID_URL = "https://airbnb.com/calendar/ical/test.ics"

    def test_parsea_eventos_correctamente(self):
        today = date.today()
        body = _make_ical([(today, today + timedelta(days=3))])

        with patch("requests.get", return_value=_mock_response(body)):
            result = fetch_ical_bookings(self.VALID_URL)

        assert len(result) == 1
        start, end = result[0]
        assert start == today
        assert end == today + timedelta(days=3)

    def test_usa_cache_en_segunda_llamada(self):
        today = date.today()
        body = _make_ical([(today, today + timedelta(days=2))])

        with patch("requests.get", return_value=_mock_response(body)) as mock_get:
            fetch_ical_bookings(self.VALID_URL)
            fetch_ical_bookings(self.VALID_URL)

        # Solo debe haber hecho UNA petición HTTP real
        assert mock_get.call_count == 1

    def test_rechaza_host_no_permitido(self):
        with pytest.raises(ValueError, match="no está en la lista"):
            fetch_ical_bookings("https://malicious.com/cal.ics")

    def test_rechaza_esquema_no_http(self):
        with pytest.raises(ValueError, match="esquema"):
            fetch_ical_bookings("ftp://airbnb.com/cal.ics")

    def test_rechaza_url_sin_host(self):
        with pytest.raises(ValueError):
            fetch_ical_bookings("https:///sin-host.ics")

    def test_error_http_lanza_valueerror(self):
        with patch("requests.get", return_value=_mock_response(b"", status_code=404)):
            with pytest.raises(ValueError, match="Error HTTP"):
                fetch_ical_bookings(self.VALID_URL)

    def test_archivo_demasiado_grande_rechazado(self):
        oversized = 6 * 1024 * 1024  # 6 MB > límite de 5 MB
        resp = _mock_response(b"x", content_length=oversized)
        with patch("requests.get", return_value=resp):
            with pytest.raises(ValueError, match="grande"):
                fetch_ical_bookings(self.VALID_URL)

    def test_ical_malformado_lanza_valueerror(self):
        with patch("requests.get", return_value=_mock_response(b"NO_ES_ICAL")):
            with pytest.raises(ValueError, match="parsear"):
                fetch_ical_bookings(self.VALID_URL)

    def test_multiples_eventos(self):
        today = date.today()
        body = _make_ical([
            (today, today + timedelta(days=2)),
            (today + timedelta(days=10), today + timedelta(days=15)),
        ])
        with patch("requests.get", return_value=_mock_response(body)):
            result = fetch_ical_bookings(self.VALID_URL)

        assert len(result) == 2

    def test_acepta_subdominio_de_host_permitido(self):
        body = _make_ical([])
        with patch("requests.get", return_value=_mock_response(body)):
            result = fetch_ical_bookings("https://www.airbnb.com/calendar/ical/test.ics")
        assert result == []


# ---------------------------------------------------------------------------
# generate_ical_for_property — qué reservas exportamos
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateIcalForProperty:

    def _property(self):
        return baker.make("properties.Property", max_people=4, nightly_price="100.00")

    def _booking(self, prop, status, days_ahead=10, hold_delta=None):
        arrival = timezone.now() + timedelta(days=days_ahead)
        departure = arrival + timedelta(days=3)
        hold = timezone.now() + timedelta(hours=hold_delta) if hold_delta is not None else None
        return baker.make(
            "bookings.Booking",
            property=prop,
            status=status,
            arrival=arrival,
            departure=departure,
            person_num=2,
            hold_expires_at=hold,
        )

    def _uids(self, prop):
        cal = generate_ical_for_property(prop)
        return {str(c.get("uid")) for c in cal.walk() if c.name == "VEVENT"}

    def test_confirmed_siempre_se_exporta(self):
        prop = self._property()
        b = self._booking(prop, "confirmed")
        assert f"booking_{b.id}@reyesestancias.com" in self._uids(prop)

    def test_pending_con_hold_activo_se_exporta(self):
        prop = self._property()
        b = self._booking(prop, "pending", hold_delta=2)  # expira en 2 horas
        assert f"booking_{b.id}@reyesestancias.com" in self._uids(prop)

    def test_pending_con_hold_expirado_no_se_exporta(self):
        prop = self._property()
        b = self._booking(prop, "pending", hold_delta=-1)  # ya expiró
        assert f"booking_{b.id}@reyesestancias.com" not in self._uids(prop)

    def test_pending_sin_hold_no_se_exporta(self):
        prop = self._property()
        b = self._booking(prop, "pending", hold_delta=None)
        assert f"booking_{b.id}@reyesestancias.com" not in self._uids(prop)

    def test_cancelled_no_se_exporta(self):
        prop = self._property()
        b = self._booking(prop, "cancelled")
        assert f"booking_{b.id}@reyesestancias.com" not in self._uids(prop)

    def test_completed_no_se_exporta(self):
        prop = self._property()
        b = self._booking(prop, "completed")
        assert f"booking_{b.id}@reyesestancias.com" not in self._uids(prop)

    def test_propiedad_sin_reservas_genera_calendario_vacio(self):
        prop = self._property()
        cal = generate_ical_for_property(prop)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert events == []

    def test_multiples_reservas_todas_incluidas(self):
        prop = self._property()
        b1 = self._booking(prop, "confirmed", days_ahead=5)
        b2 = self._booking(prop, "confirmed", days_ahead=20)
        b3 = self._booking(prop, "pending", days_ahead=35, hold_delta=2)
        uids = self._uids(prop)
        assert f"booking_{b1.id}@reyesestancias.com" in uids
        assert f"booking_{b2.id}@reyesestancias.com" in uids
        assert f"booking_{b3.id}@reyesestancias.com" in uids

    def test_ical_exportado_es_parseable(self):
        prop = self._property()
        self._booking(prop, "confirmed")
        raw = generate_ical_for_property(prop).to_ical()
        parsed = Calendar.from_ical(raw)
        events = [c for c in parsed.walk() if c.name == "VEVENT"]
        assert len(events) == 1

    def test_dtstart_y_dtend_son_correctos(self):
        prop = self._property()
        arrival = timezone.now() + timedelta(days=10)
        departure = arrival + timedelta(days=3)
        b = baker.make(
            "bookings.Booking",
            property=prop,
            status="confirmed",
            arrival=arrival,
            departure=departure,
            person_num=2,
        )
        cal = generate_ical_for_property(prop)
        events = [c for c in cal.walk() if c.name == "VEVENT"]
        assert len(events) == 1
        assert events[0].get("dtstart").dt == arrival
        assert events[0].get("dtend").dt == departure


# ---------------------------------------------------------------------------
# ExportCalendarView — endpoint público /properties/calendar/<token>/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestExportCalendarView:

    def test_token_valido_devuelve_200_y_content_type_ics(self, client):
        prop = baker.make("properties.Property", max_people=2, nightly_price="80.00")
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        assert resp.status_code == 200
        assert "text/calendar" in resp["Content-Type"]

    def test_contenido_es_vcalendar_valido(self, client):
        prop = baker.make("properties.Property", max_people=2, nightly_price="80.00")
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        cal = Calendar.from_ical(resp.content)
        assert cal.get("version") == "2.0"

    def test_token_invalido_devuelve_404(self, client):
        resp = client.get("/properties/calendar/token-que-no-existe/")
        assert resp.status_code == 404

    def test_reserva_confirmed_aparece_en_ics(self, client):
        prop = baker.make("properties.Property", max_people=4, nightly_price="100.00")
        arrival = timezone.now() + timedelta(days=5)
        b = baker.make(
            "bookings.Booking",
            property=prop,
            status="confirmed",
            arrival=arrival,
            departure=arrival + timedelta(days=3),
            person_num=2,
        )
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        cal = Calendar.from_ical(resp.content)
        uids = [str(c.get("uid")) for c in cal.walk() if c.name == "VEVENT"]
        assert f"booking_{b.id}@reyesestancias.com" in uids

    def test_reserva_pending_con_hold_activo_aparece_en_ics(self, client):
        prop = baker.make("properties.Property", max_people=4, nightly_price="100.00")
        arrival = timezone.now() + timedelta(days=5)
        b = baker.make(
            "bookings.Booking",
            property=prop,
            status="pending",
            arrival=arrival,
            departure=arrival + timedelta(days=3),
            person_num=2,
            hold_expires_at=timezone.now() + timedelta(hours=2),
        )
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        cal = Calendar.from_ical(resp.content)
        uids = [str(c.get("uid")) for c in cal.walk() if c.name == "VEVENT"]
        assert f"booking_{b.id}@reyesestancias.com" in uids

    def test_reserva_cancelled_no_aparece_en_ics(self, client):
        prop = baker.make("properties.Property", max_people=4, nightly_price="100.00")
        arrival = timezone.now() + timedelta(days=5)
        b = baker.make(
            "bookings.Booking",
            property=prop,
            status="cancelled",
            arrival=arrival,
            departure=arrival + timedelta(days=3),
            person_num=2,
        )
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        cal = Calendar.from_ical(resp.content)
        uids = [str(c.get("uid")) for c in cal.walk() if c.name == "VEVENT"]
        assert f"booking_{b.id}@reyesestancias.com" not in uids

    def test_content_disposition_incluye_nombre_de_archivo(self, client):
        prop = baker.make("properties.Property", name="Casa Sol", max_people=2, nightly_price="80.00")
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        assert "attachment" in resp["Content-Disposition"]
        assert ".ics" in resp["Content-Disposition"]

    def test_no_requiere_autenticacion(self, client):
        prop = baker.make("properties.Property", max_people=2, nightly_price="80.00")
        resp = client.get(f"/properties/calendar/{prop.ical_token}/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Property.is_available — bloqueo por calendario externo (Airbnb → web)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestIsAvailableWithExternalCalendar:

    ICAL_URL = "https://airbnb.com/calendar/ical/test.ics"

    def _prop(self, with_ical=True):
        return baker.make(
            "properties.Property",
            max_people=4,
            nightly_price="100.00",
            airbnb_ical_url=self.ICAL_URL if with_ical else None,
        )

    def _checkin(self, days_ahead=10):
        return (date.today() + timedelta(days=days_ahead)).isoformat()

    def _checkout(self, days_ahead=13):
        return (date.today() + timedelta(days=days_ahead)).isoformat()

    def test_fechas_libres_en_airbnb_permiten_reserva(self):
        prop = self._prop()
        body = _make_ical([])
        with patch("requests.get", return_value=_mock_response(body)):
            assert prop.is_available(self._checkin(), self._checkout(), 2) is True

    def test_fechas_bloqueadas_en_airbnb_rechazan_reserva(self):
        prop = self._prop()
        today = date.today()
        blocked_start = today + timedelta(days=9)
        blocked_end = today + timedelta(days=14)
        body = _make_ical([(blocked_start, blocked_end)])
        with patch("requests.get", return_value=_mock_response(body)):
            assert prop.is_available(self._checkin(10), self._checkout(13), 2) is False

    def test_fechas_contiguas_no_solapan(self):
        prop = self._prop()
        today = date.today()
        # Reserva en Airbnb: días 5-10. Solicitud: días 10-13. No deben solapar.
        body = _make_ical([(today + timedelta(days=5), today + timedelta(days=10))])
        with patch("requests.get", return_value=_mock_response(body)):
            assert prop.is_available(self._checkin(10), self._checkout(13), 2) is True

    def test_sin_ical_url_ignora_calendario_externo(self):
        prop = self._prop(with_ical=False)
        assert prop.is_available(self._checkin(), self._checkout(), 2) is True

    def test_fallo_en_fetch_bloquea_por_seguridad(self):
        prop = self._prop()
        with patch("requests.get", side_effect=Exception("network down")):
            assert prop.is_available(self._checkin(), self._checkout(), 2) is False

    def test_host_no_permitido_bloquea_por_seguridad(self):
        prop = baker.make(
            "properties.Property",
            max_people=4,
            nightly_price="100.00",
            airbnb_ical_url="https://malicious.com/cal.ics",
        )
        assert prop.is_available(self._checkin(), self._checkout(), 2) is False


# ---------------------------------------------------------------------------
# sync_all_property_calendars — tarea Celery
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSyncAllPropertyCalendars:

    ICAL_URL = "https://airbnb.com/calendar/ical/test.ics"

    def test_sin_propiedades_devuelve_cero(self):
        from properties.tasks import sync_all_property_calendars
        result = sync_all_property_calendars()
        assert result["total"] == 0

    def test_sincroniza_propiedades_con_url(self):
        from properties.tasks import sync_all_property_calendars
        baker.make("properties.Property", airbnb_ical_url=self.ICAL_URL)
        body = _make_ical([])
        with patch("requests.get", return_value=_mock_response(body)):
            result = sync_all_property_calendars()
        assert result["total"] == 1
        assert result["success"] == 1
        assert result["errors"] == 0

    def test_ignora_propiedades_sin_url(self):
        from properties.tasks import sync_all_property_calendars
        baker.make("properties.Property", airbnb_ical_url=None)
        baker.make("properties.Property", airbnb_ical_url="")
        result = sync_all_property_calendars()
        assert result["total"] == 0

    def test_error_en_una_propiedad_no_aborta_las_demas(self):
        from properties.tasks import sync_all_property_calendars
        baker.make("properties.Property", airbnb_ical_url=self.ICAL_URL)
        baker.make("properties.Property", airbnb_ical_url=self.ICAL_URL)
        body = _make_ical([])

        call_count = 0

        def flaky_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("timeout simulado")
            return _mock_response(body)

        with patch("requests.get", side_effect=flaky_get):
            result = sync_all_property_calendars()

        assert result["total"] == 2
        assert result["success"] == 1
        assert result["errors"] == 1

    def test_resultado_incluye_total_bookings(self):
        from properties.tasks import sync_all_property_calendars
        baker.make("properties.Property", airbnb_ical_url=self.ICAL_URL)
        today = date.today()
        body = _make_ical([
            (today + timedelta(days=5), today + timedelta(days=8)),
            (today + timedelta(days=15), today + timedelta(days=20)),
        ])
        with patch("requests.get", return_value=_mock_response(body)):
            result = sync_all_property_calendars()
        assert result["total_bookings"] == 2
