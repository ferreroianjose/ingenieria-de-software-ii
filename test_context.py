import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GYMFlow.settings")
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.template import RequestContext, Template
from apps.core.page_chrome import PAGE_CHROME_ADMIN

User = get_user_model()
user = User.objects.filter(rol="ADMIN").first()
factory = RequestFactory()
request = factory.get('/')
request.user = user

# Let's see what RequestContext has.
ctx = RequestContext(request, {"page_section": "Panel de administración"})
print("Context dicts:")
for d in ctx.dicts:
    if "theme_color" in d:
        print("Found theme_color:", d["theme_color"])
    if "sidebar_variant" in d:
        print("Found sidebar_variant:", d["sidebar_variant"])
