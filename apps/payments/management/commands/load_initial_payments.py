import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Carga periodos de cobro, precios, inscripciones de ejemplo y pagos (idempotente)."

    def handle(self, *args, **options):
        User = apps.get_model("users", "User")
        PeriodoCobro = apps.get_model("payments", "PeriodoCobro")
        PrecioClase = apps.get_model("payments", "PrecioClase")
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

        self._eliminar_periodos_legacy(PeriodoCobro, Inscripcion, data)

        periodos_por_nombre = self._load_periodos(PeriodoCobro, data)
        if not periodos_por_nombre:
            self.stdout.write(self.style.ERROR("No se cargó ningún período."))
            return

        periodo_default = self._periodo_default(periodos_por_nombre, data)
        precios_created = 0
        for meta in periodos_por_nombre.values():
            precios_created += self._load_precios(
                PrecioClase,
                Disciplina,
                meta["periodo"],
                data.get("precios_disciplina", []),
            )

        inscripciones_created = self._load_inscripciones(
            Inscripcion,
            User,
            Class,
            Disciplina,
            Sede,
            Sala,
            periodos_por_nombre,
            periodo_default,
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
            periodos_por_nombre,
            periodo_default,
            data.get("pagos", []),
        )
        creditos_created = self._load_creditos(
            Credito,
            User,
            Disciplina,
            periodos_por_nombre,
            periodo_default,
            data.get("creditos", []),
        )

        resumen_periodos = ", ".join(
            f"«{p.nombre}» ({periodos_por_nombre[p.nombre]['estado']})"
            for p in PeriodoCobro.objects.filter(
                nombre__in=periodos_por_nombre.keys()
            ).order_by("fecha_inicio_periodo")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Payments seed: {resumen_periodos}; "
                f"{precios_created} precios nuevos, {inscripciones_created} inscripciones, "
                f"{pagos_created} pagos, {creditos_created} créditos."
            )
        )

    def _parse_date(self, value):
        return date.fromisoformat(value)

    def _eliminar_periodos_legacy(self, PeriodoCobro, Inscripcion, data):
        for nombre in data.get("eliminar_periodos", ["Ciclo de cobro (desarrollo)"]):
            periodo = PeriodoCobro.objects.filter(nombre=nombre).first()
            if not periodo:
                continue
            if periodo.inscripciones.exists() or periodo.pago_set.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"  Período legacy «{nombre}» no se eliminó (tiene inscripciones)."
                    )
                )
                continue
            periodo.delete()
            self.stdout.write(
                self.style.WARNING(f"  Eliminado período legacy: {nombre}")
            )

    def _load_periodos(self, PeriodoCobro, data):
        """Carga periodos mensuales; conserva fechas del fixture (sin estirar a año completo)."""
        periodos_data = data.get("periodos")
        if not periodos_data and data.get("periodo"):
            periodos_data = [{**data["periodo"], "ajustar_fechas": True}]

        if not periodos_data:
            raise ValueError("Fixture must define periodos[] or periodo.")

        por_nombre = {}
        for row in periodos_data:
            nombre = row["nombre"]
            estado = row.get("estado", "")
            defaults = {
                "fecha_inicio_periodo": self._parse_date(row["fecha_inicio_periodo"]),
                "fecha_fin_periodo": self._parse_date(row["fecha_fin_periodo"]),
                "apertura_abonados": self._parse_date(row["apertura_abonados"]),
                "apertura_general": self._parse_date(row["apertura_general"]),
            }
            periodo, _ = PeriodoCobro.objects.update_or_create(
                nombre=nombre, defaults=defaults
            )

            if row.get("ajustar_fechas"):
                self._ajustar_periodo_a_hoy(periodo)

            por_nombre[nombre] = {"periodo": periodo, "estado": estado}
            self.stdout.write(
                f"  · {nombre}: {defaults['fecha_inicio_periodo']} → "
                f"{defaults['fecha_fin_periodo']} [{estado or 'sin etiqueta'}]"
            )

        return por_nombre

    def _ajustar_periodo_a_hoy(self, periodo):
        """Solo para el modo legacy de un único período de desarrollo."""
        today = timezone.now().date()
        if periodo.fecha_fin_periodo < today:
            periodo.fecha_fin_periodo = today + timedelta(days=180)
            periodo.save(update_fields=["fecha_fin_periodo"])
        if periodo.fecha_inicio_periodo > today:
            periodo.fecha_inicio_periodo = today - timedelta(days=30)
            periodo.save(update_fields=["fecha_inicio_periodo"])

    def _periodo_default(self, periodos_por_nombre, data):
        nombre = data.get("periodo_default")
        if nombre and nombre in periodos_por_nombre:
            return periodos_por_nombre[nombre]["periodo"]
        for meta in periodos_por_nombre.values():
            if meta.get("estado") == "activo":
                return meta["periodo"]
        return next(iter(periodos_por_nombre.values()))["periodo"]

    def _resolve_periodo(self, periodos_por_nombre, periodo_default, row):
        nombre = row.get("periodo")
        if nombre:
            meta = periodos_por_nombre.get(nombre)
            if not meta:
                raise ValueError(f"Período desconocido en fixture: {nombre!r}")
            return meta["periodo"]
        return periodo_default

    def _load_precios(self, PrecioClase, Disciplina, periodo, precios_data):
        created = 0
        for row in precios_data:
            disciplina = Disciplina.objects.get(nombre=row["disciplina"])
            clases = apps.get_model("classes", "Class").objects.filter(disciplina=disciplina)
            
            for clase in clases:
                _, was_created = PrecioClase.objects.update_or_create(
                    clase=clase,
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

    def _resolve_inscripcion(
        self, Inscripcion, User, Class, Disciplina, Sede, Sala, periodo, slot
    ):
        usuario = User.objects.get(email=slot["usuario_email"])
        clase = self._resolve_class(Class, Disciplina, Sede, Sala, slot)
        return (
            Inscripcion.objects.filter(
                usuario=usuario,
                clase=clase,
                periodo=periodo,
            )
            .exclude(estado=Inscripcion.Estado.CANCELADA)
            .first()
        )

    def _load_inscripciones(
        self,
        Inscripcion,
        User,
        Class,
        Disciplina,
        Sede,
        Sala,
        periodos_por_nombre,
        periodo_default,
        inscripciones_data,
    ):
        created = 0
        for row in inscripciones_data:
            periodo = self._resolve_periodo(periodos_por_nombre, periodo_default, row)
            usuario = User.objects.get(email=row["usuario_email"])
            clase = self._resolve_class(Class, Disciplina, Sede, Sala, row)

            if (
                Inscripcion.objects.filter(
                    usuario=usuario,
                    clase=clase,
                    periodo=periodo,
                )
                .exclude(estado=Inscripcion.Estado.CANCELADA)
                .exists()
            ):
                continue

            insc = Inscripcion.objects.create(
                usuario=usuario,
                clase=clase,
                periodo=periodo,
                tipo=row.get("tipo", Inscripcion.Tipo.CLASE_SUELTA),
                estado=row.get("estado", Inscripcion.Estado.PENDIENTE_PAGO),
            )
            created += 1

            # Auto-generate occurrences for the fixture
            if insc.tipo == Inscripcion.Tipo.MENSUAL:
                from apps.classes.ocurrencias import generar_ocurrencias_mensual
                generar_ocurrencias_mensual(insc)
            elif insc.tipo == Inscripcion.Tipo.CLASE_SUELTA:
                from apps.classes.ocurrencias import crear_ocurrencia_suelta
                from apps.classes.services import ocurrencias_clase_en_ventana
                fechas_v = ocurrencias_clase_en_ventana(clase)
                fechas = [dt for dt, p in fechas_v if p.id == periodo.id]
                if not fechas:
                    fechas = [dt for dt, p in fechas_v]
                if fechas:
                    # Target the first valid future date
                    crear_ocurrencia_suelta(insc, fechas[0])
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
        periodos_por_nombre,
        periodo_default,
        pagos_data,
    ):
        created = 0
        for row in pagos_data:
            periodo = self._resolve_periodo(periodos_por_nombre, periodo_default, row)
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

    def _load_creditos(
        self,
        Credito,
        User,
        Disciplina,
        periodos_por_nombre,
        periodo_default,
        creditos_data,
    ):
        created = 0
        for row in creditos_data:
            periodo = self._resolve_periodo(periodos_por_nombre, periodo_default, row)
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
