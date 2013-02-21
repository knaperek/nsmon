#!/usr/bin/env python
#
# This is helper script for calling scripts in this project from outside of web server context (e.g. from CRON)
#

import os, sys

def set_django_enviroment():
    print('Dbg: scheduler: setting django enviroment')
    NSMON_ROOT = os.path.realpath(os.path.dirname(__file__))
    NSMON_PARENTDIR = os.path.abspath(os.path.join(NSMON_ROOT, os.pardir))

    for path in (NSMON_ROOT, NSMON_PARENTDIR):
        if path not in sys.path:
            sys.path.append(path)

    os.environ['DJANGO_SETTINGS_MODULE'] = 'nsmon.settings'


set_django_enviroment()
