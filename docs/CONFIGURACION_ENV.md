# 🔧 Guía de Configuración de Variables de Entorno

**Fecha**: 2026-01-05
**Versión**: 1.0

---

## 📋 Archivos de Configuración

| Archivo | Propósito | ¿Incluir en Git? |
|---------|-----------|------------------|
| `.env` | Desarrollo local | ❌ NO (en .gitignore) |
| `.env.production` | Producción | ❌ NO (en .gitignore) |
| `.env.example` | Plantilla sin valores reales | ✅ SÍ (referencia para equipo) |

---

## 🚀 Inicio Rápido

### Desarrollo Local

```bash
# 1. Copiar plantilla
cp .env.example .env

# 2. Editar .env con tus valores de desarrollo
nano .env

# 3. Verificar configuración
python manage.py check
```

### Producción

```bash
# 1. Usar el archivo pre-configurado
cp .env.production .env

# 2. IMPORTANTE: Editar y cambiar TODOS los valores marcados con <CAMBIAR>
nano .env

# 3. Ejecutar verificación pre-deployment
python scripts/pre_deploy_check.py

# 4. Si todo está OK, hacer deployment
```

---

## 📖 Referencia Completa de Variables

### 🔐 Django Core Settings

#### `SECRET_KEY` (CRÍTICO)
**Descripción**: Clave secreta para firmar cookies, tokens CSRF, sesiones, etc.

**Desarrollo**:
```bash
SECRET_KEY=django-insecure-mdsb1(#fbr2gh2$p6g8pr2=)hqxq^wv(wqy(_qrp*a3^i!kh9a
```

**Producción**:
```bash
SECRET_KEY=a19m3#8te$+klj@#a0gppz1j8@gt*g95webcs15bip98npj^cp
```

**⚠️ IMPORTANTE**:
- Debe ser diferente entre desarrollo y producción
- NUNCA compartir públicamente
- Mínimo 50 caracteres aleatorios
- Generar nuevo: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

---

#### `DEBUG` (CRÍTICO)
**Descripción**: Activa/desactiva modo de depuración

**Desarrollo**:
```bash
DEBUG=True
```

**Producción**:
```bash
DEBUG=False  # SIEMPRE False en producción
```

**⚠️ IMPORTANTE**:
- `DEBUG=True` en producción es un **riesgo de seguridad masivo**
- Expone información sensible (rutas, configuración, queries SQL)
- Desactiva protecciones de seguridad

---

#### `ALLOWED_HOSTS` (CRÍTICO)
**Descripción**: Hosts/dominios permitidos para acceder a la aplicación

**Desarrollo**:
```bash
ALLOWED_HOSTS=localhost,127.0.0.1
```

**Producción**:
```bash
ALLOWED_HOSTS=reyes-estancias.com,www.reyes-estancias.com
```

**⚠️ IMPORTANTE**:
- Separa múltiples valores con comas (sin espacios)
- Debe incluir todos tus dominios (con y sin www)
- No incluir `http://` o `https://`, solo el dominio

---

### 🌐 Site Configuration

#### `SITE_BASE_URL`
**Descripción**: URL base completa del sitio (usado por Celery para webhooks y emails)

**Desarrollo**:
```bash
SITE_BASE_URL=http://127.0.0.1:8000
```

**Producción**:
```bash
SITE_BASE_URL=https://reyes-estancias.com
```

**Uso en el código**:
- Generación de URLs absolutas en emails
- Webhooks de Stripe
- Tareas de Celery que necesitan construir URLs

---

### 💳 Stripe Configuration

#### `STRIPE_SECRET_KEY` (CRÍTICO)
**Descripción**: Clave secreta de Stripe para API

**Desarrollo (Test Mode)**:
```bash
clave_secreta_test_de_stripe=>
```

**Producción (Live Mode)**:
```bash
clave_secreta_real_de_stripe=>
```

**Cómo obtenerla**:
1. Ir a https://dashboard.stripe.com/apikeys
2. En "Standard keys" → "Secret key"
3. Para producción, activar "View live data" arriba a la derecha
4. Copiar la clave que empieza con `sk_live_`

---

#### `STRIPE_PUBLISHABLE_KEY`
**Descripción**: Clave pública de Stripe (usada en el frontend)

**Desarrollo**:
```bash
STRIPE_PUBLISHABLE_KEY=pk_test_51RvHUiECYEYfC0UgQQYHqg5Sgh7DpJDwD5DqC1ODMoosPGbJDGUpP11Uce3f4VO1gOxitp92MUePCxIG2PAd2u0l00ApHEJFqG1
```

**Producción**:
```bash
STRIPE_PUBLISHABLE_KEY=pk_live_<TU_CLAVE_AQUI>
```

---

#### `STRIPE_WEBHOOK_SECRET` (CRÍTICO)
**Descripción**: Secret para verificar webhooks de Stripe

**Desarrollo**:
```bash
STRIPE_WEBHOOK_SECRET=whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

**Producción**:
```bash
STRIPE_WEBHOOK_SECRET=whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

**Cómo obtenerlo**:
1. Ir a https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. Endpoint URL: `https://reyes-estancias.com/payments/webhook/`
4. Seleccionar eventos:
   - `payment_intent.succeeded`
   - `payment_intent.payment_failed`
5. Click "Add endpoint"
6. En la página del endpoint, click "Reveal" en "Signing secret"
7. Copiar el valor que empieza con `whsec_`

---

### 🗄️ Database Configuration

