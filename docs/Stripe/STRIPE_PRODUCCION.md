# Guía Completa: Migración de Stripe a Producción

## 📋 Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Análisis del Estado Actual](#análisis-del-estado-actual)
3. [Checklist de Producción](#checklist-de-producción)
4. [Configuración Paso a Paso](#configuración-paso-a-paso)
5. [Testing y Validación](#testing-y-validación)
6. [Troubleshooting](#troubleshooting)
7. [Referencias](#referencias)

---

## 🎯 Resumen Ejecutivo

### Estado Actual
- ✅ Implementación de Stripe **CORRECTA** y lista para producción
- ⚠️ Actualmente usando credenciales de **prueba** (test mode)
- ✅ Arquitectura de pagos en dos fases (30% depósito + 70% balance)
- ✅ Sistema de webhooks implementado correctamente
- ✅ Cobros off-session con fallback a Checkout Sessions
- ✅ Sistema de reembolsos completo

### Cambios Mínimos Necesarios

Para pasar a producción solo necesitas:

1. **Cambiar 3 variables de entorno** (credenciales de Stripe)
2. **Configurar 1 webhook** en Stripe Dashboard
3. **Cambiar proveedor de email** (de Mailtrap a producción)
4. **Corregir 2 bugs menores** (ya identificados y corregidos)

**Tiempo estimado**: 30-60 minutos

---

## 📊 Análisis del Estado Actual

### ✅ Aspectos Implementados Correctamente

#### 1. **Arquitectura de Pagos en Dos Fases**
**Ubicación**: `payments/views.py:37-167`, `payments/services.py:62-191`

**Flujo**:
```
1. Depósito (30%)
   ↓
   Cobrado inmediatamente con Checkout Session
   ↓
   Guarda método de pago (setup_future_usage="off_session")
   ↓
2. Balance (70%)
   ↓
   Programado para arrival + 2 días (Celery)
   ↓
   Intenta cobro off-session automático
   ↓
   Si falla → Crea Checkout Session + envía email
```

**Ventajas**:
- ✅ Mejor cash flow (cobras 30% inmediatamente)
- ✅ Experiencia de usuario mejorada (un solo pago manual)
- ✅ Cumplimiento de normativas de pagos

---

#### 2. **Sistema de Webhooks Robusto**
**Ubicación**: `payments/views.py:196-374`

**Eventos manejados**:
- ✅ `checkout.session.completed` → Confirma pagos
- ✅ `payment_intent.payment_failed` → Marca pagos fallidos
- ✅ `refund.updated` → Actualiza estado de reembolsos
- ✅ `charge.refunded` → Procesa reembolsos

**Seguridad**:
- ✅ Validación de firma con `STRIPE_WEBHOOK_SECRET`
- ✅ Idempotencia (evita procesamiento duplicado)
- ✅ Transacciones atómicas

---

#### 3. **Gestión de Estados**
**Ubicación**: `payments/models.py:7-16`

**Estados definidos**:
```python
PAYMENT_STATUS = [
    ("pending", "Pendiente"),
    ("paid", "Pagado"),
    ("failed", "Fallido"),
    ("requires_action", "Requiere intervención"),
    ("void", "Anulado"),
    ("superseded", "Reemplazado"),
    ("expired", "Caducado"),
]
```

**Transiciones correctas**:
- ✅ `pending` → `paid` (webhook: checkout.session.completed)
- ✅ `pending` → `requires_action` (cobro off-session falla)
- ✅ `requires_action` → `paid` (usuario completa pago manual)

---

#### 4. **Sistema de Reembolsos**
**Ubicación**: `payments/services.py:233-284`, `payments/models.py:78-91`

**Política de cancelación**:
- **>7 días antes del check-in**: Reembolso total del depósito
- **0-7 días antes**: No hay reembolso (penalización 50%)
- **No show (pasó check-in)**: No hay reembolso (penalización 100%)

**Implementación**:
- ✅ Modelo `RefundLog` para auditoría
- ✅ Soporte para reembolsos parciales
- ✅ Manejo de múltiples depósitos (top-ups)

---

#### 5. **Cobros Off-Session con Fallback**
**Ubicación**: `payments/services.py:62-191`

**Flujo inteligente**:
```python
try:
    # Intenta cobro off-session (sin interacción del usuario)
    stripe.PaymentIntent.create(..., off_session=True, confirm=True)
except stripe.error.CardError:
    # Si falla (ej: requiere 3DS)
    # Crea Checkout Session + envía email al usuario
```

**Ventajas**:
- ✅ Automatización máxima
- ✅ Fallback elegante cuando se requiere acción del usuario
- ✅ Notificación por email

---

#### 6. **Tareas Celery para Automatización**
**Ubicación**: `payments/tasks.py`, `reyes_estancias/settings.py:211-225`

**Tareas configuradas**:

1. **`scan_and_charge_balances`** (cada 15 min):
   - Busca reservas confirmadas con arrival >= 2 días atrás
   - Encola cobro de balance para cada una

2. **`charge_balance_for_booking`**:
   - Cobra el balance de una reserva específica
   - Reintentos automáticos (max 3, delay 30s)

3. **`mark_expired_bookings`** (diario a las 3 AM):
   - Marca reservas pendientes con hold expirado

4. **`mark_expired_holds`** (cada hora):
   - Libera fechas de reservas con hold expirado

---

### ⚠️ Bugs Identificados y Corregidos

#### Bug 1: `SITE_BASE_URL` Sobrescrito ✅ CORREGIDO
**Ubicación**: `reyes_estancias/settings.py`

**Problema**:
```python
# Línea 19: Carga correctamente desde .env
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "http://127.0.0.1:8000")

# Línea 230: ¡SOBRESCRIBE el valor! ❌
SITE_BASE_URL = "http://127.0.0.1:8000"  # Esta línea ha sido eliminada
```

**Impacto**: Las URLs de webhooks y emails siempre usaban `http://127.0.0.1:8000` en producción.

**Solución**: Eliminada la línea 230.

---

#### Bug 2: Typo en `payments/tasks.py` ✅ CORREGIDO
**Ubicación**: `payments/tasks.py:26`

**Problema**:
```python
b = booking.objects.select_for_update().get(pk=booking_id)  # ❌ debe ser Booking
```

**Solución**:
```python
b = Booking.objects.select_for_update().get(pk=booking_id)  # ✅
```

---

#### Bug 3: Lógica Redundante en `RetryBalancePaymentView` ✅ CORREGIDO
**Ubicación**: `payments/views.py:498-541`

**Problema**: Ver documento `BUGFIX_RETRY_BALANCE_PAYMENT.md` para detalles completos.

**Resumen**: Creaba sesiones duplicadas de Stripe y flujo innecesariamente complejo.

**Solución**: Guardar `session.id` en BD y redirigir directamente a Stripe.

---

## 📋 Checklist de Producción

Usa este checklist para asegurar que todo está configurado correctamente.

### Fase 1: Credenciales de Stripe 🔴 CRÍTICO

- [ ] Obtener credenciales de producción desde [Stripe Dashboard](https://dashboard.stripe.com/apikeys)
- [ ] Actualizar `STRIPE_SECRET_KEY` (de `sk_test_...` a `sk_live_...`)
- [ ] Actualizar `STRIPE_PUBLISHABLE_KEY` (de `pk_test_...` a `pk_live_...`)
- [ ] Configurar webhook en producción (ver Fase 2)
- [ ] Actualizar `STRIPE_WEBHOOK_SECRET` con el secret del webhook de producción

---

### Fase 2: Webhook de Stripe 🔴 CRÍTICO

- [ ] Ir a [Stripe Webhooks](https://dashboard.stripe.com/webhooks)
- [ ] Crear nuevo endpoint: `https://tu-dominio.com/payments/webhook/`
- [ ] Seleccionar eventos:
  - [ ] `checkout.session.completed`
  - [ ] `payment_intent.payment_failed`
  - [ ] `refund.updated`
  - [ ] `charge.refunded`
- [ ] Copiar el "Signing secret" (empieza con `whsec_`)
- [ ] Actualizar `.env` con `STRIPE_WEBHOOK_SECRET=whsec_...`
- [ ] Verificar que el webhook está activo

---

### Fase 3: Variables de Entorno 🔴 CRÍTICO

- [ ] Crear archivo `.env` de producción (no commitear a Git)
- [ ] Configurar todas las variables necesarias (ver ejemplo abajo)
- [ ] Verificar `DEBUG=False`
- [ ] Configurar `ALLOWED_HOSTS` con tu dominio
- [ ] Configurar `SITE_BASE_URL=https://tu-dominio.com`

---

### Fase 4: Base de Datos y Redis 🟡 IMPORTANTE

- [ ] Configurar base de datos MySQL de producción
- [ ] Ejecutar migraciones: `python manage.py migrate`
- [ ] Configurar Redis con contraseña
- [ ] Actualizar `CELERY_BROKER_URL` con Redis de producción
- [ ] Actualizar `CELERY_RESULT_BACKEND` con Redis de producción

---

### Fase 5: Email 🟡 IMPORTANTE

- [ ] Elegir proveedor de email (SendGrid, AWS SES, Mailgun, etc.)
- [ ] Obtener credenciales del proveedor
- [ ] Actualizar `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- [ ] Verificar dominio del email (si es necesario)
- [ ] Probar envío de email de prueba

---

### Fase 6: Seguridad 🟡 IMPORTANTE

- [ ] Verificar certificado SSL activo (HTTPS)
- [ ] Confirmar que `SECURE_SSL_REDIRECT=True` (se activa automáticamente con `DEBUG=False`)
- [ ] Verificar `SESSION_COOKIE_SECURE=True`
- [ ] Verificar `CSRF_COOKIE_SECURE=True`
- [ ] Configurar `SECURE_HSTS_SECONDS=31536000`
- [ ] Crear directorio de logs: `mkdir -p logs && chmod 755 logs`

---

### Fase 7: Servicios 🟢 RECOMENDADO

- [ ] Configurar supervisor/systemd para Celery worker
- [ ] Configurar supervisor/systemd para Celery beat
- [ ] Configurar gunicorn/uwsgi para Django
- [ ] Verificar que todos los servicios se reinician automáticamente

---

### Fase 8: Testing Pre-Producción 🟢 RECOMENDADO

- [ ] Probar flujo completo de pago con tarjetas de prueba
- [ ] Probar webhook con Stripe CLI
- [ ] Probar cobros off-session
- [ ] Probar reembolsos
- [ ] Probar emails de notificación
- [ ] Verificar logs de errores

---

### Fase 9: Monitoreo 🟢 RECOMENDADO

- [ ] Configurar alertas para pagos fallidos
- [ ] Monitorear webhooks en Stripe Dashboard
- [ ] Configurar Sentry/LogDNA para errores
- [ ] Configurar métricas de pagos exitosos/fallidos

---

### Fase 10: Documentación 🟢 RECOMENDADO

- [ ] Documentar proceso de rollback
- [ ] Documentar manejo de disputas
- [ ] Documentar proceso de reembolsos manuales
- [ ] Documentar troubleshooting común

---

## 🔧 Configuración Paso a Paso

### Paso 1: Obtener Credenciales de Stripe

#### 1.1 Acceder al Dashboard
1. Ir a https://dashboard.stripe.com
2. Cambiar el toggle superior de **"Test mode"** a **"Live mode"** (producción)

#### 1.2 Obtener API Keys
1. Ir a **Developers → API Keys**
2. Copiar **Publishable key** (empieza con `pk_live_`)
3. Hacer clic en **"Reveal live key"** en Secret key
4. Copiar **Secret key** (empieza con `sk_live_`)

⚠️ **IMPORTANTE**: La secret key solo se muestra una vez. Guárdala de forma segura.

---

### Paso 2: Configurar Webhook

#### 2.1 Crear Endpoint
1. Ir a **Developers → Webhooks**
2. Clic en **"Add endpoint"**
3. En "Endpoint URL": `https://tu-dominio.com/payments/webhook/`
4. En "Description": `Webhook de producción para Reyes Estancias`

#### 2.2 Seleccionar Eventos
Hacer clic en **"Select events"** y marcar:
- ✅ `checkout.session.completed`
- ✅ `payment_intent.payment_failed`
- ✅ `refund.updated`
- ✅ `charge.refunded`

#### 2.3 Obtener Signing Secret
1. Clic en **"Add endpoint"**
2. En la página del webhook, hacer clic en **"Reveal"** en "Signing secret"
3. Copiar el valor (empieza con `whsec_`)

---

### Paso 3: Configurar Variables de Entorno

Crear archivo `.env` en el directorio raíz del proyecto:

```bash
# ==========================================
# CONFIGURACIÓN DE PRODUCCIÓN
# ==========================================

# Django Core
SECRET_KEY=tu-secret-key-super-segura-aqui  # Generar con: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DEBUG=False
ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com

# Site URL (IMPORTANTE: debe ser HTTPS)
SITE_BASE_URL=https://tu-dominio.com

# ==========================================
# STRIPE - PRODUCCIÓN
# ==========================================
clave_secreta_stripe=>
STRIPE_PUBLISHABLE_KEY=pk_live_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
#STRIPE_WEBHOOK_SECRET=whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# ==========================================
# BASE DE DATOS - PRODUCCIÓN
# ==========================================
DB_NAME=reyes_estancias_prod
DB_USER=usuario_produccion
DB_PASSWORD=contraseña_super_segura_aqui
DB_HOST=tu-servidor-mysql.com
DB_PORT=3306
MYSQL_ROOT_PASSWORD=otra_contraseña_super_segura

# ==========================================
# REDIS - PRODUCCIÓN (CON CONTRASEÑA)
# ==========================================
# Formato: redis://:[contraseña]@[host]:[puerto]/[db]
CELERY_BROKER_URL=redis://:tu_contraseña_redis_aqui@redis-host:6379/0
CELERY_RESULT_BACKEND=redis://:tu_contraseña_redis_aqui@redis-host:6379/1

# ==========================================
# EMAIL - PRODUCCIÓN
# ==========================================

# Opción A: SendGrid (Recomendado)
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
EMAIL_PORT=587

# Opción B: AWS SES
# EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
# EMAIL_HOST_USER=AKIAXXXXXXXXXXXXXXXX
# EMAIL_HOST_PASSWORD=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# EMAIL_PORT=587

# Opción C: Mailgun
# EMAIL_HOST=smtp.mailgun.org
# EMAIL_HOST_USER=postmaster@tu-dominio.com
# EMAIL_HOST_PASSWORD=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# EMAIL_PORT=587

# ==========================================
# NPM (si usas Tailwind)
# ==========================================
NPM_BIN_PATH=/usr/bin/npm  # o la ruta completa si usas nvm

# ==========================================
# SEGURIDAD iCal (Opcional)
# ==========================================
ICAL_REQUEST_TIMEOUT=10
ICAL_MAX_SIZE=5242880
ICAL_ALLOWED_HOSTS=airbnb.com,airbnb.es,calendar.google.com,booking.com
```

⚠️ **CRÍTICO**:
- **NUNCA** commitear este archivo a Git
- Agregar `.env` a `.gitignore`
- Usar gestión de secretos (AWS Secrets Manager, etc.) en producción

---

### Paso 4: Configurar Proveedor de Email

#### Opción A: SendGrid (Recomendado) ⭐

**Ventajas**:
- ✅ Free tier: 100 emails/día gratis
- ✅ Fácil configuración
- ✅ Excelente deliverability
- ✅ Dashboard con métricas

**Configuración**:
1. Crear cuenta en https://sendgrid.com
2. Ir a **Settings → API Keys**
3. Crear nueva API Key con permisos de "Mail Send"
4. Copiar la key (empieza con `SG.`)
5. Actualizar `.env`:
```bash
EMAIL_HOST=smtp.sendgrid.net
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.tu_api_key_aqui
EMAIL_PORT=587
```

---

#### Opción B: AWS SES

**Ventajas**:
- ✅ Muy económico ($0.10 por 1,000 emails)
- ✅ Integración con AWS
- ✅ Alta escalabilidad

**Configuración**:
1. Ir a AWS Console → SES
2. Verificar dominio o email
3. Crear SMTP credentials
4. Actualizar `.env`:
```bash
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_HOST_USER=AKIAXXXXXXXXXXXXXXXX
EMAIL_HOST_PASSWORD=tu_secret_key_aqui
EMAIL_PORT=587
```

---

#### Opción C: Mailgun

**Ventajas**:
- ✅ Free tier: 5,000 emails/mes
- ✅ API simple
- ✅ Buena documentación

**Configuración**:
1. Crear cuenta en https://mailgun.com
2. Verificar dominio
3. Obtener SMTP credentials
4. Actualizar `.env`:
```bash
EMAIL_HOST=smtp.mailgun.org
EMAIL_HOST_USER=postmaster@tu-dominio.com
EMAIL_HOST_PASSWORD=tu_password_aqui
EMAIL_PORT=587
```

---

### Paso 5: Configurar Servicios (Celery, Gunicorn)

#### 5.1 Celery Worker (systemd)

Crear archivo `/etc/systemd/system/celery-worker.service`:

```ini
[Unit]
Description=Celery Worker para Reyes Estancias
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/var/www/reyes-estancias
Environment="PATH=/var/www/reyes-estancias/venv/bin"
ExecStart=/var/www/reyes-estancias/venv/bin/celery -A reyes_estancias worker \
    --loglevel=info \
    --logfile=/var/log/celery/worker.log \
    --pidfile=/var/run/celery/worker.pid

Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable celery-worker
sudo systemctl start celery-worker
```

---

#### 5.2 Celery Beat (systemd)

Crear archivo `/etc/systemd/system/celery-beat.service`:

```ini
[Unit]
Description=Celery Beat para Reyes Estancias
After=network.target redis.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/reyes-estancias
Environment="PATH=/var/www/reyes-estancias/venv/bin"
ExecStart=/var/www/reyes-estancias/venv/bin/celery -A reyes_estancias beat \
    --loglevel=info \
    --logfile=/var/log/celery/beat.log \
    --pidfile=/var/run/celery/beat.pid

Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable celery-beat
sudo systemctl start celery-beat
```

---

#### 5.3 Gunicorn (systemd)

Crear archivo `/etc/systemd/system/gunicorn.service`:

```ini
[Unit]
Description=Gunicorn para Reyes Estancias
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/reyes-estancias
Environment="PATH=/var/www/reyes-estancias/venv/bin"
ExecStart=/var/www/reyes-estancias/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/var/www/reyes-estancias/gunicorn.sock \
    reyes_estancias.wsgi:application

Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
```

---

### Paso 6: Deployment Final

#### 6.1 Preparación

```bash
# 1. Activar entorno virtual
source venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Ejecutar migraciones
python manage.py migrate

# 4. Recolectar archivos estáticos
python manage.py collectstatic --noinput

# 5. Crear directorio de logs
mkdir -p logs
chmod 755 logs
```

---

#### 6.2 Verificación Pre-Deployment

```bash
# Verificar configuración de Django
python manage.py check --deploy

# Verificar que DEBUG está en False
python manage.py shell -c "from django.conf import settings; print(f'DEBUG={settings.DEBUG}')"
# Debe imprimir: DEBUG=False

# Verificar Stripe keys
python manage.py shell -c "from django.conf import settings; print(f'STRIPE_SECRET_KEY={settings.STRIPE_SECRET_KEY[:10]}...')"
# Debe empezar con: sk_live_
```

---

#### 6.3 Reiniciar Servicios

```bash
# Reiniciar todos los servicios
sudo systemctl restart gunicorn
sudo systemctl restart celery-worker
sudo systemctl restart celery-beat
sudo systemctl restart nginx  # si usas nginx
sudo systemctl restart redis
```

---

#### 6.4 Verificar Estado

```bash
# Verificar que todos los servicios están activos
sudo systemctl status gunicorn
sudo systemctl status celery-worker
sudo systemctl status celery-beat
sudo systemctl status redis
```

---

## 🧪 Testing y Validación

### Test 1: Webhook de Stripe

#### Usando Stripe CLI (Local)
```bash
# Instalar Stripe CLI
# https://stripe.com/docs/stripe-cli

# Escuchar webhooks localmente
stripe listen --forward-to http://localhost:8000/payments/webhook/

# En otra terminal, disparar evento de prueba
stripe trigger checkout.session.completed
```

#### Verificar en Producción
1. Ir a [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks)
2. Seleccionar tu webhook
3. Ir a la pestaña "Testing"
4. Hacer clic en "Send test webhook"
5. Seleccionar `checkout.session.completed`
6. Verificar que la respuesta es `200 OK`

---

### Test 2: Flujo Completo de Pago

#### Crear Reserva de Prueba

1. **Crear reserva** en la aplicación
2. **Iniciar pago de depósito**
3. Usar tarjeta de prueba de Stripe:
   - **Éxito**: `4242 4242 4242 4242`
   - **Requiere 3DS**: `4000 0025 0000 3155`
   - **Declinada**: `4000 0000 0000 9995`
4. **Verificar**:
   - Payment guardado con `status="paid"`
   - Booking actualizado con `status="confirmed"`
   - `stripe_customer_id` y `stripe_payment_method_id` guardados

---

### Test 3: Cobro Off-Session (Balance)

#### Simular Cobro Automático

```bash
# Desde Django shell
python manage.py shell

# Ejecutar cobro de balance para una reserva
from payments.tasks import charge_balance_for_booking
result = charge_balance_for_booking.apply_async(args=[booking_id, "https://tu-dominio.com"])
print(result.get())  # Debe devolver "succeeded" o "requires_action"
```

#### Verificar en Stripe Dashboard
1. Ir a **Payments**
2. Buscar el payment intent
3. Verificar que el estado es "Succeeded"

---

### Test 4: Email de Notificación

#### Probar Envío de Email

```bash
# Desde Django shell
python manage.py shell

from django.core.mail import send_mail
from django.conf import settings

send_mail(
    subject="Test de Email - Reyes Estancias",
    message="Este es un email de prueba.",
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=["tu-email@ejemplo.com"],
    fail_silently=False,
)
```

---

### Test 5: Reembolso

#### Crear Reembolso de Prueba

```bash
# Desde Django shell
python manage.py shell

from bookings.models import Booking
from payments.services import compute_refund_plan, refund_payment

booking = Booking.objects.get(pk=1)  # Ajustar ID
plan = compute_refund_plan(booking)
print(plan)

# Si hay reembolsos en el plan
for item in plan["refunds"]:
    result = refund_payment(item["payment"], item["amount"], reason="requested_by_customer")
    print(result)
```

#### Verificar en Stripe Dashboard
1. Ir a **Payments → Refunds**
2. Verificar que el reembolso está procesándose
3. Verificar webhook `refund.updated` recibido

---

## 🔍 Troubleshooting

### Problema 1: Webhook No Recibe Eventos

**Síntomas**:
- Pago exitoso en Stripe pero `Payment.status` sigue en "pending"
- No hay registros en logs de webhook

**Diagnóstico**:
```bash
# Ver logs de Django
tail -f logs/general.log

# Ver logs de Celery
tail -f /var/log/celery/worker.log

# Verificar webhook en Stripe Dashboard
# Dashboard → Webhooks → [tu webhook] → Pestaña "Events"
```

**Soluciones**:
1. **Verificar URL del webhook**:
   - Debe ser `https://tu-dominio.com/payments/webhook/` (con HTTPS)
   - Verificar que no hay firewall bloqueando

2. **Verificar STRIPE_WEBHOOK_SECRET**:
   ```bash
   python manage.py shell -c "from django.conf import settings; print(settings.STRIPE_WEBHOOK_SECRET[:10])"
   # Debe empezar con: whsec_
   ```

3. **Verificar que el endpoint está activo**:
   ```bash
   curl -X POST https://tu-dominio.com/payments/webhook/
   # Debe devolver 400 (Invalid payload), no 404
   ```

---

### Problema 2: Cobro Off-Session Falla

**Síntomas**:
- Email enviado al usuario en vez de cobro automático
- `Payment.status` = "requires_action"

**Causas Comunes**:
1. **Tarjeta requiere 3DS** (Strong Customer Authentication)
2. **Tarjeta sin fondos**
3. **Tarjeta expirada**

**Solución**:
Este es el comportamiento **correcto**. El sistema:
1. Intenta cobro off-session
2. Si falla, crea Checkout Session
3. Envía email al usuario
4. Usuario completa pago manualmente

**Verificar**:
```bash
# Ver intentos de cobro en Stripe Dashboard
# Payments → filtrar por "Incomplete" o "Requires action"
```

---

### Problema 3: Emails No Se Envían

**Síntomas**:
- No llegan emails de notificación
- No hay errores en logs

**Diagnóstico**:
```bash
# Probar envío manual
python manage.py shell

from django.core.mail import send_mail
from django.conf import settings

try:
    send_mail(
        subject="Test",
        message="Test",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=["tu-email@ejemplo.com"],
        fail_silently=False,
    )
    print("✅ Email enviado")
except Exception as e:
    print(f"❌ Error: {e}")
```

**Soluciones**:
1. **Verificar credenciales de email**:
   ```bash
   python manage.py shell -c "from django.conf import settings; print(f'EMAIL_HOST={settings.EMAIL_HOST}')"
   ```

2. **Verificar que no es spam**:
   - Revisar carpeta de spam
   - Verificar dominio del email (SPF, DKIM records)

3. **Probar con otro proveedor**:
   - SendGrid suele tener mejor deliverability

---

### Problema 4: Celery No Ejecuta Tareas

**Síntomas**:
- Balance no se cobra automáticamente
- Reservas expiradas no se marcan

**Diagnóstico**:
```bash
# Verificar que Celery worker está corriendo
sudo systemctl status celery-worker

# Verificar que Celery beat está corriendo
sudo systemctl status celery-beat

# Ver logs de Celery
tail -f /var/log/celery/worker.log
tail -f /var/log/celery/beat.log
```

**Soluciones**:
1. **Reiniciar servicios**:
   ```bash
   sudo systemctl restart celery-worker
   sudo systemctl restart celery-beat
   ```

2. **Verificar conexión a Redis**:
   ```bash
   redis-cli ping
   # Debe responder: PONG
   ```

3. **Probar tarea manualmente**:
   ```bash
   python manage.py shell
   from payments.tasks import scan_and_charge_balances
   result = scan_and_charge_balances.apply_async(args=["https://tu-dominio.com"])
   print(result.get())
   ```

---

### Problema 5: Error 500 en Producción

**Síntomas**:
- Páginas devuelven error 500
- Aplicación funciona en desarrollo

**Diagnóstico**:
```bash
# Ver logs de Django
tail -f logs/general.log

# Ver logs de Gunicorn
sudo journalctl -u gunicorn -f

# Ejecutar check de deployment
python manage.py check --deploy
```

**Soluciones Comunes**:
1. **Archivos estáticos no encontrados**:
   ```bash
   python manage.py collectstatic --noinput
   sudo systemctl restart nginx
   ```

2. **Permisos de archivos**:
   ```bash
   sudo chown -R www-data:www-data /var/www/reyes-estancias
   ```

3. **Variables de entorno no cargadas**:
   - Verificar que `.env` está en el directorio correcto
   - Verificar que systemd carga el `.env`:
   ```ini
   # En el archivo .service
   EnvironmentFile=/var/www/reyes-estancias/.env
   ```

---

## 📚 Referencias

### Documentación Oficial

- [Stripe API Documentation](https://stripe.com/docs/api)
- [Stripe Checkout](https://stripe.com/docs/payments/checkout)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [Stripe Testing](https://stripe.com/docs/testing)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/)
- [Celery Documentation](https://docs.celeryproject.org/)

---

### Recursos Útiles

- [Stripe CLI](https://stripe.com/docs/stripe-cli)
- [Stripe Dashboard](https://dashboard.stripe.com)
- [Tarjetas de Prueba de Stripe](https://stripe.com/docs/testing#cards)
- [Códigos de Error de Stripe](https://stripe.com/docs/error-codes)

---

### Archivos del Proyecto

- `payments/views.py` - Vistas de pago y webhook
- `payments/services.py` - Lógica de negocio de pagos
- `payments/models.py` - Modelos de Payment y RefundLog
- `payments/tasks.py` - Tareas de Celery
- `payments/urls.py` - URLs de pagos
- `reyes_estancias/settings.py` - Configuración del proyecto
- `.env` - Variables de entorno (NO commitear)

---

## ✅ Resumen Final

### Cambios Mínimos para Producción

1. **3 variables en `.env`**:
   ```bash
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

2. **1 webhook en Stripe Dashboard**:
   - URL: `https://tu-dominio.com/payments/webhook/`
   - Eventos: 4 eventos marcados

3. **Proveedor de email**:
   - Recomendado: SendGrid
   - Actualizar 3 variables de email

4. **Bugs corregidos**:
   - ✅ settings.py línea 230 eliminada
   - ✅ tasks.py línea 26 corregida
   - ✅ RetryBalancePaymentView corregida

### Estado del Código

Tu implementación de Stripe es **excelente** y está **lista para producción**. Los cambios necesarios son mínimos y se limitan a configuración, no a código.

### Próximos Pasos

1. Configurar credenciales (15 min)
2. Configurar webhook (5 min)
3. Configurar email (10 min)
4. Hacer testing completo (30 min)
5. Deploy a producción (15 min)

**Total estimado**: 1 hora y 15 minutos

---

**¿Preguntas?** Consulta la sección de [Troubleshooting](#troubleshooting) o revisa los logs de errores.

**Última actualización**: 2026-01-04
**Versión**: 1.0
