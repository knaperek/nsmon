#
# This wsgi application is deprecated since using Django 1.4. Pleasu use original wsgi.py file, in project directory (which is already configured for working with apache)
#
import os
import sys

NSMON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
NSMON_PARENTDIR = os.path.abspath(os.path.join(NSMON_ROOT, os.pardir))

for path in (NSMON_PARENTDIR, NSMON_ROOT):
    if path not in sys.path:
        sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'nsmon.settings'

import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()

print('Debug: running NSMon django.wsgi')

