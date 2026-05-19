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
):
    """HTMX success: 204, close modal, show flash via JS, optional list refresh."""
    response = HttpResponse(status=204)
    response['HX-Reswap'] = 'none'
    trigger = {'adminFlash': {'message': message, 'level': level}}
    if close_modal:
        trigger['closeAdminModal'] = close_modal
    if refresh:
        trigger['adminRefreshList'] = refresh
    if locations_reload:
        trigger['adminLocationsReload'] = locations_reload
    response['HX-Trigger'] = json.dumps(trigger)
    if redirect_url:
        response['HX-Redirect'] = redirect_url
    return response
