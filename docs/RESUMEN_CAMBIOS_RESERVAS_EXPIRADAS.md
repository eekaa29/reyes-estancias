# Resumen de Cambios - Sistema de Reservas Expiradas

**Fecha:** 2026-01-03
**Objetivo:** Solucionar el problema de reservas que no expiran automáticamente después del checkout

---

## 🎯 Problema identificado

Las reservas confirmadas que ya pasaron su fecha de checkout permanecían en estado "confirmed" indefinidamente, causando:

1. ❌ Usuarios no podían hacer nuevas reservas en propiedades donde ya tuvieron reservas pasadas
2. ❌ Las reservas expiradas seguían bloqueando la disponibilidad de propiedades
3. ❌ El estado "expired" existía en el modelo pero nunca se usaba

**Ejemplo real:** Una reserva que terminó el 27 de diciembre seguía apareciendo como activa el 3 de enero, impidiendo al usuario hacer una nueva reserva.

---

## ✅ Solución implementada

### 1. **Corrección crítica en configuración de Celery**

**Archivo:** `reyes_estancias/celery.py:4`

```diff
- os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
+ os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reyes_estancias.settings")
```

**Impacto:** Este error habría causado que Celery fallara completamente en producción.

---

### 2. **Nuevas tareas automáticas de Celery**

**Archivo nuevo:** `bookings/tasks.py`

#### Tarea 1: `mark_expired_bookings()`
- **Función:** Marca como "expired" las reservas confirmadas cuyo checkout ya pasó
- **Frecuencia:** Diariamente a las 3:00 AM
- **Consulta:**
  ```python
  Booking.objects.filter(
      status="confirmed",
      departure__lt=timezone.now()
  ).update(status="expired")
  ```

#### Tarea 2: `mark_expired_holds()`
- **Función:** Marca como "expired" las reservas pendientes cuyo hold expiró
- **Frecuencia:** Cada hora en punto
- **Consulta:**
  ```python
  Booking.objects.filter(
      status="pending",
      hold_expires_at__isnull=False,
      hold_expires_at__lt=timezone.now()
  ).update(status="expired")
  ```

---

### 3. **Actualización del schedule de Celery Beat**

**Archivo:** `reyes_estancias/settings.py:211-225`

```python
CELERY_BEAT_SCHEDULE = {
    "charge-balances-every-15-min": {
        "task": "payments.tasks.scan_and_charge_balances",
        "schedule": crontab(minute="*/15"),
        "args": (SITE_BASE_URL,),
    },
    "mark-expired-bookings-daily": {  # ← NUEVO
        "task": "bookings.tasks.mark_expired_bookings",
        "schedule": crontab(hour=3, minute=0),
    },
    "mark-expired-holds-hourly": {  # ← NUEVO
        "task": "bookings.tasks.mark_expired_holds",
        "schedule": crontab(minute=0),
    },
}
```

---

### 4. **Actualización del método de disponibilidad**

**Archivo:** `properties/models.py:105-111`

**Antes:**
```python
qs = self.bookings.filter(status__in=["confirmed", "pending"])
qs = qs.exclude(status="pending", hold_expires_at__lt=current_time)
```

**Después:**
```python
qs = self.bookings.filter(status__in=["confirmed", "pending"])
qs = qs.exclude(status="pending", hold_expires_at__lt=current_time)
qs = qs.exclude(status="confirmed", departure__lt=current_time)  # ← NUEVO
```

**Beneficio:** Doble seguridad - aunque Celery tarde en marcar una reserva como expirada, el método `is_available()` la excluye automáticamente.

---

### 5. **Actualización de vista de detalle de propiedad**

**Archivo:** `properties/views.py:163-167`

**Antes:**
```python
booking = base_qs.filter(status__in=["pending", "confirmed"]).first()
```

**Después:**
```python
now = timezone.now()
booking = (base_qs.filter(status__in=["pending", "confirmed"])
          .exclude(status="confirmed", departure__lt=now)
          .first())
```

**Beneficio:** La reserva del 27 de diciembre ya NO aparece como "active_booking" aunque todavía esté en estado "confirmed".

---

### 6. **Actualización de vista de lista de propiedades**

**Archivo:** `properties/views.py:77-83`

**Antes:**
```python
ub = list(
    Booking.objects
    .filter(user=user, property_id__in=prop_ids, status="confirmed")
    .only("property_id", "arrival", "departure")
)
```

