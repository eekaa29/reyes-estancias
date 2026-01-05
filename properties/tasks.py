# properties/tasks.py
from celery import shared_task
from properties.models import Property
from properties.utils.ical import fetch_ical_bookings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_all_property_calendars():
    """
    Sincroniza los calendarios iCal de todas las propiedades con URLs configuradas.

    Esta tarea se ejecuta periódicamente (cada 30 minutos) para:
    1. Mantener el caché de calendarios siempre actualizado (warm cache)
    2. Garantizar que los usuarios siempre obtengan respuestas instantáneas
    3. Evitar que el primer usuario después de expiración espere la petición HTTP

    Proceso:
    - Obtiene todas las propiedades con airbnb_ical_url configurado
    - Para cada una, llama a fetch_ical_bookings() que:
      * Actualiza el caché si ya existe
      * Carga el caché si no existe
    - Registra estadísticas de éxito/errores

    Returns:
        dict: Resumen de la sincronización con estadísticas
    """
    logger.info("=" * 70)
    logger.info("Iniciando sincronización automática de calendarios iCal")
    logger.info("=" * 70)

    # Obtener propiedades con calendario configurado
    properties_with_ical = Property.objects.filter(
        airbnb_ical_url__isnull=False
    ).exclude(airbnb_ical_url='')

    total = properties_with_ical.count()
    success = 0
    errors = 0
    total_bookings = 0

    if total == 0:
        logger.warning("No hay propiedades con calendario iCal configurado")
        return {
            'total': 0,
            'success': 0,
            'errors': 0,
            'total_bookings': 0,
            'message': 'No properties with iCal configured'
        }

    logger.info(f"Sincronizando {total} propiedades con calendarios iCal...")

    for prop in properties_with_ical:
        try:
            logger.info(f"Sincronizando '{prop.name}' (ID: {prop.id})...")

            # fetch_ical_bookings automáticamente usa y actualiza el caché
            bookings = fetch_ical_bookings(prop.airbnb_ical_url)

            logger.info(
                f"✅ Calendario sincronizado para '{prop.name}': "
                f"{len(bookings)} reservas bloqueadas"
            )

            success += 1
            total_bookings += len(bookings)

        except Exception as e:
            logger.error(
                f"❌ Error sincronizando calendario de '{prop.name}' (ID: {prop.id}): {e}",
                exc_info=True,
                extra={
                    'property_id': prop.id,
                    'property_name': prop.name,
                    'ical_url': prop.airbnb_ical_url[:100] if prop.airbnb_ical_url else None
                }
            )
            errors += 1

    # Log de resumen
    logger.info("=" * 70)
    logger.info(
        f"Sincronización completada: {success}/{total} exitosas, {errors} errores, "
        f"{total_bookings} reservas totales"
    )
    logger.info("=" * 70)

    result = {
        'total': total,
        'success': success,
        'errors': errors,
        'total_bookings': total_bookings,
        'message': f'{success}/{total} calendars synced successfully'
    }

    return result


@shared_task
def sync_single_property_calendar(property_id):
    """
    Sincroniza el calendario iCal de una propiedad específica.

    Útil para sincronización manual o bajo demanda.

    Args:
        property_id: ID de la propiedad a sincronizar

    Returns:
        dict: Resultado de la sincronización
    """
    try:
        prop = Property.objects.get(id=property_id)

        if not prop.airbnb_ical_url:
            logger.warning(
                f"Propiedad '{prop.name}' (ID: {property_id}) no tiene calendario iCal configurado"
            )
            return {
                'success': False,
                'error': 'No iCal URL configured',
                'property_id': property_id,
                'property_name': prop.name
            }

        logger.info(f"Sincronizando calendario de '{prop.name}' (ID: {property_id})...")

        bookings = fetch_ical_bookings(prop.airbnb_ical_url)

        logger.info(
            f"✅ Calendario sincronizado para '{prop.name}': {len(bookings)} reservas"
        )

        return {
            'success': True,
            'property_id': property_id,
            'property_name': prop.name,
            'bookings_count': len(bookings)
        }

    except Property.DoesNotExist:
        logger.error(f"Propiedad con ID {property_id} no existe")
        return {
            'success': False,
            'error': 'Property not found',
            'property_id': property_id
        }

    except Exception as e:
        logger.error(
            f"Error sincronizando calendario de propiedad {property_id}: {e}",
            exc_info=True
        )
        return {
            'success': False,
            'error': str(e),
            'property_id': property_id
        }
