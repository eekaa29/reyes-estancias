import requests
from django.core.management.base import BaseCommand
from properties.models import Property
from properties.utils.ical import get_blocked_dates  # Asegúrate de tener esta función implementada

class Command(BaseCommand):
    help = 'Importa y parsea los calendarios .ics de cada propiedad'

    def handle(self, *args, **options):
        props = Property.objects.exclude(airbnb_ical_url__isnull=True).exclude(airbnb_ical_url__exact="")
        if not props.exists():
            self.stdout.write(self.style.WARNING("No hay propiedades con calendar_url configurado."))
            return

        for prop in props:
            self.stdout.write(self.style.NOTICE(f"\nProcesando propiedad: {prop.name}"))
            try:
                blocked = get_blocked_dates(prop.airbnb_ical_url)

                if blocked:
                    self.stdout.write(self.style.SUCCESS(f"Fechas bloqueadas encontradas: {len(blocked)}"))
                    for b in blocked:
                        self.stdout.write(f" - {b}")
                else:
                    self.stdout.write(self.style.WARNING("No se encontraron fechas bloqueadas."))
            
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error procesando {prop.name}: {str(e)}"))
