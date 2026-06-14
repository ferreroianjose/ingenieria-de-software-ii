"""Valores de chrome de página (footer, fondo) reutilizables por vista.

page_background: CSS del lienzo visual (#page-canvas). Puede incluir gradientes.
color_scheme: light | dark para color-scheme del documento.
footer_variant: light | dark — color del texto del footer transparente.
"""

PAGE_CHROME_DARK = {
    "footer_variant": "dark",
    "color_scheme": "dark",
    "page_background": "",
    "sidebar_variant": "dark",
}

_CF_GRADIENT = (
    "background:"
    " radial-gradient(circle at 18% 0%, rgba(223, 2, 255, 0.14), transparent 32%),"
    " radial-gradient(circle at 82% 6%, rgba(92, 225, 230, 0.09), transparent 28%),"
    " #000000;"
)

PAGE_CHROME_CLIENTE_FLOW = {
    "footer_variant": "dark",
    "color_scheme": "dark",
    "page_background": _CF_GRADIENT,
    "sidebar_variant": "dark",
}

PAGE_CHROME_LIGHT = {
    "footer_variant": "light",
    "color_scheme": "light",
    "page_background": "background:#ffffff;",
    "sidebar_variant": "light",
}

PAGE_CHROME_ADMIN = {
    "footer_variant": "light",
    "color_scheme": "light",
    "page_background": "background:#ffffff;",
    "sidebar_variant": "light",
}


def merge_page_chrome(preset=None, **overrides):
    """Combina preset + overrides para pasar al contexto del template."""
    chrome = dict(PAGE_CHROME_DARK)
    if preset:
        chrome.update(preset)
    chrome.update(overrides)
    return chrome
