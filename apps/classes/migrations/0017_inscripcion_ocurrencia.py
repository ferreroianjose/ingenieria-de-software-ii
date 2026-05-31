from datetime import datetime, timedelta

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def _ocurrencias_mensual_en_periodo(clase, periodo, desde_fecha):
    if not clase.hora_inicio:
        return []
    inicio = max(periodo.fecha_inicio_periodo, desde_fecha)
    fin = periodo.fecha_fin_periodo
    if inicio > fin:
        return []
    tz = timezone.get_current_timezone()
    cursor = inicio + timedelta(days=(clase.dia_semana - inicio.weekday()) % 7)
    fechas = []
    while cursor <= fin:
        fechas.append(
            timezone.make_aware(datetime.combine(cursor, clase.hora_inicio), tz)
        )
        cursor += timedelta(days=7)
    return fechas


def _desde_fecha_cobro_mensual(periodo, hoy):
    if hoy < periodo.fecha_inicio_periodo:
        return periodo.fecha_inicio_periodo
    return hoy


def migrar_a_inscripcion_ocurrencia(apps, schema_editor):
    Inscripcion = apps.get_model("classes", "Inscripcion")
    InscripcionOcurrencia = apps.get_model("classes", "InscripcionOcurrencia")
    Class = apps.get_model("classes", "Class")
    PeriodoCobro = apps.get_model("payments", "PeriodoCobro")

    InscripcionOcurrencia.objects.all().update(estado="CANCELADA")

    for ins in Inscripcion.objects.filter(tipo="CLASE_SUELTA").exclude(
        fecha_clase__isnull=True
    ):
        estado = "CANCELADA" if ins.estado == "CANCELADA" else "ACTIVA"
        InscripcionOcurrencia.objects.update_or_create(
            inscripcion_id=ins.id,
            fecha_clase=ins.fecha_clase,
            defaults={"estado": estado, "otorga_credito": False},
        )

    hoy = timezone.localdate()
    for ins in Inscripcion.objects.filter(tipo="MENSUAL", estado="RESERVADA"):
        clase = Class.objects.get(pk=ins.clase_id)
        periodo = PeriodoCobro.objects.get(pk=ins.periodo_id)
        desde = _desde_fecha_cobro_mensual(periodo, hoy)
        canceladas = {
            oc.fecha_clase
            for oc in InscripcionOcurrencia.objects.filter(inscripcion_id=ins.id)
        }
        for fecha in _ocurrencias_mensual_en_periodo(clase, periodo, desde):
            if fecha in canceladas:
                continue
            InscripcionOcurrencia.objects.get_or_create(
                inscripcion_id=ins.id,
                fecha_clase=fecha,
                defaults={"estado": "ACTIVA", "otorga_credito": False},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0016_cancelacion_ocurrencia"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="CancelacionOcurrencia",
            new_name="InscripcionOcurrencia",
        ),
        migrations.RemoveConstraint(
            model_name="inscripcionocurrencia",
            name="uniq_cancelacion_inscripcion_fecha",
        ),
        migrations.AddConstraint(
            model_name="inscripcionocurrencia",
            constraint=models.UniqueConstraint(
                fields=("inscripcion", "fecha_clase"),
                name="uniq_inscripcion_ocurrencia_fecha",
            ),
        ),
        migrations.AddField(
            model_name="inscripcionocurrencia",
            name="estado",
            field=models.CharField(
                choices=[("ACTIVA", "Activa"), ("CANCELADA", "Cancelada")],
                default="CANCELADA",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="inscripcionocurrencia",
            name="credito",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ocurrencias_canceladas",
                to="payments.credito",
            ),
        ),
        migrations.RunPython(
            migrar_a_inscripcion_ocurrencia,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="inscripcion",
            name="fecha_clase",
        ),
        migrations.AlterField(
            model_name="inscripcionocurrencia",
            name="estado",
            field=models.CharField(
                choices=[("ACTIVA", "Activa"), ("CANCELADA", "Cancelada")],
                default="ACTIVA",
                max_length=20,
            ),
        ),
    ]
