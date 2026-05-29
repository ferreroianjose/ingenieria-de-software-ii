"""Valores de chrome de página (footer, fondo) reutilizables por vista.

page_background: CSS del lienzo visual (#page-canvas). Puede incluir gradientes.
color_scheme: light | dark para color-scheme del documento.
footer_variant: light | dark — color del texto del footer transparente.
"""

PAGE_CHROME_DARK = {
    "footer_variant": "dark",
    "color_scheme": "dark",
    "page_background": "",
}

PAGE_CHROME_CLIENTE_FLOW = {
    "footer_variant": "dark",
    "color_scheme": "dark",
    "page_background": "background:#000000;",
}

PAGE_CHROME_LIGHT = {
    "footer_variant": "light",
    "color_scheme": "light",
    "page_background": "background:#ffffff;",
}

PAGE_CHROME_ADMIN = {
    "footer_variant": "light",
    "color_scheme": "light",
    "page_background": "background:#ffffff;",
}

PAGE_CHROME_DASHBOARD_CLIENTE = {
    "footer_variant": "light",
    "color_scheme": "light",
    "page_background": (
        "background:"
        " radial-gradient(circle at 8% 0%, rgba(223, 2, 255, 0.14), transparent 32%),"
        " radial-gradient(circle at 92% 10%, rgba(92, 225, 230, 0.14), transparent 28%),"
        " linear-gradient(180deg, #ffffff 0%, #f8f9ff 40%, #f5f7ff 100%);"
    ),
}


def merge_page_chrome(preset=None, **overrides):
    """Combina preset + overrides para pasar al contexto del template."""
    chrome = dict(PAGE_CHROME_DARK)
    if preset:
        chrome.update(preset)
    chrome.update(overrides)
    return chrome
