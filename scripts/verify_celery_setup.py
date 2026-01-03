#!/usr/bin/env python
"""
Script de verificación de configuración de Celery

Ejecuta este script antes de ir a producción para verificar que todo esté correctamente configurado.

Uso:
    python scripts/verify_celery_setup.py
"""

import os
import sys
from pathlib import Path

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reyes_estancias.settings')
django.setup()

from django.conf import settings
from django.utils import timezone
from bookings.models import Booking
import redis


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_success(msg):
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")


def print_error(msg):
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")


def print_warning(msg):
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {msg}")


def print_header(msg):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{msg}{Colors.RESET}")


def verify_redis_connection():
    """Verifica conexión a Redis"""
    print_header("1. Verificando conexión a Redis...")

    try:
        broker_url = settings.CELERY_BROKER_URL
        print(f"   Broker URL: {broker_url}")

        # Intentar conectar
        r = redis.from_url(broker_url)
        r.ping()
        print_success("Redis está accesible y respondiendo")
        return True
    except Exception as e:
        print_error(f"No se puede conectar a Redis: {e}")
        print_warning("   Asegúrate de que Redis esté corriendo: redis-server")
        return False


def verify_celery_settings():
    """Verifica configuración de Celery en settings.py"""
    print_header("2. Verificando configuración de Celery...")

    checks = [
        ('CELERY_BROKER_URL', getattr(settings, 'CELERY_BROKER_URL', None)),
        ('CELERY_RESULT_BACKEND', getattr(settings, 'CELERY_RESULT_BACKEND', None)),
        ('CELERY_TIMEZONE', getattr(settings, 'CELERY_TIMEZONE', None)),
        ('CELERY_BEAT_SCHEDULE', getattr(settings, 'CELERY_BEAT_SCHEDULE', None)),
    ]

    all_ok = True
    for name, value in checks:
        if value:
            print_success(f"{name} configurado")
        else:
            print_error(f"{name} NO configurado")
            all_ok = False

    return all_ok


def verify_beat_schedule():
    """Verifica que las tareas estén en el schedule"""
    print_header("3. Verificando CELERY_BEAT_SCHEDULE...")

    expected_tasks = [
        'charge-balances-every-15-min',
        'mark-expired-bookings-daily',
        'mark-expired-holds-hourly',
    ]

    schedule = settings.CELERY_BEAT_SCHEDULE
    all_ok = True

    for task_name in expected_tasks:
        if task_name in schedule:
            task_path = schedule[task_name]['task']
            schedule_info = schedule[task_name]['schedule']
            print_success(f"{task_name}")
            print(f"      Tarea: {task_path}")
            print(f"      Horario: {schedule_info}")
        else:
            print_error(f"{task_name} NO encontrado en schedule")
            all_ok = False

    return all_ok


def verify_tasks_import():
    """Verifica que las tareas se puedan importar"""
    print_header("4. Verificando importación de tareas...")

    tasks_to_import = [
        ('bookings.tasks', 'mark_expired_bookings'),
        ('bookings.tasks', 'mark_expired_holds'),
        ('payments.tasks', 'scan_and_charge_balances'),
        ('payments.tasks', 'charge_balance_for_booking'),
    ]

    all_ok = True
    for module_name, task_name in tasks_to_import:
        try:
            module = __import__(module_name, fromlist=[task_name])
            task = getattr(module, task_name)
            print_success(f"{module_name}.{task_name}")
            print(f"      Nombre completo: {task.name}")
        except Exception as e:
            print_error(f"No se puede importar {module_name}.{task_name}: {e}")
            all_ok = False

    return all_ok


def verify_booking_model():
    """Verifica que el modelo Booking tenga el estado 'expired'"""
    print_header("5. Verificando modelo Booking...")

    # Verificar que 'expired' esté en STATUS_CHOICES
    status_choices = dict(Booking.STATUS_CHOICES)

    if 'expired' in status_choices:
        print_success("Estado 'expired' existe en STATUS_CHOICES")
    else:
        print_error("Estado 'expired' NO existe en STATUS_CHOICES")
        return False

    # Contar reservas por estado
    total = Booking.objects.count()
    confirmed = Booking.objects.filter(status='confirmed').count()
    expired = Booking.objects.filter(status='expired').count()
    pending = Booking.objects.filter(status='pending').count()
    cancelled = Booking.objects.filter(status='cancelled').count()

    print(f"   Total de reservas: {total}")
    print(f"   - Confirmadas: {confirmed}")
    print(f"   - Expiradas: {expired}")
    print(f"   - Pendientes: {pending}")
    print(f"   - Canceladas: {cancelled}")

    # Buscar reservas que deberían estar expiradas
    now = timezone.now()
    should_be_expired = Booking.objects.filter(
        status='confirmed',
        departure__lt=now
    ).count()

    if should_be_expired > 0:
        print_warning(f"{should_be_expired} reserva(s) confirmada(s) ya pasaron su checkout")
        print("      Ejecuta: python manage.py shell -c \"from bookings.tasks import mark_expired_bookings; mark_expired_bookings()\"")
    else:
        print_success("No hay reservas confirmadas que deban estar expiradas")

    return True


def test_task_execution():
    """Prueba ejecutar la tarea manualmente"""
    print_header("6. Probando ejecución de tarea...")

    try:
        from bookings.tasks import mark_expired_bookings

        # Ejecutar de forma síncrona
        result = mark_expired_bookings()
        print_success(f"Tarea ejecutada correctamente: {result}")
        return True
    except Exception as e:
        print_error(f"Error al ejecutar tarea: {e}")
        return False


def main():
    print(f"\n{Colors.BOLD}{'='*70}")
    print("  VERIFICACIÓN DE CONFIGURACIÓN DE CELERY - REYES ESTANCIAS")
    print(f"{'='*70}{Colors.RESET}\n")

    results = []

    results.append(("Redis", verify_redis_connection()))
    results.append(("Settings", verify_celery_settings()))
    results.append(("Beat Schedule", verify_beat_schedule()))
    results.append(("Importación", verify_tasks_import()))
    results.append(("Modelo Booking", verify_booking_model()))
    results.append(("Ejecución de tarea", test_task_execution()))

    # Resumen
    print_header("RESUMEN")

    all_passed = all(result for _, result in results)

    for name, passed in results:
        if passed:
            print_success(f"{name}: OK")
        else:
            print_error(f"{name}: FALLO")

    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}\n")

    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ TODAS LAS VERIFICACIONES PASARON{Colors.RESET}")
        print("\nEstás listo para ir a producción. Sigue la guía:")
        print("  docs/CELERY_PRODUCCION.md")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ ALGUNAS VERIFICACIONES FALLARON{Colors.RESET}")
        print("\nRevisa los errores arriba y consulta:")
        print("  docs/PRUEBAS_LOCALES_CELERY.md")
        return 1


if __name__ == '__main__':
    sys.exit(main())
