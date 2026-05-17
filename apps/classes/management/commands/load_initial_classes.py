from datetime import datetime, timedelta

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

import json
import os


class Command(BaseCommand):
    help = "Loads sedes, salas, disciplinas, teachers and classes from fixture (idempotent)."

    def handle(self, *args, **options):
        Teacher = apps.get_model("classes", "Teacher")
        Class = apps.get_model("classes", "Class")
        Sede = apps.get_model("classes", "Sede")
        Disciplina = apps.get_model("classes", "Disciplina")
        Sala = apps.get_model("classes", "Sala")

        classes_path = apps.get_app_config("classes").path
        fixtures_path = os.path.join(classes_path, "fixtures", "initial_classes.json")

        if not os.path.exists(fixtures_path):
            self.stdout.write(self.style.WARNING(f"Fixture not found: {fixtures_path}"))
            return

        with open(fixtures_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        sedes_created = self._load_sedes(Sede, Sala, data.get("sedes", []))
        disciplinas_created = self._load_disciplinas(Disciplina, data.get("disciplinas", []))
        teachers_created, teachers_skipped = self._load_teachers(
            Teacher, data.get("teachers", [])
        )
        classes_created, classes_skipped = self._load_classes(
            Class, Teacher, Disciplina, Sede, Sala, data.get("classes", [])
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Sedes/salas: {sedes_created} sedes processed. "
                f"Disciplinas: {disciplinas_created} created. "
                f"Teachers: {teachers_created} created, {teachers_skipped} skipped. "
                f"Classes: {classes_created} created, {classes_skipped} skipped."
            )
        )

    def _load_sedes(self, Sede, Sala, sedes_data):
        created = 0
        for sede_data in sedes_data:
            salas_data = sede_data.pop("salas", [])
            sede, was_created = Sede.objects.get_or_create(
                nombre=sede_data["nombre"],
                defaults={"direccion": sede_data.get("direccion", "")},
            )
            if was_created:
                created += 1
            elif sede_data.get("direccion") and sede.direccion != sede_data["direccion"]:
                sede.direccion = sede_data["direccion"]
                sede.save(update_fields=["direccion"])

            for sala_data in salas_data:
                Sala.objects.get_or_create(
                    nombre=sala_data["nombre"],
                    sede=sede,
                    defaults={"capacidad": sala_data["capacidad"]},
                )
        return created

    def _load_disciplinas(self, Disciplina, disciplinas_data):
        created = 0
        for d_data in disciplinas_data:
            _, was_created = Disciplina.objects.get_or_create(
                nombre=d_data["nombre"],
                defaults={"descripcion": d_data.get("descripcion", "")},
            )
            if was_created:
                created += 1
        return created

    def _load_teachers(self, Teacher, teachers_data):
        created = 0
        skipped = 0
        for t_data in teachers_data:
            if Teacher.objects.filter(
                nombre=t_data["nombre"], apellido=t_data["apellido"]
            ).exists():
                skipped += 1
                continue
            Teacher.objects.create(**t_data)
            created += 1
        return created, skipped

    def _resolve_schedule(self, c_data):
        if "dia_semana" in c_data and "hora" in c_data:
            dia_semana = int(c_data.pop("dia_semana"))
            hora_parts = c_data.pop("hora").split(":")
            hora_inicio = datetime.strptime(
                f"{int(hora_parts[0]):02d}:{int(hora_parts[1]):02d}",
                "%H:%M",
            ).time()
            return dia_semana, hora_inicio

        inicio_str = c_data.pop("inicio")
        inicio_dt = parse_datetime(inicio_str)
        return inicio_dt.weekday(), inicio_dt.time()

    def _load_classes(self, Class, Teacher, Disciplina, Sede, Sala, classes_data):
        created = 0
        skipped = 0

        for c_data in list(classes_data):
            row = dict(c_data)
            teacher_nombre = row.pop("teacher_nombre")
            teacher_apellido = row.pop("teacher_apellido")
            duracion_minutos = row.pop("duracion_minutos")
            disciplina_nombre = row.pop("disciplina")
            sala_nombre = row.pop("sala")
            sede_nombre = row.pop("sede", None)

            try:
                teacher = Teacher.objects.get(
                    nombre=teacher_nombre, apellido=teacher_apellido
                )
            except Teacher.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f"Teacher {teacher_nombre} {teacher_apellido} not found."
                    )
                )
                continue

            try:
                dia_semana, hora_inicio = self._resolve_schedule(row)
            except (KeyError, ValueError) as exc:
                self.stdout.write(self.style.ERROR(f"Invalid schedule: {exc}"))
                continue

            disciplina, _ = Disciplina.objects.get_or_create(nombre=disciplina_nombre)

            if sede_nombre:
                try:
                    sede = Sede.objects.get(nombre=sede_nombre)
                except Sede.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f"Sede «{sede_nombre}» not found.")
                    )
                    continue
                sala, _ = Sala.objects.get_or_create(
                    nombre=sala_nombre,
                    sede=sede,
                    defaults={"capacidad": row.get("cupo_maximo", 20)},
                )
            else:
                default_sede, _ = Sede.objects.get_or_create(
                    nombre="Sede Central",
                    defaults={"direccion": "Dirección Principal 123"},
                )
                sala, _ = Sala.objects.get_or_create(
                    nombre=sala_nombre,
                    sede=default_sede,
                    defaults={"capacidad": row.get("cupo_maximo", 20)},
                )

            if Class.objects.filter(
                disciplina=disciplina,
                dia_semana=dia_semana,
                hora_inicio=hora_inicio,
                sala=sala,
            ).exists():
                skipped += 1
                continue

            Class.objects.create(
                profesor=teacher,
                dia_semana=dia_semana,
                hora_inicio=hora_inicio,
                duracion=timedelta(minutes=duracion_minutos),
                disciplina=disciplina,
                sala=sala,
                cupo_maximo=row.get("cupo_maximo", 20),
                estado=row.get("estado", "disponible"),
            )
            created += 1

        return created, skipped
