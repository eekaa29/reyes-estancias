# Bug Fix: RetryBalancePaymentView - Lógica Redundante

## 📋 Resumen

**Archivo afectado**: `payments/views.py` (líneas 498-541)
**Clase**: `RetryBalancePaymentView`
**Fecha de corrección**: 2026-01-04
**Severidad**: Media (duplicación de sesiones de Stripe, experiencia de usuario subóptima)

---

## 🐛 Problema Detectado

La vista `RetryBalancePaymentView` tenía una lógica redundante que causaba la creación de múltiples sesiones de Stripe para el mismo pago y un flujo de usuario innecesariamente complejo.

### Código Problemático (Antes)

```python
def get(self, request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    payment = booking.payments.filter(payment_type="balance").order_by("-created_at").first()

    if not self.request.user == booking.user and not self.request.user.is_staff:
        messages.error(request, "No autorizado")
        return redirect("home")

    success_url = request.build_absolute_uri(reverse("payment_success")) + f"?booking_id={booking.id}"
    cancel_url = request.build_absolute_uri(reverse("payment_cancel")) + f"?booking_id={booking.id}"

    if not payment.stripe_checkout_session_id:
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=booking.stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[{...}],
            metadata={"booking_id": str(booking.id), "payment_id": str(payment.id), "type": "balance"},
        )
        return redirect("start_balance", booking_id=booking.id)  # ❌ PROBLEMA

    session = stripe.checkout.Session.retrieve(payment.stripe_checkout_session_id)
    return redirect(session.url)
```

---

## ⚠️ Problemas Identificados

### 1. **Sesión de Stripe Perdida** 💸

**Qué pasaba**:
- Se creaba una `CheckoutSession` en Stripe (líneas 514-531)
- **NUNCA** se guardaba `session.id` en `payment.stripe_checkout_session_id`
- La sesión quedaba "huérfana" en Stripe sin referencia en la base de datos
- Si el usuario volvía a intentar, se creaba OTRA sesión (duplicados)

**Impacto**:
- Sesiones de Stripe sin usar acumulándose
- Imposibilidad de reutilizar la sesión creada
- Datos inconsistentes entre Stripe y la BD

---

### 2. **Loop de Redirecciones Innecesario** 🔄

**Flujo actual (INCORRECTO)**:
```
Usuario → RetryBalancePaymentView
       ↓
   Crea Stripe Session #1
       ↓
   Redirect a "start_balance" (StartBalanceCheckoutView)
       ↓
   Llama a charge_offsession_with_fallback()
       ↓
   Intenta cobro off-session (probablemente falla de nuevo)
       ↓
   Crea Stripe Session #2
       ↓
   Envía email al usuario
       ↓
   Usuario hace clic en email
       ↓
   Va a página de pago de Stripe (Session #2)
```

**Problemas**:
- Se crean **2 sesiones de Stripe** para el mismo pago
- El usuario pasa por **múltiples redirecciones** innecesarias
- Se envía un **email redundante** (cuando el usuario ya está en el flujo)
- La Session #1 nunca se usa
- Mala experiencia de usuario (más pasos de los necesarios)

---

### 3. **Inconsistencia Interna** 🤔

El código tenía un comportamiento inconsistente:

**Cuando NO existe `checkout_session_id`** (líneas 513-532):
```python
session = stripe.checkout.Session.create(...)
return redirect("start_balance", booking_id=booking.id)  # ❌ Redirige a otra vista
```

**Cuando SÍ existe `checkout_session_id`** (líneas 534-535):
```python
session = stripe.checkout.Session.retrieve(payment.stripe_checkout_session_id)
return redirect(session.url)  # ✅ Redirige directamente a Stripe
```

La segunda parte hacía lo correcto, pero la primera no.

---

## ✅ Solución Implementada

### Código Corregido (Después)

```python
def get(self, request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    payment = booking.payments.filter(payment_type="balance").order_by("-created_at").first()

    if not self.request.user == booking.user and not self.request.user.is_staff:
        messages.error(request, "No autorizado")
        return redirect("home")

    success_url = request.build_absolute_uri(reverse("payment_success")) + f"?booking_id={booking.id}"
    cancel_url = request.build_absolute_uri(reverse("payment_cancel")) + f"?booking_id={booking.id}"

    if not payment.stripe_checkout_session_id:
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=booking.stripe_customer_id,
            success_url= success_url,
            cancel_url=cancel_url,
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": "mxn",
                    "unit_amount": to_cents(booking.balance_due),
                    "product_data": {
                        "name": f"Segundo pago · {booking.property.name}",
                        "description": f"Booking #{booking.id} — {booking.arrival.date()} → {booking.departure.date()}",
                    },
                },
            }],
            metadata={"booking_id": str(booking.id), "payment_id": str(payment.id), "type": "balance"},
        )

        # ✅ FIX 1: Guarda la sesión en la BD para evitar duplicados
        payment.stripe_checkout_session_id = session.id
        payment.save(update_fields=["stripe_checkout_session_id"])

        # ✅ FIX 2: Redirige directamente a Stripe (no a otra vista)
        return redirect(session.url)

    # Reutiliza sesión existente
    session = stripe.checkout.Session.retrieve(payment.stripe_checkout_session_id)
    return redirect(session.url)
```

