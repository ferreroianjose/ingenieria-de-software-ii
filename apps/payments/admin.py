from django.contrib import admin

from .models import Credito, Pago, PagoInscripcion, PeriodoCobro, PrecioClase


@admin.register(PeriodoCobro)
class PeriodoCobroAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "fecha_inicio_periodo",
        "fecha_fin_periodo",
        "apertura_abonados",
        "apertura_general",
    )
    search_fields = ("nombre",)


@admin.register(PrecioClase)
class PrecioClaseAdmin(admin.ModelAdmin):
    list_display = ("clase", "periodo", "monto")
    list_filter = ("periodo", "clase")
    search_fields = ("clase__disciplina__nombre", "periodo__nombre")


class PagoInscripcionInline(admin.TabularInline):
    model = PagoInscripcion
    extra = 0
    fields = ("inscripcion", "monto_aplicado")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "periodo", "monto", "metodo", "estado", "fecha_pago")
    list_filter = ("estado", "metodo", "periodo")
    search_fields = ("usuario__username", "usuario__dni", "usuario__email")
    readonly_fields = ("fecha_pago",)
    date_hierarchy = "fecha_pago"
    inlines = (PagoInscripcionInline,)


@admin.register(PagoInscripcion)
class PagoInscripcionAdmin(admin.ModelAdmin):
    list_display = ("pago", "inscripcion", "monto_aplicado")
    list_filter = ("pago__periodo", "pago__estado")
    search_fields = (
        "pago__usuario__username",
        "inscripcion__usuario__username",
        "inscripcion__clase__disciplina__nombre",
    )


@admin.register(Credito)
class CreditoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "periodo", "disciplina", "estado")
    list_filter = ("estado", "periodo", "disciplina")
    search_fields = ("usuario__username", "usuario__dni", "disciplina__nombre")
