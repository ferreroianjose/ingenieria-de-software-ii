# Simple migration to add ForeignKey fields to Class

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0006_sede_disciplina_sala'),
    ]

    operations = [
        migrations.AlterField(
            model_name='class',
            name='disciplina',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='classes.disciplina'),
        ),
        migrations.AlterField(
            model_name='class',
            name='sala',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='classes.sala'),
        ),
    ]
