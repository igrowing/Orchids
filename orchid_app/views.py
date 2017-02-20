from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from . import models

# @login_required
def list(request, year=None, month=None):
    qs = models.Sensors.objects.filter(user=request.user)
    if year:
        qs = qs.filter(date__year=year)
    if month:
        qs = qs.filter(date__month=month)
    total = qs.count()
    return render(request)
    # , "expenses/expense_list.html", {
    #     'year': year,
    #     'month': month,
    #     'total': total,
    #     'objects': qs,
    # })
