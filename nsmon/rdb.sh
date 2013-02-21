#!/bin/bash
echo 'Recreating DB'
dropdb nsmondb &&
createdb nsmondb &&

# drop all tables form my app
# python manage.py sqlclear serviceconfig | python manage.py dbshell

python manage.py syncdb

