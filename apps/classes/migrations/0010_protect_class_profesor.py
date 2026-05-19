from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0009_protect_class_sala'),
    ]

    operations = [
        migrations.AlterField(
            model_name='class',
            name='profesor',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='classes.teacher',
            ),
        ),
    ]
