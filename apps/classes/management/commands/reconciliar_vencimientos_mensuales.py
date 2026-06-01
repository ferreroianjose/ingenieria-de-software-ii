from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.classes.services import reconciliar_vencimientos_mensuales


class Command(BaseCommand):
    help = (
        "Cancela inscripciones mensuales impagas vencidas del período vigente "
        "y promueve la lista de espera."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fecha",
            type=str,
            help="Fecha de corte en formato YYYY-MM-DD (opcional).",
        )

    def handle(self, *args, **options):
        fecha_raw = options.get("fecha")
        fecha = None
        if fecha_raw:
            try:
                fecha = date.fromisoformat(fecha_raw)
            except ValueError as err:
                raise CommandError("Formato de --fecha inválido. Usá YYYY-MM-DD.") from err

        canceladas = reconciliar_vencimientos_mensuales(fecha=fecha)
        if canceladas == 0:
            self.stdout.write("Sin vencimientos mensuales para reconciliar.")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Se cancelaron {canceladas} inscripciones mensuales impagas y "
                "se promovió lista de espera."
            )
        )
