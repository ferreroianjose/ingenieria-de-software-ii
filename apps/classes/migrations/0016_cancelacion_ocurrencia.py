import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0015_inscripcion_fecha_clase"),
        ("payments", "0004_pago_usuario"),
    ]

    operations = [
        migrations.CreateModel(
            name="CancelacionOcurrencia",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("fecha_clase", models.DateTimeField()),
                ("otorga_credito", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "credito",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cancelaciones",
                        to="payments.credito",
                    ),
                ),
                (
                    "inscripcion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cancelaciones",
                        to="classes.inscripcion",
                    ),
                ),
            ],
            options={
                "ordering": ["fecha_clase"],
            },
        ),
        migrations.AddConstraint(
            model_name="cancelacionocurrencia",
            constraint=models.UniqueConstraint(
                fields=("inscripcion", "fecha_clase"),
                name="uniq_cancelacion_inscripcion_fecha",
            ),
        ),
    ]
