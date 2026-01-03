# Guía de Pruebas Locales - Celery

Esta guía te ayudará a probar la configuración de Celery localmente antes de ir a producción.

## 🎯 Cambios realizados

### Archivos modificados

1. ✅ **reyes_estancias/celery.py** - Corregido error crítico en DJANGO_SETTINGS_MODULE
2. ✅ **bookings/tasks.py** - Creado con 2 nuevas tareas
3. ✅ **reyes_estancias/settings.py** - Agregadas 2 tareas al CELERY_BEAT_SCHEDULE
4. ✅ **properties/models.py** - Actualizado is_available() para excluir reservas expiradas
5. ✅ **properties/views.py** - Actualizadas vistas para excluir reservas expiradas

### Nuevas tareas de Celery

1. **`bookings.tasks.mark_expired_bookings`**
   - Se ejecuta: Diariamente a las 3:00 AM
   - Función: Marca como "expired" las reservas confirmadas cuyo checkout ya pasó

2. **`bookings.tasks.mark_expired_holds`**
   - Se ejecuta: Cada hora en punto
   - Función: Marca como "expired" las reservas pendientes cuyo hold_expires_at expiró

---

## 🧪 Cómo probar localmente

### Paso 1: Verificar que Redis esté corriendo

```bash
redis-cli ping
# Debe responder: PONG
```

Si no está corriendo:
```bash
# Linux/Mac
redis-server

# O si lo tienes como servicio
sudo systemctl start redis
```

### Paso 2: Ejecutar el worker de Celery

En una terminal, desde la raíz del proyecto:

```bash
celery -A reyes_estancias worker --loglevel=info
```

Deberías ver algo como:

```
[2026-01-03 09:00:00,000: INFO/MainProcess] Connected to redis://127.0.0.1:6379/0
[2026-01-03 09:00:00,000: INFO/MainProcess] celery@hostname ready.
```

**Deja esta terminal abierta.**

### Paso 3: Ejecutar Celery Beat (en otra terminal)

En otra terminal, desde la raíz del proyecto:

```bash
celery -A reyes_estancias beat --loglevel=info
```

Deberías ver algo como:

```
[2026-01-03 09:00:00,000: INFO/MainProcess] beat: Starting...
[2026-01-03 09:00:00,000: INFO/MainProcess] Scheduler: Loading...
```

Verás las tareas programadas listadas:

```
DatabaseScheduler: Schedule:
<ModelEntry: charge-balances-every-15-min ...
<ModelEntry: mark-expired-bookings-daily ...
<ModelEntry: mark-expired-holds-hourly ...
```

**Deja esta terminal abierta también.**

### Paso 4: Verificar las tareas registradas

En otra terminal:

```bash
python manage.py shell
```

```python
from reyes_estancias.celery import app

# Ver todas las tareas registradas
tasks = [t for t in app.tasks.keys() if not t.startswith('celery.')]
for task in sorted(tasks):
    print(f"  ✓ {task}")
```

Deberías ver:
```
  ✓ bookings.tasks.mark_expired_bookings
  ✓ bookings.tasks.mark_expired_holds
  ✓ payments.tasks.charge_balance_for_booking
  ✓ payments.tasks.scan_and_charge_balances
```

### Paso 5: Probar manualmente la tarea de expiración

En el shell de Django:

```python
from bookings.models import Booking
from django.utils import timezone

# Ver estado actual
print(f"Confirmadas: {Booking.objects.filter(status='confirmed').count()}")
print(f"Expiradas: {Booking.objects.filter(status='expired').count()}")

# Ver reservas que deberían estar expiradas
past_bookings = Booking.objects.filter(
    status="confirmed",
    departure__lt=timezone.now()
)
print(f"\nReservas pasadas que deberían expirar: {past_bookings.count()}")

for b in past_bookings:
    print(f"  - {b.property.name}: {b.departure}")
```

Ahora ejecuta la tarea manualmente:

```python
from bookings.tasks import mark_expired_bookings

result = mark_expired_bookings()
print(f"\nResultado: {result}")

# Verificar después
print(f"\nConfirmadas: {Booking.objects.filter(status='confirmed').count()}")
print(f"Expiradas: {Booking.objects.filter(status='expired').count()}")
```

### Paso 6: Probar que las vistas funcionan correctamente

Abre el navegador y:

1. **Ir a la lista de propiedades** con tu usuario autenticado
2. **Buscar la propiedad** donde tenías la reserva del 27 de diciembre
3. **Verificar** que ya NO aparezca el mensaje de "ya tienes una reserva"
4. **Intentar hacer una nueva reserva** - ahora debería permitirte

