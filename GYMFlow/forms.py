"""Mensajes de validación de formularios en español (sin depender de gettext)."""


def required_field_message(label: str) -> str:
    return f'El campo "{label}" es obligatorio.'


def apply_required_error_messages(form) -> None:
    """Mismo criterio que BaseStyledForm: required con el label del campo."""
    for name, field in form.fields.items():
        if not field.required:
            continue
        label = field.label if field.label is not None else name
        field.error_messages["required"] = required_field_message(str(label))
