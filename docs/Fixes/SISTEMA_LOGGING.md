# 📋 Sistema de Logging - Reyes Estancias

**Fecha**: 2026-01-05
**Versión**: 2.0 (Mejorado para producción)

---

## 📊 Resumen

El sistema de logging está configurado para:
- ✅ Separar logs por tipo (calendarios, pagos, celery, etc.)
- ✅ Rotación automática (10 MB por archivo, 5 backups)
- ✅ Diferentes niveles según ambiente (DEBUG/INFO)
- ✅ Envío de errores críticos por email en producción
- ✅ Formato detallado con timestamp, módulo, función y línea

---

## 📂 Archivos de Log

| Archivo | Contenido | Nivel | Tamaño |
|---------|-----------|-------|--------|
| `django.log` | Logs generales de Django | INFO+ | 10 MB × 5 |
| `ical.log` | Sincronización de calendarios | INFO+ | 10 MB × 5 |
| `payments.log` | Pagos y Stripe | INFO+ | 10 MB × 5 |
| `celery.log` | Tareas de Celery | INFO+ | 10 MB × 5 |
| `errors.log` | Solo errores (ERROR+) | ERROR+ | 10 MB × 5 |
| `security.log` | Seguridad y accesos | WARNING+ | 10 MB × 5 |

**Ubicación**:
- Desarrollo: `logs/` (en el proyecto)
- Producción: `/var/log/reyes_estancias/`

---

## 🎯 Formato de Logs

### Formato Verbose (Principal)
```
[LEVEL] YYYY-MM-DD HH:MM:SS logger_name module.function:line - message
```

**Ejemplo**:
```
[INFO] 2026-01-05 10:30:45 properties.utils.ical fetch_ical_bookings:188 - Successfully fetched 2 bookings from www.airbnb.mx
```

### Formato Celery
```
[LEVEL] YYYY-MM-DD HH:MM:SS [Celery] logger_name - message
```

**Ejemplo**:
```
[INFO] 2026-01-05 10:30:00 [Celery] properties.tasks - Sincronización completada: 6/6 exitosas
```

---

## 📖 Guía de Uso

### Ver Logs en Tiempo Real

```bash
# Ver todos los logs de calendarios
tail -f logs/ical.log

# Ver solo errores
tail -f logs/errors.log

# Ver logs de Celery
tail -f logs/celery.log

# Ver múltiples archivos simultáneamente
tail -f logs/{ical,payments,celery}.log
```

### Buscar en Logs

```bash
# Buscar errores específicos
grep "ERROR" logs/ical.log

# Buscar por fecha
grep "2026-01-05" logs/django.log

# Buscar sincronizaciones fallidas
grep "error" logs/ical.log -i

# Contar errores
grep -c "ERROR" logs/errors.log

# Ver últimas 100 líneas con errores
grep "ERROR" logs/errors.log | tail -100
```

### Limpiar Logs

```bash
# Limpiar un archivo específico (cuidado!)
> logs/ical.log

# Limpiar todos los logs (CUIDADO!)
find logs/ -name "*.log" -type f -exec truncate -s 0 {} \;

# Eliminar logs antiguos (más de 30 días)
find logs/ -name "*.log.*" -mtime +30 -delete
```

---

## 🔧 Configuración

### Variables de Entorno

```bash
# Directorio de logs
LOG_DIR=/var/log/reyes_estancias  # Producción
LOG_DIR=logs                       # Desarrollo (por defecto)

# Nivel de logging
LOG_LEVEL=DEBUG   # Desarrollo (muestra todo)
LOG_LEVEL=INFO    # Producción (recomendado)
LOG_LEVEL=WARNING # Solo warnings y errores
LOG_LEVEL=ERROR   # Solo errores

# Email para notificaciones de errores (solo producción)
ADMIN_EMAIL=admin@reyes-estancias.com
```

### Niveles de Log

| Nivel | Descripción | Cuándo usar |
|-------|-------------|-------------|
| `DEBUG` | Información detallada | Desarrollo, debugging |
| `INFO` | Información general | Producción, eventos normales |
| `WARNING` | Advertencias | Problemas potenciales |
| `ERROR` | Errores | Fallos que afectan funcionalidad |
| `CRITICAL` | Errores críticos | Fallos que requieren atención inmediata |

