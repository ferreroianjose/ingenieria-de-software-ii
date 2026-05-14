from django.shortcuts import redirect
from django.urls import reverse


class TwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.session.get("is_2fa_pending"):
            # Lista de URLs permitidas durante el 2FA
            allowed_urls = [
                reverse("two_factor"),
                reverse("logout"),
            ]

            # Permitir static files y media si es necesario
            if (
                request.path not in allowed_urls
                and not request.path.startswith("/static/")
                and not request.path.startswith("/__reload__/")
            ):
                return redirect("two_factor")

        response = self.get_response(request)
        return response
