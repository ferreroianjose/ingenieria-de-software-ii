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

    hoy = timezone.now()
    fecha_inicio = None

    if rango == 'este_mes':
        fecha_inicio = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif rango == 'ultimos_30':
        fecha_inicio = hoy - timedelta(days=30)
    elif rango == 'este_anio':
        fecha_inicio = hoy.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    # Base queries
    ocurrencias = InscripcionOcurrencia.objects.all()
    pagos = Pago.objects.filter(estado=Pago.Estado.COMPLETADO)

    if fecha_inicio:
        ocurrencias = ocurrencias.filter(fecha_clase__gte=fecha_inicio, fecha_clase__lte=hoy)
        pagos = pagos.filter(fecha_pago__gte=fecha_inicio, fecha_pago__lte=hoy)

    # 1. Clases más concurridas (Top 5)
    # Consideramos las asistencias 'ACTIVAS'
    concurridas_qs = (
        ocurrencias.filter(estado=InscripcionOcurrencia.Estado.ACTIVA)
        .values(nombre_disciplina=F('inscripcion__clase__disciplina__nombre'))
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )
    clases_concurridas = {
        "labels": [c['nombre_disciplina'] or 'Sin Disciplina' for c in concurridas_qs],
        "data": [c['total'] for c in concurridas_qs]
    }

    # 2. Horarios más concurridos
    horarios_activas = ocurrencias.filter(estado=InscripcionOcurrencia.Estado.ACTIVA)
    
    WEEKDAYS_ES = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]

    if agrupar_horario == 'dia_hora':
        # En Django, ExtractWeekDay retorna 1 (Domingo) a 7 (Sábado)
        horarios_qs = (
            horarios_activas
            .annotate(hora=ExtractHour('fecha_clase'), dia=ExtractWeekDay('fecha_clase'))
            .values('dia', 'hora')
            .annotate(total=Count('id'))
            .order_by('-total')[:10]  # Top 10 para no saturar si hay muchos
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
        horarios_qs = (
            horarios_activas
            .annotate(hora=ExtractHour('fecha_clase'))
            .values('hora')
            .annotate(total=Count('id'))
            .order_by('hora')
        )
        horarios_labels = [f"{h['hora']:02d}:00" for h in horarios_qs if h['hora'] is not None]
        horarios_data = [h['total'] for h in horarios_qs if h['hora'] is not None]

    horarios_concurridos = {
        "labels": horarios_labels,
        "data": horarios_data
    }

    # 3. Dinero ganado
    # Agrupamos por mes
    pagos_qs = (
        pagos
        .annotate(mes=TruncMonth('fecha_pago'))
        .values('mes')
        .annotate(total=Sum('monto'))
        .order_by('mes')
    )
    MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    
    dinero_ganado = {
        "labels": [f"{MESES_ES[p['mes'].month - 1]} {p['mes'].year}" for p in pagos_qs if p['mes']],
        "data": [float(p['total'] or 0) for p in pagos_qs if p['mes']]
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
    total_asistencias_activas = total_activas

    # Ocupación Promedio e Ingreso Promedio
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
