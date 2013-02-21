#!/bin/bash
# NSMon helper tool for adding crontab entrys of nsmon's users to /etc/cron.d directory, that is writable only for user root (and CRON also does check owner of files in there)
# Must be run as root!
#
tool=nsmon-add-crontab
wrapper=$tool-wrapper
echo "Installing tool $tool"
echo "For adding NSMon's crontab use $wrapper, which has set required setuid permissions"
#make
gcc $wrapper.c -o $wrapper
cp nsmon-add-crontab /sbin/
cp $tool /sbin/
chown root:root $wrapper
chmod +s $wrapper

