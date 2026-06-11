# Fix: Anti-fraude en cancelaciones tras cambio de fechas

**Fecha:** 2026-06-11  
**Archivo modificado:** `payments/services.py` — función `compute_refund_plan`

---

## El problema

Un usuario podía obtener un reembolso del 100% que no le correspondía explotando la política de cancelación:

1. Tiene una reserva con check-in en ≤7 días → le correspondería **0% de reembolso** (penalización del 50%).
2. Cambia las fechas para que el nuevo check-in quede a >7 días.
3. Cancela inmediatamente → el sistema calculaba **100% de reembolso** del depósito.

La política de reembolso se basa en `booking.arrival`, que ya apuntaba a la fecha nueva, sin tener en cuenta el historial de cambios.

---

## La solución (Opción A)

En `compute_refund_plan`, antes de calcular `days_before`, se consulta `BookingChangeLog` para detectar si el usuario retrasó el check-in en los últimos 7 días:

```python
fraud_window = now() - timedelta(days=7)
early_change = (
    BookingChangeLog.objects
    .filter(
        booking=booking,
        status="applied",
        created_at__gte=fraud_window,
        new_arrival__gt=F("old_arrival"),
    )
    .order_by("old_arrival")
    .first()
)
effective_arrival = early_change.old_arrival if early_change else booking.arrival

days_before = (effective_arrival.date() - today).days
```

Si existe un cambio que retrasó el check-in dentro de la ventana de 7 días, se usa la `old_arrival` más temprana para calcular la ventana de reembolso. En caso contrario, se usa `booking.arrival` como siempre.

---

## Por qué no la Opción B (usar siempre `original_arrival`)

Si el usuario reagendó legítimamente a una fecha lejana (hace más de 7 días) y luego cancela cerca de la nueva fecha, `original_arrival` podría estar ya en el pasado. El sistema lo trataría como **no-show** aplicando una penalización del 100%, lo cual sería incorrecto.

La Opción A limita la protección a la ventana de 7 días, que es la misma ventana que define la política de cancelación estricta.

---

## Política de reembolso resultante

| Situación | `days_before` calculado sobre | Resultado |
|---|---|---|
| Sin cambios de fecha recientes | `booking.arrival` | Normal |
| Cambio de fecha hace >7 días | `booking.arrival` (nueva) | Normal — reagenda legítimo |
| Cambio de fecha hace ≤7 días retrasando el check-in | `old_arrival` más temprana | Aplica política original |

---

## Modelos involucrados

- `BookingChangeLog` (`bookings/models.py:85`) — campos usados: `booking`, `status`, `created_at`, `old_arrival`, `new_arrival`.
- Solo se consideran entradas con `status="applied"` para ignorar cambios pendientes o reemplazados.
