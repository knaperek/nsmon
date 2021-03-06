"""
WSGI config for nsmon project.

This module contains the WSGI application used by Django's development server
and any production WSGI deployments. It should expose a module-level variable
named ``application``. Django's ``runserver`` and ``runfcgi`` commands discover
this application via the ``WSGI_APPLICATION`` setting.

Usually you will have the standard Django WSGI application here, but it also
might make sense to replace the whole Django WSGI application with a custom one
that later delegates to the Django one. For example, you could introduce WSGI
middleware here, or combine a Django application with an application of another
framework.

"""
import os
import sys
# import site

print('Debug: running NSMon wsgi.py')
import django
print('   running wsgi application with django version: {}'.format(django.VERSION))
# print('   path: {}'.format(sys.path))

NSMON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
# NSMON_PARENTDIR = os.path.abspath(os.path.join(NSMON_ROOT, os.pardir))
# virtualenv_libs_path = os.path.join(NSMON_PARENTDIR, 'lib/python2.7/site-packages')

if NSMON_ROOT not in sys.path:
    # sys.path.insert(0, NSMON_ROOT)
    sys.path.append(NSMON_ROOT)

# sys.path.insert(0, virtualenv_libs_path)
# site.addsitedir(virtualenv_libs_path)
# print('   New path: {}'.format(sys.path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nsmon.settings")

# This application object is used by any WSGI server configured to use this
# file. This includes Django's development server, if the WSGI_APPLICATION
# setting points here.
from django.core.wsgi import get_wsgi_application # aa
application = get_wsgi_application()

# Apply WSGI middleware here.
# from helloworld.wsgi import HelloWorldApplication
# application = HelloWorldApplication(application)


###########################################################################
# povodny wsgi handler:

# import os
# import sys
# 
# NSMON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
# NSMON_PARENTDIR = os.path.abspath(os.path.join(NSMON_ROOT, os.pardir))
# 
# for path in (NSMON_PARENTDIR, NSMON_ROOT):
#     if path not in sys.path:
#         sys.path.append(path)
# 
# os.environ['DJANGO_SETTINGS_MODULE'] = 'nsmon.settings'
# 
# import django.core.handlers.wsgi
# application = django.core.handlers.wsgi.WSGIHandler()
# 
# print('Debug: running NSMon django.wsgi')

