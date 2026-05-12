from django.db import migrations
from django.contrib.auth.hashers import make_password

def create_initial_users(apps, schema_editor):
    User = apps.get_model('users', 'User')
    
    users_to_create = [
        {
            "email": "laura@gymflow.com",
            "username": "laura@gymflow.com",
            "password": make_password("laura123"),
            "is_superuser": True,
            "is_staff": True,
            "rol": "ADMIN",
            "dni": "00000000",
            "first_name": "Laura",
            "last_name": "Ibarra",
            "fecha_nacimiento": "1985-03-15",
            "estado_constancia": "APROBADA"
        },
        {
            "email": "jose@gymflow.com",
            "username": "jose@gymflow.com",
            "password": make_password("jose123"),
            "is_superuser": True,
            "is_staff": True,
            "rol": "ADMIN",
            "dni": "00000001",
            "first_name": "José",
            "last_name": "Mckenzie",
            "fecha_nacimiento": "1988-07-22",
            "estado_constancia": "APROBADA"
        },
        {
            "email": "empleado@gymflow.com",
            "username": "empleado@gymflow.com",
            "password": make_password("empleado123"),
            "is_superuser": False,
            "is_staff": True,
            "rol": "EMPLEADO",
            "dni": "11111111",
            "first_name": "Empleado",
            "last_name": "Uno",
            "fecha_nacimiento": "1995-11-02",
            "estado_constancia": "APROBADA"
        },
        {
            "email": "enrique@mail.com",
            "username": "enrique@mail.com",
            "password": make_password("enrique123"),
            "is_superuser": False,
            "is_staff": False,
            "rol": "CLIENTE",
            "dni": "22222222",
            "first_name": "Enrique",
            "last_name": "Gonzales",
            "fecha_nacimiento": "2002-05-10",
            "estado_constancia": "APROBADA"
        },
        {
            "email": "guadalupe@mail.com",
            "username": "guadalupe@mail.com",
            "password": make_password("guadalupe123"),
            "is_superuser": False,
            "is_staff": False,
            "rol": "CLIENTE",
            "dni": "22222223",
            "first_name": "Guadalupe",
            "last_name": "Figueroa",
            "fecha_nacimiento": "2005-09-30",
            "estado_constancia": "PENDIENTE"
        }
    ]

    for user_data in users_to_create:
        if not User.objects.filter(email=user_data["email"]).exists():
            User.objects.create(**user_data)

def remove_initial_users(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(email__in=[
        "laura@gymflow.com",
        "jose@gymflow.com",
        "empleado@gymflow.com",
        "enrique@mail.com",
        "guadalupe@mail.com"
    ]).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_users, remove_initial_users),
    ]
