from django.db import models
from django.db.models import Q, F, Max # aggregation/annotation functions
from django.db.models.signals import post_delete, pre_delete
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User, Group
from django.contrib.sites.models import Site
from django.template import Context, loader
# from django.dispatch import receiver
from django.core.mail import send_mail
import re
import datetime
import time
import sys

from constants import *
import options
import ns_test_routines


##########################################################################################################################################################
######## <Registration: account activation handler.> #####################################################################################################
from registration.signals import user_activated
def make_staff(user, **ignore):
    """ Adds new users automatically to default group "users" and make them staff, in order to provide for standard admin interface. """
    try:
        user.is_staff = True
        g = Group.objects.get(name='users') 
        user.groups.add(g)
    except Group.DoesNotExist:
        print('WARNING: Default group "users" does not exist. Cannot add new users to this group!')
    finally:
        user.save()
user_activated.connect(make_staff)
######## </Registration> ################################################################################################################################
##########################################################################################################################################################



CRON_ADD_CRONTAB_WRAPPER_COMMAND = 'crontab-wrapper/nsmon-add-crontab-wrapper'


########################################################################################################################################################
# Main "central" class - Service
########################################################################################################################################################

class Server(models.Model):
    user = models.ForeignKey(User)
    hostname = models.CharField(max_length = 50, help_text="Server's name or IP address")
    enabled = models.BooleanField(default=True)

    def __unicode__(self):
        return self.hostname

    def get_username(self):
        """ shortcut for self.user.username Used also as column in ServiceAdmin """
        return self.user.username
    get_username.admin_order_field = 'user__username'  # sorting by username is not the same as sorting by user! (user is sorted by ID)
    get_username.short_description = 'user'


class Service(models.Model):
    """ Represents main Service abstraction """
    server = models.ForeignKey(Server)

    service_type = models.SmallIntegerField(choices = SERVICE_TYPES_CHOICES, help_text='Application protocol')

    propagate_errors = models.BooleanField(default=True, help_text='Test failure of this service will immediately trigger tests for services on the same server.')
    accept_error_propagation = models.BooleanField(default=True, help_text='This service will accept testing requests triggered by services on the same server.')

    # repeat after test failure
    repeat_times = models.SmallIntegerField(default=3) # not Positive, because of "0" value possibility
    repeat_interval = models.PositiveSmallIntegerField(default=10, help_text='seconds') # seconds

#     hold_notification_for = models.PositiveSmallIntegerField(default=120, help_text='seconds')

    # notification
    notify_if_lasts = models.PositiveIntegerField('notify me if service is down more than', default=2, help_text='minutes')
#     notify_about = models.PositiveSmallIntegerField( # do buducna: pridat

    enabled = models.BooleanField(default=True)

    def __unicode__(self):
        return self.get_service_type_display() + ' on ' + unicode(self.server)

    def get_username(self):
        """ shortcut for self.server.user.username Used also as column in ServiceAdmin """
        return self.server.user.username
    get_username.admin_order_field = 'server__user__username'  # sorting by username is not the same as sorting by user! (user is sorted by ID)
    get_username.short_description = 'user'






    ################## Service's entry point for scheduler. Performs testing of itself. ##################################

#     def test_oneself_callback(self, is_repeated=False, can_propagate_errors=True):
    def test_oneself_callback(self, is_repeated=False, is_triggered=False):
        """
        Callback method for Scheduler. Performs testing of itself, automatically handling results.
        Returns special list of additional jobs needed to be executed (due to errors occured in test - supporting test repetition and error propagation).
        This method is run within scheduler's thread context! (not web-server's one).

        Params: is_repeated: service is tested again due to test failure.
                             In this situation, service will not try to re-repeat yourself nor propagate errors to other related services.

                is_triggered: service test is called due to error propagation raised by another service.
                              Setting it to true will disable further error propagation, preventing loops to occure when more related services are down.
        """

        print('Dbg: Service.test_oneself_callback({})'.format(self))
        sys.stdout.flush() # TODO: for debug only (or maybe not?)

        if self.enabled and self.server.enabled: # perform test only if it's enabled
            params = self.get_stc() # get (connection) parrams for test
            print('Dbg: Service.test_oneself_callback: launching ns_test_routines.doTest({})'.format(self))
            retcode, duration = ns_test_routines.doTest(self.service_type, **params)

            # write result to DB
