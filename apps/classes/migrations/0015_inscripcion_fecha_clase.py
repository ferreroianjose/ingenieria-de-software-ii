from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classes", "0014_alter_inscripcion_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="inscripcion",
            name="fecha_clase",
            field=models.DateTimeField(
                blank=True,
                help_text="Fecha/hora concreta reservada (clase suelta).",
                null=True,
            ),
        ),
    ]
