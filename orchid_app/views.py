import django_tables2 as tables
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render

from forms import ActionsForm
from orchid_app.controller import activate, get_last_action
from . import models


class SensorTable(tables.Table):
    date = tables.DateTimeColumn(short=True)  # still doesn't work.
    class Meta:
        model = models.Sensors
        fields = ('date', 't_amb', 't_obj', 'rh', 'lux', 'hpa', 'wind', 'water')


class ActionTable(tables.Table):
    date = tables.DateTimeColumn(short=True)  # still doesn't work.
    class Meta:
        model = models.Actions
        fields = ('date', 'water', 'mist', 'fan', 'light', 'heat', 'reason')


# @register.filter(name='myDate')
# def myDate(value, arg):
#     #arg is optional and not needed but you could supply your own formatting if you want.
#     dateformatted = value.strftime("%b %d, %Y at %I:%M %p")
#     return dateformatted


# @login_required
def list(request):
    # Use auto_id for further form changes
    form = ActionsForm(request.POST or None, auto_id=True)
    a = get_last_action()
    if request.method == "POST":
        if form.is_valid():
            a.mist = request.POST.get("mist", False)
            a.water = request.POST.get("water", False)
            a.fan = request.POST.get("fan", False)
            a.light = request.POST.get("light", False)
            a.heat = request.POST.get("heat", False)

            msg = activate(reason='Manual', mist=a.mist, drip=a.water, fan=a.fan, light=a.light, heat=a.heat)
            if [i for i in ['wrong', 'skip'] if i not in msg.lower()]:
                messages.success(request, "Actions taken: " + msg)
            else:
                messages.error(request, "Actions tried: " + msg)

    for k, v in a.iteritems():
        a[k] = _verb(v)

    form.water = a.water

    qs = models.Sensors.objects.all().order_by('-date')  # filter(date=request.date
    paginator = Paginator(qs, 30)
    page = request.GET.get('page')
    try:
        table = paginator.page(page)
    except PageNotAnInteger:
        table = paginator.page(1)
    except EmptyPage:
        table = paginator.page(paginator.num_pages)

    # Keep reference to page. Dirty trick. TODO: improve.
    pp = table
    # Convert current page into table.
    table = SensorTable(table)
    total = qs.count()

    return render(request, 'orchid_app/sensor_list.html', {'form': form, 'paginator': pp, 'total': total, 'table': table, 'actuators': a})


def action_list(request):
    form = ActionsForm(request.POST or None)
    a = get_last_action()
    if request.method == "POST":
        if form.is_valid():
            a.mist = request.POST.get("mist", False)
            a.water = request.POST.get("water", False)
            a.fan = request.POST.get("fan", False)
            a.light = request.POST.get("light", False)
            a.heat = request.POST.get("heat", False)

            msg = activate(reason='Manual', mist=a.mist, drip=a.water, fan=a.fan, light=a.light, heat=a.heat)
            if [i for i in ['wrong', 'skip'] if i not in msg.lower()]:
                messages.success(request, "Actions taken: " + msg)
            else:
                messages.error(request, "Actions tried: " + msg)

    # Standartize/verbose actuator form values.
    for k, v in a.iteritems():
        a[k] = _verb(v)

    form.water = a.water
    qs = models.Actions.objects.all().order_by('-date')  # filter(date=request.date
    paginator = Paginator(qs, 30)
    page = request.GET.get('page')
    try:
        table = paginator.page(page)
    except PageNotAnInteger:
        table = paginator.page(1)
    except EmptyPage:
        table = paginator.page(paginator.num_pages)

    # Keep reference to page. Dirty trick. TODO: improve.
    pp = table
    # Convert current page into table.
    table = ActionTable(table)

    total = qs.count()
    return render(request, 'orchid_app/action_list.html', {'form': form, 'paginator': pp, 'total': total, 'table': table, 'actuators': a})


def _verb(b):
    '''Convert boolean into verbal off/on.'''
    return ['off', 'on'][b] if type(b) == bool else b
