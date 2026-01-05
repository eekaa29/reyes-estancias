# 🚀 Guía de Deployment - Reyes Estancias

**Versión:** 1.0
**Fecha:** 2026-01-05
**Autor:** Sistema de Calendarios - Reyes Estancias

---

## 📋 Tabla de Contenidos

1. [Requisitos Previos](#-requisitos-previos)
2. [Preparación del Servidor](#-preparación-del-servidor)
3. [Configuración de Servicios](#-configuración-de-servicios)
4. [Deployment Inicial](#-deployment-inicial)
5. [Checklist Pre-Deployment](#-checklist-pre-deployment)
6. [Verificación Post-Deployment](#-verificación-post-deployment)
7. [Proceso de Actualización](#-proceso-de-actualización)
8. [Rollback](#-rollback-en-caso-de-problemas)
9. [Comandos Útiles](#-comandos-útiles)
10. [Monitoreo (Primeras 24 horas)](#-monitoreo-primeras-24-horas)
11. [Troubleshooting](#-troubleshooting)

---

## 📦 Requisitos Previos

### Servidor

**Especificaciones mínimas:**
- **RAM:** 1 GB (recomendado: 2 GB)
- **CPU:** 1 vCPU (recomendado: 2 vCPUs)
- **Almacenamiento:** 20 GB SSD (recomendado: 40 GB)
- **Sistema Operativo:** Ubuntu 22.04 LTS o superior
- **Acceso:** SSH con usuario con permisos sudo

**Proveedores recomendados:**
- DigitalOcean: Droplet $12-24/mes
- Linode: Shared CPU $12-24/mes
- Vultr: Cloud Compute $12-24/mes
- AWS EC2: t3.small (con capa gratuita primer año)

### Dominio y DNS

- [ ] Dominio registrado (ej: `reyes-estancias.com`)
- [ ] DNS apuntando a IP del servidor:
  - Registro A: `@` → IP del servidor
  - Registro A: `www` → IP del servidor
- [ ] Tiempo de propagación: 24-48 horas (planificar con antelación)

### Acceso a Servicios

- [ ] Cuenta de Stripe con claves de producción (live keys)
- [ ] Servicio de email configurado (Gmail, SendGrid, AWS SES)
- [ ] Acceso SSH al servidor

### Software Local

- [ ] Git instalado
- [ ] Cliente SSH (OpenSSH, PuTTY)
- [ ] (Opcional) Cliente MySQL/MariaDB para backups

---

## 🖥️ Preparación del Servidor

### 1. Actualizar el Sistema

```bash
# Conectar al servidor
ssh usuario@IP_SERVIDOR

# Actualizar paquetes
sudo apt update && sudo apt upgrade -y

# Instalar dependencias básicas
sudo apt install -y build-essential python3-dev python3-pip python3-venv \
                    git curl wget vim software-properties-common
```

### 2. Instalar MySQL 8.0

```bash
# Instalar MySQL Server
sudo apt install -y mysql-server

# Asegurar instalación
sudo mysql_secure_installation

# Configurar MySQL (responder las preguntas):
# - Validar password plugin: Y
# - Nivel de contraseña: 2 (STRONG)
# - Remover usuarios anónimos: Y
# - Deshabilitar login root remoto: Y
# - Remover base de datos de test: Y
# - Recargar privilegios: Y
```

**Crear base de datos y usuario:**

```bash
sudo mysql

# Dentro de MySQL:
CREATE DATABASE reyes_estancias_prod CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'reyes_web_prod'@'localhost' IDENTIFIED BY 'PASSWORD_MUY_SEGURO_AQUI';
GRANT ALL PRIVILEGES ON reyes_estancias_prod.* TO 'reyes_web_prod'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### 3. Instalar Redis

```bash
# Instalar Redis
sudo apt install -y redis-server

# Configurar Redis para usar systemd
sudo nano /etc/redis/redis.conf

# Cambiar:
# supervised no  →  supervised systemd

# Reiniciar Redis
sudo systemctl restart redis-server
sudo systemctl enable redis-server

# Verificar
redis-cli ping
# Debe responder: PONG
```

### 4. Instalar Nginx

```bash
# Instalar Nginx
sudo apt install -y nginx

# Habilitar en el firewall
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable

# Verificar
sudo systemctl status nginx
```

### 5. Configurar Usuario de Aplicación

```bash
# Crear usuario para la aplicación
sudo useradd -m -s /bin/bash reyes
sudo usermod -aG sudo reyes

# Cambiar a usuario reyes
sudo su - reyes
```

---

## ⚙️ Configuración de Servicios

### 1. Clonar Repositorio

```bash
# Como usuario reyes
cd /home/reyes
git clone https://github.com/TU_USUARIO/REYES-ESTANCIAS.git app
cd app
```

### 2. Configurar Entorno Virtual de Python

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar entorno
source venv/bin/activate

# Actualizar pip
pip install --upgrade pip

# Instalar dependencias
pip install -r requirements.txt

# Instalar Gunicorn
pip install gunicorn
```

### 3. Configurar Variables de Entorno

```bash
# Copiar archivo de producción
cp .env.production .env

# Editar con valores reales
nano .env
```

**IMPORTANTE:** Completar TODOS los valores marcados con `<CAMBIAR>`:
- Claves de Stripe (sk_live_, pk_live_, whsec_)
- Credenciales de base de datos
- Credenciales de email
- Cualquier otra configuración específica

### 4. Configurar Django

```bash
# Activar entorno virtual (si no está activo)
source venv/bin/activate

# Verificar configuración
python manage.py check --deploy

# Crear directorio de logs
sudo mkdir -p /var/log/reyes_estancias
sudo chown reyes:reyes /var/log/reyes_estancias
sudo chmod 755 /var/log/reyes_estancias

# Aplicar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Recolectar archivos estáticos
python manage.py collectstatic --no-input
```

### 5. Configurar Gunicorn (Systemd Service)

```bash
# Crear archivo de servicio
sudo nano /etc/systemd/system/gunicorn.service
```

**Contenido:**

```ini
[Unit]
Description=Gunicorn daemon for Reyes Estancias
After=network.target

[Service]
Type=notify
User=reyes
Group=www-data
WorkingDirectory=/home/reyes/app
Environment="PATH=/home/reyes/app/venv/bin"
EnvironmentFile=/home/reyes/app/.env
ExecStart=/home/reyes/app/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/home/reyes/app/gunicorn.sock \
          --timeout 120 \
          --access-logfile /var/log/reyes_estancias/gunicorn-access.log \
          --error-logfile /var/log/reyes_estancias/gunicorn-error.log \
          --log-level info \
          reyes_estancias.wsgi:application

ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Iniciar servicio:**

```bash
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
sudo systemctl status gunicorn
```

### 6. Configurar Nginx

```bash
# Crear configuración del sitio
sudo nano /etc/nginx/sites-available/reyes-estancias
```

**Contenido:**

```nginx
upstream reyes_app {
    server unix:/home/reyes/app/gunicorn.sock fail_timeout=0;
}

server {
    listen 80;
    server_name reyes-estancias.com www.reyes-estancias.com;

    client_max_body_size 20M;

    # Logs
    access_log /var/log/nginx/reyes-estancias-access.log;
    error_log /var/log/nginx/reyes-estancias-error.log;

    # Static files
    location /static/ {
        alias /home/reyes/app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files
    location /media/ {
        alias /home/reyes/app/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

    # Proxy to Gunicorn
    location / {
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        proxy_redirect off;
        proxy_buffering off;

        if (!-f $request_filename) {
            proxy_pass http://reyes_app;
            break;
        }
    }

    # Health check endpoint
    location /health/ {
        access_log off;
        return 200 "OK\n";
        add_header Content-Type text/plain;
    }
}
```

**Activar sitio:**

```bash
# Crear enlace simbólico
sudo ln -s /etc/nginx/sites-available/reyes-estancias /etc/nginx/sites-enabled/

# Eliminar sitio por defecto
sudo rm /etc/nginx/sites-enabled/default

# Verificar configuración
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx
```

### 7. Configurar SSL con Let's Encrypt

```bash
# Instalar Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtener certificado SSL
sudo certbot --nginx -d reyes-estancias.com -d www.reyes-estancias.com

# Seguir las instrucciones:
# 1. Ingresar email para notificaciones
# 2. Aceptar términos de servicio
# 3. Opción 2: Redirect (redirigir HTTP a HTTPS)

# Verificar renovación automática
sudo certbot renew --dry-run

# El certificado se renovará automáticamente cada 90 días
```

### 8. Configurar Celery Worker (Systemd Service)

```bash
# Crear archivo de servicio
sudo nano /etc/systemd/system/celery-worker.service
```

**Contenido:**

```ini
[Unit]
Description=Celery Worker for Reyes Estancias
After=network.target redis-server.service

[Service]
Type=forking
User=reyes
Group=reyes
WorkingDirectory=/home/reyes/app
Environment="PATH=/home/reyes/app/venv/bin"
EnvironmentFile=/home/reyes/app/.env

ExecStart=/home/reyes/app/venv/bin/celery -A reyes_estancias worker \
          --loglevel=info \
          --logfile=/var/log/reyes_estancias/celery-worker.log \
          --pidfile=/var/run/celery/worker.pid \
          --concurrency=2

ExecStop=/bin/kill -s TERM $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Crear directorio para PID:**

```bash
sudo mkdir -p /var/run/celery
sudo chown reyes:reyes /var/run/celery
```

**Iniciar servicio:**

```bash
sudo systemctl start celery-worker
sudo systemctl enable celery-worker
sudo systemctl status celery-worker
```

### 9. Configurar Celery Beat (Systemd Service)

```bash
# Crear archivo de servicio
sudo nano /etc/systemd/system/celery-beat.service
```

**Contenido:**

```ini
[Unit]
Description=Celery Beat Scheduler for Reyes Estancias
After=network.target redis-server.service

[Service]
Type=simple
User=reyes
Group=reyes
WorkingDirectory=/home/reyes/app
Environment="PATH=/home/reyes/app/venv/bin"
EnvironmentFile=/home/reyes/app/.env

ExecStart=/home/reyes/app/venv/bin/celery -A reyes_estancias beat \
          --loglevel=info \
          --logfile=/var/log/reyes_estancias/celery-beat.log \
          --pidfile=/var/run/celery/beat.pid \
          --schedule=/var/run/celery/celerybeat-schedule

ExecStop=/bin/kill -s TERM $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Iniciar servicio:**

```bash
sudo systemctl start celery-beat
sudo systemctl enable celery-beat
sudo systemctl status celery-beat
```

---

## 🚀 Deployment Inicial

### Paso a Paso

1. **Verificar todos los servicios:**

```bash
# Verificar MySQL
sudo systemctl status mysql

# Verificar Redis
sudo systemctl status redis-server

# Verificar Nginx
sudo systemctl status nginx

# Verificar Gunicorn
sudo systemctl status gunicorn

# Verificar Celery Worker
sudo systemctl status celery-worker

# Verificar Celery Beat
sudo systemctl status celery-beat
```

2. **Ejecutar script de verificación:**

```bash
cd /home/reyes/app
source venv/bin/activate
python scripts/pre_deploy_check.py --env .env
```

3. **Configurar Webhook de Stripe:**

- Ir a: https://dashboard.stripe.com/webhooks
- Añadir endpoint: `https://reyes-estancias.com/payments/webhook/`
- Seleccionar eventos:
  - `payment_intent.succeeded`
  - `payment_intent.payment_failed`
- Copiar el webhook secret y actualizar en `.env`:
  ```bash
  nano .env
  # Actualizar: STRIPE_WEBHOOK_SECRET=whsec_...
  ```
- Reiniciar Gunicorn:
  ```bash
  sudo systemctl restart gunicorn
  ```

4. **Verificar el sitio:**

- Abrir navegador: `https://reyes-estancias.com`
- Verificar que carga correctamente
- Verificar certificado SSL (candado verde)
- Probar navegación básica

5. **Acceder al Admin:**

- Ir a: `https://reyes-estancias.com/admin/`
- Login con superusuario creado
- Verificar que el panel funciona

---

## ✅ Checklist Pre-Deployment

Ejecutar este checklist ANTES de hacer deployment:

### Configuración

- [ ] Archivo `.env` configurado con valores de producción
- [ ] `DEBUG=False` en `.env`
- [ ] Django `SECRET\_KEY` único y seguro
- [ ] `ALLOWED_HOSTS` configurado con dominio real
- [ ] Claves de Stripe en modo LIVE (sk_live_, pk_live_)
- [ ] Credenciales de base de datos configuradas
- [ ] Servicio de email configurado (no Mailtrap)
- [ ] Variables de seguridad activadas (SSL, cookies seguras)

### Base de Datos

- [ ] Base de datos de producción creada
- [ ] Usuario de base de datos con permisos correctos
- [ ] Migraciones aplicadas: `python manage.py migrate`
- [ ] Superusuario creado: `python manage.py createsuperuser`

### Archivos Estáticos

- [ ] `STATIC_ROOT` configurado en settings
- [ ] Archivos estáticos recolectados: `python manage.py collectstatic`
- [ ] Permisos correctos en directorio de estáticos

### Servicios

- [ ] MySQL corriendo y accesible
- [ ] Redis corriendo y accesible
- [ ] Nginx configurado y corriendo
- [ ] Gunicorn configurado como servicio systemd
- [ ] Celery Worker configurado y corriendo
- [ ] Celery Beat configurado y corriendo

### Seguridad

- [ ] SSL/HTTPS configurado con Let's Encrypt
- [ ] Firewall configurado (ufw)
- [ ] SSH con autenticación por clave (no password)
- [ ] Fail2ban instalado (recomendado)
- [ ] Backups automatizados configurados

### DNS y Dominio

- [ ] Dominio apuntando a IP del servidor
- [ ] Registros DNS propagados
- [ ] Certificado SSL válido y activo

### Stripe

- [ ] Webhook configurado en Stripe Dashboard
- [ ] STRIPE_WEBHOOK_SECRET actualizado en `.env`
- [ ] Webhook verificado con test

### Verificación Final

- [ ] Script pre_deploy_check.py ejecutado y PASADO
- [ ] Check de Django sin errores: `python manage.py check --deploy`
- [ ] Logs sin errores críticos
- [ ] Prueba de carga del sitio web
- [ ] Prueba de admin panel

---

## 🔍 Verificación Post-Deployment

### Primeros 15 Minutos

1. **Verificar servicios activos:**

```bash
# Ver todos los servicios
sudo systemctl status gunicorn celery-worker celery-beat nginx mysql redis-server
```

2. **Verificar logs sin errores:**

```bash
# Gunicorn
tail -f /var/log/reyes_estancias/gunicorn-error.log

# Nginx
tail -f /var/log/nginx/reyes-estancias-error.log

# Django
tail -f /var/log/reyes_estancias/django.log

# Celery
tail -f /var/log/reyes_estancias/celery-worker.log
```

3. **Probar funcionalidades críticas:**

- [ ] Página principal carga
- [ ] Login funciona
- [ ] Admin panel accesible
- [ ] Búsqueda de propiedades funciona
- [ ] Sistema de calendarios funcionando
- [ ] Proceso de reserva funciona
- [ ] Pagos con Stripe funcionan (usar modo test primero)
- [ ] Emails se envían correctamente

4. **Verificar tareas de Celery:**

```bash
# Ver tareas programadas
cd /home/reyes/app
source venv/bin/activate
python manage.py shell

# Dentro del shell:
from celery import current_app
inspect = current_app.control.inspect()
print(inspect.scheduled())
```

---

## 🔄 Proceso de Actualización

### Deployment de Nuevas Versiones

**Pasos para actualizar el código:**

```bash
# 1. Conectar al servidor
ssh reyes@IP_SERVIDOR

# 2. Ir al directorio de la app
cd /home/reyes/app

# 3. Activar entorno virtual
source venv/bin/activate

# 4. Hacer backup de la base de datos
mysqldump -u reyes_web_prod -p reyes_estancias_prod > ~/backups/db_$(date +%Y%m%d_%H%M%S).sql

# 5. Obtener últimos cambios
git fetch origin
git checkout main
git pull origin main

# 6. Actualizar dependencias (si cambiaron)
pip install -r requirements.txt --upgrade

# 7. Aplicar migraciones (si hay)
python manage.py migrate

# 8. Recolectar archivos estáticos (si cambiaron)
python manage.py collectstatic --no-input

# 9. Reiniciar servicios
sudo systemctl restart gunicorn
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat

# 10. Verificar que todo funciona
sudo systemctl status gunicorn celery-worker celery-beat

# 11. Verificar logs
tail -f /var/log/reyes_estancias/django.log
```

### Estrategia de Deployment sin Downtime (Zero-Downtime)

Para deployments más grandes, usar esta estrategia:

```bash
# 1. Poner el sitio en modo mantenimiento (opcional)
# Crear página de mantenimiento en Nginx

# 2. Detener workers de Celery para evitar trabajos a medias
sudo systemctl stop celery-worker celery-beat

# 3. Actualizar código
git pull origin main

# 4. Instalar dependencias
pip install -r requirements.txt --upgrade

# 5. Aplicar migraciones
python manage.py migrate

# 6. Recolectar estáticos
python manage.py collectstatic --no-input

# 7. Reiniciar Gunicorn (sin downtime usando reload)
sudo systemctl reload gunicorn

# 8. Reiniciar Celery
sudo systemctl start celery-worker
sudo systemctl start celery-beat

# 9. Quitar modo mantenimiento
```

---

## ⏮️ Rollback en Caso de Problemas

### Rollback Rápido (Git)

Si el deployment falla, volver a la versión anterior:

```bash
# 1. Ver commits recientes
git log --oneline -5

# 2. Volver al commit anterior
git reset --hard HASH_DEL_COMMIT_ANTERIOR

# 3. Restaurar dependencias (si cambiaron)
pip install -r requirements.txt

# 4. Revertir migraciones (si se aplicaron)
python manage.py migrate nombre_app numero_migracion_anterior

# 5. Recolectar estáticos
python manage.py collectstatic --no-input

# 6. Reiniciar servicios
sudo systemctl restart gunicorn celery-worker celery-beat

# 7. Verificar que funciona
curl -I https://reyes-estancias.com
```

### Rollback de Base de Datos

Si las migraciones causaron problemas:

```bash
# 1. Detener servicios
sudo systemctl stop gunicorn celery-worker celery-beat

# 2. Restaurar backup
mysql -u reyes_web_prod -p reyes_estancias_prod < ~/backups/db_FECHA.sql

# 3. Reiniciar servicios
sudo systemctl start gunicorn celery-worker celery-beat
```

### Plan de Contingencia

En caso de fallo crítico:

1. **Activar página de mantenimiento**
2. **Notificar a usuarios** (si es posible)
3. **Investigar logs** para identificar el problema
4. **Decidir:** ¿Rollback o Fix Forward?
5. **Ejecutar solución**
6. **Verificar funcionamiento**
7. **Quitar página de mantenimiento**
8. **Post-mortem:** Documentar qué pasó y cómo prevenirlo

---

## 🛠️ Comandos Útiles

### Gestión de Servicios

```bash
# Ver estado de todos los servicios
sudo systemctl status gunicorn celery-worker celery-beat nginx mysql redis-server

# Reiniciar servicios
sudo systemctl restart gunicorn
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
sudo systemctl restart nginx

# Recargar configuración (sin downtime)
sudo systemctl reload gunicorn
sudo systemctl reload nginx

# Ver logs en tiempo real
sudo journalctl -u gunicorn -f
sudo journalctl -u celery-worker -f
```

### Django Management

```bash
# Activar entorno
cd /home/reyes/app && source venv/bin/activate

# Shell de Django
python manage.py shell

# Verificar configuración
python manage.py check --deploy

# Ver migraciones
python manage.py showmigrations

# Crear superusuario
python manage.py createsuperuser

# Limpiar caché
python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

### Base de Datos

```bash
# Backup manual
mysqldump -u reyes_web_prod -p reyes_estancias_prod > backup_$(date +%Y%m%d).sql

# Backup con compresión
mysqldump -u reyes_web_prod -p reyes_estancias_prod | gzip > backup_$(date +%Y%m%d).sql.gz

# Restaurar backup
mysql -u reyes_web_prod -p reyes_estancias_prod < backup_20260105.sql

# Conectar a MySQL
mysql -u reyes_web_prod -p reyes_estancias_prod
```

### Logs

```bash
# Ver logs de aplicación
tail -f /var/log/reyes_estancias/django.log
tail -f /var/log/reyes_estancias/errors.log
tail -f /var/log/reyes_estancias/celery-worker.log
tail -f /var/log/reyes_estancias/celery-beat.log
tail -f /var/log/reyes_estancias/ical.log
tail -f /var/log/reyes_estancias/payments.log

# Ver logs de Nginx
tail -f /var/log/nginx/reyes-estancias-access.log
tail -f /var/log/nginx/reyes-estancias-error.log

# Ver logs de Gunicorn
tail -f /var/log/reyes_estancias/gunicorn-access.log
tail -f /var/log/reyes_estancias/gunicorn-error.log

# Buscar errores en logs
grep -i error /var/log/reyes_estancias/django.log
grep -i critical /var/log/reyes_estancias/errors.log
```

### Celery

```bash
cd /home/reyes/app && source venv/bin/activate

# Inspeccionar workers activos
celery -A reyes_estancias inspect active

# Ver tareas programadas
celery -A reyes_estancias inspect scheduled

# Ver estadísticas
celery -A reyes_estancias inspect stats

# Purgar todas las tareas pendientes (CUIDADO)
celery -A reyes_estancias purge

# Ejecutar tarea manualmente
python manage.py shell
>>> from properties.tasks import sync_all_property_calendars
>>> sync_all_property_calendars.delay()
```

### Monitoreo del Sistema

```bash
# Uso de CPU y memoria
htop

# Espacio en disco
df -h

# Procesos de Python
ps aux | grep python

# Conexiones activas a MySQL
mysql -u root -p -e "SHOW PROCESSLIST;"

# Conexiones activas en Nginx
sudo netstat -plan | grep :80 | wc -l
```

---

## 📊 Monitoreo (Primeras 24 Horas)

### Checklist de Monitoreo

**Primera hora:**
- [ ] Verificar logs cada 15 minutos
- [ ] Verificar que todos los servicios están activos
- [ ] Probar todas las funcionalidades críticas
- [ ] Verificar que Celery ejecuta tareas programadas
- [ ] Monitorear uso de recursos (CPU, RAM, disco)

**Primeras 6 horas:**
- [ ] Verificar logs cada hora
- [ ] Revisar logs de errores
- [ ] Verificar que se envían emails correctamente
- [ ] Verificar sincronización de calendarios
- [ ] Probar proceso de reserva completo

**Primeras 24 horas:**
- [ ] Verificar logs cada 3-4 horas
- [ ] Revisar métricas de rendimiento
- [ ] Verificar backups automáticos
- [ ] Monitorear errores en Stripe
- [ ] Verificar que no hay memory leaks

### Métricas Clave a Monitorear

1. **Disponibilidad:**
   - Uptime del sitio: debe ser > 99.9%
   - Tiempo de respuesta: < 2 segundos

2. **Errores:**
   - Errores 500: idealmente 0
   - Errores 404: revisar si hay páginas rotas
   - Errores de Celery: revisar logs

3. **Recursos:**
   - CPU: < 70% en promedio
   - RAM: < 80% en promedio
   - Disco: < 80% usado

4. **Base de Datos:**
   - Conexiones activas: < 50
   - Slow queries: revisar y optimizar

5. **Celery:**
   - Tareas fallidas: revisar y corregir
   - Workers activos: mínimo 1
   - Beat programado: verificar schedule

### Herramientas de Monitoreo (Opcionales)

- **Uptime Robot:** Monitoreo de disponibilidad (gratuito)
- **Sentry:** Tracking de errores (tiene plan gratuito)
- **Grafana + Prometheus:** Métricas avanzadas
- **New Relic:** APM completo
- **Flower:** Monitoreo de Celery en tiempo real

---

## 🔧 Troubleshooting

### Problemas Comunes y Soluciones

#### 1. Sitio no carga (502 Bad Gateway)

**Causa:** Gunicorn no está corriendo o no puede conectar

```bash
# Verificar estado de Gunicorn
sudo systemctl status gunicorn

# Ver logs
tail -f /var/log/reyes_estancias/gunicorn-error.log

# Reiniciar
sudo systemctl restart gunicorn

# Si persiste, verificar permisos del socket
ls -la /home/reyes/app/gunicorn.sock
```

#### 2. Errores 500 en el sitio

**Causa:** Error en el código de Django

```bash
# Ver logs de Django
tail -f /var/log/reyes_estancias/errors.log

# Ver logs de Gunicorn
tail -f /var/log/reyes_estancias/gunicorn-error.log

# Verificar DEBUG=False
grep DEBUG /home/reyes/app/.env

# Verificar ALLOWED_HOSTS
grep ALLOWED_HOSTS /home/reyes/app/.env
```

#### 3. Archivos estáticos no cargan (CSS, JS, imágenes)

**Causa:** Archivos no recolectados o permisos incorrectos

```bash
# Recolectar estáticos
cd /home/reyes/app
source venv/bin/activate
python manage.py collectstatic --no-input

# Verificar permisos
ls -la staticfiles/

# Verificar configuración de Nginx
sudo nginx -t
```

#### 4. Celery no ejecuta tareas

**Causa:** Worker no está corriendo o Redis no está accesible

```bash
# Verificar Celery Worker
sudo systemctl status celery-worker

# Verificar Redis
redis-cli ping

# Ver logs de Celery
tail -f /var/log/reyes_estancias/celery-worker.log

# Reiniciar Celery
sudo systemctl restart celery-worker celery-beat
```

#### 5. Emails no se envían

**Causa:** Configuración de email incorrecta

```bash
# Verificar configuración
grep EMAIL /home/reyes/app/.env

# Probar desde Django shell
cd /home/reyes/app && source venv/bin/activate
python manage.py shell

# En el shell:
from django.core.mail import send_mail
send_mail('Test', 'This is a test', 'from@example.com', ['to@example.com'])
```

#### 6. No se puede conectar a MySQL

**Causa:** MySQL no está corriendo o credenciales incorrectas

```bash
# Verificar MySQL
sudo systemctl status mysql

# Probar conexión
mysql -u reyes_web_prod -p -h localhost reyes_estancias_prod

# Ver logs de MySQL
sudo tail -f /var/log/mysql/error.log

# Verificar credenciales en .env
grep DB_ /home/reyes/app/.env
```

#### 7. SSL/HTTPS no funciona

**Causa:** Certificado no instalado o expirado

```bash
# Verificar certificado
sudo certbot certificates

# Renovar certificado
sudo certbot renew

# Verificar configuración de Nginx
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx
```

#### 8. Alto uso de memoria

**Causa:** Memory leak o configuración inadecuada

```bash
# Ver procesos
htop

# Reiniciar Gunicorn (libera memoria)
sudo systemctl restart gunicorn

# Reducir workers de Gunicorn si es necesario
sudo nano /etc/systemd/system/gunicorn.service
# Cambiar --workers 3 a --workers 2
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

---

## 📚 Referencias Adicionales

### Documentación del Proyecto

- [ROADMAP_MEJORAS_CALENDARIOS.md](./ROADMAP_MEJORAS_CALENDARIOS.md) - Roadmap de mejoras
- [CELERY_ANALISIS_Y_PRODUCCION.md](./CELERY_ANALISIS_Y_PRODUCCION.md) - Configuración de Celery
- [STRIPE_PRODUCCION.md](./STRIPE_PRODUCCION.md) - Configuración de Stripe
- [SISTEMA_LOGGING.md](./SISTEMA_LOGGING.md) - Sistema de logs
- [CONFIGURACION_ENV.md](./CONFIGURACION_ENV.md) - Variables de entorno

### Comandos Esenciales de Referencia Rápida

```bash
# Script de verificación pre-deployment
python scripts/pre_deploy_check.py --env .env

# Verificar configuración Django
python manage.py check --deploy

# Reiniciar todos los servicios
sudo systemctl restart gunicorn celery-worker celery-beat nginx

# Ver todos los logs
tail -f /var/log/reyes_estancias/*.log

# Backup de base de datos
mysqldump -u reyes_web_prod -p reyes_estancias_prod | gzip > backup_$(date +%Y%m%d).sql.gz

# Limpiar caché de Redis
redis-cli FLUSHDB
```

---

## 🆘 Contacto y Soporte

**En caso de emergencia durante el deployment:**

1. **Revisar logs** para identificar el problema
2. **Consultar sección de Troubleshooting** en este documento
3. **Ejecutar rollback** si es necesario
4. **Documentar el problema** para análisis posterior

**Post-Deployment:**
- Crear issues en GitHub para problemas encontrados
- Actualizar esta documentación con lecciones aprendidas
- Mantener backups regulares de base de datos y código

---

**Última actualización:** 2026-01-05
**Versión del documento:** 1.0
**Autor:** Sistema de Calendarios - Reyes Estancias
