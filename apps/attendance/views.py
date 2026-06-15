from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
from datetime import date
import django.core.signing as signing

from apps.core.access import staff_required
from apps.users.models import User
from apps.classes.models import Inscripcion, InscripcionOcurrencia
from apps.attendance.models import Asistencia
from apps.payments.models import Pago, PagoInscripcion
from apps.payments.inscripcion_pago import resumen_pago_inscripcion, aplicar_pago_aprobado


@login_required
def generate_qr(request):
    """Retorna el fragmento del código QR o un JSON con el token nuevo para refresco."""
    signer = signing.TimestampSigner()
    token = signer.sign(str(request.user.id))
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={token}&margin=0&format=svg"

    if request.headers.get("accept") == "application/json" or request.GET.get("format") == "json":
        return JsonResponse({
            "qr_url": qr_url,
            "qr_token": token
        })

    return render(request, "partials/dashboards/_qr_code.html", {
        "qr_url": qr_url,
        "qr_token": token,
        "class": "size-full"
    })


@staff_required
def staff_asistencia(request):
    """Página principal del panel de administración/empleado para gestionar asistencia."""
    ATTENDANCE_VIEW_TABS = [
        {"id": "ingreso", "label": "Ingreso rápido"},
        {"id": "planillas", "label": "Planillas por clase"},
    ]

    from apps.classes.models import Class
    from apps.payments.models import PeriodoCobro
    from datetime import date
    clases_disponibles = Class.objects.filter(estado='disponible').select_related('disciplina', 'profesor')
    periodos = PeriodoCobro.objects.filter(fecha_inicio_periodo__lte=date.today()).order_by('-fecha_inicio_periodo')[:12]

    return render(request, "attendance/manage.html", {
        "page_section": "Control de Asistencia",
        "view_tabs": ATTENDANCE_VIEW_TABS,
        "clases_disponibles": clases_disponibles,
        "periodos": periodos,
        "initial_user_id": request.GET.get("user_id"),
    })


@staff_required
def buscar_cliente(request):
    """Endpoint HTMX para buscar clientes por nombre, apellido, DNI o email."""
    query = request.GET.get("q", "").strip()
    if not query:
        return render(request, "partials/attendance/_client_ready_state.html")

    clientes = User.objects.filter(
        rol="CLIENTE"
    ).filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(dni__icontains=query) |
        Q(email__icontains=query)
    )[:10]

    return render(request, "partials/attendance/_client_search_results.html", {
        "clientes": clientes
    })


def _calcular_edad(fecha_nacimiento):
    if not fecha_nacimiento:
        return None
    hoy = date.today()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )



def _get_client_detail_context(client_user, qr_token=None):
    # Calcular edad
    edad = _calcular_edad(client_user.fecha_nacimiento)
    es_menor = edad is not None and edad < 18

    # Verificar teléfono de emergencia
    tiene_telefono_emergencia = bool(
        client_user.telefono_emergencia and client_user.telefono_emergencia.strip()
    )

    # Clases/ocurrencias del día de hoy
    today = timezone.localdate()
    ocurrencias_hoy = InscripcionOcurrencia.objects.filter(
        inscripcion__usuario=client_user,
        fecha_clase__date=today,
        estado=InscripcionOcurrencia.Estado.ACTIVA
    ).select_related(
        "inscripcion__clase__disciplina",
        "inscripcion__clase__sala__sede",
        "inscripcion__clase__profesor"
    ).order_by("fecha_clase")

    # Enriquecer ocurrencias con datos de pago y asistencia
    ocurrencias_detalle = []
    for oc in ocurrencias_hoy:
        insc = oc.inscripcion
        resumen_pago = resumen_pago_inscripcion(insc)
        
        # Verificar si ya asistió hoy
        asistencias = Asistencia.objects.filter(
            inscripcion=insc,
            fecha_hora_ingreso__date=today
        ).order_by("fecha_hora_ingreso")
        
        ya_asistio = asistencias.exists()
        hora_asistencia = asistencias.first().fecha_hora_ingreso if ya_asistio else None

        ocurrencias_detalle.append({
            "ocurrencia": oc,
            "inscripcion": insc,
            "resumen_pago": resumen_pago,
            "ya_asistio": ya_asistio,
            "hora_asistencia": hora_asistencia,
        })

    return {
        "cliente": client_user,
        "edad": edad,
        "es_menor": es_menor,
        "tiene_telefono_emergencia": tiene_telefono_emergencia,
        "ocurrencias_detalle": ocurrencias_detalle,
        "today": today,
        "qr_used": bool(qr_token),
    }


