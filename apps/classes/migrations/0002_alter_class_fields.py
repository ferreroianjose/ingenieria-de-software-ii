from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='class',
            old_name='cupo',
            new_name='cupo_maximo',
        ),
        migrations.AlterField(
            model_name='class',
            name='disciplina',
            field=models.CharField(choices=[('Funcional', 'Funcional'), ('Pilates', 'Pilates'), ('Yoga', 'Yoga')], max_length=100),
        ),
        migrations.AlterField(
            model_name='class',
            name='sala',
            field=models.CharField(choices=[('A', 'A'), ('B', 'B')], max_length=100),
        ),
        migrations.AlterField(
            model_name='class',
            name='cupo_maximo',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name='class',
            name='estado',
            field=models.CharField(choices=[('disponible', 'Disponible'), ('pausada', 'Pausada')], default='disponible', max_length=20),
        ),
    ]
