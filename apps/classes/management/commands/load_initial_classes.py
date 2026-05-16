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

        teachers_data = data.get("teachers", [])
        classes_data = data.get("classes", [])

        # Ensure a default Sede exists
        default_sede, _ = Sede.objects.get_or_create(
            nombre="Sede Central",
            defaults={"direccion": "Dirección Principal 123"}
        )

        # Load Teachers
        teachers_created = 0
        teachers_skipped = 0
        for t_data in teachers_data:
            nombre = t_data.get("nombre")
            apellido = t_data.get("apellido")
            
            if Teacher.objects.filter(nombre=nombre, apellido=apellido).exists():
                teachers_skipped += 1
                continue
            
            Teacher.objects.create(**t_data)
            teachers_created += 1

        # Load Classes
        classes_created = 0
        classes_skipped = 0
        for c_data in classes_data:
            teacher_nombre = c_data.pop("teacher_nombre")
            teacher_apellido = c_data.pop("teacher_apellido")
            duracion_minutos = c_data.pop("duracion_minutos")
            disciplina_nombre = c_data.pop("disciplina")
            sala_nombre = c_data.pop("sala")
            inicio_str = c_data["inicio"]
            
            try:
                teacher = Teacher.objects.get(nombre=teacher_nombre, apellido=teacher_apellido)
            except Teacher.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Teacher {teacher_nombre} {teacher_apellido} not found for class at {inicio_str}")
                )
                continue

            inicio = parse_datetime(inicio_str)
            
            # Get or create infrastructure objects
            disciplina, _ = Disciplina.objects.get_or_create(nombre=disciplina_nombre)
            sala, _ = Sala.objects.get_or_create(
                nombre=sala_nombre,
                sede=default_sede,
                defaults={"capacidad": c_data.get("cupo_maximo", 20)}
            )
            
            if Class.objects.filter(disciplina=disciplina, inicio=inicio, sala=sala).exists():
                classes_skipped += 1
                continue

            c_data["profesor"] = teacher
            c_data["inicio"] = inicio
            c_data["duracion"] = timedelta(minutes=duracion_minutos)
            c_data["disciplina"] = disciplina
            c_data["sala"] = sala
            
            Class.objects.create(**c_data)
            classes_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Teachers: {teachers_created} created, {teachers_skipped} skipped. "
                f"Classes: {classes_created} created, {classes_skipped} skipped."
            )
        )
