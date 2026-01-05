#!/usr/bin/env python3
"""
Script de Verificación Pre-Deployment para Reyes Estancias
===========================================================

Verifica que todos los requisitos estén cumplidos antes de hacer deployment a producción.

Uso:
    python scripts/pre_deploy_check.py           # Solo verificar
    python scripts/pre_deploy_check.py --fix     # Intentar corregir problemas automáticamente
    python scripts/pre_deploy_check.py --env production  # Usar .env.production

Autor: Sistema de Calendarios - Reyes Estancias
Fecha: 2026-01-05
"""

import os
import sys
import django
import argparse
from pathlib import Path
from typing import List, Tuple
import subprocess

# Colores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(text: str):
    """Imprime un header de sección"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(80)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.RESET}\n")

def print_check(name: str, passed: bool, message: str = ""):
    """Imprime el resultado de una verificación"""
    symbol = f"{Colors.GREEN}✓{Colors.RESET}" if passed else f"{Colors.RED}✗{Colors.RESET}"
    status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
    print(f"{symbol} {name:.<60} [{status}]")
    if message:
        color = Colors.GREEN if passed else Colors.RED
        print(f"  {color}{message}{Colors.RESET}")

def print_warning(message: str):
    """Imprime un mensaje de advertencia"""
    print(f"{Colors.YELLOW}⚠ WARNING: {message}{Colors.RESET}")

def print_info(message: str):
    """Imprime un mensaje informativo"""
    print(f"{Colors.BLUE}ℹ INFO: {message}{Colors.RESET}")

class PreDeploymentChecker:
    """Clase principal para verificaciones pre-deployment"""

    def __init__(self, fix_mode: bool = False, env_file: str = '.env'):
        self.fix_mode = fix_mode
        self.env_file = env_file
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []

        # Configurar Django
        self.base_dir = Path(__file__).resolve().parent.parent
        os.chdir(self.base_dir)

        # Cargar variables de entorno del archivo especificado
        env_path = self.base_dir / env_file
        if env_path.exists():
            print_info(f"Usando archivo de entorno: {env_file}")
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reyes_estancias.settings')
            # Forzar lectura del archivo de entorno específico
            os.environ['DJANGO_READ_DOT_ENV_FILE'] = 'True'
        else:
            print_warning(f"Archivo {env_file} no encontrado, usando variables del sistema")

        sys.path.insert(0, str(self.base_dir))

        try:
            django.setup()
            from django.conf import settings
            self.settings = settings
        except Exception as e:
            print_check("Django Settings Initialization", False, f"Error: {e}")
            sys.exit(1)

    def check_django_settings(self) -> bool:
        """Verifica que Django settings sea válido"""
        try:
            from django.core.management import call_command
            from io import StringIO

            out = StringIO()
            call_command('check', '--deploy', stdout=out, stderr=out)
            output = out.getvalue()

            if 'System check identified no issues' in output or output.strip() == '':
                print_check("Django Settings válidos", True)
                self.checks_passed.append("Django Settings")
                return True
            else:
                print_check("Django Settings válidos", False, output)
                self.checks_failed.append("Django Settings")
                return False
        except Exception as e:
            print_check("Django Settings válidos", False, str(e))
            self.checks_failed.append("Django Settings")
            return False

    def check_secret_key(self) -> bool:
        """Verifica que SECRET_KEY sea diferente al de desarrollo"""
        try:
            secret_key = self.settings.SECRET_KEY

            # Lista de SECRET_KEYs inseguros comunes
            insecure_keys = [
                'django-insecure-',
                'tu_secret_key_aqui',
                'changeme',
                'secret',
                '1234',
            ]

            is_insecure = any(key in secret_key.lower() for key in insecure_keys)
            is_short = len(secret_key) < 50

            if is_insecure or is_short:
                msg = "SECRET_KEY parece inseguro o es de desarrollo"
                print_check("SECRET_KEY seguro", False, msg)
                self.checks_failed.append("SECRET_KEY")

                if self.fix_mode:
                    print_info("Generando nuevo SECRET_KEY...")
                    from django.core.management.utils import get_random_secret_key
                    new_key = get_random_secret_key()
                    print(f"\n{Colors.YELLOW}Nuevo SECRET_KEY generado:{Colors.RESET}")
                    print(f"{Colors.GREEN}{new_key}{Colors.RESET}")
                    print(f"{Colors.YELLOW}Añade esto a tu {self.env_file}:{Colors.RESET}")
                    print(f"SECRET_KEY={new_key}\n")

                return False
            else:
                print_check("SECRET_KEY seguro", True)
                self.checks_passed.append("SECRET_KEY")
                return True
        except Exception as e:
            print_check("SECRET_KEY seguro", False, str(e))
            self.checks_failed.append("SECRET_KEY")
            return False

    def check_debug_mode(self) -> bool:
        """Verifica que DEBUG esté en False para producción"""
        try:
            debug = self.settings.DEBUG

            if debug:
                msg = "DEBUG=True es inseguro en producción"
                print_check("DEBUG=False", False, msg)
                self.checks_failed.append("DEBUG mode")

                if self.fix_mode:
                    print_warning("Cambia DEBUG=False en tu archivo de entorno")

                return False
            else:
                print_check("DEBUG=False", True)
                self.checks_passed.append("DEBUG mode")
                return True
        except Exception as e:
            print_check("DEBUG=False", False, str(e))
            self.checks_failed.append("DEBUG mode")
            return False

    def check_allowed_hosts(self) -> bool:
        """Verifica que ALLOWED_HOSTS esté configurado"""
        try:
            allowed_hosts = self.settings.ALLOWED_HOSTS

            if not allowed_hosts or allowed_hosts == ['*']:
                msg = "ALLOWED_HOSTS debe estar configurado con dominios específicos"
                print_check("ALLOWED_HOSTS configurado", False, msg)
                self.checks_failed.append("ALLOWED_HOSTS")
                return False

            # Verificar que no contenga localhost en producción
            has_localhost = any(host in ['localhost', '127.0.0.1'] for host in allowed_hosts)
            if has_localhost and not self.settings.DEBUG:
                print_warning("ALLOWED_HOSTS contiene localhost/127.0.0.1 en producción")
                self.warnings.append("ALLOWED_HOSTS contiene valores de desarrollo")

            print_check("ALLOWED_HOSTS configurado", True, f"Hosts: {', '.join(allowed_hosts)}")
            self.checks_passed.append("ALLOWED_HOSTS")
            return True
        except Exception as e:
            print_check("ALLOWED_HOSTS configurado", False, str(e))
            self.checks_failed.append("ALLOWED_HOSTS")
            return False

    def check_database_migrations(self) -> bool:
        """Verifica que todas las migraciones estén aplicadas"""
        try:
            from django.core.management import call_command
            from io import StringIO

            out = StringIO()
            call_command('showmigrations', '--plan', stdout=out)
            output = out.getvalue()

            # Verificar si hay migraciones sin aplicar (líneas sin [X])
            unapplied = [line for line in output.split('\n') if line.strip() and '[ ]' in line]

            if unapplied:
                msg = f"{len(unapplied)} migraciones sin aplicar"
                print_check("Migraciones aplicadas", False, msg)
                self.checks_failed.append("Database migrations")

                if self.fix_mode:
                    print_info("Aplicando migraciones...")
                    call_command('migrate', '--no-input')
                    print_check("Migraciones aplicadas automáticamente", True)
                    return True

                return False
            else:
                print_check("Migraciones aplicadas", True)
                self.checks_passed.append("Database migrations")
                return True
        except Exception as e:
            print_check("Migraciones aplicadas", False, str(e))
            self.checks_failed.append("Database migrations")
            return False

    def check_redis_connection(self) -> bool:
        """Verifica que Redis esté accesible"""
        try:
            from django.core.cache import cache

            # Intentar set/get en cache
            test_key = 'pre_deploy_check_test'
            test_value = 'test_value_12345'

            cache.set(test_key, test_value, 10)
            retrieved = cache.get(test_key)
            cache.delete(test_key)

            if retrieved == test_value:
                print_check("Redis accesible", True)
                self.checks_passed.append("Redis connection")
                return True
            else:
                print_check("Redis accesible", False, "No se pudo verificar set/get")
                self.checks_failed.append("Redis connection")
                return False
        except Exception as e:
            print_check("Redis accesible", False, str(e))
            self.checks_failed.append("Redis connection")
            return False

    def check_database_connection(self) -> bool:
        """Verifica que la base de datos esté accesible"""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            if result and result[0] == 1:
                db_name = connection.settings_dict.get('NAME', 'unknown')
                print_check("Base de datos accesible", True, f"DB: {db_name}")
                self.checks_passed.append("Database connection")
                return True
            else:
                print_check("Base de datos accesible", False)
                self.checks_failed.append("Database connection")
                return False
        except Exception as e:
            print_check("Base de datos accesible", False, str(e))
            self.checks_failed.append("Database connection")
            return False

    def check_stripe_mode(self) -> bool:
        """Verifica que Stripe esté en modo live para producción"""
        try:
            secret_key = self.settings.STRIPE_SECRET_KEY
            publishable_key = self.settings.STRIPE_PUBLISHABLE_KEY

            is_test_secret = secret_key.startswith('sk_test_')
            is_test_publishable = publishable_key.startswith('pk_test_')

            if not self.settings.DEBUG:
                # En producción, las claves deben ser live
                if is_test_secret or is_test_publishable:
                    msg = "Stripe está en modo test (debe ser live en producción)"
                    print_check("Stripe en modo live", False, msg)
                    self.checks_failed.append("Stripe mode")
                    return False
                else:
                    print_check("Stripe en modo live", True)
                    self.checks_passed.append("Stripe mode")
                    return True
            else:
                # En desarrollo, está bien usar test
                if is_test_secret and is_test_publishable:
                    print_check("Stripe en modo test", True, "OK para desarrollo")
                    self.checks_passed.append("Stripe mode")
                    return True
                else:
                    print_warning("Stripe en modo live en desarrollo (no recomendado)")
                    self.warnings.append("Stripe live en desarrollo")
                    self.checks_passed.append("Stripe mode")
                    return True
        except Exception as e:
            print_check("Stripe configurado", False, str(e))
            self.checks_failed.append("Stripe mode")
            return False

    def check_static_files(self) -> bool:
        """Verifica que los archivos estáticos estén generados"""
        try:
            static_root = getattr(self.settings, 'STATIC_ROOT', None)

            if not static_root:
                print_warning("STATIC_ROOT no configurado")
                self.warnings.append("STATIC_ROOT no configurado")
                return True  # No es crítico si no está configurado

            static_path = Path(static_root)

            if static_path.exists() and any(static_path.iterdir()):
                print_check("Archivos estáticos generados", True, f"Path: {static_root}")
                self.checks_passed.append("Static files")
                return True
            else:
                msg = "STATIC_ROOT existe pero está vacío. Ejecuta collectstatic"
                print_check("Archivos estáticos generados", False, msg)
                self.checks_failed.append("Static files")

                if self.fix_mode:
                    print_info("Ejecutando collectstatic...")
                    from django.core.management import call_command
                    call_command('collectstatic', '--no-input', '--clear')
                    print_check("Archivos estáticos generados automáticamente", True)
                    return True

                return False
        except Exception as e:
            # Si STATIC_ROOT no existe, es solo una advertencia
            print_warning(f"No se pudo verificar archivos estáticos: {e}")
            self.warnings.append("Static files no verificados")
            return True

    def check_critical_env_vars(self) -> bool:
        """Verifica que todas las variables de entorno críticas estén configuradas"""
        critical_vars = {
            'SECRET_KEY': 'Clave secreta de Django',
            'DB_NAME': 'Nombre de la base de datos',
            'DB_USER': 'Usuario de la base de datos',
            'DB_PASSWORD': 'Contraseña de la base de datos',
            'DB_HOST': 'Host de la base de datos',
            'STRIPE_SECRET_KEY': 'Clave secreta de Stripe',
            'STRIPE_PUBLISHABLE_KEY': 'Clave pública de Stripe',
            'STRIPE_WEBHOOK_SECRET': 'Secret del webhook de Stripe',
            'EMAIL_HOST': 'Host del servidor de email',
            'EMAIL_HOST_USER': 'Usuario del servidor de email',
            'EMAIL_HOST_PASSWORD': 'Contraseña del servidor de email',
            'CELERY_BROKER_URL': 'URL del broker de Celery (Redis)',
        }

        missing_vars = []
        insecure_vars = []

        for var, description in critical_vars.items():
            value = os.environ.get(var, '')

            if not value:
                missing_vars.append(f"{var} ({description})")
            elif value in ['tu_secret_key_aqui', 'changeme', 'tu_password', 'tu_clave_de_prueba']:
                insecure_vars.append(f"{var} ({description})")

        all_ok = len(missing_vars) == 0 and len(insecure_vars) == 0

        if missing_vars:
            msg = f"Variables faltantes: {', '.join(missing_vars)}"
            print_check("Variables de entorno críticas", False, msg)
            self.checks_failed.append("Environment variables")

        if insecure_vars:
            msg = f"Variables con valores por defecto: {', '.join(insecure_vars)}"
            print_check("Variables de entorno seguras", False, msg)
            self.checks_failed.append("Environment variables")

        if all_ok:
            print_check("Variables de entorno críticas", True, f"{len(critical_vars)} variables configuradas")
            self.checks_passed.append("Environment variables")

        return all_ok

    def check_celery_workers(self) -> bool:
        """Verifica que Celery workers estén accesibles"""
        try:
            from celery import Celery

            app = Celery('reyes_estancias')
            app.config_from_object('django.conf:settings', namespace='CELERY')

            # Intentar inspeccionar workers activos
            inspect = app.control.inspect(timeout=3.0)
            active_workers = inspect.active()

            if active_workers and len(active_workers) > 0:
                worker_count = len(active_workers)
                print_check("Celery workers accesibles", True, f"{worker_count} worker(s) activo(s)")
                self.checks_passed.append("Celery workers")
                return True
            else:
                msg = "No se detectaron workers activos. Asegúrate de iniciar Celery"
                print_check("Celery workers accesibles", False, msg)
                self.checks_failed.append("Celery workers")
                return False
        except Exception as e:
            msg = f"No se pudo conectar con Celery: {e}"
            print_check("Celery workers accesibles", False, msg)
            self.checks_failed.append("Celery workers")
            return False

    def check_celery_beat(self) -> bool:
        """Verifica que Celery Beat esté configurado"""
        try:
            beat_schedule = self.settings.CELERY_BEAT_SCHEDULE

            if beat_schedule and len(beat_schedule) > 0:
                task_count = len(beat_schedule)
                tasks = ', '.join(beat_schedule.keys())
                print_check("Celery Beat configurado", True, f"{task_count} tarea(s) programada(s)")
                print_info(f"Tareas: {tasks}")
                self.checks_passed.append("Celery Beat")
                return True
            else:
                print_check("Celery Beat configurado", False, "No hay tareas programadas")
                self.checks_failed.append("Celery Beat")
                return False
        except Exception as e:
            print_check("Celery Beat configurado", False, str(e))
            self.checks_failed.append("Celery Beat")
            return False

    def check_security_settings(self) -> bool:
        """Verifica configuraciones de seguridad para producción"""
        if self.settings.DEBUG:
            print_info("Verificación de seguridad omitida en modo DEBUG")
            return True

        security_checks = {
            'SECURE_SSL_REDIRECT': True,
            'SESSION_COOKIE_SECURE': True,
            'CSRF_COOKIE_SECURE': True,
            'SECURE_BROWSER_XSS_FILTER': True,
            'SECURE_CONTENT_TYPE_NOSNIFF': True,
        }

        failed_checks = []
        for setting, expected_value in security_checks.items():
            actual_value = getattr(self.settings, setting, None)
            if actual_value != expected_value:
                failed_checks.append(f"{setting}={actual_value} (esperado: {expected_value})")

        if failed_checks:
            msg = "Configuraciones de seguridad incorrectas: " + ", ".join(failed_checks)
            print_check("Configuraciones de seguridad", False, msg)
            self.checks_failed.append("Security settings")
            return False
        else:
            print_check("Configuraciones de seguridad", True)
            self.checks_passed.append("Security settings")
            return True

    def generate_report(self):
        """Genera reporte final de verificación"""
        print_header("REPORTE DE VERIFICACIÓN PRE-DEPLOYMENT")

        total_checks = len(self.checks_passed) + len(self.checks_failed)
        passed_count = len(self.checks_passed)
        failed_count = len(self.checks_failed)
        warnings_count = len(self.warnings)

        print(f"\n{Colors.BOLD}Resumen:{Colors.RESET}")
        print(f"  Total de verificaciones: {total_checks}")
        print(f"  {Colors.GREEN}✓ Pasadas: {passed_count}{Colors.RESET}")
        print(f"  {Colors.RED}✗ Fallidas: {failed_count}{Colors.RESET}")
        print(f"  {Colors.YELLOW}⚠ Advertencias: {warnings_count}{Colors.RESET}")

        if self.checks_failed:
            print(f"\n{Colors.BOLD}{Colors.RED}Verificaciones fallidas:{Colors.RESET}")
            for check in self.checks_failed:
                print(f"  {Colors.RED}• {check}{Colors.RESET}")

        if self.warnings:
            print(f"\n{Colors.BOLD}{Colors.YELLOW}Advertencias:{Colors.RESET}")
            for warning in self.warnings:
                print(f"  {Colors.YELLOW}• {warning}{Colors.RESET}")

        print("\n" + "=" * 80)

        if failed_count == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ SISTEMA LISTO PARA DEPLOYMENT{Colors.RESET}\n")
            return 0
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ SISTEMA NO LISTO PARA DEPLOYMENT{Colors.RESET}")
            print(f"{Colors.YELLOW}Corrige los problemas antes de hacer deployment{Colors.RESET}\n")

            if not self.fix_mode:
                print(f"{Colors.BLUE}Tip: Ejecuta con --fix para intentar corregir algunos problemas automáticamente{Colors.RESET}\n")

            return 1

    def run_all_checks(self) -> int:
        """Ejecuta todas las verificaciones"""
        print_header("VERIFICACIÓN PRE-DEPLOYMENT - REYES ESTANCIAS")

        if self.fix_mode:
            print(f"{Colors.YELLOW}{Colors.BOLD}MODO FIX ACTIVADO{Colors.RESET}")
            print(f"{Colors.YELLOW}Se intentarán corregir problemas automáticamente{Colors.RESET}\n")

        # Ejecutar todas las verificaciones
        print_header("1. VERIFICACIONES DE DJANGO")
        self.check_django_settings()
        self.check_secret_key()
        self.check_debug_mode()
        self.check_allowed_hosts()

        print_header("2. VERIFICACIONES DE BASE DE DATOS")
        self.check_database_connection()
        self.check_database_migrations()

        print_header("3. VERIFICACIONES DE SERVICIOS")
        self.check_redis_connection()
        self.check_celery_workers()
        self.check_celery_beat()

        print_header("4. VERIFICACIONES DE INTEGRATIONS")
        self.check_stripe_mode()

        print_header("5. VERIFICACIONES DE DEPLOYMENT")
        self.check_static_files()
        self.check_critical_env_vars()
        self.check_security_settings()

        # Generar reporte
        return self.generate_report()


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description='Verificación pre-deployment para Reyes Estancias',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python scripts/pre_deploy_check.py                    # Solo verificar
  python scripts/pre_deploy_check.py --fix              # Corregir problemas
  python scripts/pre_deploy_check.py --env .env.production  # Usar archivo específico
        """
    )

    parser.add_argument(
        '--fix',
        action='store_true',
        help='Intentar corregir problemas automáticamente'
    )

    parser.add_argument(
        '--env',
        type=str,
        default='.env',
        help='Archivo de entorno a usar (default: .env)'
    )

    args = parser.parse_args()

    # Ejecutar verificaciones
    checker = PreDeploymentChecker(fix_mode=args.fix, env_file=args.env)
    exit_code = checker.run_all_checks()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
