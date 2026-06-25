# Flujo de cambio de fechas — todos los casos y ramas

**Última actualización:** 2026-06-25

---

## Contexto

El sistema permite a un huésped cambiar las fechas de una reserva confirmada. Dependiendo de si el balance ya está pagado y de si el nuevo precio es mayor o menor, se activan diferentes flujos. Toda la lógica vive en `bookings/services.py` (`quote_change_booking_dates` + `apply_change_booking_dates`).

---

## Mapa de casos

```
¿balance ya pagado?
│
├─ NO
│   ├─ T_new > T_old  →  Caso A: top-up de depósito
│   └─ T_new ≤ T_old
│       ├─ paid_dep > T_new  →  Caso B1: reembolso de depósito excedido
│       └─ paid_dep ≤ T_new  →  Caso B2: ajuste de balance (sin reembolso)
│
└─ SÍ
    ├─ T_new > T_old  →  Caso C1: cobrar diferencia como "extension"
    ├─ T_new < T_old  →  Caso C2: reembolsar diferencia ← NUEVO (2026-06-25)
    └─ T_new = T_old  →  Caso C3: solo actualizar fechas, sin movimiento de dinero
```

---

## Caso A — Extensión positiva, balance no pagado

**Condición:** `balance_already_paid = False` y `T_new > T_old`

**Lógica del quote:**
```
deposit_target = T_new × 0.30
dep_topup      = deposit_target − paid_dep   (si paid_dep < deposit_target)
balance_next   = T_new − (paid_dep + dep_topup)
```

**Flujo en apply:**
1. NO se tocan las fechas ni el booking hasta que se pague el top-up
2. Se invalidan logs pendientes anteriores (misma reserva)
3. Se crea un `BookingChangeLog` con `status="pending"` y los importes futuros
4. Se genera un Checkout Session para cobrar `dep_topup`
5. El log queda enlazado a ese pago (`topup_payment`, `checkout_session_id`)

**Resolución (webhook `checkout.session.completed`):**
- Se leen `new_arrival`, `new_departure`, `new_T` del log
- Se actualiza el booking con las nuevas fechas y el balance recalculado
- El log pasa a `"applied"`
- Se reprograma el cobro de balance con `reschedule_balance_charge`

**Archivos clave:** `bookings/services.py:159`, `payments/views.py` (webhook), `tests/test_extension_sin_balance.py`

---

## Caso B1 — Reducción, balance no pagado, depósito excedido

**Condición:** `balance_already_paid = False`, `T_new < T_old` y `paid_dep > T_new`

**Lógica del quote:**
```
dep_refund   = paid_dep − T_new
balance_next = 0
dep_topup    = 0
```

**Flujo en apply:**
1. Se aplican inmediatamente las nuevas fechas y el total
2. `balance_due = 0` (el depósito ya cubre el nuevo total)
3. Se crea log con `status="applied"`
4. Se llama a `trigger_refund_for_deposit_diff(booking, dep_refund)` que reembolsa desde pagos de depósito pagados

**Archivos clave:** `bookings/services.py:199`, `payments/services.py:trigger_refund_for_deposit_diff`, `tests/test_extension_negativa.py`

---

## Caso B2 — Reducción, balance no pagado, depósito NO excedido

**Condición:** `balance_already_paid = False`, `T_new < T_old` y `paid_dep ≤ T_new`

**Lógica del quote:**
```
dep_refund   = 0
balance_next = T_new − paid_dep
dep_topup    = 0
```

**Flujo en apply:**
1. Se aplican inmediatamente las nuevas fechas y el total
2. `balance_due = T_new − paid_dep` (reducido respecto al anterior)
3. Se crea log con `status="applied"`
4. No hay reembolso, solo se reduce el balance pendiente
5. Se reprograma el cobro de balance con `reschedule_balance_charge`

**Archivos clave:** `bookings/services.py:199`, `tests/test_extension_negativa.py`

---

## Caso C1 — Extensión positiva, balance ya pagado

**Condición:** `balance_already_paid = True` y `T_new > T_old`

**Lógica del quote:**
```
extension_charge = T_new − T_old
extension_refund = 0
```

**Flujo en apply:**
1. Se actualiza el booking inmediatamente (fechas, `total_amount`, `balance_due = extension_charge`)
2. Se crea log con `status="pending"`
3. Se intenta cobro off-session con `charge_offsession_with_fallback(type="extension")`

**Rama: cobro exitoso**
- `balance_due = 0`
- Log pasa a `"applied"`

