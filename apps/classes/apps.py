from django.apps import AppConfig


class ClassesConfig(AppConfig):
    name = 'apps.classes'

    def ready(self):
        from django.db.models.signals import post_migrate

        from .scheduling import ensure_reconciliation_schedule

        post_migrate.connect(
            ensure_reconciliation_schedule,
            sender=self,
            dispatch_uid="classes.ensure_reconciliation_schedule",
        )