@staff_required
def detalle_cliente_asistencia(request):
    """Retorna la ficha del cliente."""
    client_id = request.GET.get("user_id")
    qr_token = request.GET.get("qr_token")

    if qr_token:
        # Intentar descifrar token QR
        signer = signing.TimestampSigner()
        try:
            # Token válido por 5 minutos (300 segundos)
            client_id = signer.unsign(qr_token, max_age=300)
        except signing.SignatureExpired:
            error_message = "El código QR ha expirado. Por favor, solicitá uno nuevo."
        except signing.BadSignature:
            error_message = "Código QR inválido."
        
        if 'error_message' in locals():
            return render(request, "partials/attendance/_client_error.html", {
                "error_message": error_message
            })

    if not client_id:
        return HttpResponse("")

    client_user = get_object_or_404(User, id=client_id, rol="CLIENTE")
    context = _get_client_detail_context(client_user, qr_token)
    context["source"] = request.GET.get("source") or request.POST.get("source") or ""
    error_msg = request.GET.get("error_message") or ""
    context["error_message_from_scan"] = error_msg

    response = render(request, "partials/attendance/_client_detail.html", context)
    if error_msg:
        import json
        response['HX-Trigger'] = json.dumps({
            'adminFlash': {'message': error_msg, 'level': 'error'}
        })
    return response


import json
from apps.users.forms import ProfileUpdateForm

@staff_required
def cargar_telefono(request):
    user_id = request.GET.get("user_id") or request.POST.get("user_id")
    source = request.GET.get("source") or request.POST.get("source") or ""
    client_user = get_object_or_404(User, id=user_id, rol="CLIENTE")

    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, instance=client_user)
        if form.is_valid():
            form.save()
            context = _get_client_detail_context(client_user)
            context["source"] = source
            response = render(request, "partials/attendance/_client_detail.html", context)
            response['HX-Trigger'] = json.dumps({
                'closeAdminModal': 'emergencyPhoneModalOpen',
                'adminFlash': {'message': 'Teléfono de emergencia guardado exitosamente.', 'level': 'success'}
            })
            if source == 'dashboard':
                response['HX-Retarget'] = '#qr-modal-content'
            else:
                response['HX-Retarget'] = '#main-content-container'
            return response
    else:
        form = ProfileUpdateForm(instance=client_user)

    return render(
        request,
        "partials/attendance/_emergency_phone_modal_panel.html",
        {
            "modal_form": form,
            "cliente": client_user,
            "modal_title": "Cargar Teléfono de Emergencia",
            "modal_subtitle": f"Registrá el teléfono para {client_user.get_full_name()}",
            "modal_button_label": "Guardar",
            "action_url": f"{reverse('attendance:cargar_telefono')}?user_id={client_user.id}",
        }
    )