#             _write_result(service, retcode, duration, is_repeated)
            was_ok = self.put_test_result(retcode, duration) # returns retcode == RESULT_OK and on_time

            self.notify_if_needed() # TODO: improve..

            if not was_ok and not is_repeated: # Test repetition is being considered
                now = int(time.time())

                # repeat itself
                self_repetition_times = [ now + (i+1)*self.repeat_interval for i in range(self.repeat_times) ] # list of time-values specifying test repetition times
                self_activated_jobs = [ (runFrom, None, self, {'is_repeated':True}) for runFrom in self_repetition_times ] # prepare list to return back to scheduler with new jobs to plan

                activated_jobs = self_activated_jobs

                # Error propagation: reschedule related services
                if self.propagate_errors and not is_triggered: # propagation of errors is allowed for this service
                    services_to_test = Service.objects.select_related().filter(
                            ~Q(pk=self.pk), # except itself
                            server=self.server, accept_error_propagation=True) # all other services with the same server
                    # other services will have is_triggered set to prevent for loop when more than 1 service on the same server are down (they would propagate errors one to another forever)
                    related_activated_jobs = [ (None, None, service, {'is_triggered': True}) for service in services_to_test ] # list of all services on the same server accepting error propagation (in form for returning)
                    activated_jobs += related_activated_jobs # join both lists

####            returning list of tuples: (runFrom, runTill, service, kwargs) # kwargs is dict with extra params (e.g. is_repeated, is_triggered) that callback wish (and will) to be called with
                return activated_jobs
        else:
            print('Dbg: Service is disabled, not performing test.')

        return [] # Nothing to re-run (test was ok, so there's no need to repeat it)
            

    def get_stc(self):
        """ Fetches Service Test Configuration from DB and returns it as dict """
        try:
            config_class = SERVICE_TYPES_CONFIG_CLASSES[self.service_type]
            config = config_class.objects.get(service=self)
            params = {field.attname: field.value_from_object(config) for field in config._meta.fields if field.attname != 'service_id'} # vyber vsetkych konfiguracnych parametrov pre test sluzby
            params['host'] = self.server.hostname
            return params

        except config_class.DoesNotExist: # config for service does not exist
            print('Dbg: Config for specified service does not exist!')
            return None # TODO: ?


    def get_new_status(self, test_result=None):
        """ Computes and returns new status from given (or last if not given) TestResult entry and ServiceRequirements """
        # helper functions used to measure coutners values against thresholds
        BAD = lambda value, threshold: value < threshold
        GOOD = lambda value, threshold: not BAD(value, threshold)

        # First, get test_result
        try:
            if test_result == None: # test_result not supplied, getting the last one
                test_result = self.testresult_set.latest() # TODO: handle DoesNotExist
        except ObjectDoesNotExist:
            return SERVICE_STATUS_OK # TODO: STATUS_UNKNOWN ???

        sr = self.servicerequirements
