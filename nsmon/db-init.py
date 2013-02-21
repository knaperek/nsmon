#!/usr/bin/env python
# This script sets up the default group 'users' with appropriate permissions

print('Setting default group "users"')

import set_django_enviroment

from django.contrib.auth.models import Group, Permission

default_group = Group.objects.create(name='users')
perms = Permission.objects.filter(content_type__app_label='serviceconfig') # all permissions for whole app
# default_group.permissions = list(perms)
default_group.permissions = perms
default_group.save()

