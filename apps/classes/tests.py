from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.classes.models import Class, Disciplina, Sala, Sede, Teacher
from apps.payments.models import PeriodoCobro, PrecioClase

User = get_user_model()

class MassPriceIncreaseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_superuser(
            username='admin@gymflow.com',
            email='admin@gymflow.com',
            password='testpassword123',
            rol='EMPLEADO',
        )
        self.client.login(username='admin@gymflow.com', password='testpassword123')
        
        self.disciplina = Disciplina.objects.create(nombre="Pilates")
        self.sede = Sede.objects.create(nombre="Sede Central", direccion="123")
        self.sala = Sala.objects.create(nombre="Sala Principal", capacidad=20, sede=self.sede)
        self.teacher = Teacher.objects.create(nombre="Ana", apellido="Gomez")
        
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=self.sala,
            profesor=self.teacher,
            dia_semana=1,
            hora_inicio=time(18, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=15,
        )
        
        self.periodo = PeriodoCobro.objects.create(
            nombre="Octubre 2026",
            fecha_inicio_periodo=date(2026, 10, 1),
            fecha_fin_periodo=date(2026, 10, 31),
            apertura_abonados=date(2026, 9, 20),
            apertura_general=date(2026, 10, 1),
        )
        
        self.precio = PrecioClase.objects.create(
            clase=self.clase,
            periodo=self.periodo,
            monto=Decimal("5000.00")
        )

    def test_apply_mass_price_increase_porcentaje(self):
        url = reverse('classes:apply_mass_price_increase')
        response = self.client.post(url, {
            'periodo_id': self.periodo.id,
            'tipo_aumento': 'porcentaje',
            'porcentaje': '10',  # 10% increase
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.precio.refresh_from_db()
        self.assertEqual(self.precio.monto, Decimal("5500.00"))
        
    def test_apply_mass_price_increase_fijo(self):
        url = reverse('classes:apply_mass_price_increase')
        response = self.client.post(url, {
            'periodo_id': self.periodo.id,
            'tipo_aumento': 'fijo',
            'monto_fijo': '1000.00',
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.precio.refresh_from_db()
        self.assertEqual(self.precio.monto, Decimal("6000.00"))

    def test_apply_mass_price_increase_no_params(self):
        url = reverse('classes:apply_mass_price_increase')
        response = self.client.post(url, {
            'periodo_id': self.periodo.id,
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.precio.refresh_from_db()
        self.assertEqual(self.precio.monto, Decimal("5000.00"))  # Unchanged

    def test_class_price_for_period(self):
        url = reverse('classes:class_price_for_period', kwargs={'class_id': self.clase.id})
        response = self.client.get(url, {
            'mes_a_aplicar': self.periodo.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '5000.00')


class SalaUniquenessTests(TestCase):
    """Una sala no debe poder crearse dos veces en la misma sede ignorando caso."""

    def setUp(self):
        self.sede = Sede.objects.create(nombre="Sede X", direccion="Calle 1")
        self.sede_otra = Sede.objects.create(nombre="Sede Y", direccion="Calle 2")
        Sala.objects.create(nombre="Sala Zen", capacidad=10, sede=self.sede)

    def test_form_rechaza_nombre_duplicado_distinto_caso(self):
        from apps.classes.forms import SalaForm

        form = SalaForm(data={
            'nombre': 'SALA ZEN',
            'capacidad': 12,
            'sede': self.sede.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)
        self.assertIn('Ya existe una sala con ese nombre en esta sede.', form.errors['nombre'])

    def test_form_permite_mismo_nombre_en_otra_sede(self):
        from apps.classes.forms import SalaForm

        form = SalaForm(data={
            'nombre': 'sala zen',
            'capacidad': 12,
            'sede': self.sede_otra.pk,
        })
        self.assertTrue(form.is_valid(), msg=form.errors)

    def test_db_rechaza_duplicado_case_insensitive(self):
        """La constraint protege contra creación directa (admin, shell, seed)."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sala.objects.create(nombre="sala zen", capacidad=12, sede=self.sede)
