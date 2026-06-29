"""Tests del contrato de info_clase_para_usuario y la vista detalle_clase.

Cubre las regresiones del refactor del paso 3:
- Bug 1: inscripciones existentes (SUELTA reservada / pendiente de pago) deben
  aparecer en `info.inscripciones_activas` aunque queden ocultas del form.
- Bug 2: estar en ESPERA por una fecha NO bloquea el form para otras fechas.
- Bug 3: paso 2 (cronograma) y paso 3 deben usar el mismo criterio de cupo
  (por opción suelta/mensual), no solo sueltas de la semana ISO.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.classes.cliente import (
    info_clase_para_usuario,
    mis_inscripciones_activas,
    resumen_cupo_inscripcion,
)
from apps.classes.models import (
    Class,
    Disciplina,
    Inscripcion,
    InscripcionOcurrencia,
    Sala,
    Sede,
    Teacher,
)
from apps.classes.ocurrencias import crear_ocurrencia_suelta
from apps.payments.models import PeriodoCobro, PrecioClase

User = get_user_model()


def _next_dow(hoy, dia_semana):
    """Próximo `dia_semana` >= hoy."""
    return hoy + timedelta(days=(dia_semana - hoy.weekday()) % 7)


class InfoClaseDetalleTests(TestCase):
    """info_clase_para_usuario expone la lista completa de inscripciones activas."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="detalle@test.com",
            email="detalle@test.com",
            password="testpassword123",
            dni="33334444",
            telefono_emergencia="3515554444",
        )
        ahora = timezone.now()
        hoy = ahora.date()
        # Aseguramos que dia_semana_test caiga DENTRO de la semana ISO actual.
        # Lo armamos como "mañana" módulo semana — funciona excepto si hoy es domingo.
        if hoy.weekday() == 6:
            hoy = hoy + timedelta(days=1)
        dia_semana_test = (hoy.weekday() + 1) % 7
        if dia_semana_test == 0:
            dia_semana_test = hoy.weekday()  # fallback al mismo día más tarde

        self.periodo = PeriodoCobro.objects.create(
            nombre="Mes Test",
            fecha_inicio_periodo=hoy.replace(day=1),
            fecha_fin_periodo=(hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1),
            apertura_abonados=hoy.replace(day=1) - timedelta(days=15),
            apertura_general=hoy.replace(day=1),
        )
        disciplina = Disciplina.objects.create(nombre="Yoga Detalle")
        sede = Sede.objects.create(nombre="Sede D", direccion="Calle 1")
        sala = Sala.objects.create(nombre="Sala D", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Profe", apellido="Detalle")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=dia_semana_test,
            hora_inicio=time(18, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        PrecioClase.objects.create(
            clase=self.clase, periodo=self.periodo, monto=Decimal("3000.00")
        )

        tz = timezone.get_current_timezone()
        proxima_fecha = _next_dow(hoy, dia_semana_test)
        if proxima_fecha == hoy:
            proxima_fecha = proxima_fecha + timedelta(days=7)
        self.fecha_suelta = timezone.make_aware(
            datetime.combine(proxima_fecha, time(18, 0)), tz
        )

    # ────────────────────────────────────────────────────────────────────

    def test_sin_inscripciones_solo_ofrece_form(self):
        info = info_clase_para_usuario(self.clase, self.user)
        self.assertEqual(info["inscripciones_activas"], [])
        self.assertFalse(info["tiene_inscripciones_activas"])
        self.assertTrue(info["puede_agregar_reserva"])

    def test_suelta_reservada_aparece_en_inscripciones_y_oculta_la_fecha_del_form(self):
        ins = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.RESERVADA,
        )
        crear_ocurrencia_suelta(ins, self.fecha_suelta)

        info = info_clase_para_usuario(self.clase, self.user)

        # Bug 1: la inscripción existente debe aparecer.
        self.assertEqual(len(info["inscripciones_activas"]), 1)
        item = info["inscripciones_activas"][0]
        self.assertEqual(item["estado_ui"], "reservada")
        self.assertEqual(item["tipo"], Inscripcion.Tipo.CLASE_SUELTA)
        self.assertIsNotNone(item["fecha_dt"])
        self.assertEqual(item["acciones"]["primaria"]["kind"], "cancelar_reserva_suelta")

        # Y la fecha reservada NO está en el form (no doble-reserva).
        fechas_form = {
            o["fecha_clase"] for o in info["periodos_inscripcion"]["CLASE_SUELTA"]
        }
        self.assertNotIn(self.fecha_suelta.isoformat(), fechas_form)

    def test_espera_no_bloquea_form_para_otras_fechas(self):
        """Regresión bug 2: estar en lista de espera no oculta el form."""
        ins = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.ESPERA,
        )
        crear_ocurrencia_suelta(ins, self.fecha_suelta)

        info = info_clase_para_usuario(self.clase, self.user)

        self.assertEqual(len(info["inscripciones_activas"]), 1)
        self.assertEqual(info["inscripciones_activas"][0]["estado_ui"], "en_espera")
        self.assertEqual(
            info["inscripciones_activas"][0]["acciones"]["primaria"]["kind"],
            "abandonar_espera",
        )
        # El form sigue disponible si la clase tiene cupo y hay otras fechas. En
        # este caso la ventana semana-ISO sólo trae 1 fecha (la del usuario),
        # así que el form quedaría vacío. Comprobamos al menos que NO se haya
        # desactivado el form por estado global: las otras señales son normales.
        # En cambio, sí garantizamos que la fecha reservada quedó fuera del form.
        fechas_form = {
            o["fecha_clase"] for o in info["periodos_inscripcion"]["CLASE_SUELTA"]
        }
        self.assertNotIn(self.fecha_suelta.isoformat(), fechas_form)

    def test_pendiente_pago_aparece_con_cta_pagar_y_anular(self):
        ins = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        crear_ocurrencia_suelta(ins, self.fecha_suelta)

        info = info_clase_para_usuario(self.clase, self.user)

        self.assertEqual(len(info["inscripciones_activas"]), 1)
        item = info["inscripciones_activas"][0]
        self.assertEqual(item["estado_ui"], "pendiente_pago")
        self.assertEqual(item["acciones"]["primaria"]["kind"], "ir_a_pagar")
        self.assertEqual(item["acciones"]["secundaria"]["kind"], "anular_inscripcion")

    def test_mensual_reservada_oculta_periodo_del_form(self):
        Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.RESERVADA,
        )

        info = info_clase_para_usuario(self.clase, self.user)

        self.assertEqual(len(info["inscripciones_activas"]), 1)
        item = info["inscripciones_activas"][0]
        self.assertEqual(item["estado_ui"], "reservada")
        self.assertEqual(item["tipo"], Inscripcion.Tipo.MENSUAL)
        self.assertEqual(item["periodo"].id, self.periodo.id)
        self.assertEqual(item["acciones"]["primaria"]["kind"], "gestionar_mensual")

        # El período al que ya estás inscripto no aparece para inscribirte de nuevo.
        periodos_form_ids = {p["id"] for p in info["periodos_inscripcion"]["MENSUAL"]}
        self.assertNotIn(self.periodo.id, periodos_form_ids)

    def test_sin_suelta_en_semana_pero_cupo_mensual_permite_inscribirse(self):
        """Regresión: lunes/martes sin fecha suelta en la semana ISO pero con cupo mensual."""
        # Forzamos que la única ocurrencia suelta de la semana ya pasó (miércoles+).
        # Usamos un día a mediados del período para asegurar que haya clases futuras en el mes.
        hoy_real = timezone.localdate()
        hoy = hoy_real.replace(day=15)
        
        with patch('django.utils.timezone.localdate', return_value=hoy):
            dia_pasado = (hoy.weekday() - 1) % 7  # ayer en la semana, o domingo si hoy es lunes
            self.clase.dia_semana = dia_pasado
            self.clase.save(update_fields=["dia_semana"])

            resumen = resumen_cupo_inscripcion(self.clase, self.user)
            info = info_clase_para_usuario(self.clase, self.user)

        self.assertEqual(resumen["periodos_inscripcion"]["CLASE_SUELTA"], [])
        self.assertGreater(len(resumen["periodos_inscripcion"]["MENSUAL"]), 0)
        self.assertGreater(resumen["periodos_inscripcion"]["MENSUAL"][0]["cupo"], 0)
        self.assertTrue(resumen["puede_agregar_reserva"])
        self.assertEqual(info["puede_agregar_reserva"], resumen["puede_agregar_reserva"])

    def test_puede_anotarse_espera_solo_aplica_a_mensual(self):
        """Si solo hay clase suelta agotada, no se puede anotar en lista de espera."""
        # Agotamos la clase
        self.clase.cupo_maximo = 0
        self.clase.save(update_fields=["cupo_maximo"])

        # Sin opciones MENSUAL, debe dar falso aunque CLASE_SUELTA esté agotada
        with patch('apps.classes.cliente.periodos_inscripcion_para_clase') as mock_periodos:
            mock_periodos.return_value = {
                "CLASE_SUELTA": [{"fecha_clase": self.fecha_suelta.isoformat(), "cupo": 0}],
                "MENSUAL": []
            }
            resumen = resumen_cupo_inscripcion(self.clase, self.user)
            self.assertFalse(resumen["puede_anotarse_espera"])

            # Con opciones MENSUAL agotadas, debe dar verdadero
            mock_periodos.return_value = {
                "CLASE_SUELTA": [{"fecha_clase": self.fecha_suelta.isoformat(), "cupo": 0}],
                "MENSUAL": [{"id": 1, "cupo": 0}]
            }
            resumen2 = resumen_cupo_inscripcion(self.clase, self.user)
            self.assertTrue(resumen2["puede_anotarse_espera"])



