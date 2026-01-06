# Configuración de Celery en Producción

Esta guía explica cómo configurar Celery y Celery Beat para el proyecto Reyes Estancias en producción.

## 📋 Requisitos previos

- ✅ Redis instalado y accesible
- ✅ Python 3.12 con virtualenv
- ✅ Supervisor o systemd (para gestionar procesos)

---

## 🔧 1. Configuración de Redis

### Instalación de Redis (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### Verificar que Redis funciona

```bash
redis-cli ping
# Debería responder: PONG
```

### Configurar variables de entorno

En tu archivo `.env` de producción:

```env
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

Si usas Redis en la nube (Redis Cloud, AWS ElastiCache, etc.):

```env
CELERY_BROKER_URL=redis://usuario:password@host:puerto/0
CELERY_RESULT_BACKEND=redis://usuario:password@host:puerto/1
```

---

## 🚀 2. Configuración de procesos con Supervisor

Supervisor es la forma más simple de gestionar los procesos de Celery en producción.

### Instalación de Supervisor

```bash
sudo apt install supervisor
```

### Crear configuración para Celery Worker

Crea el archivo `/etc/supervisor/conf.d/reyes_estancias_celery.conf`:

```ini
[program:reyes_estancias_celery_worker]
command=/home/tu_usuario/reyes_estancias/venv/bin/celery -A reyes_estancias worker --loglevel=info
directory=/home/tu_usuario/reyes_estancias
user=tu_usuario
numprocs=1
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
killasgroup=true
priority=998

# Logs
stdout_logfile=/var/log/celery/worker.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stderr_logfile=/var/log/celery/worker_error.log
stderr_logfile_maxbytes=50MB
stderr_logfile_backups=10

# Variables de entorno
environment=DJANGO_SETTINGS_MODULE="reyes_estancias.settings",LANG="es_MX.UTF-8",LC_ALL="es_MX.UTF-8"

[program:reyes_estancias_celery_beat]
command=/home/tu_usuario/reyes_estancias/venv/bin/celery -A reyes_estancias beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
directory=/home/tu_usuario/reyes_estancias
user=tu_usuario
numprocs=1
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=60
killasgroup=true
priority=999

# Logs
stdout_logfile=/var/log/celery/beat.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stderr_logfile=/var/log/celery/beat_error.log
stderr_logfile_maxbytes=50MB
stderr_logfile_backups=10

# Variables de entorno
environment=DJANGO_SETTINGS_MODULE="reyes_estancias.settings",LANG="es_MX.UTF-8",LC_ALL="es_MX.UTF-8"
```

### Crear directorio de logs

```bash
sudo mkdir -p /var/log/celery
sudo chown tu_usuario:tu_usuario /var/log/celery
```

### Recargar y arrancar Supervisor

```bash
# Recargar configuración
sudo supervisorctl reread
sudo supervisorctl update

# Arrancar los procesos
sudo supervisorctl start reyes_estancias_celery_worker
sudo supervisorctl start reyes_estancias_celery_beat

# Verificar estado
sudo supervisorctl status
```

Deberías ver:

```
reyes_estancias_celery_worker    RUNNING   pid 12345, uptime 0:00:10
reyes_estancias_celery_beat      RUNNING   pid 12346, uptime 0:00:10
```

---

## 🔄 3. Comandos útiles de Supervisor

```bash
# Ver estado de todos los procesos
sudo supervisorctl status

# Reiniciar un proceso
sudo supervisorctl restart reyes_estancias_celery_worker
sudo supervisorctl restart reyes_estancias_celery_beat

# Detener un proceso
sudo supervisorctl stop reyes_estancias_celery_worker

# Ver logs en tiempo real
sudo tail -f /var/log/celery/worker.log
sudo tail -f /var/log/celery/beat.log

# Reiniciar todos los procesos
sudo supervisorctl restart all
```

---

## 🔍 4. Verificación en producción

### Verificar que las tareas estén registradas

```bash
cd /home/tu_usuario/reyes_estancias
source venv/bin/activate
python manage.py shell

>>> from bookings.tasks import mark_expired_bookings, mark_expired_holds
>>> print(mark_expired_bookings.name)
bookings.tasks.mark_expired_bookings
>>> print(mark_expired_holds.name)
bookings.tasks.mark_expired_holds
```

### Probar manualmente una tarea

```bash
python manage.py shell