### Paso 7: Probar el filtro de disponibilidad

En el shell:

```python
from properties.models import Property
from datetime import date, timedelta

# Obtener una propiedad
prop = Property.objects.first()

# Probar disponibilidad con fechas futuras
checkin = (date.today() + timedelta(days=7)).isoformat()
checkout = (date.today() + timedelta(days=10)).isoformat()

print(f"\n¿Disponible para {checkin} a {checkout}?")
print(prop.is_available(checkin, checkout, cant_personas=2))
```

---

## 🔄 Probar tareas programadas (opcional)

Si quieres probar que las tareas se ejecuten automáticamente:

### Opción 1: Cambiar temporalmente el schedule

Edita `settings.py` y cambia la frecuencia:

```python
CELERY_BEAT_SCHEDULE = {
    # ... otras tareas ...
    "mark-expired-bookings-test": {
        "task": "bookings.tasks.mark_expired_bookings",
        "schedule": crontab(minute="*/2"),  # Cada 2 minutos para prueba
    },
}
```

Reinicia Celery Beat y espera 2 minutos. Verás en los logs:

```
[2026-01-03 09:02:00,000: INFO/MainProcess] Received task: bookings.tasks.mark_expired_bookings
[2026-01-03 09:02:00,100: INFO/ForkPoolWorker-1] Task bookings.tasks.mark_expired_bookings succeeded in 0.1s: 'expired=0'
```

**¡No olvides revertir el cambio después!**

### Opción 2: Ejecutar manualmente via Celery

```bash
python manage.py shell
```

```python
from bookings.tasks import mark_expired_bookings

# Ejecutar de forma asíncrona
result = mark_expired_bookings.delay()
print(f"Task ID: {result.id}")

# Esperar resultado
print(f"Resultado: {result.get(timeout=10)}")
```

---

## 📊 Monitoreo en tiempo real

Mientras tienes worker y beat corriendo, puedes ver en tiempo real:

### Logs del Worker

Verás cuándo se ejecutan las tareas:

```
[2026-01-03 03:00:00,000: INFO/MainProcess] Received task: bookings.tasks.mark_expired_bookings
[2026-01-03 03:00:00,500: INFO/ForkPoolWorker-1] Marcadas 3 reservas como expiradas...
[2026-01-03 03:00:00,500: INFO/ForkPoolWorker-1] Task bookings.tasks.mark_expired_bookings succeeded
```

### Logs del Beat

Verás cuándo se programan las tareas:

```
[2026-01-03 03:00:00,000: INFO/MainProcess] Scheduler: Sending due task mark-expired-bookings-daily
```

---

## ✅ Checklist de pruebas

Antes de ir a producción, verifica que:

- [ ] Redis está corriendo y conecta correctamente
- [ ] Celery worker arranca sin errores
- [ ] Celery beat arranca sin errores y muestra las 3 tareas programadas
- [ ] Las tareas se pueden importar (`from bookings.tasks import ...`)
- [ ] La tarea manual funciona y marca reservas como expiradas
- [ ] Las vistas de propiedades YA NO muestran reservas expiradas como activas
- [ ] Puedes hacer una nueva reserva en una propiedad donde antes no podías
- [ ] El método `is_available()` excluye correctamente las reservas expiradas
- [ ] Los logs no muestran errores

---

## 🐛 Problemas comunes

### "Connection refused" al conectar con Redis

**Solución:**
```bash
redis-server
# O
sudo systemctl start redis
```

### "ModuleNotFoundError: No module named 'bookings.tasks'"

**Solución:** Asegúrate de estar en el directorio raíz del proyecto cuando ejecutas Celery.

### Las tareas no aparecen en el worker

**Solución:** Reinicia el worker (Ctrl+C y vuelve a ejecutar el comando).

### "ImportError: cannot import name 'app'"

**Solución:** Verifica que `reyes_estancias/__init__.py` importe correctamente Celery.

---

## 🎓 Comandos de referencia rápida

```bash
# Terminal 1: Worker
celery -A reyes_estancias worker --loglevel=info

# Terminal 2: Beat
celery -A reyes_estancias beat --loglevel=info

# Terminal 3: Django dev server
python manage.py runserver

# Terminal 4: Redis (si no es servicio)
redis-server

# Ver tareas registradas
celery -A reyes_estancias inspect registered

# Ver tareas programadas
celery -A reyes_estancias inspect scheduled

# Ver workers activos
celery -A reyes_estancias inspect active
```

---

**Última actualización:** 2026-01-03
