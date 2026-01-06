# Guía de Deployment en Railway - Reyes Estancias

Esta guía te llevará paso a paso por el proceso de desplegar Reyes Estancias en Railway.

## 📋 Pre-requisitos

Antes de empezar, asegúrate de tener:
- ✅ Cuenta de GitHub con el repositorio subido
- ✅ Email y contraseña del cliente para crear cuenta
- ✅ Claves de Stripe en modo LIVE (producción)
- ✅ Configuración de email (Gmail, SendGrid, etc.)

---

## 🚀 FASE 1: Crear cuenta y proyecto en Railway

### Paso 1: Crear cuenta

1. Ve a https://railway.app
2. Click en "Start a New Project"
3. Selecciona "Sign up with email"
4. Usa el **email del cliente**
5. Verifica el email

### Paso 2: Conectar con GitHub

1. En Railway, ve a Account Settings
2. Click en "Connect GitHub account"
3. Autoriza Railway para acceder a tus repositorios
4. Selecciona el repositorio `REYES-ESTANCIAS`

### Paso 3: Crear nuevo proyecto

1. Click en "New Project"
2. Selecciona "Deploy from GitHub repo"
3. Busca y selecciona `REYES-ESTANCIAS`
4. Railway detectará automáticamente que es un proyecto Django

---

## 🗄️ FASE 2: Añadir servicios de base de datos

### Paso 4: Añadir MySQL

1. En tu proyecto, click en "+ New"
2. Selecciona "Database" → "Add MySQL"
3. Railway creará automáticamente:
   - `MYSQLHOST`
   - `MYSQLPORT`
   - `MYSQLDATABASE`
   - `MYSQLUSER`
   - `MYSQLPASSWORD`
   - `MYSQL_ROOT_PASSWORD`

### Paso 5: Añadir Redis

1. Click en "+ New" nuevamente
2. Selecciona "Database" → "Add Redis"
3. Railway creará automáticamente:
   - `REDIS_URL`

---

## ⚙️ FASE 3: Configurar el servicio Web (Django)

### Paso 6: Configurar variables de entorno

En el servicio que desplegó tu código (debería llamarse algo como `reyes-estancias`):

1. Click en el servicio
2. Ve a la pestaña "Variables"
3. Click en "+ New Variable" y añade las siguientes:

#### Variables obligatorias:

```bash
# Django Core
SECRET_KEY=<genera una clave con: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=.railway.app

# Site
SITE_BASE_URL=https://tu-proyecto.up.railway.app

# Database - Referenciar variables de MySQL
DB_NAME=${{MySQL.MYSQLDATABASE}}
DB_USER=${{MySQL.MYSQLUSER}}
DB_PASSWORD=${{MySQL.MYSQLPASSWORD}}
DB_HOST=${{MySQL.MYSQLHOST}}
DB_PORT=${{MySQL.MYSQLPORT}}
MYSQL_ROOT_PASSWORD=${{MySQL.MYSQL_ROOT_PASSWORD}}

# Redis - Referenciar variables de Redis
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/0
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/1

# Stripe (PRODUCCIÓN - usa claves LIVE)
STRIPE_SECRET_KEY=sk_live_tu_clave_secreta
STRIPE_PUBLISHABLE_KEY=pk_live_tu_clave_publica
STRIPE_WEBHOOK_SECRET=whsec_tu_webhook_secret

# Email (ejemplo con Gmail)
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=tu-email@gmail.com
EMAIL_HOST_PASSWORD=tu_app_password_de_gmail
EMAIL_PORT=587
```

**Nota:** Para las variables de base de datos, Railway te permite referenciar las variables auto-generadas usando `${{NombreServicio.VARIABLE}}`.

### Paso 7: Configurar el comando de inicio

1. En el servicio web, ve a "Settings"
2. Busca "Start Command"
3. Verifica que use: `gunicorn reyes_estancias.wsgi:application --bind 0.0.0.0:$PORT`
   - (Railway debería detectarlo automáticamente del Procfile)

### Paso 8: Ejecutar migraciones

Después del primer deploy:

1. Ve a la pestaña "Deployments"
2. Una vez que el deploy esté en estado "Success", click en los 3 puntos (...)
3. Selecciona "View Logs"
4. En la parte superior, click en "Shell" o usa el botón de terminal
5. Ejecuta:
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

---

## 👷 FASE 4: Configurar Workers de Celery

### Paso 9: Crear servicio Worker

1. En el proyecto, click en "+ New"
2. Selecciona "Empty Service"
3. Nómbralo "celery-worker"
4. En Settings:
   - **Source**: Mismo repositorio de GitHub que el servicio web
   - **Start Command**: `celery -A reyes_estancias worker --loglevel=info`
