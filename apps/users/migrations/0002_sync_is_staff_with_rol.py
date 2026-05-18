from django.db import migrations


def sync_is_staff(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(rol="EMPLEADO").update(is_staff=False)
    User.objects.filter(rol="CLIENTE").update(is_staff=False)
    User.objects.filter(rol="ADMIN").update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sync_is_staff, migrations.RunPython.noop),
    ]
