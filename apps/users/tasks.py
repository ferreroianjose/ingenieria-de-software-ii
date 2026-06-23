from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

User = get_user_model()


def clean_unverified_users():
    """
    Elimina los usuarios creados hace más de 48 horas
    cuya contraseña no haya sido establecida.
    Esta tarea se ejecuta periódicamente usando Django Q.
    """
    threshold_date = timezone.now() - timedelta(hours=48)

    users_to_delete = User.objects.filter(date_joined__lt=threshold_date)

    count = 0
    for user in users_to_delete:
        if not user.has_usable_password():
            user.delete()
            count += 1

    return f"{count} usuarios eliminados que no establecieron contraseña."
