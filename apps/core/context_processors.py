from apps.core.page_chrome import PAGE_CHROME_ADMIN, PAGE_CHROME_DARK


def page_chrome(request):
    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.rol in ("ADMIN", "EMPLEADO"):
        return dict(PAGE_CHROME_ADMIN)
    return dict(PAGE_CHROME_DARK)