@staff_required
def registrar_asistencia(request):
    """Registra la asistencia para una inscripción y re-renderiza la ficha del cliente."""
    if request.method != "POST":
        return HttpResponse("Método no permitido", status=405)

    inscripcion_id = request.POST.get("inscripcion_id")
    metodo = request.POST.get("metodo", "MANUAL")
    
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id)

    # Validaciones estrictas de backend
    client_user = inscripcion.usuario
    edad = _calcular_edad(client_user.fecha_nacimiento)
    es_menor = edad is not None and edad < 18
    tiene_telefono_emergencia = bool(client_user.telefono_emergencia and client_user.telefono_emergencia.strip())

    if es_menor and client_user.estado_constancia != 'APROBADA':
        return HttpResponse("Asistencia bloqueada: El menor no tiene una constancia médica aprobada.", status=403)
    
    if not tiene_telefono_emergencia:
        return HttpResponse("Asistencia bloqueada: No se ha registrado un teléfono de emergencia.", status=403)

    resumen_pago = resumen_pago_inscripcion(inscripcion)
    if resumen_pago["mostrar_pagar"] or resumen_pago["mostrar_pagar_saldo"]:
        return HttpResponse("Asistencia bloqueada: El cliente registra deuda para esta inscripción.", status=403)

    # Evitar duplicados del mismo día
    today = timezone.localdate()
    ya_registrada = Asistencia.objects.filter(
        inscripcion=inscripcion,
        fecha_hora_ingreso__date=today
    ).exists()

    if not ya_registrada:
        Asistencia.objects.create(
            inscripcion=inscripcion,
            metodo=metodo,
            registrado_por=request.user
        )

    # Recargar el detalle del cliente directamente
    mutable_get = request.GET.copy()
    mutable_get["user_id"] = inscripcion.usuario_id
    request.GET = mutable_get
    return detalle_cliente_asistencia(request)


@staff_required
def anular_asistencia(request):
    """Anula la asistencia registrada para una inscripción en el día actual."""
    if request.method != "POST":
        return HttpResponse("Método no permitido", status=405)

    inscripcion_id = request.POST.get("inscripcion_id")
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id)

    today = timezone.localdate()
    Asistencia.objects.filter(
        inscripcion=inscripcion,
        fecha_hora_ingreso__date=today
    ).delete()

    # Recargar el detalle del cliente directamente
    mutable_get = request.GET.copy()
    mutable_get["user_id"] = inscripcion.usuario_id
    request.GET = mutable_get
    return detalle_cliente_asistencia(request)


@staff_required
def cobrar_efectivo_recepcion(request):
    """Registra un pago en efectivo por el saldo restante en recepción."""
    if request.method != "POST":
        return HttpResponse("Método no permitido", status=405)

    inscripcion_id = request.POST.get("inscripcion_id")
    monto_str = request.POST.get("monto")
    
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id)
    monto = Decimal(monto_str)

    # Crear Pago en efectivo
    pago = Pago.objects.create(
        usuario=inscripcion.usuario,
        periodo=inscripcion.periodo,
        monto=monto,
        metodo=Pago.Metodo.EFECTIVO,
        estado=Pago.Estado.COMPLETADO
    )

    # Crear Detalle PagoInscripcion
    PagoInscripcion.objects.create(
        pago=pago,
        inscripcion=inscripcion,
        monto_applied=monto
    )

    # Aplicar lógica de pago
    aplicar_pago_aprobado(pago)

    # Recargar el detalle del cliente directamente
    mutable_get = request.GET.copy()
    mutable_get["user_id"] = inscripcion.usuario_id
    request.GET = mutable_get
    return detalle_cliente_asistencia(request)


@staff_required
def aprobar_constancia_recepcion(request):
    """Marca la constancia de tutor del menor de edad como aprobada."""
    if request.method != "POST":
        return HttpResponse("Método no permitido", status=405)

    user_id = request.POST.get("user_id")
    cliente = get_object_or_404(User, id=user_id, rol="CLIENTE")
    
    cliente.estado_constancia = "APROBADA"
    cliente.save(update_fields=["estado_constancia"])

    # Recargar el detalle del cliente
    # Recargar el detalle del cliente directamente
    mutable_get = request.GET.copy()
    mutable_get["user_id"] = cliente.id
    request.GET = mutable_get
    return detalle_cliente_asistencia(request)


