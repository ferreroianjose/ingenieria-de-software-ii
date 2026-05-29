from django.core.management.base import BaseCommand
from django.apps import apps
import os
import json
from datetime import date
from django.contrib.auth.hashers import make_password


class Command(BaseCommand):
    help = "Loads initial users data idempotently from fixture"

    def handle(self, *args, **options):
        User = apps.get_model("users", "User")
        users_path = apps.get_app_config("users").path
        fixtures_path = os.path.join(users_path, "fixtures", "initial_users.json")

        if not os.path.exists(fixtures_path):
            self.stdout.write(
                self.style.WARNING(f"Fixture file not found: {fixtures_path}")
            )
            return

        with open(fixtures_path, "r", encoding="utf-8") as f:
            users = json.load(f)

        created_count = 0
        skipped_count = 0

        for u in users:
            email = u.get("email")
            if not email:
                continue

            existing = User.objects.filter(email=email).first()
            if existing:
                if existing.rol == "CLIENTE" and not existing.telefono_emergencia:
                    dni = existing.dni or "00000000"
                    existing.telefono_emergencia = f"35155{str(dni)[-6:]}"
                    existing.save(update_fields=["telefono_emergencia"])
                skipped_count += 1
                continue

            if u.get("rol") == "CLIENTE" and not u.get("telefono_emergencia"):
                dni = u.get("dni", "00000000")
                u["telefono_emergencia"] = f"35155{str(dni)[-6:]}"

            raw_password = u.pop("raw_password", None)

            # Convert fecha_nacimiento to a date object if present
            fecha_nacimiento = u.get("fecha_nacimiento")
            if fecha_nacimiento:
                try:
                    u["fecha_nacimiento"] = date.fromisoformat(fecha_nacimiento)
                except ValueError:
                    # leave as-is if conversion fails
                    pass

            if raw_password:
                u["password"] = make_password(raw_password)

            User.objects.create(**u)
            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Initial users loaded: {created_count} created, {skipped_count} skipped"
            )
        )