#         sr.t_responding
#         sr.t_responding_on_time
#         sr.t_responding_ok

        bad_r = BAD(test_result.q_responding, sr.t_responding)
        bad_ont = BAD(test_result.q_responding_on_time, sr.t_responding_on_time)
        bad_ok = BAD(test_result.q_responding_ok, sr.t_responding_ok)

        if bad_r:
            new_status = SERVICE_STATUS_UA
        elif bad_ont and bad_ok:
            new_status = SERVICE_STATUS_ERR_LATE
        elif bad_ont:
            new_status = SERVICE_STATUS_LATE
        elif bad_ok:
            new_status = SERVICE_STATUS_ERR
        else:
            new_status = SERVICE_STATUS_OK # default

        return new_status


    ########## <Status info methods> ##############################################################################################
    def current_status(self):
        """ Returns current Service status as string (get_FOO_display) """
        try:
            return self.servicestatussummary_set.latest().get_status_changed_to_display()
        except: # todo
            return None

    def current_status_duration(self):
        summary = self.get_last_status_summary()
        if summary:
            return summary.status_duration
        return 0 # None?

    def get_last_status_summary(self):
        """ Returns last Service's status summary """
        try:
            return self.servicestatussummary_set.latest()
        except:
            return None
    last_summary = get_last_status_summary

    def get_last_testresult(self):
        """ Returns last Service's TestResult """
        try:
            return self.testresult_set.latest()
        except TestResult.DoesNotExist:
            return None

    def get_status_from_time(self, timestamp=None):
        """ Returns Service status that was actual at <timestamp> (default is right now). """
        if timestamp == None:
            timestamp = datetime.datetime.now()
        try:
            return self.servicestatussummary_set.filter(timestamp__lte = timestamp).latest().status_changed_to
        except ServiceStatusSummary.DoesNotExist:
            return None # SERVICE_STATUS_OK # ? TODO: service status unknown?

    ########## </Status info methods> ##############################################################################################

    def put_test_result(self, retcode, duration):
        """
        Accepts result of test, timestamps it and performs corresponding calculations (time of passing to DB is stored as Test's Timestamp).
        Returns True, if test result was good, otherwise returns False (used for potential re-planning of test and other related Services' tests).
        (Note: Test is considered good, if both retcode = RESULT_OK and response was on time)
        """

        MAX = 100
        MIN = 0
        _L = lambda q: min(max(q, MIN), MAX) # helper function to limit values of counters to be in range <MIN; MAX> """

        try:
            max_ok_duration = self.servicerequirements.max_OK_duration
            on_time = duration < max_ok_duration if retcode < RESULT_UA else None # if it's not unavailable, on_time is rentabile. Otherwise None

            # get current values (values from last test)
            try:
                last_test_result = self.testresult_set.latest()
                responding = last_test_result.q_responding
                responding_on_time = last_test_result.q_responding_on_time
                responding_ok = last_test_result.q_responding_ok
            except TestResult.DoesNotExist:
                # default values (for first test)
                responding = MAX
                responding_on_time = MAX
                responding_ok = MAX

            if retcode == RESULT_INTERNAL_ERROR: # Fatal Internal Error
                on_time = None
                duration = None

            else: # "Not internal error" :-)
                # recompute 3 counters
                coefs = self.conditioncalculationcoeficients

                # responding (at all) calculation
                if retcode < RESULT_UA: # Is responding
                    responding = _L(responding + coefs.on_response_increment)
                else: # Unavailable
                    responding = _L(responding - coefs.on_no_response_decrement)

                # responding_on_time calculation
                if on_time != None:
                    if on_time: # On time
                        responding_on_time = _L(responding_on_time + coefs.on_ontime_increment)
                    else: # Late
                        responding_on_time = _L(responding_on_time - coefs.on_late_decrement)

                # responding_ok calculation
                if retcode == RESULT_OK:
                    responding_ok = _L(responding_ok + coefs.on_ok_increment)
                elif retcode == RESULT_ERR:
                    responding_ok = _L(responding_ok - coefs.on_error_decrement)

            # Next: write data do DB 
            # TestResult entry
            test_result = TestResult.objects.create(
                    service = self,
                    duration = duration,
                    on_time = on_time,
                    retcode = retcode,
                    q_responding = responding,
                    q_responding_on_time = responding_on_time,
                    q_responding_ok = responding_ok)

            # Write summary data to DB
            try:
                latest_status = self.servicestatussummary_set.latest().status_changed_to # get latest service status summary
            except ServiceStatusSummary.DoesNotExist: # this is first summary record
                latest_status = None # will be surely replaced

            new_status = self.get_new_status(test_result)

            if latest_status != new_status: # Status of service has changed since last test. Creating new entry.
                ServiceStatusSummary.objects.create(service=self, timestamp = test_result.timestamp, status_changed_to = new_status)

            return retcode == RESULT_OK and on_time # returned valude will be used for test(s) repetition consideration (repeat_times; propagate_errors)
            
        except ObjectDoesNotExist: # error, some config is missing
            print('Dbg: Error! Service.put_test_result: ObjectDoesNotExist exception (missing some config entry in associated table?)')
            return


    def is_bad_long_enough(self):
        """ Returns True if service is in bad status (and it's been) for long enough (according to config). """
