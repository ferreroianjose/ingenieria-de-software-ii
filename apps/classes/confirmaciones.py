"""Textos del modal de confirmación (título = acción; cuerpo = mensaje específico)."""

from django.conf import settings
from django.utils import timezone


def _horas_minimas_credito_mensual():
    return getattr(settings, "CANCELACION_MENSUAL_HORAS_MIN", 48)


def etiqueta_horario_clase(clase):
    hora = clase.hora_inicio.strftime("%H:%M") if clase.hora_inicio else ""
    return (
        f"{clase.disciplina.nombre} - {clase.profesor.nombre} {clase.profesor.apellido} "
        f"- {clase.get_dia_semana_display()} {hora}"
    )


def mensaje_confirm_eliminar_clase(etiqueta):
    return f"¿Seguro que querés eliminar la clase «{etiqueta}»?"


def mensaje_confirm_eliminar_disciplina(nombre):
    return f"¿Seguro que querés eliminar la disciplina «{nombre}»?"


def mensaje_confirm_eliminar_profesor(nombre_completo):
    return f"¿Seguro que querés eliminar al profesor «{nombre_completo}»?"


def mensaje_confirm_eliminar_sede(nombre):
    return (
        f"¿Seguro que querés eliminar la sede «{nombre}»? "
        "También se eliminarán sus salas asociadas."
    )


def mensaje_confirm_eliminar_sala(nombre):
    return f"¿Seguro que querés eliminar la sala «{nombre}»?"


def mensaje_confirm_anular_inscripcion_impaga(inscripcion):
    from apps.classes.models import Inscripcion

    etiqueta = etiqueta_horario_clase(inscripcion.clase)
    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return (
            f"¿Seguro que querés anular la inscripción mensual de «{etiqueta}»? "
            "Liberás el cupo; no hay pagos que reintegrar."
        )
    return (
        f"¿Seguro que querés anular la inscripción de «{etiqueta}»? "
        "Liberás el cupo; no hay pagos que reintegrar."
    )


def acciones_anular_inscripcion_impaga(inscripcion):
    """Label y textos del modal para anular una inscripción PENDIENTE_PAGO."""
    from apps.classes.models import Inscripcion
    from apps.payments.inscripcion_pago import resumen_pago_inscripcion

    pago = resumen_pago_inscripcion(inscripcion)
    if (
        inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA
        and pago["mostrar_pagar_saldo"]
    ):
        return {
            "label": "Cancelar reserva",
            "confirm_title": "Cancelar reserva",
            "confirm_message": mensaje_confirm_cancelar_reserva_suelta(inscripcion),
            "confirm_label": "Sí, cancelar",
        }
    return {
        "label": "Anular inscripción",
        "confirm_title": "Anular inscripción",
        "confirm_message": mensaje_confirm_anular_inscripcion_impaga(inscripcion),
        "confirm_label": "Sí, anular",
    }


def mensaje_confirm_cancelar_reserva_suelta(inscripcion):
    etiqueta = etiqueta_horario_clase(inscripcion.clase)
    return (
        f"¿Seguro que querés cancelar la reserva de «{etiqueta}»? "
        "Con 24 h o más de anticipación se reintegra la seña; con menos tiempo queda retenida."
    )


def mensaje_confirm_salir_lista_espera(inscripcion):
    etiqueta = etiqueta_horario_clase(inscripcion.clase)
    return f"¿Seguro que querés salir de la lista de espera para «{etiqueta}»?"


def mensaje_confirm_cancelar_ocurrencia_mensual(inscripcion, fecha_clase, horas_restantes):
    etiqueta = etiqueta_horario_clase(inscripcion.clase)
    fecha_txt = timezone.localtime(fecha_clase).strftime("%d/%m/%Y %H:%M")
    minimo = _horas_minimas_credito_mensual()
    if horas_restantes is not None and horas_restantes >= minimo:
        return (
            f"¿Seguro que querés cancelar la clase «{etiqueta}» del {fecha_txt}? "
            "Recibirás un crédito para recuperarla en otro horario de la misma "
            "disciplina este mes."
        )
    return (
        f"¿Seguro que querés cancelar la clase «{etiqueta}» del {fecha_txt}? "
        f"Con menos de {minimo:g} h de anticipación la sesión se pierde "
        "(sin devolución de dinero)."
    )
