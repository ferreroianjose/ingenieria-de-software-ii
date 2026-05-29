from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.conf import settings
from decimal import Decimal
from datetime import timedelta, date, time
from unittest.mock import patch

from apps.classes.models import Sede, Sala, Teacher, Disciplina, Class, Inscripcion
from apps.payments.models import PeriodoCobro, PrecioDisciplina, Pago, PagoInscripcion

User = get_user_model()

class PaymentLogicTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        #
        # Configuración de tests
        #
 
        # Cliente
        self.user = User.objects.create_user(
            username='test@gymflow.com',
            email='test@gymflow.com',
            password='testpassword123',
            dni='12345678',
            first_name='Test',
            last_name='User'
        )
        self.client.login(username='test@gymflow.com', password='testpassword123')

        self.sede = Sede.objects.create(nombre="Sede Central", direccion="Calle Falsa 123")

        # Salas/Sedes/Clases
        self.sala = Sala.objects.create(nombre="Sala 1", capacidad=20, sede=self.sede)
        self.teacher = Teacher.objects.create(nombre="Juan", apellido="Perez")
        self.disciplina = Disciplina.objects.create(nombre="Crossfit")
        
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=self.sala,
            profesor=self.teacher,
            duracion=timedelta(hours=1),
            hora_inicio=time(10, 0),
            cupo_maximo=10
        )

        # Período
        self.periodo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 20),
            apertura_general=date(2026, 5, 1)
        )

        # Inscripción (clase suelta)
        self.inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.RESERVADA
        )

    @patch('apps.payments.views.mercadopago_service.create_preference')
    def test_pagar_inscripcion_fallback_price(self, mock_create_preference):
        # Sin PrecioDisciplina, cobra CLASE_DEFAULT_PRICE y redirige a MP.
        mock_create_preference.return_value = "http://mercadopago.mock/init"
        
        url = reverse('payments:pagar', args=[self.inscripcion.id])
        response = self.client.get(f"{url}?modalidad=TOTAL")
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://mercadopago.mock/init")

        pago = Pago.objects.last()
        self.assertIsNotNone(pago)
        
        expected_amount = Decimal(getattr(settings, "CLASE_DEFAULT_PRICE", "2500.0"))
        self.assertEqual(pago.monto, expected_amount)
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.PENDIENTE_PAGO)

    @patch('apps.payments.views.mercadopago_service.create_preference')
    def test_pagar_inscripcion_with_precio_disciplina(self, mock_create_preference):
        # Usa el monto de PrecioDisciplina para el período y la disciplina.
        mock_create_preference.return_value = "http://mercadopago.mock/init"
        
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('5000.00')
        )
        
        url = reverse('payments:pagar', args=[self.inscripcion.id])
        self.client.get(f"{url}?modalidad=TOTAL")
        
        pago = Pago.objects.last()
        self.assertEqual(pago.monto, Decimal('5000.00'))

    @patch('apps.payments.views.mercadopago_service.create_preference')
    def test_pagar_inscripcion_clase_suelta_sena(self, mock_create_preference):
        # No abonado con modalidad=SENA paga la seña (50%).
        mock_create_preference.return_value = "http://mercadopago.mock/init"

        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('4000.00')
        )
        
        url = reverse('payments:pagar', args=[self.inscripcion.id])
        self.client.get(f"{url}?modalidad=SENA")
        
        pago = Pago.objects.last()
        self.assertEqual(pago.monto, Decimal('2000.00'))

    @patch('apps.payments.views.mercadopago_service.create_preference')
    def test_pagar_inscripcion_mensual_ignores_sena(self, mock_create_preference):
        # Abonado (MENSUAL) no puede pagar seña: siempre cobra el 100%.
        mock_create_preference.return_value = "http://mercadopago.mock/init"
        
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('6000.00')
        )
        
        self.inscripcion.tipo = Inscripcion.Tipo.MENSUAL
        self.inscripcion.save()
        
        url = reverse('payments:pagar', args=[self.inscripcion.id])
        self.client.get(f"{url}?modalidad=SENA")
        
        pago = Pago.objects.last()
        self.assertEqual(pago.monto, Decimal('6000.00'))

    def test_success_callback_full_payment(self):
        # MP vuelve con approved y pago total: inscripción queda RESERVADA.
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('4000.00')
        )
        
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=Decimal('4000.00'),
            estado=Pago.Estado.PENDIENTE,
            metodo=Pago.Metodo.MERCADOPAGO
        )
        PagoInscripcion.objects.create(pago=pago, inscripcion=self.inscripcion, monto_aplicado=pago.monto)
        self.inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        self.inscripcion.save()

        url = reverse('payments:success', args=[pago.id])
        response = self.client.get(f"{url}?status=approved")
        
        pago.refresh_from_db()
        self.inscripcion.refresh_from_db()
        
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.RESERVADA)

    def test_success_callback_sena_payment(self):
        # MP approved pero solo se pagó seña: inscripción sigue PENDIENTE_PAGO.
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('4000.00')
        )
        
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=Decimal('2000.00'),
            estado=Pago.Estado.PENDIENTE,
            metodo=Pago.Metodo.MERCADOPAGO
        )
        PagoInscripcion.objects.create(pago=pago, inscripcion=self.inscripcion, monto_aplicado=pago.monto)
        self.inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        self.inscripcion.save()

        url = reverse('payments:success', args=[pago.id])
        response = self.client.get(f"{url}?status=approved")
        
        pago.refresh_from_db()
        self.inscripcion.refresh_from_db()
        
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.PENDIENTE_PAGO)

    @patch('apps.payments.views.mercadopago_service.create_preference')
    def test_pagar_inscripcion_creates_pago_inscripcion(self, mock_create_preference):
        # Al pagar, crea Pago + PagoInscripcion con el monto aplicado correcto.
        mock_create_preference.return_value = "http://mercadopago.mock/init"
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('5000.00'),
        )

        url = reverse('payments:pagar', args=[self.inscripcion.id])
        self.client.get(url)

        pago = Pago.objects.get(usuario=self.user)
        detalle = PagoInscripcion.objects.get(pago=pago)
        self.assertEqual(detalle.inscripcion, self.inscripcion)
        self.assertEqual(detalle.monto_aplicado, Decimal('5000.00'))
        self.assertEqual(pago.metodo, Pago.Metodo.MERCADOPAGO)

    @patch('apps.payments.views.mercadopago_service.create_preference')
    def test_pagar_inscripcion_mp_failure(self, mock_create_preference):
        # Si MP no devuelve init_point, avisa error y vuelve a mis reservas.
        mock_create_preference.return_value = None

        url = reverse('payments:pagar', args=[self.inscripcion.id])
        response = self.client.get(url)

        self.assertRedirects(
            response, reverse('classes:mis_reservas'), fetch_redirect_response=False
        )
        pago = Pago.objects.get(usuario=self.user)
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("Pago fallido por error al intentar conectar al servidor", messages[0])

    def test_pagar_inscripcion_requires_login(self):
        # Hay que estar logueado para iniciar un pago.
        self.client.logout()
        url = reverse('payments:pagar', args=[self.inscripcion.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)

    def test_pagar_inscripcion_other_user_returns_404(self):
        # No podés pagar la inscripción de otro cliente.
        other = User.objects.create_user(
            username='other@gymflow.com',
            email='other@gymflow.com',
            password='testpassword123',
            dni='99999999',
        )
        other_inscripcion = Inscripcion.objects.create(
            usuario=other,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
        )
        url = reverse('payments:pagar', args=[other_inscripcion.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_success_callback_rejected_status(self):
        # MP vuelve con rejected: el pago no se completa.
        pago = self._create_pending_pago(Decimal('4000.00'))
        url = reverse('payments:success', args=[pago.id])
        response = self.client.get(f"{url}?status=rejected")

        pago.refresh_from_db()
        self.inscripcion.refresh_from_db()
        self.assertRedirects(
            response, reverse('classes:mis_reservas'), fetch_redirect_response=False
        )
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("El pago no pudo ser completado.", messages[0])

    def test_success_callback_without_status(self):
        # Sin status en la URL, el pago sigue PENDIENTE.
        pago = self._create_pending_pago(Decimal('4000.00'))
        url = reverse('payments:success', args=[pago.id])
        response = self.client.get(url)

        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)

    def test_success_callback_collection_status_approved(self):
        # Acepta collection_status=approved (param legacy de MP).
        pago = self._create_pending_pago(Decimal('4000.00'))
        url = reverse('payments:success', args=[pago.id])
        self.client.get(f"{url}?collection_status=approved")

        pago.refresh_from_db()
        self.inscripcion.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.RESERVADA)

    def test_success_callback_multiple_inscriptions(self):
        # Un pago mensual con varias clases: todas quedan RESERVADA al aprobar.
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal('4000.00'),
        )
        clase_miercoles = Class.objects.create(
            disciplina=self.disciplina,
            sala=self.sala,
            profesor=self.teacher,
            dia_semana=2,
            duracion=timedelta(hours=1),
            hora_inicio=time(9, 0),
            cupo_maximo=10,
        )
        inscripcion_miercoles = Inscripcion.objects.create(
            usuario=self.user,
            clase=clase_miercoles,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=Decimal('8000.00'),
            estado=Pago.Estado.PENDIENTE,
            metodo=Pago.Metodo.MERCADOPAGO,
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=self.inscripcion,
            monto_aplicado=Decimal('4000.00'),
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=inscripcion_miercoles,
            monto_aplicado=Decimal('4000.00'),
        )
        self.inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        self.inscripcion.save()

        url = reverse('payments:success', args=[pago.id])
        self.client.get(f"{url}?status=approved")

        pago.refresh_from_db()
        self.inscripcion.refresh_from_db()
        inscripcion_miercoles.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.RESERVADA)
        self.assertEqual(inscripcion_miercoles.estado, Inscripcion.Estado.RESERVADA)

    def test_success_requires_login(self):
        # Hay que estar logueado para procesar el callback de success.
        pago = self._create_pending_pago(Decimal('4000.00'))
        self.client.logout()
        url = reverse('payments:success', args=[pago.id])
        response = self.client.get(f"{url}?status=approved")
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)

    def test_success_other_user_returns_404(self):
        # No podés confirmar el pago de otro cliente.
        pago = self._create_pending_pago(Decimal('4000.00'))
        other = User.objects.create_user(
            username='other2@gymflow.com',
            email='other2@gymflow.com',
            password='testpassword123',
            dni='88888888',
        )
        self.client.login(username='other2@gymflow.com', password='testpassword123')
        url = reverse('payments:success', args=[pago.id])
        response = self.client.get(f"{url}?status=approved")
        self.assertEqual(response.status_code, 404)

    def test_failure_marks_pago_as_fallido(self):
        # Callback failure de MP: pago pasa a FALLIDO.
        pago = self._create_pending_pago(Decimal('4000.00'))
        url = reverse('payments:failure', args=[pago.id])
        response = self.client.get(url)

        pago.refresh_from_db()
        self.assertRedirects(
            response, reverse('classes:mis_reservas'), fetch_redirect_response=False
        )
        self.assertEqual(pago.estado, Pago.Estado.FALLIDO)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("Pago fallido. Por favor intente nuevamente.", messages[0])

    def test_failure_requires_login(self):
        # Hay que estar logueado para procesar el callback de failure.
        pago = self._create_pending_pago(Decimal('4000.00'))
        self.client.logout()
        url = reverse('payments:failure', args=[pago.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)

    def test_failure_other_user_returns_404(self):
        # No podés marcar como fallido el pago de otro cliente.
        pago = self._create_pending_pago(Decimal('4000.00'))
        User.objects.create_user(
            username='other3@gymflow.com',
            email='other3@gymflow.com',
            password='testpassword123',
            dni='77777777',
        )
        self.client.login(username='other3@gymflow.com', password='testpassword123')
        url = reverse('payments:failure', args=[pago.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def _create_pending_pago(self, monto):
        PrecioDisciplina.objects.get_or_create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            defaults={'monto': monto},
        )
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=monto,
            estado=Pago.Estado.PENDIENTE,
            metodo=Pago.Metodo.MERCADOPAGO,
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=self.inscripcion,
            monto_aplicado=monto,
        )
        self.inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        self.inscripcion.save()
        return pago


class StaffPagosTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username='staff@gymflow.com',
            email='staff@gymflow.com',
            password='testpassword123',
            dni='11111111',
            rol='EMPLEADO',
        )
        self.client_user = User.objects.create_user(
            username='client@gymflow.com',
            email='client@gymflow.com',
            password='testpassword123',
            dni='22222222',
        )

    def test_staff_pagos_accessible_by_staff(self):
        # Empleado/admin puede entrar al panel de pagos.
        self.client.login(username='staff@gymflow.com', password='testpassword123')
        response = self.client.get(reverse('payments:manage'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'payments/manage.html')

    def test_staff_pagos_denied_for_client(self):
        # Cliente común no puede ver el panel de pagos.
        self.client.login(username='client@gymflow.com', password='testpassword123')
        response = self.client.get(reverse('payments:manage'))
        self.assertRedirects(response, reverse('dashboard'))
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("No tenés permiso para acceder a esta sección.", messages[0])


class MercadoPagoServiceTests(TestCase):
    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_charges_sum_of_line_items(self, mock_sdk_class):
        # Preferencia MP: un ítem por clase, el total cobrado es la suma de montos.
        from django.test import RequestFactory
        from apps.payments.services import MercadoPagoService

        user = User.objects.create_user(
            username="mp@test.com",
            email="mp@test.com",
            password="testpassword123",
            dni="87654321",
        )
        sede = Sede.objects.create(nombre="Sede MP", direccion="Calle 1")
        sala = Sala.objects.create(nombre="Sala MP", capacidad=20, sede=sede)
        teacher = Teacher.objects.create(nombre="Ana", apellido="Lopez")
        disciplina = Disciplina.objects.create(nombre="Yoga")
        periodo = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 20),
            apertura_general=date(2026, 6, 1),
        )
        clase_lunes = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=teacher,
            dia_semana=0,
            duracion=timedelta(hours=1),
            hora_inicio=time(9, 0),
            cupo_maximo=10,
        )
        clase_miercoles = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=teacher,
            dia_semana=2,
            duracion=timedelta(hours=1),
            hora_inicio=time(9, 0),
            cupo_maximo=10,
        )
        inscripcion_lunes = Inscripcion.objects.create(
            usuario=user,
            clase=clase_lunes,
            periodo=periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
        )
        inscripcion_miercoles = Inscripcion.objects.create(
            usuario=user,
            clase=clase_miercoles,
            periodo=periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
        )
        pago = Pago.objects.create(
            usuario=user,
            periodo=periodo,
            monto=Decimal("9000.00"),
            metodo=Pago.Metodo.MERCADOPAGO,
            estado=Pago.Estado.PENDIENTE,
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=inscripcion_lunes,
            monto_aplicado=Decimal("4000.00"),
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=inscripcion_miercoles,
            monto_aplicado=Decimal("5000.00"),
        )

        mock_sdk_class.return_value.preference.return_value.create.return_value = {
            "status": 201,
            "response": {"init_point": "http://mercadopago.mock/init"},
        }

        request = RequestFactory().get("/")
        init_point = MercadoPagoService().create_preference(pago, request)

        self.assertEqual(init_point, "http://mercadopago.mock/init")
        preference_data = (
            mock_sdk_class.return_value.preference.return_value.create.call_args[0][0]
        )
        items = preference_data["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["quantity"] == 1 for item in items))
        total = sum(item["quantity"] * item["unit_price"] for item in items)
        self.assertEqual(total, float(pago.monto))

    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_raises_without_detalles(self, mock_sdk_class):
        # Pago sin PagoInscripcion: no se puede crear preferencia.
        from django.test import RequestFactory
        from apps.payments.services import MercadoPagoService

        user = User.objects.create_user(
            username="empty@test.com",
            email="empty@test.com",
            password="testpassword123",
            dni="00000001",
        )
        periodo = PeriodoCobro.objects.create(
            nombre="Julio 2026",
            fecha_inicio_periodo=date(2026, 7, 1),
            fecha_fin_periodo=date(2026, 7, 31),
            apertura_abonados=date(2026, 6, 20),
            apertura_general=date(2026, 7, 1),
        )
        pago = Pago.objects.create(
            usuario=user,
            periodo=periodo,
            monto=Decimal("1000.00"),
            metodo=Pago.Metodo.MERCADOPAGO,
        )
        request = RequestFactory().get("/")

        with self.assertRaises(ValueError):
            MercadoPagoService().create_preference(pago, request)

        mock_sdk_class.return_value.preference.return_value.create.assert_not_called()

    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_returns_none_on_sdk_error(self, mock_sdk_class):
        # Si la API de MP falla, devuelve None (no init_point).
        from django.test import RequestFactory
        from apps.payments.services import MercadoPagoService

        pago, request = self._build_single_item_pago()
        mock_sdk_class.return_value.preference.return_value.create.side_effect = Exception(
            "MP down"
        )

        init_point = MercadoPagoService().create_preference(pago, request)
        self.assertIsNone(init_point)

    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_includes_back_urls_and_external_reference(
        self, mock_sdk_class
    ):
        # La preferencia incluye back_urls, external_reference y email del pagador.
        from apps.payments.services import MercadoPagoService

        pago, request = self._build_single_item_pago()
        mock_sdk_class.return_value.preference.return_value.create.return_value = {
            "status": 201,
            "response": {"init_point": "http://mercadopago.mock/init"},
        }

        MercadoPagoService().create_preference(pago, request)
        preference_data = (
            mock_sdk_class.return_value.preference.return_value.create.call_args[0][0]
        )

        self.assertEqual(preference_data["external_reference"], str(pago.id))
        self.assertEqual(preference_data["payer"]["email"], pago.usuario.email)
        self.assertEqual(preference_data["items"][0]["currency_id"], "ARS")
        self.assertIn("success", preference_data["back_urls"])
        self.assertIn("failure", preference_data["back_urls"])
        self.assertIn("pending", preference_data["back_urls"])
        self.assertIn(f"/payments/pago/{pago.id}/success/", preference_data["back_urls"]["success"])
        self.assertIn(f"/payments/pago/{pago.id}/failure/", preference_data["back_urls"]["failure"])
        self.assertNotIn("auto_return", preference_data)

    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_uses_sandbox_init_point_when_debug(self, mock_sdk_class):
        # Credenciales de prueba: redirigir al checkout sandbox, no al de producción.
        from django.test import RequestFactory, override_settings
        from apps.payments.services import MercadoPagoService

        pago, request = self._build_single_item_pago()
        mock_sdk_class.return_value.preference.return_value.create.return_value = {
            "status": 201,
            "response": {
                "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=x",
                "sandbox_init_point": "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=x",
            },
        }

        with override_settings(DEBUG=True):
            init_point = MercadoPagoService().create_preference(pago, request)

        self.assertEqual(
            init_point,
            "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?pref_id=x",
        )

    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_omits_auto_return_on_localhost(self, mock_sdk_class):
        # En desarrollo (http://localhost) MP rechaza auto_return; no lo enviamos.
        from django.test import RequestFactory
        from apps.payments.services import MercadoPagoService

        pago, request = self._build_single_item_pago()
        request.META["HTTP_HOST"] = "localhost:8000"
        mock_sdk_class.return_value.preference.return_value.create.return_value = {
            "status": 201,
            "response": {"init_point": "http://mercadopago.mock/init"},
        }

        init_point = MercadoPagoService().create_preference(pago, request)

        self.assertEqual(init_point, "http://mercadopago.mock/init")
        preference_data = (
            mock_sdk_class.return_value.preference.return_value.create.call_args[0][0]
        )
        self.assertNotIn("auto_return", preference_data)

    @patch("apps.payments.services.mercadopago.SDK")
    def test_create_preference_returns_none_on_api_error_response(self, mock_sdk_class):
        # Respuesta 400 de MP sin excepción → None (vuelve a mis reservas).
        from django.test import RequestFactory
        from apps.payments.services import MercadoPagoService

        pago, request = self._build_single_item_pago()
        mock_sdk_class.return_value.preference.return_value.create.return_value = {
            "status": 400,
            "response": {"message": "invalid request"},
        }

        init_point = MercadoPagoService().create_preference(pago, request)
        self.assertIsNone(init_point)

    def _build_single_item_pago(self):
        from django.test import RequestFactory

        user = User.objects.create_user(
            username="single@test.com",
            email="single@test.com",
            password="testpassword123",
            dni="00000002",
        )
        sede = Sede.objects.create(nombre="Sede Single", direccion="Calle 2")
        sala = Sala.objects.create(nombre="Sala Single", capacidad=10, sede=sede)
        teacher = Teacher.objects.create(nombre="Lu", apellido="Garcia")
        disciplina = Disciplina.objects.create(nombre="Pilates")
        periodo = PeriodoCobro.objects.create(
            nombre="Agosto 2026",
            fecha_inicio_periodo=date(2026, 8, 1),
            fecha_fin_periodo=date(2026, 8, 31),
            apertura_abonados=date(2026, 7, 20),
            apertura_general=date(2026, 8, 1),
        )
        clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=teacher,
            dia_semana=4,
            duracion=timedelta(hours=1),
            hora_inicio=time(18, 0),
            cupo_maximo=10,
        )
        inscripcion = Inscripcion.objects.create(
            usuario=user,
            clase=clase,
            periodo=periodo,
        )
        pago = Pago.objects.create(
            usuario=user,
            periodo=periodo,
            monto=Decimal("3500.00"),
            metodo=Pago.Metodo.MERCADOPAGO,
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=inscripcion,
            monto_aplicado=Decimal("3500.00"),
        )
        request = RequestFactory().get("/")
        return pago, request
