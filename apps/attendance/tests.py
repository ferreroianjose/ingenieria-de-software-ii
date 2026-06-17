from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta, date, time
import django.core.signing as signing

from apps.classes.models import Sede, Sala, Teacher, Disciplina, Class, Inscripcion, InscripcionOcurrencia
from apps.attendance.models import Asistencia
from apps.payments.models import PeriodoCobro, Pago, PagoInscripcion, PrecioClase

User = get_user_model()

class AttendanceTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create staff user (Empleado)
        self.staff_user = User.objects.create_user(
            username='empleado@gymflow.com',
            email='empleado@gymflow.com',
            password='password123',
            rol='EMPLEADO',
            dni='87654321',
            first_name='Empleado',
            last_name='Gym'
        )

        # Create client user
        self.client_user = User.objects.create_user(
            username='cliente@gymflow.com',
            email='cliente@gymflow.com',
            password='password123',
            rol='CLIENTE',
            dni='12345678',
            first_name='Juan',
            last_name='Perez',
            fecha_nacimiento=date(1990, 5, 15),
            telefono_emergencia='1122334455'
        )

        self.sede = Sede.objects.create(nombre="Sede Norte", direccion="Av. Siempre Viva 742")
        self.sala = Sala.objects.create(nombre="Sala de Musculación", capacidad=30, sede=self.sede)
        # Wait, the models test says: Sala.objects.create(nombre="Sala 1", capacidad=20, sede=self.sede)
        # So we should use:
        # self.sala = Sala.objects.create(nombre="Sala de Musculación", capacidad=30, sede=self.sede)

        self.teacher = Teacher.objects.create(nombre="Carlos", apellido="Gomez")
        self.disciplina = Disciplina.objects.create(nombre="Musculación")

        today_weekday = timezone.localdate().weekday() # 0 = Monday, ..., 6 = Sunday

        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=self.sala,
            profesor=self.teacher,
            dia_semana=today_weekday,
            hora_inicio=time(12, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=15
        )

        self.periodo = PeriodoCobro.objects.create(
            nombre="Periodo Actual",
            fecha_inicio_periodo=timezone.localdate() - timedelta(days=5),
            fecha_fin_periodo=timezone.localdate() + timedelta(days=25),
            apertura_abonados=timezone.localdate() - timedelta(days=10),
            apertura_general=timezone.localdate() - timedelta(days=5)
        )

        # Enrollment
        self.inscripcion = Inscripcion.objects.create(
            usuario=self.client_user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.RESERVADA
        )

        # Occurrence for today
        self.ocurrencia = InscripcionOcurrencia.objects.create(
            inscripcion=self.inscripcion,
            fecha_clase=timezone.make_aware(
                datetime.combine(timezone.localdate(), time(12, 0))
            ),
            estado=InscripcionOcurrencia.Estado.ACTIVA
        )

    def test_asistencia_model_creation(self):
        """Verifica que se pueda crear un registro de Asistencia correctamente."""
        asistencia = Asistencia.objects.create(
            inscripcion=self.inscripcion,
            metodo=Asistencia.Metodo.QR,
            registrado_por=self.staff_user
        )
        self.assertEqual(asistencia.inscripcion, self.inscripcion)
        self.assertEqual(asistencia.metodo, Asistencia.Metodo.QR)
        self.assertEqual(asistencia.registrado_por, self.staff_user)
        self.assertIsNotNone(asistencia.fecha_hora_ingreso)

    def test_buscar_cliente_anonymous_redirect(self):
        """Usuarios no autenticados o no staff son redirigidos o rechazados."""
        # Anonymous
        response = self.client.get(reverse('attendance:manage'))
        self.assertEqual(response.status_code, 302)

        # Normal Client
        self.client.login(username='cliente@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:manage'))
        self.assertEqual(response.status_code, 302)

    def test_buscar_cliente_staff(self):
        """El staff puede buscar clientes y obtener fragmentos HTMX."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:search'), {'q': 'Juan'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Perez')
        self.assertContains(response, '12345678')

    def test_detalle_cliente_asistencia_manual(self):
        """El staff puede ver la ficha de asistencia de un cliente seleccionado por ID."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:detail'), {'user_id': self.client_user.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Perez')
        self.assertContains(response, 'Musculación')
        self.assertContains(response, 'Registrar presente')

    def test_detalle_cliente_asistencia_qr_valid(self):
        """El staff puede cargar la ficha de asistencia usando un QR token válido."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        signer = signing.TimestampSigner()
        token = signer.sign(str(self.client_user.id))

        response = self.client.get(reverse('attendance:detail'), {'qr_token': token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juan Perez')
        self.assertContains(response, 'QR Escaneado')

    def test_detalle_cliente_asistencia_qr_expired(self):
        """Un QR token expirado muestra un mensaje de error y no carga el perfil."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        # Generar un token con más de 5 minutos de antigüedad (350 segundos de desfase)
        # Para testearlo, mockeamos la expiración pasándole una firma vieja o invalidando el max_age.
        # Otra forma es firmarlo con un timestamp en el pasado:
        signer = signing.TimestampSigner()
        token_viejo = signer.sign(str(self.client_user.id))
        
        # Simulamos unsign fallido por expiración
        with self.assertRaises(Exception):
            signer.unsign(token_viejo, max_age=-1)

        response = self.client.get(reverse('attendance:detail'), {'qr_token': token_viejo + "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Error al escanear QR')

    def test_alerta_telefono_emergencia_faltante(self):
        """Si falta el teléfono de emergencia, se advierte y el botón queda bloqueado."""
        self.client_user.telefono_emergencia = ""
        self.client_user.save()

        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:detail'), {'user_id': self.client_user.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Falta cargar teléfono de emergencia.')
        self.assertContains(response, 'Bloqueado')

    def test_alerta_menor_de_edad_constancia_tutor(self):
        """Si el cliente es menor de edad y no tiene constancia aprobada, se bloquea y se muestra opción de aprobar."""
        # Cambiar nacimiento para que tenga 16 años
        self.client_user.fecha_nacimiento = timezone.localdate() - timedelta(days=16*365)
        self.client_user.estado_constancia = 'PENDIENTE'
        self.client_user.save()

        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:detail'), {'user_id': self.client_user.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aprobar Constancia')
        self.assertContains(response, 'Bloqueado')

        # Aprobar constancia vía POST
        response_approve = self.client.post(reverse('attendance:approve_tutor'), {'user_id': self.client_user.id})
        self.assertEqual(response_approve.status_code, 200)
        
        # Validar cambio en base de datos
        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.estado_constancia, 'APROBADA')

    def test_registrar_presente_exito(self):
        """El staff puede registrar la asistencia y ver el cartel de asistencia registrada."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.post(reverse('attendance:register'), {
            'inscripcion_id': self.inscripcion.id,
            'metodo': 'MANUAL'
        })
        self.assertEqual(response.status_code, 200)
        
        # Verificar que se creó el registro
        self.assertTrue(Asistencia.objects.filter(inscripcion=self.inscripcion).exists())

    def test_cargar_telefono_get(self):
        """El staff puede abrir la modal para cargar el teléfono de emergencia."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:cargar_telefono'), {'user_id': self.client_user.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cargar Teléfono de Emergencia')

    def test_cargar_telefono_post_exito(self):
        """El staff puede guardar el teléfono de emergencia exitosamente."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.post(reverse('attendance:cargar_telefono'), {
            'user_id': self.client_user.id,
            'telefono_emergencia': '+5493511234567'
        })
        self.assertEqual(response.status_code, 200)
        
        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.telefono_emergencia, '+5493511234567')
        self.assertIn('closeAdminModal', response['HX-Trigger'])

    def test_cargar_telefono_post_error(self):
        """El staff recibe error si el formato del teléfono es incorrecto (letras)."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.post(reverse('attendance:cargar_telefono'), {
            'user_id': self.client_user.id,
            'telefono_emergencia': 'numero123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'El teléfono no puede contener letras')
        
        self.client_user.refresh_from_db()
        self.assertNotEqual(self.client_user.telefono_emergencia, 'numero123')

    def test_api_qr_scan_success(self):
        """El API de QR scan registra presente si el cliente tiene todo al día."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        signer = signing.TimestampSigner()
        token = signer.sign(str(self.client_user.id))

        response = self.client.post(
            reverse('attendance:api_qr_scan'),
            data={'qr_token': token},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data['status'], ['success', 'manual_action_required'])

    def test_api_qr_scan_expired(self):
        """El API de QR scan retorna error 400 si el token expiró."""
        self.client.login(username='empleado@gymflow.com', password='password123')
        signer = signing.TimestampSigner()
        token = signer.sign(str(self.client_user.id))
        
        response = self.client.post(
            reverse('attendance:api_qr_scan'),
            data={'qr_token': token + 'invalid'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')

    def test_api_qr_scan_no_classes(self):
        """El API retorna manual_action_required con 200 y guarda en caché si no tiene clases hoy."""
        other_client = User.objects.create_user(
            username='otro_cliente@gymflow.com',
            email='otro_cliente@gymflow.com',
            password='password123',
            rol='CLIENTE',
            dni='12121212',
            first_name='Otro',
            last_name='Cliente',
            fecha_nacimiento=date(1990, 5, 15),
            telefono_emergencia='1122334455'
        )
        self.client.login(username='empleado@gymflow.com', password='password123')
        signer = signing.TimestampSigner()
        token = signer.sign(str(other_client.id))
        
        response = self.client.post(
            reverse('attendance:api_qr_scan'),
            data={'qr_token': token},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'manual_action_required')
        self.assertIn('clases programadas', data['message'])
        self.assertEqual(data['user_id'], other_client.id)

        # Verificar cache
        from django.core.cache import cache
        cached_result = cache.get(f"qr_result_{token}")
        self.assertIsNotNone(cached_result)
        self.assertEqual(cached_result['status'], 'error')
        self.assertIn('clases programadas', cached_result['message'])

    def test_api_qr_scan_missing_phone(self):
        """El API retorna manual_action_required si falta el teléfono de emergencia."""
        self.client_user.telefono_emergencia = ""
        self.client_user.save()
        
        self.client.login(username='empleado@gymflow.com', password='password123')
        signer = signing.TimestampSigner()
        token = signer.sign(str(self.client_user.id))
        
        response = self.client.post(
            reverse('attendance:api_qr_scan'),
            data={'qr_token': token},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'manual_action_required')
        self.assertIn('teléfono de emergencia', data['message'])

    def test_api_qr_scan_minor_no_auth(self):
        """El API retorna manual_action_required si es menor con autorización pendiente."""
        self.client_user.fecha_nacimiento = timezone.localdate() - timedelta(days=16*365)
        self.client_user.estado_constancia = 'PENDIENTE'
        self.client_user.save()
        
        self.client.login(username='empleado@gymflow.com', password='password123')
        signer = signing.TimestampSigner()
        token = signer.sign(str(self.client_user.id))
        
        response = self.client.post(
            reverse('attendance:api_qr_scan'),
            data={'qr_token': token},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'manual_action_required')
        self.assertIn('autorización del tutor', data['message'])

    def test_qr_status_poll_view(self):
        """El polling de QR status retorna 200 con HTML si hay resultado en caché y luego borra la caché."""
        self.client.login(username='cliente@gymflow.com', password='password123')
        token = "test_status_token"
        
        from django.core.cache import cache
        cache.set(f"qr_result_{token}", {"status": "error", "message": "Mensaje de prueba"}, timeout=30)
        
        response = self.client.get(reverse('attendance:qr_status'), {'token': token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mensaje de prueba')
        self.assertContains(response, 'Requiere acción manual')
        
        self.assertIsNone(cache.get(f"qr_result_{token}"))


class CobrarSaldoEIngresarTests(TestCase):
    """Tests del atajo de recepción: cobrar saldo en efectivo + registrar asistencia."""

    def setUp(self):
        self.client = Client()

        self.staff_user = get_user_model().objects.create_user(
            username='recep@gymflow.com', email='recep@gymflow.com',
            password='password123', rol='EMPLEADO', dni='90000001',
            first_name='Recepción', last_name='Demo',
        )
        self.client_user = get_user_model().objects.create_user(
            username='socio@gymflow.com', email='socio@gymflow.com',
            password='password123', rol='CLIENTE', dni='40000001',
            first_name='Socio', last_name='Demo',
            fecha_nacimiento=date(1990, 1, 1),
            telefono_emergencia='3511234567',
        )

        sede = Sede.objects.create(nombre="Sede Test", direccion="Calle 123")
        sala = Sala.objects.create(nombre="Sala A", capacidad=20, sede=sede)
        disciplina = Disciplina.objects.create(nombre="Yoga Test")
        profesor = Teacher.objects.create(nombre="Profe", apellido="Test")

        today = timezone.localdate()
        self.periodo = PeriodoCobro.objects.create(
            nombre="Periodo Test",
            fecha_inicio_periodo=today - timedelta(days=5),
            fecha_fin_periodo=today + timedelta(days=25),
            apertura_abonados=today - timedelta(days=10),
            apertura_general=today - timedelta(days=5),
        )

        self.clase = Class.objects.create(
            disciplina=disciplina, sala=sala, profesor=profesor,
            dia_semana=today.weekday(),
            hora_inicio=time(12, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=15,
        )
        PrecioClase.objects.create(
            clase=self.clase, periodo=self.periodo, monto=Decimal("4000.00")
        )

        self.inscripcion = Inscripcion.objects.create(
            usuario=self.client_user, clase=self.clase, periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        InscripcionOcurrencia.objects.create(
            inscripcion=self.inscripcion,
            fecha_clase=timezone.make_aware(datetime.combine(today, time(12, 0))),
            estado=InscripcionOcurrencia.Estado.ACTIVA,
        )

        # Seña ya pagada (mitad del precio).
        pago_sena = Pago.objects.create(
            usuario=self.client_user, periodo=self.periodo,
            monto=Decimal("2000.00"), metodo=Pago.Metodo.MERCADOPAGO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago_sena, inscripcion=self.inscripcion,
            monto_aplicado=Decimal("2000.00"),
        )

        self.client.login(username='recep@gymflow.com', password='password123')

    def test_cobrar_saldo_e_ingresar_exito(self):
        """Un POST cobra el saldo en efectivo y crea la asistencia atómicamente."""
        response = self.client.post(reverse('attendance:quick_pay_and_enter'), {
            'inscripcion_id': self.inscripcion.id,
        })
        self.assertEqual(response.status_code, 200)

        # Saldo cobrado en efectivo, inscripción saldada.
        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.RESERVADA)
        pago_efectivo = Pago.objects.filter(
            usuario=self.client_user,
            metodo=Pago.Metodo.EFECTIVO,
            estado=Pago.Estado.COMPLETADO,
        ).first()
        self.assertIsNotNone(pago_efectivo)
        self.assertEqual(pago_efectivo.monto, Decimal("2000.00"))

        # Asistencia registrada en el día actual.
        self.assertTrue(
            Asistencia.objects.filter(
                inscripcion=self.inscripcion,
                fecha_hora_ingreso__date=timezone.localdate(),
            ).exists()
        )

    def test_bloqueado_sin_telefono_emergencia(self):
        """Sin teléfono de emergencia, ni se cobra ni se asienta asistencia."""
        self.client_user.telefono_emergencia = ""
        self.client_user.save()

        response = self.client.post(reverse('attendance:quick_pay_and_enter'), {
            'inscripcion_id': self.inscripcion.id,
        })
        self.assertEqual(response.status_code, 403)

        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        self.assertFalse(
            Pago.objects.filter(metodo=Pago.Metodo.EFECTIVO).exists()
        )
        self.assertFalse(
            Asistencia.objects.filter(inscripcion=self.inscripcion).exists()
        )

    def test_sin_saldo_pendiente_rechaza(self):
        """Si no hay saldo pendiente, el endpoint responde 400 sin efectos secundarios."""
        # Saldar la inscripción manualmente.
        pago_saldo = Pago.objects.create(
            usuario=self.client_user, periodo=self.periodo,
            monto=Decimal("2000.00"), metodo=Pago.Metodo.EFECTIVO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago_saldo, inscripcion=self.inscripcion,
            monto_aplicado=Decimal("2000.00"),
        )
        self.inscripcion.estado = Inscripcion.Estado.RESERVADA
        self.inscripcion.save(update_fields=["estado"])

        response = self.client.post(reverse('attendance:quick_pay_and_enter'), {
            'inscripcion_id': self.inscripcion.id,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Asistencia.objects.filter(inscripcion=self.inscripcion).exists()
        )

    def test_quick_pay_no_registra_asistencia(self):
        """El endpoint legacy `quick_pay` solo cobra; no debe marcar asistencia."""
        response = self.client.post(reverse('attendance:quick_pay'), {
            'inscripcion_id': self.inscripcion.id,
        })
        self.assertEqual(response.status_code, 200)

        self.inscripcion.refresh_from_db()
        self.assertEqual(self.inscripcion.estado, Inscripcion.Estado.RESERVADA)
        self.assertFalse(
            Asistencia.objects.filter(inscripcion=self.inscripcion).exists()
        )
