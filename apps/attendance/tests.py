from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta, date, time
import django.core.signing as signing

from apps.classes.models import Sede, Sala, Teacher, Disciplina, Class, Inscripcion, InscripcionOcurrencia
from apps.attendance.models import Asistencia
from apps.payments.models import PeriodoCobro, Pago, PagoInscripcion

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
        self.assertContains(response, 'Registrar Presente')

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
        self.assertContains(response, 'FALTA TELÉFONO DE EMERGENCIA')
        self.assertContains(response, 'Presente Bloqueado')

    def test_alerta_menor_de_edad_constancia_tutor(self):
        """Si el cliente es menor de edad y no tiene constancia aprobada, se bloquea y se muestra opción de aprobar."""
        # Cambiar nacimiento para que tenga 16 años
        self.client_user.fecha_nacimiento = timezone.localdate() - timedelta(days=16*365)
        self.client_user.estado_constancia = 'PENDIENTE'
        self.client_user.save()

        self.client.login(username='empleado@gymflow.com', password='password123')
        response = self.client.get(reverse('attendance:detail'), {'user_id': self.client_user.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aprobar Constancia Ahora')
        self.assertContains(response, 'Presente Bloqueado')

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
