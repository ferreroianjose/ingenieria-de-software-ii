from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = 'apps.payments'

    def ready(self):
        import sys
        
        # Avoid running in management commands like migrate, makemigrations, etc.
        if 'manage.py' in sys.argv and ('migrate' in sys.argv or 'makemigrations' in sys.argv or 'createsuperuser' in sys.argv):
            return
            
        from django_q.models import Schedule
        from django_q.tasks import async_task
        from django.db.utils import OperationalError, ProgrammingError
        
        try:
            # 1. Run the task once at startup (asynchronously)
            async_task('apps.payments.tasks.crear_siguiente_periodo_si_es_necesario')

            # 2. Schedule it to run daily if it doesn't exist
            if not Schedule.objects.filter(func='apps.payments.tasks.crear_siguiente_periodo_si_es_necesario').exists():
                Schedule.objects.create(
                    func='apps.payments.tasks.crear_siguiente_periodo_si_es_necesario',
                    schedule_type=Schedule.DAILY,
                    name='Crear siguiente periodo automaticamente',
                )
        except (OperationalError, ProgrammingError):
            # Database might not be fully set up yet
            pass
