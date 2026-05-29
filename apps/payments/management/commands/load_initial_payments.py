import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Carga periodo de cobro, precios, inscripciones de ejemplo y pagos (idempotente)."

    def handle(self, *args, **options):
        User = apps.get_model("users", "User")
        PeriodoCobro = apps.get_model("payments", "PeriodoCobro")
        PrecioDisciplina = apps.get_model("payments", "PrecioDisciplina")
        Pago = apps.get_model("payments", "Pago")
        PagoInscripcion = apps.get_model("payments", "PagoInscripcion")
        Credito = apps.get_model("payments", "Credito")
        Class = apps.get_model("classes", "Class")
        Disciplina = apps.get_model("classes", "Disciplina")
        Sede = apps.get_model("classes", "Sede")
        Sala = apps.get_model("classes", "Sala")
        Inscripcion = apps.get_model("classes", "Inscripcion")

        payments_path = apps.get_app_config("payments").path
        fixtures_path = os.path.join(payments_path, "fixtures", "initial_payments.json")

        if not os.path.exists(fixtures_path):
            self.stdout.write(self.style.WARNING(f"Fixture not found: {fixtures_path}"))
            return

        with open(fixtures_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        periodo = self._load_periodo(PeriodoCobro, data.get("periodo", {}))
        precios_created = self._load_precios(
            PrecioDisciplina, Disciplina, periodo, data.get("precios_disciplina", [])
        )
        inscripciones_created = self._load_inscripciones(
            Inscripcion,
            User,
            Class,
            Disciplina,
            Sede,
            Sala,
            periodo,
            data.get("inscripciones", []),
        )
        pagos_created = self._load_pagos(
            Pago,
            PagoInscripcion,
            User,
            Inscripcion,
            Class,
            Disciplina,
            Sede,
            Sala,
            periodo,
            data.get("pagos", []),
        )
        creditos_created = self._load_creditos(
            Credito, User, Disciplina, periodo, data.get("creditos", [])
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Payments seed: periodo «{periodo.nombre}», "
                f"{precios_created} precios, {inscripciones_created} inscripciones, "
                f"{pagos_created} pagos, {creditos_created} créditos."
            )
        )

    def _parse_date(self, value):
        return date.fromisoformat(value)

    def _load_periodo(self, PeriodoCobro, periodo_data):
        if not periodo_data:
            raise ValueError("Fixture must define a periodo block.")

        nombre = periodo_data["nombre"]
        defaults = {
            "fecha_inicio_periodo": self._parse_date(periodo_data["fecha_inicio_periodo"]),
            "fecha_fin_periodo": self._parse_date(periodo_data["fecha_fin_periodo"]),
            "apertura_abonados": self._parse_date(periodo_data["apertura_abonados"]),
            "apertura_general": self._parse_date(periodo_data["apertura_general"]),
        }
        periodo, _ = PeriodoCobro.objects.update_or_create(nombre=nombre, defaults=defaults)

        today = timezone.now().date()
        if periodo.fecha_fin_periodo < today:
            periodo.fecha_fin_periodo = today + timedelta(days=180)
            periodo.save(update_fields=["fecha_fin_periodo"])
        if periodo.fecha_inicio_periodo > today:
            periodo.fecha_inicio_periodo = today - timedelta(days=30)
            periodo.save(update_fields=["fecha_inicio_periodo"])

        return periodo

    def _load_precios(self, PrecioDisciplina, Disciplina, periodo, precios_data):
        created = 0
        for row in precios_data:
            disciplina = Disciplina.objects.get(nombre=row["disciplina"])
            _, was_created = PrecioDisciplina.objects.update_or_create(
                disciplina=disciplina,
                periodo=periodo,
                defaults={"monto": Decimal(row["monto"])},
            )
            if was_created:
                created += 1
        return created

    def _parse_hora(self, hora_str):
        hora_parts = hora_str.split(":")
        return datetime.strptime(
            f"{int(hora_parts[0]):02d}:{int(hora_parts[1]):02d}",
            "%H:%M",
        ).time()

    def _resolve_class(self, Class, Disciplina, Sede, Sala, slot):
        disciplina = Disciplina.objects.get(nombre=slot["disciplina"])
        sede = Sede.objects.get(nombre=slot["sede"])
        sala = Sala.objects.get(nombre=slot["sala"], sede=sede)
        return Class.objects.get(
            disciplina=disciplina,
            sala=sala,
            dia_semana=int(slot["dia_semana"]),
            hora_inicio=self._parse_hora(slot["hora"]),
        )

    def _resolve_inscripcion(self, Inscripcion, User, Class, Disciplina, Sede, Sala, periodo, slot):
        usuario = User.objects.get(email=slot["usuario_email"])
        clase = self._resolve_class(Class, Disciplina, Sede, Sala, slot)
        return Inscripcion.objects.filter(
            usuario=usuario,
            clase=clase,
            periodo=periodo,
        ).exclude(estado=Inscripcion.Estado.CANCELADA).first()

    def _load_inscripciones(
        self, Inscripcion, User, Class, Disciplina, Sede, Sala, periodo, inscripciones_data
    ):
        created = 0
        for row in inscripciones_data:
            usuario = User.objects.get(email=row["usuario_email"])
            clase = self._resolve_class(Class, Disciplina, Sede, Sala, row)

            if Inscripcion.objects.filter(
                usuario=usuario,
                clase=clase,
                periodo=periodo,
            ).exclude(estado=Inscripcion.Estado.CANCELADA).exists():
                continue

            Inscripcion.objects.create(
                usuario=usuario,
                clase=clase,
                periodo=periodo,
                tipo=row.get("tipo", Inscripcion.Tipo.CLASE_SUELTA),
                estado=row.get("estado", Inscripcion.Estado.PENDIENTE_PAGO),
            )
            created += 1
        return created

    def _load_pagos(
        self,
        Pago,
        PagoInscripcion,
        User,
        Inscripcion,
        Class,
        Disciplina,
        Sede,
        Sala,
        periodo,
        pagos_data,
    ):
        created = 0
        for row in pagos_data:
            usuario = User.objects.get(email=row["usuario_email"])
            monto = Decimal(row["monto"])

            detalle_refs = row.get("inscripciones", [])
            if Pago.objects.filter(
                usuario=usuario,
                periodo=periodo,
                monto=monto,
                estado=row.get("estado", Pago.Estado.COMPLETADO),
                metodo=row.get("metodo", Pago.Metodo.MERCADOPAGO),
            ).exists():
                continue

            pago = Pago.objects.create(
                usuario=usuario,
                periodo=periodo,
                monto=monto,
                metodo=row.get("metodo", Pago.Metodo.MERCADOPAGO),
                estado=row.get("estado", Pago.Estado.COMPLETADO),
            )
            created += 1

            for ref in detalle_refs:
                slot = {**ref, "usuario_email": row["usuario_email"]}
                inscripcion = self._resolve_inscripcion(
                    Inscripcion, User, Class, Disciplina, Sede, Sala, periodo, slot
                )
                if not inscripcion:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Pago {pago.id}: inscripción no encontrada para {ref}"
                        )
                    )
                    continue

                monto_aplicado = Decimal(ref.get("monto_aplicado", monto))
                PagoInscripcion.objects.get_or_create(
                    pago=pago,
                    inscripcion=inscripcion,
                    defaults={"monto_aplicado": monto_aplicado},
                )
        return created

    def _load_creditos(self, Credito, User, Disciplina, periodo, creditos_data):
        created = 0
        for row in creditos_data:
            usuario = User.objects.get(email=row["usuario_email"])
            disciplina = Disciplina.objects.get(nombre=row["disciplina"])
            _, was_created = Credito.objects.get_or_create(
                usuario=usuario,
                periodo=periodo,
                disciplina=disciplina,
                defaults={"estado": row.get("estado", Credito.Estado.DISPONIBLE)},
            )
            if was_created:
                created += 1
        return created