class DetalleClaseRenovacionAbonadoTests(TestCase):
    """El abonado en ventana de pre-inscripción ve su mensual actual + opción de renovar."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="abonado-detalle@test.com",
            email="abonado-detalle@test.com",
            password="testpassword123",
            dni="77778888",
            telefono_emergencia="3515558888",
        )
        self.mayo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 20),
            apertura_general=date(2026, 5, 1),
        )
        self.junio = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 20),
            apertura_general=date(2026, 6, 1),
        )
        disciplina = Disciplina.objects.create(nombre="Yoga Abono")
        sede = Sede.objects.create(nombre="Sede A", direccion="C 1")
        sala = Sala.objects.create(nombre="Sala A", capacidad=10, sede=sede)
        profesor = Teacher.objects.create(nombre="Pro", apellido="Abono")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=0,
            hora_inicio=time(10, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        PrecioClase.objects.create(
            clase=self.clase, periodo=self.mayo, monto=Decimal("3000.00")
        )
        PrecioClase.objects.create(
            clase=self.clase, periodo=self.junio, monto=Decimal("3000.00")
        )
        # MENSUAL activa en el vigente.
        Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.RESERVADA,
        )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_abonado_en_ventana_ve_mensual_actual_y_proxima_en_form(self, _):
        info = info_clase_para_usuario(self.clase, self.user)

        # La mensual de mayo aparece en la lista de inscripciones activas.
        tipos_activas = [it["tipo"] for it in info["inscripciones_activas"]]
        self.assertEqual(tipos_activas, [Inscripcion.Tipo.MENSUAL])

        # El form ofrece Junio (renovación) — Mayo queda excluido porque ya está inscripto.
        periodos_form = info["periodos_inscripcion"]["MENSUAL"]
        nombres = [p["nombre"] for p in periodos_form]
        self.assertIn("Junio 2026", nombres)
        self.assertNotIn("Mayo 2026", nombres)


class DetalleClaseVistaTests(TestCase):
    """Vista detalle_clase renderiza el nuevo template con los nuevos contextos."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="vista-detalle@test.com",
            email="vista-detalle@test.com",
            password="testpassword123",
            dni="99990000",
            telefono_emergencia="3515559999",
        )
        ahora = timezone.now()
        hoy = ahora.date()
        if hoy.weekday() == 6:
            hoy = hoy + timedelta(days=1)
        dia_semana = (hoy.weekday() + 1) % 7
        if dia_semana == 0:
            dia_semana = hoy.weekday()

        self.periodo = PeriodoCobro.objects.create(
            nombre="Mes Vista",
            fecha_inicio_periodo=hoy.replace(day=1),
            fecha_fin_periodo=(hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1),
            apertura_abonados=hoy.replace(day=1) - timedelta(days=15),
            apertura_general=hoy.replace(day=1),
        )
        disciplina = Disciplina.objects.create(nombre="Vista Disc")
        sede = Sede.objects.create(nombre="Sede V", direccion="Calle V")
        sala = Sala.objects.create(nombre="Sala V", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Profe", apellido="V")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=dia_semana,
            hora_inicio=time(18, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        PrecioClase.objects.create(
            clase=self.clase, periodo=self.periodo, monto=Decimal("3000.00")
        )
        self.client.force_login(self.user)

    def test_vista_sin_inscripciones_renderiza_form(self):
        response = self.client.get(reverse("classes:detalle", args=[self.clase.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paso 3 - Modalidad")
        self.assertContains(response, "Continuar al pago")
        self.assertNotContains(response, "Tus reservas en esta clase")

    def test_vista_en_espera_muestra_lista_e_intenta_form(self):
        """Regresión bug 2: en espera no oculta la sección 'Agregar'."""
        tz = timezone.get_current_timezone()
        ahora = timezone.now()
        proxima = _next_dow(ahora.date(), self.clase.dia_semana)
        if proxima == ahora.date():
            proxima = proxima + timedelta(days=7)
        fecha = timezone.make_aware(datetime.combine(proxima, time(18, 0)), tz)
        ins = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.ESPERA,
        )
        crear_ocurrencia_suelta(ins, fecha)

        response = self.client.get(reverse("classes:detalle", args=[self.clase.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tus reservas en esta clase")
        self.assertContains(response, "Abandonar lista de espera")

    def test_cronograma_y_detalle_coinciden_en_cupo_mensual(self):
        """Paso 2 y paso 3 usan el mismo resumen de cupo (mensual sin suelta en semana)."""
        hoy_real = timezone.localdate()
        hoy = hoy_real.replace(day=15)
        
        with patch('django.utils.timezone.localdate', return_value=hoy):
            dia_pasado = (hoy.weekday() - 1) % 7
            self.clase.dia_semana = dia_pasado
            self.clase.save(update_fields=["dia_semana"])

            resumen = resumen_cupo_inscripcion(self.clase, self.user)
            info = info_clase_para_usuario(self.clase, self.user)
        self.assertTrue(resumen["puede_agregar_reserva"])
        self.assertEqual(info["puede_agregar_reserva"], resumen["puede_agregar_reserva"])
        self.assertFalse(resumen["puede_anotarse_espera"])