---

## 📚 Loggers Disponibles

### Django Core

```python
import logging
logger = logging.getLogger('django')

logger.info("Aplicación iniciada")
logger.error("Error al procesar petición")
```

**Archivos**: `django.log`, `errors.log` (si ERROR+)

---

### Calendarios iCal

```python
import logging
logger = logging.getLogger('properties.utils.ical')

logger.info("Sincronizando calendario de Airbnb")
logger.warning("Timeout al obtener calendario")
logger.error("Error crítico en sincronización")
```

**Archivos**: `ical.log`, `errors.log` (si ERROR+), console

---

### Pagos y Stripe

```python
import logging
logger = logging.getLogger('payments')  # O 'payments.tasks'

logger.info("Procesando pago de $100")
logger.error("Fallo en cobro de Stripe")
```

**Archivos**: `payments.log`, `errors.log` (si ERROR+), console

---

### Celery

```python
import logging
logger = logging.getLogger('celery')

logger.info("Tarea ejecutada correctamente")
logger.warning("Worker ocupado")
logger.error("Tarea falló después de 3 reintentos")
```

**Archivos**: `celery.log`, `errors.log` (si ERROR+), console

---

## 🎨 Ejemplos Prácticos

### Logging en Tareas de Celery

```python
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def sync_calendar(property_id):
    logger.info(f"Iniciando sincronización para propiedad {property_id}")

    try:
        # ... lógica ...
        logger.info(f"Sincronización completada: {count} reservas")
        return {'success': True, 'count': count}

    except Exception as e:
        logger.error(f"Error en sincronización: {e}", exc_info=True)
        raise
```

### Logging en Vistas

```python
from django.views import View
import logging

logger = logging.getLogger(__name__)

class ExportCalendarView(View):
    def get(self, request, ical_token):
        logger.info(f"Acceso a calendario con token {ical_token[:8]}...")

        try:
            # ... lógica ...
            logger.info(f"Calendario exportado: {property.name}")
            return response

        except Exception as e:
            logger.error(f"Error exportando calendario: {e}", exc_info=True)
            raise
```

### Logging en Utilidades

```python
import logging

logger = logging.getLogger(__name__)

def fetch_ical_bookings(ical_url):
    logger.info(f"Fetching iCal from {host}")

    try:
        # ... petición HTTP ...
        logger.info(f"Successfully fetched {len(bookings)} bookings")
        return bookings

    except requests.Timeout:
        logger.error(f"Timeout fetching iCal from {host}")
        raise
    except Exception as e:
        logger.error(f"Error fetching iCal: {e}", exc_info=True)
        raise
```

---

## 🚨 Errores y Notificaciones

### Envío de Emails en Producción

En producción (`DEBUG=False`), los errores de nivel `ERROR` y `CRITICAL` se envían automáticamente por email a los administradores configurados.

**Requisitos**:
1. Configurar `ADMIN_EMAIL` en `.env`
2. Configurar email en `settings.py` (Gmail, SendGrid, etc)
3. `DEBUG=False`

**Administradores** (configurado en `settings.py`):
```python
ADMINS = [
    ('Admin Reyes Estancias', 'admin@reyes-estancias.com'),
]
```

**Email de ejemplo**:
```
Subject: [ERROR] reyes-estancias.com - Error in properties.tasks

[ERROR] 2026-01-05 10:30:45 properties.tasks sync_all_property_calendars:45
Error sincronizando calendario de 'Casa Expo': Connection timeout

Traceback (most recent call last):
  File "/app/properties/tasks.py", line 42, in sync_all_property_calendars
    bookings = fetch_ical_bookings(prop.airbnb_ical_url)
  ...
```

---

## 📊 Monitoreo y Análisis

### Comandos Útiles

```bash
# Ver estadísticas de logs
wc -l logs/*.log                    # Líneas por archivo
du -sh logs/*.log                   # Tamaño por archivo
ls -lh logs/                        # Lista con tamaños

# Análisis de errores
grep -c "ERROR" logs/errors.log     # Contar errores
grep "ERROR" logs/* | wc -l         # Total errores en todos los logs

# Errores más frecuentes
grep "ERROR" logs/errors.log | sort | uniq -c | sort -rn | head -10

# Actividad por hora
grep "2026-01-05 10:" logs/django.log | wc -l  # Actividad a las 10am

# Ver solo errores de sincronización
grep "ERROR" logs/ical.log
```