**Rama: requiere acción (3DS / tarjeta rechazada)**
- Se genera Checkout Session por el importe de la extensión
- Log queda `"pending"` con `checkout_session_id`
- Webhook `checkout.session.completed` marca el log como `"applied"` y recalcula `balance_due`

**Rama: fallo completo**
- Se revierten fechas y montos al estado anterior
- Log pasa a `"superseded"`
- Retorna `{"ok": False}`

**N extensiones sucesivas:** cada una genera un pago `extension` independiente. `compute_balance_due_snapshot` suma todos, por lo que el balance real siempre es correcto.

**Archivos clave:** `bookings/services.py:98`, `payments/services.py:charge_offsession_with_fallback`, `tests/test_extension_balance_pagado.py`

---

## Caso C2 — Reducción, balance ya pagado ← NUEVO (2026-06-25)

**Condición:** `balance_already_paid = True` y `T_new < T_old`

**Lógica del quote:**
```
extension_refund = T_old − T_new
extension_charge = 0
```

**Flujo en apply:**
1. Se actualiza el booking inmediatamente (fechas, `total_amount`, `balance_due = 0`)
2. Se crea log con `status="applied"` directamente (no hay pago pendiente)
3. Se llama a `trigger_refund_for_reduction(booking, extension_refund)`

**Orden de búsqueda de pagos para el reembolso:**
```
1º extension (paid, más reciente primero)
2º balance   (paid, más reciente primero)
3º deposit   (paid, más reciente primero)
```
Stripe exige un refund por PaymentIntent, por lo que si el importe supera un solo pago se generan varios refunds parciales.

**Archivos clave:** `bookings/services.py:107`, `payments/services.py:trigger_refund_for_reduction`, `tests/test_extension_negativa.py`

---

## Caso C3 — Mismo precio, balance ya pagado

**Condición:** `balance_already_paid = True` y `T_new = T_old`

**Lógica del quote:**
```
extension_charge = 0
extension_refund = 0
```

**Flujo en apply:**
- Entra en el Caso C2 (`extension_charge = 0`), pero como `extension_refund = 0` no se llama a ninguna función de reembolso
- Solo se actualizan fechas y montos
- Log `status="applied"`

---

## Funciones de reembolso disponibles

| Función | Cuándo se usa | Busca en |
|---|---|---|
| `trigger_refund_for_reduction(booking, amount)` | Casos B1 y C2: cualquier reducción de estancia | `extension → balance → deposit` (paid) |
| `refund_payment(payment, amount)` | Función base, llamada por la anterior. Ejecuta `stripe.Refund.create` | — |

---

## Tabla resumen de todos los casos

| Caso | Balance pagado | Precio | Acción principal | Reembolso | Cobro extra |
|---|---|---|---|---|---|
| A | No | Sube | Top-up depósito (Checkout) | No | No (hasta pagar topup) |
| B1 | No | Baja | Aplicar ya | Sí (depósito) | No |
| B2 | No | Baja/igual | Aplicar ya | No | No |
| C1 | Sí | Sube | Cobrar extensión off-session | No | Sí |
| C2 | Sí | Baja | Aplicar ya | Sí (ext→bal→dep) | No |
| C3 | Sí | Igual | Aplicar ya | No | No |

---

## Historial de cambios

### 2026-06-09 — commit `f35a239`
- Añadido `payment_type="extension"` en `payments/models.py` (migración `0012`)
- Añadido `status="completed"` en `bookings/models.py` (migración `0013`)
- Implementados Casos A, B y C1
- Fix bug crítico en `payments/tasks.py`: eliminado guard que impedía cobrar extensiones cuando ya existía un pago `balance` paid
- `compute_balance_due_snapshot` actualizado para incluir pagos de extensión
- Webhook `checkout.session.completed` actualizado para manejar pagos de extensión

### 2026-06-25 — commit `81ca71e` (este fix)
- Implementado **Caso C2**: reembolso cuando balance ya pagado y precio baja
  - Nueva función `trigger_refund_for_reduction` en `payments/services.py`
  - `quote_change_booking_dates` calcula `extension_refund = T_old − T_new`
  - `apply_change_booking_dates` gestiona el sub-caso C2 antes de caer a Caso B
- Añadidos tests en `tests/test_extension_negativa.py` (Casos B1, B2, C2, C3)
- Eliminada `trigger_refund_for_deposit_diff` (redundante): `trigger_refund_for_reduction`
  cubre el mismo caso (Caso B1) al buscar `extension → balance → deposit` en orden,
  y como en B1 no hay pagos de extension/balance pagados, el resultado es idéntico
