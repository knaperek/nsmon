print('Importing Constants')

###################### <Site settings> ############################################ 
# Hack for Site. Ensures that current site will be the first site.
# This is workaround that preventes system failure if somebody deletes default site and creates new one. (Now, this new site will be auto-set as default)
#
# Update: this solution can't be used, because it causes syncdb to crash
# 
# from django.contrib.sites.models import Site
# from django.conf import settings
# try:
#     settings.SITE_ID = Site.objects.all()[0].pk
# except:
#     pass
##################### </Site settings> ########################################### 


# Commands:
SYSCMD_NSMON_ENQUEUE = 'nsmon-enqueue'

# Service Test Results:
RESULT_OK = 0
RESULT_ERR = 1
RESULT_ERR_AUTH = 2 # unauthorized
RESULT_UA = 3 # UNAVAILABLE (simply test result >= RESULT_UA)
RESULT_UA_NXDOMAIN = 4
RESULT_UA_SOCK_ERROR = 5 # vseobecne socket error
RESULT_UA_REFUSED = 6  # Connection refused (napr. zly port)
RESULT_UA_TIMEOUT = 7
RESULT_INTERNAL_ERROR = 8 # Problem na strane testeru

TEST_RETCODE_CHOICES = (
    (RESULT_OK, 'OK'),
    (RESULT_ERR, 'Wrong response'),
    (RESULT_ERR_AUTH, 'Authentication error'),
    (RESULT_UA, 'Unavailable'),
    (RESULT_UA_NXDOMAIN, 'Unavailable (Server does not exist)'),
    (RESULT_UA_SOCK_ERROR, 'Unavailable (Socket error)'),
    (RESULT_UA_REFUSED, 'Unavailable (Connection refused)'),
    (RESULT_UA_TIMEOUT, 'Unavailable (No response)'),
    (RESULT_INTERNAL_ERROR, '--Internal Error!--'),
    );


# Service Statuses:
SERVICE_STATUS_OK = 1 # all q_s are OK
SERVICE_STATUS_UA = 2 # q_responding is bad (other q_s doesnt matter - irrelevant when not-responding)
SERVICE_STATUS_ERR = 3 # q_responding_ok is bad
SERVICE_STATUS_LATE = 4 # q_responding_on_time is bad
SERVICE_STATUS_ERR_LATE = 5 # both q_responding_ok and q_responding_on_time are bad

SERVICE_STATUS_CHOICES = (
    (SERVICE_STATUS_OK, 'OK'),
    (SERVICE_STATUS_UA, 'Unavailable'),
    (SERVICE_STATUS_ERR, 'Wrong response'),
    (SERVICE_STATUS_LATE, 'Late response'),
    (SERVICE_STATUS_ERR_LATE, 'Wrong and late response'),
    );
# TODO: service status unknown (not yet tested... for now, implicitly OK...maybe it's ok) (if will be added, search for STATUS_UNKNOWN in models to change it!)

# Service Types:
SERVICE_TYPES_CHOICES = (
    (1, 'HTTP'),
    (2, 'HTTPS'),
    (3, 'FTP'),
    (4, 'FTP-TLS'),
    (5, 'TFTP'),
    (6, 'Telnet'),
    (7, 'SSH'),
    (8, 'SFTP'),
    (9, 'IMAP'),
    (10, 'IMAP-SSL'),
    (11, 'POP'),
    (12, 'POP-SSL'),
    (13, 'SMTP'),
    (14, 'SMTP-SSL'),
    (15, 'DNS'),
    (16, 'LDAP'),
    (17, 'Ping'),
    );


# 3 counters names (user-friendly naming) (used in more places in code)
NAME_RESPONDING = 'responding at all'
NAME_RESPONDING_ON_TIME = 'responding on time'
NAME_RESPONDING_OK = 'answering ok'


# STC specific "choices"

# Ping. Which time will be returned as duration?
PING_TAKE_RTT_MIN = 1
PING_TAKE_RTT_AVG = 2
PING_TAKE_RTT_MAX = 3

PING_AGGREGATION_CHOICES = (
    (PING_TAKE_RTT_MIN, 'min'),
    (PING_TAKE_RTT_AVG, 'average'),
    (PING_TAKE_RTT_MAX, 'max'),
    );


