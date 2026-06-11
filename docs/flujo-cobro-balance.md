# Flujo de cobro del balance

El balance (70% restante del total de la reserva) se cobra automáticamente **24 horas después del check-in** (15:00 del día siguiente a la llegada). Hay dos mecanismos independientes que garantizan el cobro.

---

## Por qué 24h después del check-in

El check-in se almacena siempre a las 15:00 (`booking.arrival`). Por tanto:

- `booking.arrival + timedelta(days=1)` = 15:00 del día siguiente
- El huésped lleva una noche en la propiedad y el pago se cobra mientras sigue allí

Cobrar con el huésped dentro reduce el riesgo: si el cobro falla, todavía hay margen para gestionarlo antes de que abandone la propiedad.

---

## Mecanismo 1 — ETA programada (camino normal)

Cuando se confirma una reserva o se cambian las fechas, se llama a `reschedule_balance_charge()` que encola la task con una fecha exacta de ejecución:

```
reschedule_balance_charge(booking, when=booking.arrival + timedelta(days=1))
    │
    └─► charge_balance_for_booking.apply_async(args=[booking.pk], eta=when)
                │
                │  Celery almacena la task en Redis con la ETA
                │  El worker la ejecuta automáticamente cuando llega el momento
                ▼
        charge_balance_for_booking(booking_id)
```

El `task_id` y la ETA se guardan en `booking.balance_charge_task_id` y `booking.balance_charge_eta`. Esto permite **revocar la task** si el usuario cancela la reserva antes de que se ejecute.

### Dónde se programa la ETA

`reschedule_balance_charge` se llama desde varios puntos, siempre con `arrival + 1 día`:

| Lugar | Cuándo |
|---|---|
| `bookings/services.py:208,235` | Al cambiar fechas sin topup (Caso B) |
| `payments/views.py:266` | En el webhook, tras pagar el topup de depósito |
| `payments/views.py:310` | En el webhook, tras cualquier `checkout.session.completed` |

---

## Mecanismo 2 — Scanner de seguridad (red de apoyo)

`scan_and_charge_balances()` es una task periódica configurada en `CELERY_BEAT_SCHEDULE` que corre **cada 15 minutos**. Su función es atrapar reservas que deberían haberse cobrado pero no lo fueron (worker caído, task perdida en Redis, etc.):

```python
# payments/tasks.py
cutoff = timezone.now() - timedelta(days=1)

Booking.objects.filter(
    status="confirmed",
    arrival__lte=cutoff,   # check-in fue hace ≥ 24h
    balance_due__gt=0,     # todavía debe dinero
    stripe_customer_id__isnull=False,
    stripe_payment_method_id__isnull=False,
)
→ para cada una: charge_balance_for_booking.delay(b.id, base_url)
```

El scanner no consulta `balance_charge_task_id` — simplemente reencola cualquier reserva que cumpla los criterios. Esto es seguro porque `charge_balance_for_booking` es **idempotente** (ver más abajo).

---

## Lo que hace `charge_balance_for_booking`

```
1. Carga el booking con select_for_update (evita doble cobro concurrente)
2. Verifica que status == "confirmed"                    → si no, "booking_not_confirmed"
3. Verifica que tiene stripe_customer_id y payment_method → si no, "missing_method"
4. Llama a compute_balance_due_snapshot()               → si amount <= 0, "no_balance"
5. Verifica que no hay topup de depósito pendiente       → si lo hay, "pending_topup"
6. Intenta cobrar off-session via stripe.PaymentIntent
      │
      ├─ succeeded  → payment.status = "paid", booking.balance_due = 0   → "succeeded"
      ├─ requires_action (3DS) → crea Checkout Session + envía email      → "requires_action"
      └─ error transitorio → self.retry() (hasta 3 reintentos, 30s entre cada uno)
```

---

## Idempotencia

La task puede ejecutarse varias veces para la misma reserva sin efectos secundarios:

- Si el balance ya fue cobrado → `compute_balance_due_snapshot()` devuelve 0 → sale con `"no_balance"`
- Si hay un topup pendiente → sale con `"pending_topup"` para no cobrar sobre un depósito que aún no se ha confirmado
- El `select_for_update` evita que dos workers cobren la misma reserva simultáneamente

Por tanto, que el scanner reencole una reserva que ya tiene una ETA activa (o ya cobrada) no genera ningún problema.

---

## Diagrama completo

```
Reserva confirmada / fechas cambiadas
        │
        └─► reschedule_balance_charge()
                │
                └─► Celery ETA (arrival + 24h)
                          │
                          │  (espera hasta las 15:00 del día siguiente)
                          │
        Celery Beat ──────┼────── cada 15 min
        scan_and_charge_balances()
        (si arrival ≤ now - 24h      │
         y balance_due > 0)          │
                          │          │
                          ▼          ▼
                   charge_balance_for_booking()
                          │
                  ┌───────┴────────┐
                  ▼                ▼
               "paid"       "requires_action"
           balance_due=0     Checkout Session
                              + email al usuario
```

---

## Configuración en `settings.py`

```python
CELERY_BEAT_SCHEDULE = {
    "charge-balances-every-15-min": {
        "task": "payments.tasks.scan_and_charge_balances",
        "schedule": crontab(minute="*/15"),
        "args": (SITE_BASE_URL,),
    },
    ...
}
```
