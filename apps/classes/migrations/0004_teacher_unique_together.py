from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('classes', '0003_create_teacher'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='teacher',
            unique_together={('nombre', 'apellido')},
        ),
    ]
