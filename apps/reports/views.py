import json
from datetime import timedelta
from django.db.models import Count, Sum, F
from django.db.models.functions import TruncMonth, ExtractHour, ExtractWeekDay
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test

from apps.classes.models import InscripcionOcurrencia, Inscripcion, Class
from apps.payments.models import Pago

def es_admin(user):
    return user.is_authenticated and user.rol == "ADMIN"

@user_passes_test(es_admin)
def metrics_api(request):
    rango = request.GET.get('rango', 'este_mes') # este_mes, ultimos_30, este_anio, todo
    agrupar_horario = request.GET.get('agrupar_horario', 'hora') # hora, dia_hora
    orden_clases = request.GET.get('orden_clases', 'desc')
    orden_horarios = request.GET.get('orden_horarios', 'desc')

    hoy = timezone.now().date()
    from apps.payments.models import PeriodoCobro
    periodos = PeriodoCobro.objects.all()

    if rango == 'este_mes':
        periodos = periodos.filter(fecha_inicio_periodo__lte=hoy, fecha_fin_periodo__gte=hoy)
    elif rango == 'ultimos_30':
        hace_30 = hoy - timedelta(days=30)
        periodos = periodos.filter(fecha_fin_periodo__gte=hace_30, fecha_inicio_periodo__lte=hoy)
    elif rango == 'este_anio':
        periodos = periodos.filter(fecha_inicio_periodo__year=hoy.year)

    periodos_ids = list(periodos.values_list('id', flat=True))

    # Base queries
    ocurrencias = InscripcionOcurrencia.objects.filter(inscripcion__periodo_id__in=periodos_ids)
    pagos = Pago.objects.filter(estado=Pago.Estado.COMPLETADO, periodo_id__in=periodos_ids)

    # 1. Clases más concurridas (Top 5)
    orden_clases_prefix = '' if orden_clases == 'asc' else '-'
    concurridas_qs = (
        ocurrencias.filter(estado=InscripcionOcurrencia.Estado.ACTIVA)
        .values(nombre_disciplina=F('inscripcion__clase__disciplina__nombre'))
        .annotate(total=Count('id'))
        .order_by(f"{orden_clases_prefix}total")[:5]
    )
    clases_concurridas = {
        "labels": [c['nombre_disciplina'] or 'Sin Disciplina' for c in concurridas_qs],
        "data": [c['total'] for c in concurridas_qs]
    }

    # 2. Horarios más concurridos
    horarios_activas = ocurrencias.filter(estado=InscripcionOcurrencia.Estado.ACTIVA)
    WEEKDAYS_ES = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]

    if agrupar_horario == 'dia_hora':
        orden_horarios_prefix = '' if orden_horarios == 'asc' else '-'
        horarios_qs = (
            horarios_activas
            .annotate(hora=ExtractHour('fecha_clase'), dia=ExtractWeekDay('fecha_clase'))
            .values('dia', 'hora')
            .annotate(total=Count('id'))
            .order_by(f"{orden_horarios_prefix}total")[:10]
        )
        horarios_labels = []
        horarios_data = []
        for h in horarios_qs:
            dia_idx = h['dia'] - 1 if h['dia'] else 0
            dia_str = WEEKDAYS_ES[dia_idx]
            hora_str = f"{h['hora']:02d}:00"
            horarios_labels.append(f"{dia_str} {hora_str}")
            horarios_data.append(h['total'])
    else:
        orden_horarios_prefix = '' if orden_horarios == 'asc' else '-'
        horarios_qs = (
            horarios_activas
            .annotate(hora=ExtractHour('fecha_clase'))
            .values('hora')
            .annotate(total=Count('id'))
            .order_by(f"{orden_horarios_prefix}total")
        )
        horarios_labels = [f"{h['hora']:02d}:00" for h in horarios_qs if h['hora'] is not None]
        horarios_data = [h['total'] for h in horarios_qs if h['hora'] is not None]

    horarios_concurridos = {
        "labels": horarios_labels,
        "data": horarios_data
    }

    # 3. Dinero ganado
    pagos_qs = (
        pagos
        .values('periodo__nombre', 'periodo__fecha_inicio_periodo')
        .annotate(total=Sum('monto'))
        .order_by('periodo__fecha_inicio_periodo')
    )
    dinero_ganado = {
        "labels": [p['periodo__nombre'] for p in pagos_qs],
        "data": [float(p['total'] or 0) for p in pagos_qs]
    }

    # 4. Cancelaciones
    total_ocurrencias = ocurrencias.count()
    total_canceladas = ocurrencias.filter(estado=InscripcionOcurrencia.Estado.CANCELADA).count()
    total_activas = total_ocurrencias - total_canceladas

    cancelaciones = {
        "labels": ["Asistencias Activas", "Cancelaciones"],
        "data": [total_activas, total_canceladas]
    }

    # Summary Stats
    total_ingresos = pagos.aggregate(total=Sum('monto'))['total'] or 0

    sesiones = (
        ocurrencias.filter(estado=InscripcionOcurrencia.Estado.ACTIVA)
        .values('inscripcion__clase', 'fecha_clase')
        .annotate(cupo=F('inscripcion__clase__cupo_maximo'))
        .distinct()
    )
    cupo_total_periodo = sum(s['cupo'] for s in sesiones)
    total_sesiones = len(sesiones)
    
    ocupacion_promedio = (total_activas / cupo_total_periodo * 100) if cupo_total_periodo > 0 else 0
    ingreso_promedio = (total_ingresos / total_sesiones) if total_sesiones > 0 else 0

    return JsonResponse({
        "clases_concurridas": clases_concurridas,
        "horarios_concurridos": horarios_concurridos,
        "dinero_ganado": dinero_ganado,
        "cancelaciones": cancelaciones,
        "summary": {
            "total_ingresos": f"${total_ingresos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "total_cancelaciones": total_canceladas,
            "total_activas": total_activas,
            "ocupacion_promedio": f"{ocupacion_promedio:.1f}%".replace(".", ","),
            "ingreso_promedio": f"${ingreso_promedio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        }
    })