**Después:**
```python
ub = list(
    Booking.objects
    .filter(user=user, property_id__in=prop_ids, status="confirmed")
    .exclude(departure__lt=now)  # ← NUEVO
    .only("property_id", "arrival", "departure")
)
```

**Beneficio:** No muestra mensajes de "ya tienes una reserva" para reservas que ya pasaron.

---

## 📊 Resultados de pruebas

### Prueba manual realizada

```
📊 Estado inicial:
  Total: 1
  Confirmadas: 1
  Confirmadas que ya pasaron: 1

⚠️  Hay 1 reserva(s) que deberían estar expiradas

Ejecutando tarea de expiración...
✓ Resultado: expired=1

📊 Estado después:
  Confirmadas: 0
  Expiradas: 1
```

**Conclusión:** ✅ La tarea funciona correctamente

---

## 🔧 Configuración de Celery Beat

```
✓ charge-balances-every-15-min:
    Tarea: payments.tasks.scan_and_charge_balances
    Horario: */15 * * * * (cada 15 minutos)

✓ mark-expired-bookings-daily:
    Tarea: bookings.tasks.mark_expired_bookings
    Horario: 0 3 * * * (3:00 AM diario)

✓ mark-expired-holds-hourly:
    Tarea: bookings.tasks.mark_expired_holds
    Horario: 0 * * * * (cada hora)
```

---

## 📚 Documentación creada

### 1. **CELERY_PRODUCCION.md**
Guía completa para configurar Celery en producción con:
- Instalación de Redis
- Configuración de Supervisor/systemd
- Monitoreo y troubleshooting
- Checklist de producción

### 2. **PRUEBAS_LOCALES_CELERY.md**
Guía paso a paso para probar localmente:
- Cómo ejecutar worker y beat
- Cómo probar tareas manualmente
- Verificación de configuración
- Troubleshooting común

### 3. **RESUMEN_CAMBIOS_RESERVAS_EXPIRADAS.md** (este archivo)
Resumen ejecutivo de todos los cambios

---

## 🚀 Próximos pasos para producción

### En desarrollo (ya hecho):
- ✅ Código implementado
- ✅ Tareas probadas manualmente
- ✅ Configuración verificada
- ✅ Documentación creada

### Para producción (pendiente):
1. **Instalar Redis** en el servidor de producción
2. **Configurar Supervisor** o systemd para gestionar procesos
3. **Configurar variables de entorno** (`CELERY_BROKER_URL`, etc.)
4. **Arrancar procesos:**
   - Django (Gunicorn/uWSGI)
   - Celery Worker
   - Celery Beat
5. **Verificar logs** y monitorear ejecución

**📖 Sigue la guía:** `docs/CELERY_PRODUCCION.md`

---

## ⚠️ Importante para producción

### Solo UN proceso de Beat

```bash
# ✅ CORRECTO
# Server 1:
gunicorn ...              # Django
celery worker ...         # Worker 1
celery worker ...         # Worker 2
celery beat ...           # Beat (solo UNO)

# ❌ INCORRECTO
# Server 1:
celery beat ...
# Server 2:
celery beat ...           # ¡NO! Las tareas se ejecutarán dos veces
```

### Redis debe ser accesible

```python
# Production .env
CELERY_BROKER_URL=redis://tu-servidor-redis:6379/0
CELERY_RESULT_BACKEND=redis://tu-servidor-redis:6379/1
```

### Logs en producción

```bash
# Verificar regularmente
tail -f /var/log/celery/worker.log
tail -f /var/log/celery/beat.log
```

---

## 🎯 Beneficios de esta solución

1. ✅ **Automático:** Las reservas se marcan como expiradas sin intervención manual
2. ✅ **Eficiente:** Se ejecuta solo una vez al día (3:00 AM) cuando hay poco tráfico
3. ✅ **Robusto:** Doble protección (tarea automática + filtros en consultas)
4. ✅ **Escalable:** Usa la infraestructura de Celery que ya tienes
5. ✅ **Mantenible:** Sigue el mismo patrón que `scan_and_charge_balances`
6. ✅ **Documentado:** Guías completas para desarrollo y producción

---

## 📞 Soporte

Si tienes dudas:
1. Consulta `docs/PRUEBAS_LOCALES_CELERY.md` para pruebas locales
2. Consulta `docs/CELERY_PRODUCCION.md` para configuración en producción
3. Revisa los logs de Celery para debugging

---

**Estado:** ✅ Completado y probado en desarrollo
**Listo para producción:** ✅ Sí (siguiendo la guía de producción)
