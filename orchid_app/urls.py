from django.conf.urls import url

from . import views

app_name = 'orchid_app'

urlpatterns = [
    url(r'^$', views.list, name='list'),
    url(r'^actions/$', views.action_list, name='action_list'),
    url(r'^sysinfo/$', views.sysinfo_list, name='sysinfo_list'),
]