5. En Variables:
   - Click en "Reference variables from another service"
   - Selecciona el servicio web (esto copiará todas las variables de entorno)

### Paso 10: Crear servicio Beat

1. Click en "+ New"
2. Selecciona "Empty Service"
3. Nómbralo "celery-beat"
4. En Settings:
   - **Source**: Mismo repositorio de GitHub
   - **Start Command**: `celery -A reyes_estancias beat --loglevel=info`
5. En Variables:
   - Click en "Reference variables from another service"
   - Selecciona el servicio web

**⚠️ IMPORTANTE**: Solo debe haber UN proceso de Beat corriendo. Nunca escales Beat a múltiples instancias.

---

## ✅ FASE 5: Verificación

### Paso 11: Verificar que todo funciona

1. **Servicio Web**:
   - Ve a la URL generada (https://tu-proyecto.up.railway.app)
   - Verifica que la página carga correctamente

2. **Celery Worker**:
   - Ve a los logs del servicio "celery-worker"
   - Deberías ver: `celery@worker ready.`

3. **Celery Beat**:
   - Ve a los logs del servicio "celery-beat"
   - Deberías ver: `beat: Starting...`

4. **Redis**:
   - En el admin de Django, prueba crear una reserva
   - Verifica que las tareas se ejecutan

### Paso 12: Configurar Webhooks de Stripe

1. Ve al Dashboard de Stripe: https://dashboard.stripe.com
2. Ve a "Developers" → "Webhooks"
3. Click en "Add endpoint"
4. URL del webhook: `https://tu-proyecto.up.railway.app/payments/webhook/stripe/`
5. Selecciona eventos:
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
   - (y cualquier otro que uses)
6. Copia el **Signing secret** (whsec_...)
7. Actualiza la variable `STRIPE_WEBHOOK_SECRET` en Railway

---

## 🔍 FASE 6: Monitoreo

### Verificar uso de recursos

1. Ve a la pestaña "Metrics" en cada servicio
2. Monitorea:
   - CPU usage
   - Memory usage
   - Network (egress)

### Ver logs

Para cada servicio:
1. Click en el servicio
2. Ve a "Deployments"
3. Click en el último deployment
4. Ve a "View Logs"

---

## 🐛 Troubleshooting

### Error: "Application failed to respond"
- Verifica que `ALLOWED_HOSTS` incluya `.railway.app`
- Verifica los logs del servicio web

### Error: "relation does not exist"
- No ejecutaste las migraciones
- Ejecuta `python manage.py migrate` en el shell

### Error: Celery workers no conectan a Redis
- Verifica que `CELERY_BROKER_URL` esté correctamente configurada
- Verifica que el servicio Redis esté corriendo

### Error: Archivos estáticos no cargan
- Ejecuta `python manage.py collectstatic --noinput`
- Verifica que `STATIC_ROOT` esté configurado

### Error: Tareas de Celery no se ejecutan
- Verifica que el worker esté corriendo (check logs)
- Verifica que Beat esté corriendo (check logs)
- Verifica la configuración de Redis

---

## 💰 Costos estimados

Con tráfico moderado:
- **Web + Worker + Beat**: ~$8-15/mes
- **MySQL**: ~$5/mes
- **Redis**: ~$3/mes
- **Total estimado**: $15-25/mes

El tier gratuito de $5/mes puede cubrir desarrollo/testing, pero en producción es normal excederlo.

---

## 📝 Checklist final

- [ ] Cuenta de Railway creada con email del cliente
- [ ] Repositorio conectado a GitHub
- [ ] MySQL añadido y configurado
- [ ] Redis añadido y configurado
- [ ] Servicio Web desplegado y corriendo
- [ ] Variables de entorno configuradas
- [ ] Migraciones ejecutadas
- [ ] Superusuario creado
- [ ] Archivos estáticos recolectados
- [ ] Celery Worker corriendo
- [ ] Celery Beat corriendo
- [ ] Webhooks de Stripe configurados
- [ ] Sitio accesible públicamente
- [ ] Pruebas de funcionalidad realizadas

---

## 🔄 Actualizaciones futuras

Cada vez que hagas cambios en el código:

1. **Push a GitHub**:
   ```bash
   git add .
   git commit -m "Descripción del cambio"
   git push origin main
   ```

2. Railway automáticamente:
   - Detectará el cambio
   - Ejecutará un nuevo build
   - Desplegará la nueva versión
   - Los 3 servicios (web, worker, beat) se actualizarán

3. Si hay nuevas migraciones:
   - Ve al shell del servicio web
   - Ejecuta `python manage.py migrate`

---

**Última actualización:** 2026-01-06