@staff_required
def deshacer_constancia_recepcion(request):
    """Marca la constancia de tutor del menor de edad como pendiente."""
    if request.method != "POST":
        return HttpResponse("Método no permitido", status=405)

    user_id = request.POST.get("user_id")
    cliente = get_object_or_404(User, id=user_id, rol="CLIENTE")
    
    cliente.estado_constancia = "PENDIENTE"
    cliente.save(update_fields=["estado_constancia"])

    mutable_get = request.GET.copy()
    mutable_get["user_id"] = cliente.id
    request.GET = mutable_get
    return detalle_cliente_asistencia(request)

from datetime import timedelta

def _get_planilla_context(class_id, periodo_id):
    from apps.classes.models import Class, Inscripcion
    from apps.payments.models import PeriodoCobro
    from apps.attendance.models import Asistencia

    if not class_id or not periodo_id:
        return None

    clase = get_object_or_404(Class, id=class_id)
    periodo = get_object_or_404(PeriodoCobro, id=periodo_id)

    # Calculate dates of the class in this period
    d = periodo.fecha_inicio_periodo
    end_date = periodo.fecha_fin_periodo
    class_dates = []
    
    # clase.dia_semana: 0=Lunes, ..., 6=Domingo
    while d <= end_date:
        if d.weekday() == clase.dia_semana:
            class_dates.append(d)
        d += timedelta(days=1)

    # Get active inscriptions for this class and period
    inscripciones = Inscripcion.objects.filter(
        clase=clase, 
        periodo=periodo,
        estado__in=[Inscripcion.Estado.RESERVADA, Inscripcion.Estado.PENDIENTE_PAGO]
    ).select_related('usuario').order_by('usuario__last_name', 'usuario__first_name')

    # Get attendance
    asistencias = Asistencia.objects.filter(
        inscripcion__in=inscripciones,
        fecha_hora_ingreso__date__gte=periodo.fecha_inicio_periodo,
        fecha_hora_ingreso__date__lte=periodo.fecha_fin_periodo
    ).values_list('inscripcion_id', 'fecha_hora_ingreso__date')
    
    asistencias_set = {(a[0], a[1]) for a in asistencias}

    matrix = []
    for insc in inscripciones:
        row = {
            'alumno': insc.usuario,
            'fechas': []
        }
        for dt in class_dates:
            row['fechas'].append({
                'date': dt,
                'asistio': (insc.id, dt) in asistencias_set,
            })
        matrix.append(row)

    return {
        "clase": clase,
        "periodo": periodo,
        "class_dates": class_dates,
        "matrix": matrix,
    }

@staff_required
def planilla_asistencia_grid(request):
    context = _get_planilla_context(request.GET.get('class_id'), request.GET.get('periodo_id'))
    if not context:
        return HttpResponse("Clase y período son requeridos.", status=400)
    return render(request, "partials/attendance/_planilla_grid.html", context)

@staff_required
def planilla_asistencia_print(request):
    context = _get_planilla_context(request.GET.get('class_id'), request.GET.get('periodo_id'))
    if not context:
        return HttpResponse("Clase y período son requeridos.", status=400)
    return render(request, "attendance/planilla_print.html", context)

from django.core.cache import cache

from django.views.decorators.cache import never_cache

@login_required
@never_cache
def qr_status_poll(request):
    """
    Endpoint de polling para el celular del cliente.
    Si hay un resultado en caché para el token dado, retorna un partial con el feedback.
    Si no hay resultado, retorna 204 No Content para seguir esperando.
    """
    qr_token = request.GET.get("token")
    if not qr_token:
        return HttpResponse(status=204)
    
    result = cache.get(f"qr_result_{qr_token}")
    if not result:
        return HttpResponse(status=204)
        
    # Borrar la caché para no mostrarlo de nuevo infinitamente
    cache.delete(f"qr_result_{qr_token}")
    
    return render(request, "partials/attendance/_qr_status_overlay.html", {"result": result})