#         current_status = self.get_new_status()
        current_status = self.get_status_from_time() # TODO: specify timestamp exactly (from last test's timestamp?)

        if current_status not in (None, SERVICE_STATUS_OK): # None should not be...

            now = datetime.datetime.now() # TODO: get now from last test's timestamp
            long_enough_duration = self.notify_if_lasts # (in minutes)

            search_from_time = now - datetime.timedelta(minutes = long_enough_duration)

            status_on_time_boundary = self.get_status_from_time(search_from_time) # status that was actual at the beginning of search-ing period
            if status_on_time_boundary not in (None, SERVICE_STATUS_OK): # if status was bad (Note: here None is important, because service might not have been configured back then)
                # fetch all Service Status changes for pertinent period
                status_changes_for_period = self.servicestatussummary_set.filter(timestamp__gt = search_from_time)
                is_long_enough = not status_changes_for_period.filter(status_changed_to = SERVICE_STATUS_OK).exists() # status has not been changed during pertinent (searching) period
                
                return is_long_enough # Service is in bad status for long enough! => sending notification is needed!

        return False # default (service is not bad for long enough)


    def get_bad_related_services(self):
        """ Returns all services (owned by same user "self") that are in bad status """
        print('Dbg: get_bad_related_services'.center(100, '_'))

        # get all related servcies
        related_services = Service.objects.select_related().filter(
#                 ~Q(pk=self.pk), # except itself # Changed. Service itself will be part of the list returned
                server__user=self.server.user,
                enabled=True # fetch only enabled services (we dont care if disabled service is bad)
                )

        # add annotation column with timestamp of Last change
        related_services = related_services.annotate(last_change_at=Max('servicestatussummary__timestamp'))

        # filter for services with current status bad
        bad_related_services = related_services.filter(
#                 ~Q(servicestatussummary__status_changed_to=SERVICE_STATUS_OK), # Why is this not working ?! (TODO: figure out!)
#                 Q(servicestatussummary__status_changed_to=SERVICE_STATUS_ERR), # this works only for status_err
                servicestatussummary__status_changed_to__gt=SERVICE_STATUS_OK, # greater than OK is bad (dirty way...but clean one above does not work)
                servicestatussummary__timestamp=F('last_change_at'),
                )

        print('Dbg: Bad related services({}):'.format(self.get_service_type_display()))
        for s in bad_related_services:
            print('{}, {}'.format(s.get_service_type_display(), repr(s.last_change_at)))
#         print('Dbg: get_bad_related_services({}): {}'.format(self.get_service_type_display(), bad_related_services))


#         # Do buducna: optimalizacia: vracat posledne polozky servicestatussummary, namiesto service (da sa dat potom na ne hromadny update(notified=True)
#         ## get last servicestatussummary of each bad related service
#         status_changes = ServiceStatusSummary.objects.filter(
#                 ~Q(service=self),
#                 service__server=self.server,
#                 service__enabled=True
#                 )

        return bad_related_services
        

    def notify_if_needed(self):
        """ Triggers notification about this and other bad services, if this service is bad for long enough. """
        if not self.is_bad_long_enough(): # TODO: uncomment (debug only)
            print('Dbg: Service {} is not bad long enough'.format(self))
            return

        bad_buddies = self.get_bad_related_services()

        print('notify_if_needed({})'.format(self.get_service_type_display()))
        for buddy in bad_buddies: # todo: optimize (bulk update...)
            print('Buddy: {}, last_change_at: {}, Match: {}'.format(buddy.get_service_type_display(), buddy.last_change_at, buddy.last_change_at == buddy.servicestatussummary_set.latest().timestamp))


        last_login = self.server.user.last_login
        print('Last login: {}'.format(last_login))

        # Select only those that user was not notified about since last login
        # Preventing of notifying multiple times for one service (if user was notified about a service and did not log in yet, he will not be notified about that service again)
        buddies_not_notified_since_last_login = bad_buddies.exclude(servicestatussummary__timestamp__gt=last_login, servicestatussummary__notified=True) # bad buddies that user was not notified about since last login

        # Select only those that changed status since last login
        buddies_to_notify = buddies_not_notified_since_last_login.filter(servicestatussummary__timestamp__gt=last_login)


#         not_notified_buddies = [] # initialization
#         for buddy in buddies_not_notified_since_last_login:
        if self not in buddies_to_notify:
            print('Dbg: Service {}, that triggered notification, is not in buddies_to_notify. Stopping.'.format(self.get_service_type_display()))
            return

        for buddy in buddies_to_notify:
            print('Updating {} -> notified=True'.format(buddy))
            last_change = buddy.servicestatussummary_set.get(timestamp=buddy.last_change_at)
            last_change.notified = True
            last_change.save()

