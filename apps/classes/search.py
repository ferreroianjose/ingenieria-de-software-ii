from django.db.models import Q


def apply_text_search(queryset, q, *fields):
    """Case-insensitive search across given text fields (OR)."""
    q = (q or '').strip()
    if not q:
        return queryset
    condition = Q()
    for field in fields:
        condition |= Q(**{f'{field}__icontains': q})
    return queryset.filter(condition)
