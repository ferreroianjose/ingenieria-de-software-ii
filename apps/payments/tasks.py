import logging
import calendar
from datetime import date, timedelta
from django.utils import timezone
from apps.payments.models import PeriodoCobro, PrecioClase
from apps.payments.periodos import dias_preinscripcion_abonados

logger = logging.getLogger(__name__)

def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def crear_siguiente_periodo_si_es_necesario():
    """
    Verifica si para el día actual + (días de preinscripción + 5) ya existe
    el período correspondiente. Si no existe, lo crea copiando los precios
    del período anterior.
    """
    hoy = timezone.localdate()
    margen_dias = dias_preinscripcion_abonados() + 5
    
    # La fecha "objetivo" que ya debería estar cubierta por un período
    fecha_objetivo = hoy + timedelta(days=margen_dias)
    
    # Buscamos si ya existe un período que cubra esta fecha_objetivo
    # Asumimos que los períodos inician el 1 del mes
    objetivo_inicio = date(fecha_objetivo.year, fecha_objetivo.month, 1)
    
    periodo_existente = PeriodoCobro.objects.filter(
        fecha_inicio_periodo__lte=objetivo_inicio,
        fecha_fin_periodo__gte=objetivo_inicio
    ).exists()
    
    if periodo_existente:
        logger.info("El período necesario ya existe. No se requiere acción.")
        return
        
    # Si no existe, lo creamos. Buscamos el último período disponible para copiar precios.
    ultimo_periodo = PeriodoCobro.objects.filter(fecha_inicio_periodo__lt=objetivo_inicio).order_by("-fecha_inicio_periodo").first()
    
    if not ultimo_periodo:
        logger.info("No hay períodos previos para usar de base. Omitiendo creación automática.")
        return
        
    # Último día del mes objetivo
    ultimo_dia = calendar.monthrange(objetivo_inicio.year, objetivo_inicio.month)[1]
    objetivo_fin = date(objetivo_inicio.year, objetivo_inicio.month, ultimo_dia)
    
    # Aperturas
    apertura_abonados = objetivo_inicio - timedelta(days=dias_preinscripcion_abonados())
    apertura_general = objetivo_inicio
    
    meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    nombre = f"{meses[objetivo_inicio.month - 1]} {objetivo_inicio.year}"
    
    nuevo_periodo = PeriodoCobro.objects.create(
        nombre=nombre,
        fecha_inicio_periodo=objetivo_inicio,
        fecha_fin_periodo=objetivo_fin,
        apertura_abonados=apertura_abonados,
        apertura_general=apertura_general
    )
    
    precios_a_crear = []
    for precio in PrecioClase.objects.filter(periodo=ultimo_periodo):
        precios_a_crear.append(PrecioClase(
            clase=precio.clase,
            periodo=nuevo_periodo,
            monto=precio.monto
        ))
        
    if precios_a_crear:
        PrecioClase.objects.bulk_create(precios_a_crear)
        
    logger.info(f"Creado nuevo período automáticamente: {nombre} con {len(precios_a_crear)} precios.")

