# Flujo de extensión post-balance y estado `completed`

**Commit:** `f35a239`  
**Fecha:** 2026-06-09

---

## Contexto y problema

El sistema original soportaba la ampliación de fechas de una reserva únicamente cuando el balance **no** había sido cobrado todavía. En ese caso se lanzaba un ciclo de top-up de depósito (30% del nuevo total − depósito ya pagado) y el balance se reprogramaba.

Sin embargo, el sistema tenía tres problemas cuando el balance ya estaba pagado:

1. **Bug de dinero:** `charge_balance_for_booking` tenía un guard que devolvía `"already_paid"` si existía cualquier pago de tipo `balance` con status `paid`. Esto impedía cobrar cualquier diferencia adicional tras una extensión.

2. **Balance incorrecto en preview:** `quote_change_booking_dates` calculaba `balance_next` sin tener en cuenta el balance ya pagado, mostrando un importe incorrecto al guest (p.ej. €840 en lugar de €140).

3. **Sin estado "completada":** Una reserva con el balance cobrado y la fecha de salida pasada seguía con `status="confirmed"`, sin distinción posible.

---

## Solución implementada

### 1. Nuevo `payment_type="extension"`

Añadido a `payments/models.py` y migración `0012`. Representa el pago directo de la diferencia de precio cuando una reserva ya está completamente pagada y el guest amplía su estancia.

**Ventaja:** al ser un tipo propio, no interfiere con la lógica existente de depósitos y balances, y permite múltiples extensiones sucesivas sin ningún problema.

---

### 2. Nuevo `status="completed"` en Booking

Añadido a `bookings/models.py` y migración `0013`.

| Estado | Significado |
|---|---|
| `pending` | Creada, esperando pago del depósito |
| `confirmed` | Depósito pagado, en curso |
| `completed` | Balance pagado + fecha de salida pasada |
| `cancelled` | Cancelada |
| `expired` | Hold expirado sin pago |

> **Nota:** el marcado automático de `confirmed → completed` debe implementarse como tarea periódica de Celery (pendiente). La condición es: `departure < now() AND compute_balance_due_snapshot() == 0`.

Las vistas de cambio de fechas bloquean reservas con `status="completed"` con un mensaje claro.

---

### 3. Nuevos flujos en `bookings/services.py`

#### `quote_change_booking_dates`

Detecta si `booking.balance_paid() == True` y devuelve un quote diferente:

```python
{
    "ok": True,
    "balance_already_paid": True,
    "extension_charge": T_new - T_old,  # diferencia directa
    "dep_topup": Decimal("0.00"),
    "dep_refund": Decimal("0.00"),
    "balance_next": Decimal("0.00"),
    "deposit_target": T_new * 0.30,
    "T_new": T_new,
}
```

Cuando `balance_already_paid=False` el quote incluye ahora los campos `balance_already_paid` y `extension_charge` con valores neutros, por consistencia.

#### `apply_change_booking_dates` — Caso C (nuevo)

```
Caso A → balance NO pagado, precio sube     → top-up de depósito (flujo original)
Caso B → balance NO pagado, precio baja/igual → aplicar ya, posible reembolso (flujo original)
Caso C → balance YA pagado, precio sube     → cobrar diferencia como "extension" (nuevo)
```

Flujo del Caso C:
1. Actualiza `booking` inmediatamente (fechas, `total_amount`, `deposit_amount`, `balance_due = extension_charge`)
2. Intenta cobro off-session con `charge_offsession_with_fallback(payment_type="extension")`
3. Si pago exitoso → `balance_due = 0`, log marcado `"applied"`
4. Si requiere acción → se genera checkout session, log queda `"pending"` con enlace al checkout
5. Si falla completamente → **revierte** fechas y montos al estado anterior

---

### 4. `compute_balance_due_snapshot` actualizado

`payments/services.py` — el aggregate ahora incluye pagos de extensión:

```python
ext=Coalesce(Sum("amount", filter=Q(payment_type="extension", status="paid")), Decimal("0.00")),
...
total_paid_net = agg["dep"] + agg["bal"] + agg["ext"] - agg["ref"]
```

Igualmente `balance_due_runtime` en `bookings/models.py` suma los pagos de `balance` y `extension` pagados.

---

### 5. Fix bug crítico — `payments/tasks.py`

**Eliminado** el guard que causaba la pérdida de dinero:

```python
# ELIMINADO - impedía cobrar extensiones
if Payment.objects.filter(booking=b, payment_type="balance", status="paid").exists():
    return "already_paid"
```

La idempotencia queda garantizada por la comprobación anterior:
```python
amount = compute_balance_due_snapshot(b)
if amount <= 0:
    return "no_balance"
```

`scan_and_charge_balances` simplificado: eliminado el `.exclude(payments__payment_type="balance", payments__status="paid")` que impedía que el scanner de seguridad detectara reservas con extensiones pendientes. Se confía en `balance_due__gt=0` + la comprobación interna de la tarea.

---

### 6. Webhook `checkout.session.completed` mejorado

`payments/views.py` — antes solo se actualizaba `balance_due` para pagos `deposit_topup`. Ahora:

- **Pago de extensión:** marca el `BookingChangeLog` como `"applied"` y recalcula `balance_due`
- **Cualquier otro pago (balance, etc.):** también recalcula `balance_due` via `compute_balance_due_snapshot`

Esto elimina el problema de que `booking.balance_due` quedara desactualizado en base de datos tras pagos via checkout session.

---

### 7. Template `change_dates_preview.html`

Muestra información diferente según el tipo de quote:

- **`balance_already_paid=True`:** "Pago de extensión: X MXN" con texto explicativo
- **Flujo normal:** "Nuevo depósito", "Extra a pagar (depósito)", "Nuevo balance pendiente"

---

## Flujo completo — extensión con balance pagado

```
Guest (€1000 pagado: €300 dep + €700 balance)
  │
  ├─ Amplía estancia → nuevo total €1200
  │
  ├─ quote_change_booking_dates()
  │   └─ balance_paid() = True
  │   └─ extension_charge = €1200 - €1000 = €200
  │
  ├─ apply_change_booking_dates() — Caso C
  │   ├─ booking.total_amount = €1200
  │   ├─ booking.balance_due  = €200
  │   └─ charge_offsession_with_fallback(€200, type="extension")
  │
  ├─ [Off-session OK] → balance_due = €0, log applied ✓
  │
  └─ [Off-session falla] → checkout session €200
      └─ Guest paga → webhook → balance_due = €0, log applied ✓

compute_balance_due_snapshot: dep(€300) + bal(€700) + ext(€200) - ref(€0) = €1200 → due = €0 ✓
```

**N extensiones sucesivas:** cada una crea un nuevo pago `extension` independiente. `compute_balance_due_snapshot` los suma todos, por lo que el balance real siempre es correcto.

---

## Migraciones

| App | Migración | Cambio |
|---|---|---|
| `payments` | `0012_add_extension_payment_type` | Añade `"extension"` a choices de `payment_type` |
| `bookings` | `0013_add_completed_status` | Añade `"completed"` a choices de `status` |

---

## Pendiente

- **Tarea periódica Celery** para marcar bookings como `completed` cuando `departure < now()` y `compute_balance_due_snapshot() == 0`.
- **Reembolso en extensión negativa** (guest acorta estancia cuando el balance ya está pagado): actualmente no hay un flujo específico para devolver la diferencia en ese caso.
