from django.contrib import admin

from .models import Sensors
from .models import Actions

admin.site.register(Sensors)
admin.site.register(Actions)
