# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-03-25 16:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orchid_app', '0005_auto_20170318_1600'),
    ]

    operations = [
        migrations.AddField(
            model_name='actions',
            name='reason',
            field=models.TextField(default=''),
        ),
    ]
