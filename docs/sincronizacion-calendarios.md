# Sincronización de Calendarios — Reyes Estancias ↔ Airbnb

## Resumen del sistema

La sincronización es **bidireccional**:

| Dirección | Qué hace | Cómo |
|---|---|---|
| Airbnb → esta web | Bloquea en esta web las fechas reservadas en Airbnb | Fetch periódico del iCal de Airbnb vía Celery |
| Esta web → Airbnb | Bloquea en Airbnb las fechas reservadas en esta web | Endpoint `.ics` público que Airbnb consulta periódicamente |

---

## Dirección 1: Airbnb → esta web

### Cómo funciona

1. Cada propiedad tiene un campo `airbnb_ical_url` (URL del calendario iCal de Airbnb).
2. Una tarea de Celery Beat (`sync_all_property_calendars`) descarga ese iCal cada **30 minutos** y almacena el resultado en caché (Redis, TTL: **15 minutos**).
3. Cuando un usuario consulta disponibilidad, `Property.is_available()` lee las fechas bloqueadas del caché (respuesta instantánea).
4. Si el caché ha expirado y Celery aún no ha refrescado, la petición hace el fetch en tiempo real y actualiza el caché.

### Archivos clave

| Archivo | Función |
|---|---|
| `properties/utils/ical.py` → `fetch_ical_bookings()` | Descarga y parsea el iCal; gestiona el caché |
| `properties/models.py` → `Property.is_available()` | Comprueba solapamiento contra las fechas bloqueadas |
| `properties/tasks.py` → `sync_all_property_calendars` | Tarea Celery que refresca el caché proactivamente |
| `reyes_estancias/settings.py` → `CELERY_BEAT_SCHEDULE` | Configura la frecuencia (cada 30 min) |

### Tiempos de propagación (Airbnb → esta web)

- **Mejor caso**: inmediato (datos en caché actualizados por Celery).
- **Peor caso**: hasta ~30 minutos (si Celery acaba de ejecutar y el caché expira antes del siguiente ciclo).
- **Ventana de doble reserva teórica**: ≤ 30 minutos.

### Cómo configurar (campo en el Admin)

1. En el Admin de Django → **Propiedades** → editar propiedad.
2. Campo **"Calendario iCal de Airbnb"**: pegar la URL del iCal de Airbnb.

Para obtener la URL del iCal en Airbnb:
> **Airbnb** → Calendario → Disponibilidad → Conectar a otro calendario → **Exportar calendario** → Copiar enlace.

Hosts permitidos en la whitelist (`ICAL_ALLOWED_HOSTS`): `airbnb.com`, `airbnb.es`, `airbnb.mx`, `calendar.google.com`, `booking.com`, `vrbo.com`, `homeaway.com`.

---

## Dirección 2: esta web → Airbnb

### Cómo funciona

1. Cada propiedad tiene un `ical_token` único (generado automáticamente al crear la propiedad).
2. El endpoint `/properties/calendar/<ical_token>/` genera y sirve un archivo `.ics` con todas las reservas `confirmed` y las `pending` con hold de depósito vigente.
3. Airbnb descarga ese `.ics` periódicamente (normalmente cada **3-24 horas**, según Airbnb) y bloquea esas fechas en su calendario.

### Archivos clave

| Archivo | Función |
|---|---|
| `properties/utils/ical.py` → `generate_ical_for_property()` | Genera el `.ics` con las reservas activas |
| `properties/views.py` → `ExportCalendarView` | Sirve el `.ics` en la URL pública |
| `properties/urls.py` | Ruta: `calendar/<str:ical_token>/` |

### Reservas incluidas en el `.ics` exportado

| Estado | ¿Se exporta? | Condición |
|---|---|---|
| `confirmed` | ✅ Siempre | — |
| `pending` | ✅ Sí | Solo si `hold_expires_at > ahora` (hold de depósito activo) |
| `pending` expirado | ❌ No | El hold ha caducado |
| `cancelled` | ❌ No | — |
| `completed` | ❌ No | — |

> **Por qué se incluyen las `pending`**: durante el tiempo que el huésped tiene para pagar el depósito, esas fechas están bloqueadas en esta web. Sin exportarlas, alguien podría reservarlas en Airbnb creando un doble bloqueo.

### Cómo configurar en Airbnb (paso a paso)

1. En el Admin de Django → **Propiedades** → editar la propiedad.
2. En el bloque **"Sincronización con Airbnb"** (parte inferior del formulario), aparece la URL de exportación ya formada. Hacer clic en **"Copiar"**.
3. Ir a **Airbnb** → Calendario → Disponibilidad → Conectar a otro calendario → **Importar calendario**.
4. Pegar la URL copiada y confirmar.

A partir de ese momento Airbnb consultará la URL periódicamente y bloqueará las fechas reservadas en esta web.

> **Importante**: el `ical_token` nunca cambia para una propiedad dada, así que la URL es permanente. No hace falta reconfigurarlo en Airbnb al actualizar la web.

---

## Tiempos de propagación combinados

| Evento | Visible en esta web | Visible en Airbnb |
|---|---|---|
| Reserva en Airbnb | ≤ 30 min (Celery) | Inmediato |
| Reserva en esta web (confirmed) | Inmediato | ≤ 3-24 h (Airbnb polling) |
| Reserva en esta web (pending+hold) | Inmediato | ≤ 3-24 h (Airbnb polling) |
| Cancelación en esta web | Inmediato | ≤ 3-24 h (Airbnb polling) |

---

## Configuración técnica relevante

```python
# reyes_estancias/settings.py

ICAL_REQUEST_TIMEOUT = 10       # segundos para el fetch del iCal externo
ICAL_MAX_SIZE = 5 * 1024 * 1024 # 5 MB máximo por archivo iCal
ICAL_CACHE_TIMEOUT = 900        # 15 minutos de TTL en caché (Redis)

CELERY_BEAT_SCHEDULE = {
    "sync-property-calendars-every-30-min": {
        "task": "properties.tasks.sync_all_property_calendars",
        "schedule": crontab(minute="*/30"),
    },
    ...
}
```

---

## Seguridad del endpoint de exportación

- La URL incluye un token de 48 bytes aleatorio (`ical_token`) generado con `secrets.token_urlsafe(48)`. Sin ese token la URL no funciona.
- Rate limiting: máximo **20 peticiones/hora por IP** (`django-ratelimit`) para evitar enumeración de tokens.
- No requiere autenticación (necesario para que Airbnb pueda acceder sin sesión).

---

## Forzar sincronización manual

Desde la terminal del servidor (o Railway shell):

```bash
# Sincronizar todas las propiedades ahora mismo
python manage.py shell -c "from properties.tasks import sync_all_property_calendars; sync_all_property_calendars()"

# O con el comando de gestión (solo importa el iCal de Airbnb, no genera el .ics)
python manage.py import_calendars
```

Desde el panel de Airbnb también se puede forzar una actualización manual del calendario importado en: **Calendario → Disponibilidad → Conectar a otro calendario → Actualizar ahora**.