---

## 📊 Comparación: Antes vs Después

### Flujo Anterior (INCORRECTO) ❌
```
Usuario → RetryBalancePaymentView
       ↓
   Crea Session #1 (se pierde)
       ↓
   Redirect a "start_balance"
       ↓
   StartBalanceCheckoutView
       ↓
   charge_offsession_with_fallback
       ↓
   Intenta off-session (falla)
       ↓
   Crea Session #2
       ↓
   Envía email
       ↓
   Usuario hace clic en email
       ↓
   Va a Stripe (Session #2)
```

**Total**: 2 sesiones, 1 email, múltiples redirecciones

---

### Flujo Nuevo (CORRECTO) ✅
```
Usuario → RetryBalancePaymentView
       ↓
   Crea Session (si no existe)
       ↓
   Guarda session.id en BD
       ↓
   Redirect DIRECTO a session.url
       ↓
   Usuario en página de pago de Stripe
```

**Total**: 1 sesión, 0 emails innecesarios, experiencia directa

---

## 🎯 Beneficios de la Corrección

### 1. **Eficiencia**
- ✅ Solo 1 sesión de Stripe por intento
- ✅ Reducción de llamadas a la API de Stripe
- ✅ Menos carga en el servidor

### 2. **Experiencia de Usuario**
- ✅ Flujo directo (menos redirecciones)
- ✅ No hay emails redundantes
- ✅ Proceso más rápido y claro

### 3. **Integridad de Datos**
- ✅ Sesiones guardadas correctamente en la BD
- ✅ Consistencia entre Stripe y la base de datos
- ✅ Posibilidad de reutilizar sesiones

### 4. **Costos**
- ✅ Menos sesiones = menos uso de API de Stripe
- ✅ Menos emails enviados

---

## 🔍 Diferenciación de Vistas

Para entender mejor cuándo usar cada vista:

| Vista | Propósito | Cuándo se usa |
|-------|-----------|---------------|
| `StartBalanceCheckoutView` | Primera vez cobrando el balance | Automático desde Celery o manual por primera vez |
| `RetryBalancePaymentView` | Reintentar pago que ya falló | Usuario hace clic en "Reintentar pago" |

**Clave**: `RetryBalancePaymentView` se usa cuando ya sabes que el cobro off-session falló, por lo que NO tiene sentido intentarlo de nuevo. Debes llevar al usuario directamente a Stripe.

---

## 📝 Cambios Realizados

### Archivos Modificados
- `payments/views.py` (líneas 498-541)

### Líneas Específicas Cambiadas
```diff
  if not payment.stripe_checkout_session_id:
      session = stripe.checkout.Session.create(...)
-     return redirect("start_balance", booking_id=booking.id)
+
+     # Guarda la sesión en la BD para evitar duplicados
+     payment.stripe_checkout_session_id = session.id
+     payment.save(update_fields=["stripe_checkout_session_id"])
+
+     # Redirige directamente a Stripe
+     return redirect(session.url)
```

---

## 🧪 Testing Recomendado

Después de este fix, verifica:

1. **Test de creación de sesión**:
   - Usuario con pago de balance fallido
   - Hace clic en "Reintentar pago"
   - Se crea UNA sesión de Stripe
   - `payment.stripe_checkout_session_id` se guarda correctamente
   - Usuario es redirigido a Stripe directamente

2. **Test de reutilización**:
   - Usuario con sesión existente
   - Hace clic en "Reintentar pago" de nuevo
   - Se reutiliza la misma sesión (no se crea otra)
   - Usuario es redirigido a la sesión existente

3. **Test de base de datos**:
   - Verificar que `payment.stripe_checkout_session_id` no es NULL después de crear sesión
   - Verificar que no hay sesiones duplicadas en Stripe para el mismo payment_id

---

## 📚 Referencias

- Código original: `payments/views.py:498-535` (antes del fix)
- Código corregido: `payments/views.py:498-541` (después del fix)
- Documentación de Stripe Checkout: https://stripe.com/docs/payments/checkout
- Documentación de Stripe Sessions: https://stripe.com/docs/api/checkout/sessions

---

## ✍️ Autor

**Análisis y corrección**: Claude Code
**Fecha**: 2026-01-04
**Versión**: 1.0
