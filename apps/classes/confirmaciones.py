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
