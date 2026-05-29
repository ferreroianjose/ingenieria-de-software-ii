from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _poblar_usuario_desde_inscripcion(apps, schema_editor):
    Pago = apps.get_model("payments", "Pago")
    PagoInscripcion = apps.get_model("payments", "PagoInscripcion")
    for pago in Pago.objects.filter(usuario__isnull=True).iterator():
        detalle = (
            PagoInscripcion.objects.filter(pago_id=pago.pk)
            .select_related("inscripcion")
            .first()
        )
        if detalle:
            pago.usuario_id = detalle.inscripcion.usuario_id
            pago.save(update_fields=["usuario_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0003_remove_pago_usuario"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pago",
            name="usuario",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            _poblar_usuario_desde_inscripcion,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="pago",
            name="usuario",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