#         print('self test')
#         for s in buddies_to_notify:
#             if s == self:
#                 print('s == self | s.last_change_at: {}'.format(s.last_change_at))
#         print('self.last_change_at: {}'.format(self.last_change_at))

        self.send_mail_notification(buddies_to_notify)


    def send_mail_notification(self, services):
        """ Sends out notification email containing services passed as param "services". Self MUST BE in the list, otherwise no email is sent (by intention) """
        print('send_mail_notification')
        if self not in services:
            print('send_mail_notification Error: self is not in services. Terminating.')
            return

        try:
            site = Site.objects.all()[0]
        except IndexError:
            site = None

        t = loader.get_template('admin/notification_email.html')
        c = Context({
            'site': site,
            'service': self,
            'others': filter(lambda s: s != self, services), # exclude self from services
        })
        message = t.render(c)
        print('Calling send_mail(..)')
        send_mail('[NSMon] Notification', message, 'NSMon Daemon', [self.server.user.email], fail_silently=False)


    # pre_delete handler: 
    @staticmethod
    def pre_delete_related_plans(sender, instance, **kwargs):
        """ Deletes realted TestingPlan instances before deleting itself, in order to avoid error in sync_crontab """
        print('Service-pre_delete signal caught. Deleteing {}'.format(instance))
        print('  related testingplans: {}'.format(instance.testingplan_set.all()))
        instance.testingplan_set.all().delete()
pre_delete.connect(Service.pre_delete_related_plans, sender=Service)


######################################################################################################################################################################
######################################################################################################################################################################
########################################################    </Service>    ############################################################################################
######################################################################################################################################################################
######################################################################################################################################################################

## Service Tester Configs (STCs):

# Abstraktne triedy:
class BaseSTC(models.Model):
    service = models.OneToOneField(Service, primary_key=True)

    class Meta:
        abstract = True
#         verbose_name = sname

    def __unicode__(self):
#         return self.__class__.__name__[4:] + ' config of ' + str(self.service)
        return 'Config of {}:{}'.format(self.service, self.port)


class AuthSTC(models.Model):
    user = models.CharField(max_length = 30)
    password = models.CharField(max_length = 40)

    class Meta:
        abstract = True

class TargetSTC(models.Model):
    target = models.CharField(max_length = 200)

    class Meta:
        abstract = True


# STC_* testery
class STC_HTTP(BaseSTC, TargetSTC):
#     sname = 'HTTP'
    port = models.PositiveIntegerField(default=80)
    class Meta:
        verbose_name = "config: HTTP"
        verbose_name_plural = "configs: HTTP"

class STC_HTTPS(BaseSTC, TargetSTC):
#     sname = 'HTTPS'
    port = models.PositiveIntegerField(default=443)
    class Meta:
        verbose_name = "config: HTTPS"
        verbose_name_plural = "configs: HTTPS"

class STC_FTP(BaseSTC):
#     sname = 'FTP'
    port = models.PositiveIntegerField(default=21)
    user = models.CharField(max_length = 30, blank=True) # TODO: null=True (DB recreation needed)
    password = models.CharField(max_length = 40, blank=True) # TODO: null=True (DB recreation needed)
    class Meta:
        verbose_name = "config: FTP"
        verbose_name_plural = "configs: FTP"

class STC_FTP_TLS(BaseSTC, AuthSTC):
#     sname = 'FTP-TLS'
    port = models.PositiveIntegerField(default=21)
    class Meta:
        verbose_name = "config: FTP-TLS"
        verbose_name_plural = "configs: FTP-TLS"

class STC_TFTP(BaseSTC, TargetSTC):
#     sname = 'TFTP'
    port = models.PositiveIntegerField(default=69)
    class Meta:
        verbose_name = "config: TFTP"
        verbose_name_plural = "configs: TFTP"

class STC_Telnet(BaseSTC, AuthSTC):
#     sname = 'Telnet'
    port = models.PositiveIntegerField(default=23)
    class Meta:
        verbose_name = "config: Telnet"
        verbose_name_plural = "configs: Telnet"

class STC_SSH(BaseSTC, AuthSTC):
#     sname = 'SSH'
    port = models.PositiveIntegerField(default=22)
    class Meta:
        verbose_name = "config: SSH"
        verbose_name_plural = "configs: SSH"

class STC_SFTP(BaseSTC, AuthSTC):
#     sname = 'SFTP'
    port = models.PositiveIntegerField(default=22)
    class Meta:
        verbose_name = "config: SFTP"
        verbose_name_plural = "configs: SFTP"

class STC_IMAP(BaseSTC, AuthSTC):
#     sname = 'IMAP'
    port = models.PositiveIntegerField(default=143)
    class Meta:
        verbose_name = "config: IMAP"
        verbose_name_plural = "configs: IMAP"

