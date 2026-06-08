import json

from django.http import HttpResponse


def hx_ok(
    request,
    *,
    message,
    level='success',
    close_modal=None,
    refresh=None,
    redirect_url=None,
    locations_reload=None,
    trigger=None,
):
    """HTMX success: 204, close modal, show flash via JS, optional list refresh."""
    response = HttpResponse(status=204)
    response['HX-Reswap'] = 'none'
    triggers = {'adminFlash': {'message': message, 'level': level}}
    if close_modal:
        triggers['closeAdminModal'] = close_modal
    if refresh:
        triggers['adminRefreshList'] = refresh
    if locations_reload:
        triggers['adminLocationsReload'] = locations_reload
    if trigger:
        if isinstance(trigger, str):
            triggers[trigger] = True
        else:
            triggers.update(trigger)
            
    response['HX-Trigger'] = json.dumps(triggers)
    if redirect_url:
        response['HX-Redirect'] = redirect_url
    return response
