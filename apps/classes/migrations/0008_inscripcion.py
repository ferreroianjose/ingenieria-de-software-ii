# Generated for feature/reservarClase — depends on 0007 (FK migration from listaDeClases)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0007_alter_class_to_foreignkey'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Inscripcion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_inscripcion', models.DateTimeField(auto_now_add=True)),
                ('estado', models.CharField(
                    choices=[
                        ('ESPERA', 'En lista de espera'),
                        ('RESERVADA', 'Reservada'),
                        ('PENDIENTE_PAGO', 'Pendiente de pago'),
                        ('CANCELADA', 'Cancelada'),
                    ],
                    default='RESERVADA',
                    max_length=20,
                )),
                ('clase', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inscripciones',
                    to='classes.class',
                )),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inscripciones',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['fecha_inscripcion'],
            },
        ),
    ]