#### `DB_NAME`
**Desarrollo**: `reyes_estancias`
**Producción**: `reyes_estancias_prod`

#### `DB_USER`
**Desarrollo**: `reyes_web`
**Producción**: `reyes_web_prod`

#### `DB_PASSWORD` (CRÍTICO)
**Desarrollo**: Contraseña simple
**Producción**: Contraseña fuerte (mínimo 16 caracteres, letras, números, símbolos)

Generar contraseña segura:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### `DB_HOST`
**Desarrollo**: `127.0.0.1` (local)
**Producción**: IP o hostname del servidor MySQL

#### `DB_PORT`
**Desarrollo**: `3306`
**Producción**: `3306` (o el puerto configurado en tu servidor)

---

### 📧 Email Configuration

#### Opción 1: Gmail (Recomendado para empezar)

```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=tu_email@gmail.com
EMAIL_HOST_PASSWORD=tu_app_password_aqui
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

**Cómo obtener App Password de Gmail**:
1. Ir a https://myaccount.google.com/security
2. Activar "2-Step Verification" si no está activo
3. Ir a "App passwords"
4. Generar nueva app password para "Mail"
5. Copiar el código de 16 caracteres (sin espacios)

#### Opción 2: SendGrid

```bash
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.tu_api_key_aqui
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

#### Opción 3: AWS SES

```bash
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_HOST_USER=tu_smtp_username
EMAIL_HOST_PASSWORD=tu_smtp_password
EMAIL_PORT=587
EMAIL_USE_TLS=True
```

---

### 🔴 Celery/Redis Configuration

#### `CELERY_BROKER_URL`
**Descripción**: URL del broker de mensajes (Redis)

**Desarrollo (local)**:
```bash
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
```

**Producción (local)**:
```bash
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
```

**Producción (servicio externo)**:
```bash
# Sin autenticación
CELERY_BROKER_URL=redis://tu-redis-host.com:6379/0

# Con autenticación
CELERY_BROKER_URL=redis://:tu_password@tu-redis-host.com:6379/0
```

**Servicios de Redis recomendados**:
- Railway (Gratis hasta cierto límite)
- Redis Cloud (Gratis 30 MB)
- Upstash (Serverless, gratis hasta 10k comandos/día)

---

### 🔒 Security Settings (Solo Producción)

```bash
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

**⚠️ IMPORTANTE**:
- Solo activar cuando tengas HTTPS configurado
- `SECURE_SSL_REDIRECT=True` redirige todo HTTP a HTTPS
- `HSTS` hace que el navegador siempre use HTTPS

---

### 📅 iCal Configuration

#### `ICAL_CACHE_TIMEOUT`
**Descripción**: Tiempo de caché para calendarios (en segundos)

**Valores recomendados**:
```bash
ICAL_CACHE_TIMEOUT=300   # 5 minutos (desarrollo, ver cambios rápido)
ICAL_CACHE_TIMEOUT=900   # 15 minutos (producción recomendado)
ICAL_CACHE_TIMEOUT=1800  # 30 minutos (menos peticiones)
```

#### `ICAL_REQUEST_TIMEOUT`
**Descripción**: Timeout para peticiones HTTP a calendarios externos

```bash
ICAL_REQUEST_TIMEOUT=10  # 10 segundos (recomendado)
```

#### `ICAL_MAX_SIZE`
**Descripción**: Tamaño máximo de archivos iCal (en bytes)

```bash
ICAL_MAX_SIZE=5242880  # 5 MB (recomendado)
```

---

## ✅ Checklist de Verificación

### Antes de Deployment

- [ ] `SECRET_KEY` es diferente al de desarrollo
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` contiene tu dominio
- [ ] `SITE_BASE_URL` usa `https://`
- [ ] Claves de Stripe en modo `live` (no `test`)
- [ ] Webhook de Stripe configurado en dashboard
- [ ] Base de datos de producción configurada
- [ ] Email real configurado (no Mailtrap)
- [ ] Redis accesible
- [ ] Variables de seguridad SSL activas

### Después de Deployment

- [ ] Ejecutar `python scripts/pre_deploy_check.py`
- [ ] Verificar que emails se envían correctamente
- [ ] Hacer un pago de prueba con Stripe
- [ ] Verificar que Celery Beat ejecuta tareas
- [ ] Ver logs para errores
- [ ] Probar sincronización de calendarios

---

## 🔍 Troubleshooting

### Error: "Invalid HTTP_HOST header"
**Causa**: Dominio no está en `ALLOWED_HOSTS`
**Solución**: Añadir dominio a `ALLOWED_HOSTS`

### Error: "CSRF verification failed"
**Causa**: `CSRF_COOKIE_SECURE=True` pero no hay HTTPS
**Solución**: Configurar HTTPS primero, o temporalmente `CSRF_COOKIE_SECURE=False`

### Error: "Connection refused" (Redis)
**Causa**: Redis no está corriendo o URL incorrecta
**Solución**: Verificar que Redis esté corriendo: `redis-cli ping`

### Error: "Access denied" (MySQL)
**Causa**: Usuario/contraseña incorrectos o permisos faltantes
**Solución**: Verificar credenciales y permisos de usuario en MySQL

---

## 📚 Referencias

- [Django Settings](https://docs.djangoproject.com/en/5.2/ref/settings/)
- [Stripe API Keys](https://stripe.com/docs/keys)
- [Django Security Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Celery Configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html)

---

**Última actualización**: 2026-01-05
