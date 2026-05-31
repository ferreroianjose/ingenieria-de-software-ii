STEP_ORDER = ("actividades", "horarios", "clase", "pago")


def build_flow_stepper_context(current_step, **step_urls):
    try:
        current_idx = STEP_ORDER.index(current_step)
    except ValueError:
        current_idx = 0

    links = {}
    enabled = {}

    for idx, step in enumerate(STEP_ORDER):
        key = f"{step}_url"
        url = step_urls.get(key)
        links[step] = url

        if not url:
            enabled[step] = False
            continue

        if idx <= current_idx:
            enabled[step] = True
            continue

        # Forward navigation is allowed only when every intermediary step
        # already has a concrete URL (selection done).
        enabled[step] = all(step_urls.get(f"{s}_url") for s in STEP_ORDER[: idx + 1])

    return {"flow_step_links": links, "flow_step_enabled": enabled}