>>> from bookings.tasks import mark_expired_bookings
>>> result = mark_expired_bookings()
>>> print(result)
expired=X
```

### Verificar el schedule de Beat

```bash
python manage.py shell

>>> from django.conf import settings
>>> for name, config in settings.CELERY_BEAT_SCHEDULE.items():
...     print(f"{name}: {config['task']}")
...
charge-balances-every-15-min: payments.tasks.scan_and_charge_balances
mark-expired-bookings-daily: bookings.tasks.mark_expired_bookings
mark-expired-holds-hourly: bookings.tasks.mark_expired_holds
```

---

## 📊 5. Monitoreo de tareas programadas

Las tareas programadas en el `CELERY_BEAT_SCHEDULE`:

| Tarea | Frecuencia | Descripción |
|-------|------------|-------------|
| `charge-balances-every-15-min` | Cada 15 minutos | Cobra el balance de reservas 2 días después del check-in |
| `mark-expired-bookings-daily` | Diariamente a las 3:00 AM | Marca como "expired" las reservas confirmadas cuyo checkout ya pasó |
| `mark-expired-holds-hourly` | Cada hora en punto | Marca como "expired" las reservas pendientes cuyo hold expiró |

---

## 🐛 6. Troubleshooting

### Problema: Las tareas no se ejecutan

**Verificar que Beat está corriendo:**
```bash
sudo supervisorctl status reyes_estancias_celery_beat
```

**Ver los logs de Beat:**
```bash
sudo tail -f /var/log/celery/beat.log
```

### Problema: Redis no conecta

**Verificar que Redis esté corriendo:**
```bash
sudo systemctl status redis-server
```

**Probar conexión:**
```bash
redis-cli -h 127.0.0.1 -p 6379 ping
```

### Problema: Las tareas fallan

**Ver logs del worker:**
```bash
sudo tail -f /var/log/celery/worker.log
sudo tail -f /var/log/celery/worker_error.log
```

### Problema: Worker se detiene inesperadamente

**Verificar memoria disponible:**
```bash
free -h
```

**Aumentar `stopwaitsecs` en la configuración de Supervisor si las tareas tardan mucho.**

---

## 🔐 7. Consideraciones de seguridad

1. **Redis protegido**: Si Redis está expuesto a internet, configura autenticación:
   ```bash
   # En /etc/redis/redis.conf
   requirepass tu_password_seguro
   ```

2. **Logs rotados**: Supervisor ya configura rotación de logs (ver `stdout_logfile_maxbytes` y `stdout_logfile_backups`).

3. **Firewall**: Asegúrate de que solo tu servidor pueda acceder a Redis:
   ```bash
   sudo ufw allow from 127.0.0.1 to any port 6379
   ```

---

## 📈 8. Escalamiento (opcional)

Si necesitas más capacidad de procesamiento:

### Múltiples workers

Edita `/etc/supervisor/conf.d/reyes_estancias_celery.conf`:

```ini
[program:reyes_estancias_celery_worker]
command=/home/tu_usuario/reyes_estancias/venv/bin/celery -A reyes_estancias worker --loglevel=info --concurrency=4
# ... resto de la configuración ...
numprocs=2  # Múltiples procesos worker
process_name=%(program_name)s_%(process_num)02d
```

**⚠️ IMPORTANTE**: Solo debes tener **UN** proceso de Beat corriendo. No escales el Beat, solo los workers.

---

## ✅ 9. Checklist de producción

- [ ] Redis instalado y corriendo
- [ ] Variables de entorno configuradas (`.env`)
- [ ] Supervisor instalado
- [ ] Archivos de configuración creados en `/etc/supervisor/conf.d/`
- [ ] Directorio de logs creado (`/var/log/celery`)
- [ ] Procesos de Celery corriendo (`supervisorctl status`)
- [ ] Tareas registradas correctamente (verificar con shell)
- [ ] Beat schedule configurado (verificar con shell)
- [ ] Logs monitoreados (sin errores)
- [ ] Prueba manual de tareas exitosa

---

## 📞 Contacto y soporte

Si encuentras problemas, revisa:
1. Los logs de Celery (`/var/log/celery/`)
2. Los logs de Django
3. Los logs de Redis (`/var/log/redis/redis-server.log`)

---

**Última actualización:** 2026-01-03
