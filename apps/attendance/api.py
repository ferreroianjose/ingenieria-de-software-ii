import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
import django.core.signing as signing
from django.utils import timezone

from apps.core.access import staff_required
from apps.users.models import User
from apps.classes.models import InscripcionOcurrencia
from apps.attendance.models import Asistencia
from apps.payments.inscripcion_pago import resumen_pago_inscripcion
from apps.attendance.views import _calcular_edad

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@staff_required
@require_POST
def api_qr_scan(request):
    try:
        data = json.loads(request.body)
        qr_token = data.get("qr_token")
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "JSON inválido"}, status=400)

    if not qr_token:
        return JsonResponse({"status": "error", "message": "Token requerido"}, status=400)

    signer = signing.TimestampSigner()
    try:
        # Token expira en 5 minutos
        client_id = signer.unsign(qr_token, max_age=300)
    except signing.SignatureExpired:
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": "El código QR ha expirado."}, timeout=30)
        return JsonResponse({"status": "error", "message": "El código QR ha expirado."}, status=400)
    except signing.BadSignature:
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": "Código QR inválido."}, timeout=30)
        return JsonResponse({"status": "error", "message": "Código QR inválido."}, status=400)

    try:
        client_user = User.objects.get(id=client_id, rol="CLIENTE")
    except User.DoesNotExist:
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": "Cliente no encontrado."}, timeout=30)
        return JsonResponse({"status": "error", "message": "Cliente no encontrado."}, status=404)

    # Buscar clases del día de hoy
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

    if not ocurrencias_hoy.exists():
        msg = "El cliente no tiene clases programadas para el día de hoy."
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": msg}, timeout=30)
        return JsonResponse({
            "status": "manual_action_required",
            "message": msg,
            "user_id": client_user.id
        })

    # Determinar la clase más próxima (en base a la hora actual)
    now_time = timezone.localtime().time()
    
    mejor_ocurrencia = None
    menor_diferencia = None

    for oc in ocurrencias_hoy:
        clase_hora = oc.inscripcion.clase.hora_inicio
        # Calcular diferencia en minutos (ignorando si fue hace un rato o es en el futuro)
        diff = abs((clase_hora.hour * 60 + clase_hora.minute) - (now_time.hour * 60 + now_time.minute))
        if menor_diferencia is None or diff < menor_diferencia:
            menor_diferencia = diff
            mejor_ocurrencia = oc

    oc = mejor_ocurrencia
    inscripcion = oc.inscripcion
    
    edad = _calcular_edad(client_user.fecha_nacimiento)
    es_menor = edad is not None and edad < 18
    tiene_telefono_emergencia = bool(client_user.telefono_emergencia and client_user.telefono_emergencia.strip())

    if es_menor and client_user.estado_constancia != 'APROBADA':
        msg = "Menor de edad con autorización del tutor pendiente de aprobación."
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": msg}, timeout=30)
        return JsonResponse({
            "status": "manual_action_required",
            "message": msg,
            "user_id": client_user.id
        })
    
    if not tiene_telefono_emergencia:
        msg = "Falta cargar el teléfono de emergencia obligatorio para ingresar."
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": msg}, timeout=30)
        return JsonResponse({
            "status": "manual_action_required",
            "message": msg,
            "user_id": client_user.id
        })

    resumen_pago = resumen_pago_inscripcion(inscripcion)
    if resumen_pago["mostrar_pagar"] or resumen_pago["mostrar_pagar_saldo"]:
        msg = f"El cliente posee cuotas o matrículas vencidas para la clase de {inscripcion.clase.disciplina.nombre}."
        cache.set(f"qr_result_{qr_token}", {"status": "error", "message": msg}, timeout=30)
        return JsonResponse({
            "status": "manual_action_required",
            "message": msg,
            "user_id": client_user.id
        })

    # Verificar si ya asistió
    ya_registrada = Asistencia.objects.filter(
        inscripcion=inscripcion,
        fecha_hora_ingreso__date=today
    ).exists()

    clase_nombre = f"{inscripcion.clase.disciplina.nombre}"
    
    if ya_registrada:
        cache.set(f"qr_result_{qr_token}", {
            "status": "success", 
            "message": "Ya habías ingresado", 
            "class_name": clase_nombre
        }, timeout=30)
        return JsonResponse({
            "status": "success", 
            "message": "Ya ingresó", 
            "client_name": client_user.first_name, 
            "class_name": clase_nombre
        })

    # Registrar asistencia
    Asistencia.objects.create(
        inscripcion=inscripcion,
        metodo="QR_SCANNER",
        registrado_por=request.user
    )

    cache.set(f"qr_result_{qr_token}", {
        "status": "success", 
        "message": "¡Adelante!", 
        "class_name": clase_nombre
    }, timeout=30)

    return JsonResponse({
        "status": "success", 
        "message": "Asistencia registrada", 
        "client_name": client_user.first_name, 
        "class_name": clase_nombre
    })
