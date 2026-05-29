# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_remove_pago_modalidad_pago_alter_pago_metodo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pago',
            name='usuario',
        ),
    ]
