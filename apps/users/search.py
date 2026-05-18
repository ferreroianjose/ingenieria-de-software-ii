from apps.classes.search import apply_text_search

USER_PAGE_SIZE = 25


def filter_users_queryset(queryset, q):
    """Empty `q` returns the full queryset (caller should paginate)."""
    return apply_text_search(
        queryset,
        q,
        "first_name",
        "last_name",
        "email",
        "dni",
        "username",
    )