class STC_IMAP_SSL(BaseSTC, AuthSTC):
#     sname = 'IMAP-SSL'
    port = models.PositiveIntegerField(default=993)
    class Meta:
        verbose_name = "config: IMAP-SSL"
        verbose_name_plural = "configs: IMAP-SSL"

class STC_POP(BaseSTC, AuthSTC):
#     sname = 'POP'
    port = models.PositiveIntegerField(default=110)
    class Meta:
        verbose_name = "config: POP"
        verbose_name_plural = "configs: POP"

class STC_POP_SSL(BaseSTC, AuthSTC):
#     sname = 'POP-SSL'
    port = models.PositiveIntegerField(default=995)
    class Meta:
        verbose_name = "config: POP-SSL"
        verbose_name_plural = "configs: POP-SSL"

# class STC_SMTP(BaseSTC, AuthSTC):
class STC_SMTP(BaseSTC):
#     sname = 'SMTP'
    port = models.PositiveIntegerField(default=25)
    user = models.CharField(max_length = 30, blank=True) # TODO: null=True (DB recreation needed)
    password = models.CharField(max_length = 40, blank=True) # TODO: null=True (DB recreation needed)
    class Meta:
        verbose_name = "config: SMTP"
        verbose_name_plural = "configs: SMTP"

class STC_SMTP_SSL(BaseSTC, AuthSTC):
#     sname = 'SMTP-SSL'
    port = models.PositiveIntegerField(default=465)
    class Meta:
        verbose_name = "config: SMTP-SSL"
        verbose_name_plural = "configs: SMTP-SSL"

class STC_DNS(BaseSTC, TargetSTC):
#     sname = 'DNS'
    port = models.PositiveIntegerField(default=53)
    class Meta:
        verbose_name = "config: DNS"
        verbose_name_plural = "configs: DNS"

class STC_LDAP(BaseSTC, TargetSTC):
#     sname = 'LDAP'
    port = models.PositiveIntegerField(default=389)
    class Meta:
        verbose_name = "config: LDAP"
        verbose_name_plural = "configs: LDAP"

class STC_Ping(BaseSTC):
#     sname = 'Ping'
    count = models.PositiveSmallIntegerField("Pings count", default=1)
    rtt_aggregation = models.PositiveSmallIntegerField("RTT aggregation", default=PING_TAKE_RTT_MAX, choices=PING_AGGREGATION_CHOICES)
    
    class Meta:
        verbose_name = "config: Ping"
        verbose_name_plural = "configs: Ping"

    def __unicode__(self):
        return 'Config of {}'.format(self.service)

#####################################################################################################


class ConditionCalculationCoeficients(models.Model):
    """ Provides calculation coeficients for 3 coutners """
    service = models.OneToOneField(Service, primary_key=True)

    # q_responding calculations:
    on_response_increment = models.SmallIntegerField(default=1)
    on_no_response_decrement = models.SmallIntegerField(default=10)

    # q_responding_on_time calculations:
    on_ontime_increment = models.SmallIntegerField(default=1)
    on_late_decrement = models.SmallIntegerField(default=10)

    # q_responding_ok calculations:
    on_ok_increment = models.SmallIntegerField(default=1)
    on_error_decrement = models.SmallIntegerField(default=10)

    class Meta:
        verbose_name = 'condition calculation coeficients'
        verbose_name_plural = verbose_name

    def __unicode__(self):
#         return self.__class__.__name__ + ' for ' + unicode(self.service)
        return 'For ' + unicode(self.service)
#         return self._meta.verbose_name.capitalize() + ' for ' + unicode(self.service)


class ServiceRequirements(models.Model):
    """ Service must comply these requirements to be considered OK """
    service = models.OneToOneField(Service, primary_key=True)

    max_OK_duration = models.FloatField(default=3, help_text='seconds (float)') # seconds
    
    # 3 quality coeficient THRESHOLDS
    t_responding = models.SmallIntegerField(NAME_RESPONDING, default=70)
    t_responding_on_time = models.SmallIntegerField(NAME_RESPONDING_ON_TIME, default=70)
    t_responding_ok = models.SmallIntegerField(NAME_RESPONDING_OK, default=70)

    class Meta:
        verbose_name_plural = 'service requirements'

    def __unicode__(self):
#         return self.__class__.__name__ + ' for ' + unicode(self.service)
        return 'For ' + unicode(self.service)
