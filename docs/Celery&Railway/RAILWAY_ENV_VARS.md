# Variables de Entorno para Railway

Esta es la lista completa de variables de entorno que deberás configurar en Railway.

## 🔴 OBLIGATORIAS

### Django Core
```
SECRET_KEY=genera_una_clave_secreta_aleatoria_larga
DEBUG=False
ALLOWED_HOSTS=tu-dominio.railway.app,tudominio.com
```

**Generar SECRET_KEY:**
```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Site Configuration
```
SITE_BASE_URL=https://tu-dominio.railway.app
```

### Database (MySQL en Railway)
Railway te proporcionará estas automáticamente cuando añadas MySQL:
```
DB_NAME=${{MySQL.MYSQLDATABASE}}
DB_USER=${{MySQL.MYSQLUSER}}
DB_PASSWORD=${{MySQL.MYSQLPASSWORD}}
DB_HOST=${{MySQL.MYSQLHOST}}
DB_PORT=${{MySQL.MYSQLPORT}}
MYSQL_ROOT_PASSWORD=${{MySQL.MYSQL_ROOT_PASSWORD}}
```

### Celery/Redis (Redis en Railway)
Railway te proporcionará estas automáticamente cuando añadas Redis:
```
CELERY_BROKER_URL=${{Redis.REDIS_URL}}/0
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}/1
```

**Nota:** Si usas Redis Cloud externo:
```
CELERY_BROKER_URL=redis://default:tu_password@redis-12345.cloud.redislabs.com:12345/0
CELERY_RESULT_BACKEND=redis://default:tu_password@redis-12345.cloud.redislabs.com:12345/1
```

### Stripe (Producción)
```
STRIPE_SECRET_KEY=sk_live_tu_clave_secreta_de_produccion
STRIPE_PUBLISHABLE_KEY=pk_live_tu_clave_publica_de_produccion
STRIPE_WEBHOOK_SECRET=whsec_tu_webhook_secret_de_produccion
```

**⚠️ IMPORTANTE:** Usa las claves LIVE (no test) en producción.

## 🟡 OPCIONALES (pero recomendadas)

### Email Configuration
Para enviar emails reales (no Mailtrap):

**Opción 1: Gmail/Google Workspace**
```
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=tu-email@gmail.com
EMAIL_HOST_PASSWORD=tu_app_password
EMAIL_PORT=587
```

**Opción 2: SendGrid**
```
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=tu_sendgrid_api_key
EMAIL_PORT=587
```

**Opción 3: Mailgun**
```
EMAIL_HOST=smtp.mailgun.org
EMAIL_HOST_USER=tu_usuario@tu-dominio.mailgun.org
EMAIL_HOST_PASSWORD=tu_password
EMAIL_PORT=587
```

### iCal Configuration (opcional, tiene defaults)
```
ICAL_CACHE_TIMEOUT=900
ICAL_REQUEST_TIMEOUT=10
ICAL_MAX_SIZE=5242880
ICAL_ALLOWED_HOSTS=airbnb.com,airbnb.es,airbnb.mx,calendar.google.com,booking.com,vrbo.com,homeaway.com
```

## 🔵 NO NECESARIAS en Railway

Estas variables NO son necesarias en Railway:
- ❌ `NPM_BIN_PATH` - Railway lo maneja automáticamente

---

## 📝 Checklist de configuración en Railway

### Servicios a crear:
- [ ] **Web** (Django app)
- [ ] **Worker** (Celery worker)
- [ ] **Beat** (Celery beat)
- [ ] **MySQL** (Base de datos)
- [ ] **Redis** (Broker y backend de Celery)

### Variables a configurar:
- [ ] SECRET_KEY
- [ ] DEBUG=False
- [ ] ALLOWED_HOSTS
- [ ] SITE_BASE_URL
- [ ] STRIPE_SECRET_KEY (LIVE)
- [ ] STRIPE_PUBLISHABLE_KEY (LIVE)
- [ ] STRIPE_WEBHOOK_SECRET
- [ ] Variables de DB (auto-generadas por Railway)
- [ ] Variables de Redis (auto-generadas por Railway)
- [ ] Variables de Email (si usas email real)

---

## 🚀 Orden de configuración en Railway

1. **Crear proyecto** en Railway
2. **Añadir servicio MySQL**
3. **Añadir servicio Redis**
4. **Crear servicio Web** (desde GitHub)
5. **Configurar variables de entorno** en el servicio Web
6. **Duplicar servicio Web** para crear Worker
7. **Duplicar servicio Web** para crear Beat
8. **Configurar comandos** en cada servicio:
   - Web: `gunicorn reyes_estancias.wsgi:application --bind 0.0.0.0:$PORT`
   - Worker: `celery -A reyes_estancias worker --loglevel=info`
   - Beat: `celery -A reyes_estancias beat --loglevel=info`

---

**Última actualización:** 2026-01-06
