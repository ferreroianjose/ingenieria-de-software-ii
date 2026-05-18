from django.core.management.base import BaseCommand
from django.apps import apps
import os
import json
from datetime import timedelta
from django.utils.dateparse import parse_datetime


class Command(BaseCommand):
    help = "Loads initial classes and teachers data idempotently from fixture"

    def handle(self, *args, **options):
        Teacher = apps.get_model("classes", "Teacher")
        Class = apps.get_model("classes", "Class")
        Sede = apps.get_model("classes", "Sede")
        Disciplina = apps.get_model("classes", "Disciplina")
        Sala = apps.get_model("classes", "Sala")

        classes_path = apps.get_app_config("classes").path
        fixtures_path = os.path.join(classes_path, "fixtures", "initial_classes.json")

        if not os.path.exists(fixtures_path):
            self.stdout.write(
                self.style.WARNING(f"Fixture file not found: {fixtures_path}")
            )
            return

        with open(fixtures_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Load Sedes
        sedes_created = 0
        sedes_skipped = 0
        for s_data in data.get("sedes", []):
            _, created = Sede.objects.get_or_create(
                nombre=s_data["nombre"],
                defaults={"direccion": s_data.get("direccion", "")},
            )
            if created:
                sedes_created += 1
            else:
                sedes_skipped += 1

        # Load Disciplinas
        disciplinas_created = 0
        disciplinas_skipped = 0
        for d_data in data.get("disciplinas", []):
            _, created = Disciplina.objects.get_or_create(
                nombre=d_data["nombre"],
                defaults={"descripcion": d_data.get("descripcion", "")},
            )
            if created:
                disciplinas_created += 1
            else:
                disciplinas_skipped += 1

        # Load Salas
        salas_created = 0
        salas_skipped = 0
        for sa_data in data.get("salas", []):
            try:
                sede = Sede.objects.get(nombre=sa_data["sede_nombre"])
            except Sede.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Sede '{sa_data['sede_nombre']}' not found for sala '{sa_data['nombre']}'")
                )
                continue
            _, created = Sala.objects.get_or_create(
                nombre=sa_data["nombre"],
                sede=sede,
                defaults={"capacidad": sa_data.get("capacidad", 20)},
            )
            if created:
                salas_created += 1
            else:
                salas_skipped += 1

        # Load Teachers
        teachers_created = 0
        teachers_skipped = 0
        for t_data in data.get("teachers", []):
            _, created = Teacher.objects.get_or_create(
                nombre=t_data["nombre"],
                apellido=t_data["apellido"],
            )
            if created:
                teachers_created += 1
            else:
                teachers_skipped += 1

        # Load Classes
        classes_created = 0
        classes_skipped = 0
        for c_data in data.get("classes", []):
            disciplina_nombre = c_data["disciplina_nombre"]
            sala_nombre = c_data["sala_nombre"]
            sala_sede_nombre = c_data["sala_sede_nombre"]
            teacher_nombre = c_data["teacher_nombre"]
            teacher_apellido = c_data["teacher_apellido"]
            duracion_minutos = c_data["duracion_minutos"]
            inicio_str = c_data["inicio"]

            try:
                teacher = Teacher.objects.get(nombre=teacher_nombre, apellido=teacher_apellido)
            except Teacher.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Teacher {teacher_nombre} {teacher_apellido} not found")
                )
                continue

            try:
                disciplina = Disciplina.objects.get(nombre=disciplina_nombre)
            except Disciplina.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Disciplina '{disciplina_nombre}' not found")
                )
                continue

            try:
                sede = Sede.objects.get(nombre=sala_sede_nombre)
                sala = Sala.objects.get(nombre=sala_nombre, sede=sede)
            except (Sede.DoesNotExist, Sala.DoesNotExist):
                self.stdout.write(
                    self.style.ERROR(f"Sala '{sala_nombre}' in sede '{sala_sede_nombre}' not found")
                )
                continue

            inicio = parse_datetime(inicio_str)

            if Class.objects.filter(disciplina=disciplina, inicio=inicio, sala=sala).exists():
                classes_skipped += 1
                continue

            Class.objects.create(
                disciplina=disciplina,
                sala=sala,
                profesor=teacher,
                inicio=inicio,
                duracion=timedelta(minutes=duracion_minutos),
                cupo_maximo=c_data.get("cupo_maximo", 20),
                estado=c_data.get("estado", "disponible"),
            )
            classes_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Sedes: {sedes_created} created, {sedes_skipped} skipped. "
                f"Disciplinas: {disciplinas_created} created, {disciplinas_skipped} skipped. "
                f"Salas: {salas_created} created, {salas_skipped} skipped. "
                f"Teachers: {teachers_created} created, {teachers_skipped} skipped. "
                f"Classes: {classes_created} created, {classes_skipped} skipped."
            )
        )