#         return self._meta.verbose_name.capitalize() + ' for ' + unicode(self.service)



def validate_CRON_string(value):
    """ Validation for CRON string in TestingPlan """
    if value.strip() != value:
        raise ValidationError('Leading nor trailing spaces are allowed')
    columns = value.split()
    if columns != value.split(' '):
        raise ValidationError('Use only a single space as a column separator')

    if len(columns) != 5:
        raise ValidationError('Entry has to consist of exactly 5 columns')

    pattern = r'^(\*|\d+(-\d+)?(,\d+(-\d+)?)*)(/\d+)?$'
    p = re.compile(pattern)
#     for c in columns:
    for i, c in zip(range(len(columns)), columns): # foreach with iteration coutner (i)
        if not p.match(c):
            raise ValidationError("Incorrect value {} in column {}".format(c, i+1))

class TestingPlan(models.Model):
    """ CRON proxy """
    service = models.ForeignKey(Service)

    description = models.CharField(max_length = 100) # consider blank=True, null=True
    CRON_string = models.CharField(max_length = 100, default='* * * * *', help_text="Minute Hour Day Month Weekday", validators=[validate_CRON_string])
    allowed_delay = models.PositiveSmallIntegerField('max. delay', default=5, help_text='minutes') # minutes

    def __unicode__(self):
#         return self.__class__.__name__ + ' for ' + unicode(self.service)
        return self.description

    class Meta:
#         order_with_respect_to = 'servcie'
        ordering = ['service']

    @staticmethod
    def _commit_crontab(user_id, crontab):
        """ Static helper function for passing User's crontab to CRON. Simply executes corresponing command, passing it all required params """
        import os
#         print(os.getcwd())
        from django.conf import settings  # recommended way of importing (even local) settings
#         os.chdir(settings.SITE_ROOT)
        # TODO: osetrit...
        wrapper_cmd = os.path.join(settings.SITE_ROOT, CRON_ADD_CRONTAB_WRAPPER_COMMAND)
