from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0008_remove_class_inicio_class_dia_semana_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='class',
            name='sala',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='classes.sala',
            ),
        ),
    ]
