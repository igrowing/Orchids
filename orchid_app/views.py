from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.generic import TemplateView, CreateView, FormView, ListView, UpdateView, DetailView

from forms import OrchidForm, ActionsForm
from . import models
import actuators

# @login_required
def list(request, year=None, month=None):
    form = ActionsForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            mist = request.POST.get("mist", False)
            drip = request.POST.get("drip", False)
            fan = request.POST.get("fan", False)
            light = request.POST.get("light", False)
            heat = request.POST.get("heat", False)

            msg = _activate(mist=mist, drip=drip, fan=fan, light=light, heat=heat)
            if 'wrong' not in msg.lower():
                messages.success(request, "Actions taken: " + msg)
            else:
                messages.error(request, "Actions tried: " + msg)

    qs = models.Sensors.objects.all()  # filter(date=request.date)
    if year:
        qs = qs.filter(date__year=year)
    if month:
        qs = qs.filter(date__month=month)
    total = qs.count()
    return render(request, 'orchid_app/sensor_list.html', {'form': form, 'objects': qs, 'total': total})
    # , "expenses/expense_list.html", {
    #     'year': year,
    #     'month': month,
    #     'total': total,
    #     'objects': qs,
    # })


def _activate(**kwargs):
    '''Internal function. Control the actuators.

    @:param kwargs: actuator_name=required_state. Can be boolean or string (on, off, value).
    @:returns string: message what was activated and deactivated.
    '''

    #TODO: move out of views!

    msg = []
    for k, v in kwargs.iteritems():
        if type(v) == unicode:
            if v.lower() in ['on', 'true', 'enable', 'start']:
                v = True
            elif v.lower() in ['off', 'false', 'disable', 'stop']:
                v = False
        # Else: keep v as is

        msg.append(k + ': ' + str(v))
        if k == 'mist':
            actuators.LatchingValve(1).set_status(v)
        elif k == 'drip':
            actuators.LatchingValve(2).set_status(v)
        elif k == 'fan':
            actuators.Relay(1).set_status(v)
        elif k == 'light':
            pass
        elif k == 'heat':
            pass
        else:
            msg[-1] += "<<--Wrong action!"

    return ', '.join(msg)