#         print('Dbg: wrapper cmd: {}'.format(wrapper_cmd))

        import subprocess
        p = subprocess.Popen([wrapper_cmd, str(user_id)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print('New crontab:')
        print(crontab)
        p.stdin.write(crontab)
        p.stdin.close()
        err = p.stderr.read()
        if err:
            print('TestingPlan._commit_crontab: calling wrapper returned: {}'.format(err))

    def get_username(self):
        """ shortcut for self.service.server.user.username Used also as column in ServiceAdmin """
        return self.service.server.user.username
    get_username.admin_order_field = 'service__server__user__username'  # sorting by username is not the same as sorting by user! (user is sorted by ID)
    get_username.short_description = 'user'

    def _generate_CRON_entry(self):
        """ Private helper method for generating CRON entry for single TestingPlan (designated for direct passing to crontab file) """
        # Zmena: do cronu ide testID, nie serviceID (aj kvoli moznosti zistenia allowed delay, a do buducna podpora m-n)
        return '{} {} {}\n'.format(self.CRON_string, SYSCMD_NSMON_ENQUEUE, self.id)

    def sync_crontab(self):
        """ Performs DB to CRON syncing of all User's cronjobs """
        try:
            user = self.service.server.user
            print('TestingPlan.sync_crontab(): Recreating CRONTAB for user {}'.format(user))
            all_plans_for_same_user = TestingPlan.objects.filter(service__server__user = user)
            crontab_generator = ( plan._generate_CRON_entry() for plan in all_plans_for_same_user )
            TestingPlan._commit_crontab(user.id, ''.join(crontab_generator)) # TODO: osetrit
        except Service.DoesNotExist:
            # Service is probably deleted already. It should not be a problem, crontab should be synced already.
            pass

    def save(self, *args, **kwargs):
        super(TestingPlan, self).save(*args, **kwargs)
        self.sync_crontab()

#     def delete(self, *args, **kwargs):
#         print('Overriden delete method')
#         super(TestingPlan, self).delete(*args, **kwargs)
#         self.sync_crontab()

#     @receiver(django.db.models.signals.post_delete, sender='TestingPlan')
    @staticmethod
    def on_delete(sender, **kwargs):
        """ Method connected to post_delete signal. Calls sync_crontab to do the rest. """
        print('TestingPlan-post_delete signal caught!')
        kwargs['instance'].sync_crontab()
post_delete.connect(TestingPlan.on_delete, sender=TestingPlan)
#
# TODO: vyriesit. Mohlo by sa to robit aj na signal pre_delete s tym, ze by sa volalo syncovanie s parametrovm exclude(self).
#       Vyhodou by bolo to, ze cely retazec related objektov by existoval a nepadlo by to.
#       Dalsia moznost je, ze ak by to bolo m<-->n, tak potom by asi aj tak TestingPlan este musel mat vlastnu referenciu rovno na usera. Vznikla by vsak slucka :-(





class DBCleanupPolicy(models.Model):
    service = models.OneToOneField(Service, primary_key=True)

    archive_results_for = models.PositiveSmallIntegerField(default=30, help_text='days') # new: value in days
    archive_status_summary_for = models.PositiveSmallIntegerField('archive status changes for', default=365, help_text='days')

    class Meta:
        verbose_name = 'DB cleanup policy'
        verbose_name_plural = 'DB cleanup policies'

    def __unicode__(self):
        return 'Cleanup policy for ' + unicode(self.service)


#################################################################################################
## "Volatile" Data.
#################################################################################################

class TestResult(models.Model):
    """ Result of single test """
    service = models.ForeignKey(Service)

    timestamp = models.DateTimeField(auto_now_add=True) # consider: auto_now_add = True
    duration = models.FloatField('duration (sec.)', null=True, blank=True, help_text='seconds') # None when no response, else seconds
    on_time = models.NullBooleanField()
    retcode = models.SmallIntegerField('result', choices=TEST_RETCODE_CHOICES)
    # TODO: consider to add status field (yea, it can be retrieved from ServiceStatusSummary, but even though...)

    # quality coeficients (recalculated after Test)
    q_responding = models.SmallIntegerField(NAME_RESPONDING, help_text='%')
    q_responding_on_time = models.SmallIntegerField(NAME_RESPONDING_ON_TIME, help_text='%')
    q_responding_ok = models.SmallIntegerField(NAME_RESPONDING_OK, help_text='%')

#     rerun_seqnum = models.PositiveSmallIntegerField(default=0) # Number of test repetition (0 means no repetition)

    class Meta:
        get_latest_by = 'timestamp'
        ordering = ['-timestamp']

    def __unicode__(self):
#         return self.__class__.__name__ + ' for ' + unicode(self.service)
        return self._meta.verbose_name.capitalize() + ' for ' + unicode(self.service)


class ServiceStatusSummary(models.Model):
    """ Agregated summary. Records only status changes. """
    service = models.ForeignKey(Service)

    timestamp = models.DateTimeField(help_text='Time of change')
    status_changed_to = models.SmallIntegerField(choices=SERVICE_STATUS_CHOICES) # choices of statuses
    notified = models.BooleanField(default=False) # Has Owner been notified about this statuch change?

    class Meta:
        verbose_name = 'service status change'
        verbose_name_plural = 'service status changes'
        get_latest_by = 'timestamp'

    def __unicode__(self):
#         return self.__class__.__name__ + ' for ' + unicode(self.service)
        return self._meta.verbose_name.capitalize() + ' for ' + unicode(self.service)

    def is_status_ok(self):
        return bool(self.status_changed_to == SERVICE_STATUS_OK)
    is_status_ok.boolean = True
    is_status_ok.short_description = 'OK'
    is_status_ok.admin_order_field = 'status_changed_to'

    @property
    def status_duration(self):
        now = datetime.datetime.now()
        delta = now - self.timestamp
        delta_round = datetime.timedelta(delta.days, delta.seconds)
        return delta_round




SERVICE_TYPES_CONFIG_CLASSES = {
    1: STC_HTTP,
    2: STC_HTTPS,
    3: STC_FTP,
    4: STC_FTP_TLS,
    5: STC_TFTP,
    6: STC_Telnet,
    7: STC_SSH,
    8: STC_SFTP,
    9: STC_IMAP,
    10: STC_IMAP_SSL,
    11: STC_POP,
    12: STC_POP_SSL,
    13: STC_SMTP,
    14: STC_SMTP_SSL,
    15: STC_DNS,
    16: STC_LDAP,
    17: STC_Ping,
    };


# TODO: SmallIntegerField
# TODO: Consider ServiceExtension(models.Model): service = FK(Service), __unicode__()...  Abstract base class
# TODO: consider Log tables (TestResult, ServiceStatusSummary) to return explicitly ordered querysets (ordered by timestamp)