### Script de Análisis (logs/analyze.sh)

```bash
#!/bin/bash
# Script para analizar logs

echo "=== Resumen de Logs ==="
echo ""

echo "📊 Tamaño de archivos:"
du -sh logs/*.log | sort -h
echo ""

echo "📈 Número de líneas:"
wc -l logs/*.log | sort -n
echo ""

echo "🔴 Errores totales:"
grep -c "ERROR" logs/errors.log 2>/dev/null || echo "0"
echo ""

echo "⚠️  Warnings totales:"
grep -c "WARNING" logs/*.log 2>/dev/null | awk '{sum+=$1} END {print sum}'
echo ""

echo "📅 Última actividad:"
tail -1 logs/django.log
```

---

## 🔒 Seguridad y Privacidad

### Qué NO Loggear

❌ **NUNCA loggear**:
- Contraseñas
- Claves de API completas
- Tokens de sesión
- Números de tarjeta de crédito
- Información personal sensible (DNI, etc.)

✅ **Sí loggear**:
- IDs de objetos
- Timestamps
- Resultados de operaciones
- Errores (sin información sensible)
- Métricas de rendimiento

### Ejemplo Correcto

```python
# ❌ INCORRECTO
logger.info(f"Usuario {email} con password {password} intentó login")

# ✅ CORRECTO
logger.info(f"Usuario {user_id} intentó login desde IP {ip}")

# ❌ INCORRECTO
logger.info(f"Stripe key: {stripe_secret_key}")

# ✅ CORRECTO
logger.info(f"Stripe key: {stripe_secret_key[:8]}...")
```

---

## 🛠️ Troubleshooting

### Logs no se generan

**Problema**: Los archivos de log están vacíos o no se crean

**Solución**:
```bash
# 1. Verificar permisos del directorio
ls -ld logs/
chmod 755 logs/

# 2. Verificar que el directorio existe
mkdir -p logs/

# 3. Verificar configuración en settings.py
python manage.py shell -c "from django.conf import settings; print(settings.LOG_DIR)"

# 4. Probar logging manualmente
python manage.py shell
>>> import logging
>>> logger = logging.getLogger('django')
>>> logger.info("Test")
```

### Logs crecen demasiado rápido

**Problema**: Archivos de log muy grandes

**Solución**:
```python
# Ajustar tamaño máximo en settings.py
'maxBytes': 1024 * 1024 * 5,  # 5 MB en vez de 10 MB

# Ajustar número de backups
'backupCount': 3,  # 3 en vez de 5

# Cambiar nivel de log a WARNING
LOG_LEVEL=WARNING  # En .env
```

### Rotación no funciona

**Problema**: Los archivos de log no rotan

**Verificación**:
```bash
# Ver archivos de backup
ls -lh logs/*.log*

# Forzar rotación manualmente
python -c "import logging.handlers; handler = logging.handlers.RotatingFileHandler('logs/django.log', maxBytes=1024, backupCount=5); handler.doRollover()"
```

---

## 📋 Checklist de Producción

Antes de deployment:

- [ ] Directorio `/var/log/reyes_estancias/` creado con permisos correctos
- [ ] `LOG_LEVEL=INFO` configurado en `.env.production`
- [ ] `ADMIN_EMAIL` configurado correctamente
- [ ] Email de producción funcionando (probar con error de prueba)
- [ ] Verificar que archivos de log se crean correctamente
- [ ] Configurar logrotate del sistema (opcional, para rotación adicional)
- [ ] Monitoreo de espacio en disco configurado

Después de deployment:

- [ ] Ver logs para verificar que todo funciona
- [ ] Probar que errores se envían por email
- [ ] Configurar alertas si logs/errors.log crece mucho
- [ ] Revisar logs diariamente la primera semana

---

## 📚 Referencias

- [Django Logging](https://docs.djangoproject.com/en/5.2/topics/logging/)
- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [Celery Logging](https://docs.celeryq.dev/en/stable/userguide/tasks.html#logging)

---

**Última actualización**: 2026-01-05
**Responsable**: Sistema de Logging - Reyes Estancias
