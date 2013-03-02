# TODO: change forms for STC_* with added link to Service
from django.contrib import admin
from django.forms import ModelForm
from django.db.models import Sum, Avg, Min, Max, Count # aggregation/annotation functions # TODO: import only those needed
from django.http import HttpResponse
from django.conf.urls import patterns, url, include
from django.shortcuts import render_to_response, render, get_object_or_404, redirect
from django.views.generic import ListView
from django.core import serializers
from django.contrib.admin import SimpleListFilter
import time, datetime, calendar
import json

import admin_views
import serviceconfig
from serviceconfig.models import *
from serviceconfig.views import *


####################################################################################################################################################################################
# TestResultAdmin 
####################################################################################################################################################################################

class ResultFilterOnTestResultsList(SimpleListFilter):
    """ Filters by Result codes on TestResutl's change_list. This filter is simplification of dummy original filter. Retcodes are groped into major types, and only these are shown """
    title = ('result')
    parameter_name = 'result'

    def lookups(self, request, model_admin):
        """ Generates list of items to display in the filter panel """
        return (
            ('ok' , 'OK'),
            ('not_ok', 'not OK'),
            ('error', 'Error'),
            ('unavailable', 'Unavailable'),
        )

        if request.user.is_superuser:
            return ( (unicode(user.id), unicode(user.username)) for user in User.objects.filter(is_superuser=False) ) # filter : not superuser
        else:
            return None

    def queryset(self, request, queryset):
        """ Does filtering based on this filter """
        result_type = self.value()
#         if result_type == None:
#             return queryset
        if result_type == 'ok':
            return queryset.filter(retcode=RESULT_OK)
        elif result_type == 'not_ok':
            return queryset.exclude(retcode=RESULT_OK)
        elif result_type == 'error':
            return queryset.filter(retcode__in=[RESULT_ERR, RESULT_ERR_AUTH, RESULT_INTERNAL_ERROR])
        elif result_type == 'unavailable':
            return queryset.filter(retcode__gte=RESULT_UA)
        else:
            return queryset  # result_type == None

class ServerFilterOnTestResultList(SimpleListFilter):  # used also with ServiceStatusSummaryAdmin and TestingPlanAdmin
    """ Filter on Server. Every user (except superuser) has only his servers displayed """

    title = ('server')
    parameter_name = 'server'

    def lookups(self, request, model_admin):
        # Filtering servers for non-superusers
        qs_servers = Server.objects.all()
        if not request.user.is_superuser:
            qs_servers = qs_servers.filter(user=request.user)
        return ( (unicode(server.id), unicode(server)) for server in qs_servers )
        
    def queryset(self, request, queryset):
        server_id = self.value()
        if server_id != None:
            return queryset.filter(service__server=int(server_id))
        else:
            return queryset

class ServiceFilterOnTestResultList(SimpleListFilter):  # used also with ServiceStatusSummaryAdmin and TestingPlanAdmin
    """ Filter on Service. Every user (except superuser) has only his services displayed """
    title = ('service')
    parameter_name = 'service'

    def lookups(self, request, model_admin):
        # Filtering servers for non-superusers
        qs_services = Service.objects.all()
        if not request.user.is_superuser:
            qs_services = qs_services.filter(server__user=request.user)
        return ( (unicode(service.id), unicode(service)) for service in qs_services )
        
    def queryset(self, request, queryset):
        service_id = self.value()
        if service_id != None:
            return queryset.filter(service=int(service_id))
        else:
            return queryset


class TestResultAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'service', 'retcode', 'duration', 'on_time')
#     list_filter = ('timestamp', 'service', 'service__server', 'retcode', ResultFilterOnTestResultsList, 'on_time')
    list_filter = ('timestamp', ServiceFilterOnTestResultList, ServerFilterOnTestResultList, ResultFilterOnTestResultsList, 'on_time')
    readonly_fields = ('service', 'timestamp', 'retcode', 'duration', 'on_time', 'q_responding', 'q_responding_on_time', 'q_responding_ok')
#     list_editable = ('retcode', 'duration')
    date_hierarchy = 'timestamp'
    actions_on_bottom = False
    actions_on_top = False

    fieldsets = (
            ('Test details', {
                'fields': ('service', 'timestamp', 'retcode', 'duration', 'on_time'),
                'classes': ('wide',)
                }),
#             ('Re-evaluated condition counters', {
#             ('Effect on service condition', {
            ('Service Condition after Test', {
                'fields': ('q_responding', 'q_responding_on_time', 'q_responding_ok'),
                'classes': ('wide',)
                })
    )

    def has_add_permission(self, request):
        return False
#     def has_change_permission(self, request, obj=None):
#         return False
    def has_delete_permission(self, request, obj=None):
        return False

    # To see:
    # def get_changelist

    def queryset(self, request): # filtering Test Results according to logged-in user
        qs = super(TestResultAdmin, self).queryset(request) # default queryset
        if not request.user.is_superuser:
            qs = qs.filter(service__server__user=request.user) # display only testresults owned by user
        return qs

    def get_urls(self):
        urls = super(TestResultAdmin, self).get_urls()

        my_urls = patterns('',
                url(r'^(?P<id>\d+)/my_view/$', self.admin_site.admin_view(self.my_view)),

                url(r'^series-json/(?P<series>\w+)/$', self.admin_site.admin_view(self.series_json), name='series-json'), # legacy url, could be removed
                url(r'^series-json/(?P<service>\d+)/(?P<series>\w+)/$', self.admin_site.admin_view(self.series_json), name='series-json'),

                url(r'^series-json/(?P<series>\w+)/(?P<from_ts>\d+)-(?P<to_ts>\d+)/$', self.admin_site.admin_view(self.series_json)), # legacy url, could be removed
                url(r'^series-json/(?P<service>\d+)/(?P<series>\w+)/(?P<from_ts>\d+)-(?P<to_ts>\d+)/$', self.admin_site.admin_view(self.series_json)),

                url(r'^duration-chart/$', self.admin_site.admin_view(self.duration_chart)),
                url(r'^counters-chart/$', self.admin_site.admin_view(self.counters_chart)),
                url(r'^charts/$', self.admin_site.admin_view(self.charts)),
        )
        return my_urls + urls

    def my_view(self, request, id): # TODO: delete (iba skusobne)
        """ Example of getting needed variables..."""
        module_name = self.model._meta.verbose_name_plural.capitalize() # priprave pre template (na breadcrumbs)
        app_label = self.model._meta.app_label.capitalize()
        str_object = unicode(get_object_or_404(self.model, pk=id))
        return render(request, 'admin/serviceconfig/service_status.html', {'object_id': id, 'current_app': self.admin_site.name, 'module_name': module_name, 'app_label': app_label, 'object': str_object})

    def series_json(self, request, series, service=None, from_ts=None, to_ts=None, aggregation='auto'):
        """ Returns JSON response with requested data series for chart.
            Args: series: string specifying the type of series requested. Can be one of ('duration', 'counters')
                  service: service ID
                  from_ts: from timestamp in MILISECONDS since Epoch (Javascript timestamp)
                  to_ts:   to timestamp (--//--)
                  aggregation: period for aggregation. Can be one of: auto, second, minute, hour, day, week, month, year
        """
        JSON_CHART_MAX_SERIES_LENGTH = 100 # default max. number of points in one chart series. Used for auto-selecting optimal aggregation function

        # fields to fetch depending on series argument
        duration_fields = ('duration',) # fields for series='duration'
        counters_fields = ('q_responding', 'q_responding_on_time', 'q_responding_ok') # fields for series='counters'
        series_fields = {'duration': duration_fields, 'counters': counters_fields}[series] # chosen fields
        AGGR_F = {'duration': Max, 'counters': Min}[series] # relevant aggregation function

#         print(service, from_ts, to_ts, aggregation)

        # Prepare queryset

        qs = TestResult.objects.all() # queryset initialization

        if service != None: # filter by service
            qs = qs.filter(service=service)

        def jsts2dt(ts): # converts Javascript timestamp passed as param to Python datetime object with correct timezone settings
            return datetime.datetime(*time.gmtime(int(ts) // 1000)[:6])

        if from_ts != None: # filter by From-time
            qs = qs.filter(timestamp__gte=jsts2dt(from_ts))
        
        if to_ts != None: # filter by to-time
            qs = qs.filter(timestamp__lte=jsts2dt(to_ts))

        # Selection of proper aggregation function (for reducing number of data being sent to chart)
        used_aggregation = None # (initialization). Just for info. Sent back to template for dispalying current aggregation used
        aggregated_qs = qs
        aggregation_periods = ('second', 'minute', 'hour', 'day', 'week', 'month', 'year') # PostgreSQL date_trunc options

        if aggregation == 'auto': # default (auto select) aggregation function
            i_next_aggregation_period = 0
            while aggregated_qs.count() > JSON_CHART_MAX_SERIES_LENGTH and i_next_aggregation_period < len(aggregation_periods): # Auto-searching for optimal aggregation period
                # use next (more particular) aggregation function
                print('Dbg: searching for optimal aggregation period. Current count = {}'.format(aggregated_qs.count()))
                used_aggregation = aggregation_periods[i_next_aggregation_period]
                aggregated_qs = qs.extra(select={'ts': "date_trunc('{}', timestamp)".format(used_aggregation)}).order_by('ts').values_list('ts').annotate(*map(AGGR_F, series_fields))
                # Note: .values() /or values_list/ method changes the default behavior of .annotate() and makes it to aggregate on unique combinations of fields specified in the values clause.
                #       More on: https://docs.djangoproject.com/en/dev/topics/db/aggregation/#values
                #
                # TODO: after migration to Django 1.4, change this to use distinct('ts') instead of .annotate when looking for optimal aggregation period (in order to speed up things a little)

                i_next_aggregation_period += 1

            if aggregated_qs == qs: # while loop above was not executed at all (aggregated_qs is not aggregated on any time period => all values will be sent in ajax response)
                aggregated_qs = aggregated_qs.order_by('timestamp').values_list('timestamp', *series_fields) # only selects field to return

            print('Dbg: generating JSON for chart: aggregation period: {} | qs.count(): {}'.format(used_aggregation, aggregated_qs.count()))

        elif aggregation in aggregation_periods: # aggregation is manualy set (passed as argument)
            used_aggregation = aggregation # aggregation period is forced
            aggregated_qs = qs.extra(select={'ts': "date_trunc('{}', timestamp)".format(aggregation)}).order_by('ts').values_list('ts').annotate(*map(AGGR_F, series_fields))
            print('Dbg: generating JSON for chart: used manualy forced aggregation: {} | qs. count(): {}'.format(aggregation, aggregated_qs.count()))

        else: # Disables aggregation (e.g. when aggregation=None is passed as argument)
            aggregated_qs = aggregated_qs.order_by('timestamp').values_list('timestamp', *series_fields) # only selects field to return
            print('Dbg: generating JSON for chart: aggregation function disabled | qs. count(): {}'.format(aggregated_qs.count()))

        # Queryset with data is now prepared in aggregated_qs

        # Convert data to proper format for Flot JS library
        # 1 serie for duration, 3 series for counters

        data_series =    [ [calendar.timegm(result[0].timetuple()) * 1000] + list(result[1:]) for result in aggregated_qs ] # Flot needs raw javascript timestamp (milisec. since Epoch), without timezone
        data = {'duration_serie': data_series, 'aggregation': used_aggregation, 'threshold': 5} # TODO: pass real threshold value

        return HttpResponse(json.dumps(data), mimetype='application/json')


    def duration_chart(self, request):
        return render(request, "admin/serviceconfig/testresult/duration_chart.html")

    def counters_chart(self, request):
        return render(request, "admin/serviceconfig/testresult/counters_chart.html")

    def charts(self, request):
        return render(request, "admin/serviceconfig/testresult/charts.html")

#     def history_view(self, request, object_id, extra_context=None):
#         print('history view')
#         print(extra_context)
#         print('self.admin_site.name', self.admin_site.name)
#         extra_context = extra_context or {}
#         extra_context['osm_data'] = 'blabal'
#         return super(TestResultAdmin, self).history_view(request, object_id,
#             extra_context=extra_context)




####################################################################################################################################################################################
# ServiceStatusSummaryAdmin (new name: ServiceStatusChangesAdmin)
####################################################################################################################################################################################

class ServiceStatusSummaryAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'service', 'status_changed_to', 'is_status_ok')

    list_display += ('notified', ) # TODO: delete (debug only)
    list_editable = ('notified', ) # TODO: delete (debug only)

    list_filter = ('timestamp', ServiceFilterOnTestResultList, ServerFilterOnTestResultList, 'status_changed_to')
#     readonly_fields = ('service', 'timestamp', 'status_changed_to') # TODO: uncomment. (only for debug)
    date_hierarchy = 'timestamp'
    actions_on_bottom = False
    actions_on_top = False

    fieldsets = (
            ('Status change detail', {
                'fields': ('service', 'timestamp', 'status_changed_to', 'notified'), # TODO: remove notified (only for debug)
                'classes': ('wide', )
                }),
    )

    def queryset(self, request): # filtering Status Summaries according to logged-in user
        qs = super(ServiceStatusSummaryAdmin, self).queryset(request) # default queryset
        if not request.user.is_superuser:
            qs = qs.filter(service__server__user=request.user) # display only testresults owned by user
        return qs

# TODO: uncomment has_add and has_delete permission (enabled for debug only)
#     def has_add_permission(self, request):
#         return False
# #     def has_change_permission(self, request, obj=None):
# #         return False
#     def has_delete_permission(self, request, obj=None):
#         return False





####################################################################################################################################################################################
# TestingPlanAdmin
####################################################################################################################################################################################

class UserFilterOnTestingPlanList(SimpleListFilter):
    """ Filter TestingPlans on User. This filter is displayed only to superuser """
    title = ('user')
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        """ Generates list of items to display in the filter panel """
        if request.user.is_superuser:
            return ( (unicode(user.id), unicode(user.username)) for user in User.objects.filter(is_superuser=False) ) # filter : not superuser
        else:
            return None

    def queryset(self, request, queryset):
        """ Does filtering based on this filter """
        user_id = self.value()
        if user_id != None:
            return queryset.filter(service__server__user=int(user_id))
        else:
            return queryset

class TestingPlanAdmin(admin.ModelAdmin):
    list_display = ('description', 'service', 'CRON_string', 'allowed_delay')
#     list_filter = ('service__server__user', 'service')
    list_filter = (UserFilterOnTestingPlanList, ServiceFilterOnTestResultList, ServerFilterOnTestResultList)
    fieldsets = (
            (None, {
                'fields': ('service', 'description', 'allowed_delay', 'CRON_string'),
                }),
    )

    def get_list_display(self, request):
        if request.user.is_superuser:
            return self.list_display + ('get_username',)
        else:
            return self.list_display

    def formfield_for_foreignkey(self, db_field, request, **kwargs): # used for filtering list of services displayed
        if db_field.name == 'service' and not request.user.is_superuser: # common users will see only their services in <select> options
            kwargs["queryset"] = Service.objects.filter(server__user=request.user)
        return super(TestingPlanAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def queryset(self, request):
        qs = super(TestingPlanAdmin, self).queryset(request) # default queryset
        if not request.user.is_superuser:
            qs = qs.filter(service__server__user=request.user) # display only services owned by user
        return qs

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if obj.service.server.user != request.user: # should never happen: user has no "legal" way to get in this, because he doesn't see servers not owned by him
                obj.service = None # TODO: ?
        obj.save()





####################################################################################################################################################################################
# ServiceAdmin
####################################################################################################################################################################################

class AlwaysChangedForm(ModelForm):
    """ Special form for inlines in Service. (for auto adding related forms even with default values) """
    def has_changed(self):
        return True # needed for always-adding when creating new service
#     class Meta: # zda sa ze nie je treba => da sa pouzit univerzalne pre viac modelov
#         model = ServiceRequirements

class ServiceRequirementsInline(admin.StackedInline):
    model = ServiceRequirements
    form = AlwaysChangedForm
    verbose_name = 'Related Service Requirements'
#     verbose_name = ''
    can_delete = False

    fieldsets = (
            (None, {
                'fields': ('max_OK_duration', ),
                'classes': ('wide',)
                }),
            ('Thresholds', {
                'description': 'Going down under these values will have effect on service status.',
                'fields': ('t_responding', 't_responding_on_time', 't_responding_ok'),
                'classes': ('wide',)
                })
    )

class ConditionCalculationCoeficientsInline(admin.StackedInline):
# class ConditionCalculationCoeficientsInline(admin.TabularInline):
    model = ConditionCalculationCoeficients
    form = AlwaysChangedForm
    verbose_name = 'Related Coeficients'
    can_delete = False

    fieldsets = (
            (None, {
                'description': 'Following values will be used for service condition counters re-evaluation after every performed Test.',
                'fields': (
                    ('on_response_increment', 'on_no_response_decrement'),
                    ('on_ontime_increment', 'on_late_decrement'),
                    ('on_ok_increment', 'on_error_decrement'),
                    ),
                'classes': ('wide', ),
                }),
    )

class DBCleanupPolicyInline(admin.StackedInline):
	model = DBCleanupPolicy
	form = AlwaysChangedForm
	verbose_name = 'Related Cleanup Policy'
	can_delete = False

	fieldsets = (
#             ('Archivation period', {
            (None, {
                'description': 'All records will be automatically removed from the database after time specified below has elapsed.',
                'fields': ('archive_results_for', 'archive_status_summary_for'),
                'classes': ('wide', ),
                }),
	)



# #############
# Filters:

class ServerFilterOnServiceList(SimpleListFilter):
    """ Filter on Server. Every user (except superuser) has only his servers displayed """

    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = ('server')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'server'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """

        # Filtering servers for non-superusers
        qs_servers = Server.objects.all()
        if not request.user.is_superuser:
            qs_servers = qs_servers.filter(user=request.user)
        return ( (unicode(server.id), unicode(server)) for server in qs_servers )
        
# # Optional:
#         # Do not display this filter in panel if there's only one item (server)
#         if qs_servers.count() > 1:
#             return ( (unicode(server.id), unicode(server)) for server in qs_servers )
#         else:
#             return None
#
# # for now disabled, because it can be useful to see either single server (user can see there's only 1 server)
#

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        server_id = self.value()
        if server_id != None:
            return queryset.filter(server=int(server_id))
        else:
            return queryset

class UserFilterOnServiceList(SimpleListFilter):
    """ Filter Services on User. This filter is displayed only to superuser """
    title = ('user')
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        """ Generates list of items to display in the filter panel """
        if request.user.is_superuser:
            return ( (unicode(user.id), unicode(user.username)) for user in User.objects.filter(is_superuser=False) ) # filter : not superuser
        else:
            return None

    def queryset(self, request, queryset):
        """ Does filtering based on this filter """
        user_id = self.value()
        if user_id != None:
            return queryset.filter(server__user=int(user_id))
        else:
            return queryset

class ServiceTypeFilterOnServiceList(SimpleListFilter):
    """ Filter Service types. Restricts displayed types only to used (not always showing all types) """
    title = ('service type')
    parameter_name = 'service_type'

    def lookups(self, request, model_admin):
        """ Generates list of items to display in the filter panel """
        qs = model_admin.queryset(request)
        qs = qs.distinct('service_type') # Note: works only with PostgreSQL (see django docs)
        return ( (unicode(service.service_type), service.get_service_type_display()) for service in qs )

    def queryset(self, request, queryset):
        """ Does filtering based on this filter """
        service_type = self.value()
        if service_type != None: # filtering is not active on this filter
            return queryset.filter(service_type=int(service_type))
        else:
            return queryset

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('service_type', 'server', 'enabled')   # replaced with get_list_display, but needs to remain because of "buggy" requirement of list_editable
    list_editable = ('enabled', )
    list_filter = (ServiceTypeFilterOnServiceList, 'enabled', ServerFilterOnServiceList, UserFilterOnServiceList)
    inlines = [ServiceRequirementsInline, ConditionCalculationCoeficientsInline, DBCleanupPolicyInline]
#     readonly_fields = ('service_type', )
    save_as = True
    save_on_top = True
    list_select_related = True

    fieldsets = (
            ('Basic properties', {
#                 'fields': ('server', 'service_type', ('propagate_errors', 'accept_error_propagation'))
                'fields': ('server', 'service_type', 'enabled')

                }),
            ('When error is detected', {
                'fields': ('repeat_times', 'repeat_interval', 'notify_if_lasts'),
                'classes': ('wide',)

                }),
            ('Triggering Tests among all related Services', {
                'fields': ('propagate_errors', 'accept_error_propagation'),
                'classes': ('wide',)
                }),
    )

#     def delete_model(self, request, obj):
#         """ Deletes all related TestingPlans before deleting itself, preventig system crash (sync_crontab requires existing service) """
#         obj.testingplan_set.delete()
#         super(ServiceAdmin, self).delete_mode(self, request, obj)  # do default (delete itself)


    def get_list_display(self, request):
#         list_display = ('service_type', 'server', 'enabled')
        if request.user.is_superuser:
            return self.list_display + ('get_username',)
        else:
            return self.list_display

    def get_urls(self): # addition for service current status
        urls = super(ServiceAdmin, self).get_urls()
        my_urls = patterns('',
                url(r'^(?P<id>\d+)/service-status/$', self.admin_site.admin_view(self.service_status), name='service-status-view'),
                url(r'^(?P<id>\d+)/redirect-to-stc/$', self.admin_site.admin_view(self.redirect_to_stc), name='redirect-to-stc'),
                url(r'^(?P<id>\d+)/test-sendmail/$', self.admin_site.admin_view(self.test_sendmail), name='test-sendmail'), # TODO: debug
                url(r'^generic-listview/$', ListView.as_view(model=Service)), # TODO: debug
#                 url(r'^(?P<id>\d+)/service-status/$', self.admin_site.admin_view(admin_views.service_status), name='service-status-view'),
#                 url(r'^(?P<id>\d+)/w_status/$', self.admin_site.admin_view(serviceconfig.views.w_status), name='service-status-view'),
        )
        return my_urls + urls

    def test_sendmail(self, request, id):
        """ Dbg: testing if email is working """
        s = Service.objects.get(id=id)
        s.send_mail_notification([s])
        return HttpResponse('Test email sent.')

    def service_status(self, request, id):
        # real names (for template path location)
        class_name = self.model.__name__.lower()
        app_name = self.model._meta.app_label.lower()
        template = 'admin/{}/{}/service_status.html'.format(app_name, class_name)

        # human-readable names (for breadcrumbs)
        module_name = self.model._meta.verbose_name_plural.capitalize()
        app_label = self.model._meta.app_label.capitalize()

        # get service object
        service = get_object_or_404(self.model, pk=id)
        str_service = unicode(service)

        testresult = service.get_last_testresult()

        if testresult != None:
            qcounters = [ {
                'label': testresult._meta.get_field_by_name(counter)[0].verbose_name.capitalize(),
                'value': getattr(testresult, counter),
                } for counter in ('q_responding', 'q_responding_on_time', 'q_responding_ok') ]

            lasttest_items = [ {
                'label': testresult._meta.get_field_by_name(counter)[0].verbose_name.capitalize(),
                'value': getattr(testresult, counter),
                } for counter in ('timestamp', 'duration', 'on_time', 'retcode') ]
            lasttest_items[-1]['value'] = testresult.get_retcode_display()
        else: # There's no TestResult for this Service yet
            qcounters = []
            lasttest_items = []

# TODO:
        return render(request, template, {
            'object_id': id,
            'current_app': self.admin_site.name,
            'module_name': module_name,
            'app_label': app_label,
            'object': str_service,
            'service': service,
            'testresult': testresult, 
#             'testresult_form': testresult_report_form,
            'statussummary': service.get_last_status_summary,
            'qcounters': qcounters,
            'lasttest_items': lasttest_items,
#             'testresult_dict': testresult_dict,
            })


    def redirect_to_stc(self, request, id):
        """ Redirects to related STC for service. Creates it if it does not exist. Argument id can be PK of Service (used from urlconf), or Service instance (used from other views) """

        # if id is Service instance already, it is no need to search for it in DB by it's ID
        service = id if isinstance(id, Service) else get_object_or_404(Service, pk=id)
        stc_class = SERVICE_TYPES_CONFIG_CLASSES[service.service_type]
        app_label = stc_class._meta.app_label
        stc_model_name = stc_class.__name__
        try:
            stc_obj = stc_class.objects.get(service=service) # get related stc object
            print('Dbg: redirect to stc: Found existing stc')
#             print(stc_model_name)
#             print(stc_model_name.lower())
#             change_view = 'admin:{}_{}_change'.format(app_label, stc_model_name.lower())
#             return redirect(change_view, id)
        except stc_class.DoesNotExist: # add new... (Edit: toto by sa uz nemalo vyskytnut. Nebude vsak presmerovane na add_view, ale bude automaticky vytvorene a redirect na change_view)
            print('Dbg: redirect to stc: Adding new stc')
            stc_obj = stc_class(service=service)
            stc_obj.save()

        change_view = 'admin:{}_{}_change'.format(app_label, stc_model_name.lower())
        return redirect(change_view, stc_obj.pk)

# # No longer needed, since add_view is disabled due to consistency issues with FK...
#             add_view = 'admin:{}_{}_add'.format(app_label, stc_model_name.lower())
#             return redirect(add_view)


    def response_add(self, request, obj, post_url_continue=None):
        """ Undocumented method override ! Is responsible for passing next url (redirect) after Service Add """#http://igorsobreira.com/blog/2011/2/12/change-object-after-saving-all-inlines-in-django-admin/

        return self.redirect_to_stc(request, obj)

        # add new related STC
        stc_class = SERVICE_TYPES_CONFIG_CLASSES[obj.service_type]
        stc_obj = stc_class(service=obj)
        stc_obj.save()

#         s = Service.objects.get(pk=obj.id)
#         print('Got it: {}'.format(s))
#         app_label = stc_class._meta.app_label
#         stc_model_name = stc_class.__name__
#         change_view = 'admin:{}_{}_change'.format(app_label, stc_model_name.lower())
#         return redirect(change_view, stc_obj.pk)


    def formfield_for_foreignkey(self, db_field, request, **kwargs): # used for filtering list of servers displayed as option for service
        if db_field.name == 'server' and not request.user.is_superuser: # common users will see only their servers in <select> options
            kwargs["queryset"] = Server.objects.filter(user=request.user)
        return super(ServiceAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def queryset(self, request):
        qs = super(ServiceAdmin, self).queryset(request) # default queryset
#         qs = qs.filter(testingplan__allowed_delay=120).filter(testingplan__allowed_delay=120).filter(testingplan__allowed_delay=120).distinct()
        if not request.user.is_superuser:
            qs = qs.filter(server__user=request.user) # display only services owned by user
        return qs

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if obj.server.user != request.user: # should never happen: user has no "legal" way to get in this, because he doesn't see servers not owned by him
                obj.server = None # TODO: ?
        obj.save()




####################################################################################################################################################################################
# ServerAdmin
####################################################################################################################################################################################

class UserFilterOnServerList(SimpleListFilter):
    """ Filter Servers on User. This filter is displayed only to superuser """
    title = ('user')
    parameter_name = 'user'

    def lookups(self, request, model_admin):
        """ Generates list of items to display in the filter panel """
        if request.user.is_superuser:
            return ( (unicode(user.id), unicode(user.username)) for user in User.objects.filter(is_superuser=False) ) # filter : not superuser
        else:
            return None

    def queryset(self, request, queryset):
        """ Does filtering based on this filter """
        user_id = self.value()
        if user_id != None:
            return queryset.filter(user=int(user_id))
        else:
            return queryset


class ServerAdmin(admin.ModelAdmin):
    list_display = ('__unicode__', 'show_service_count', 'enabled')  # extended (overrided) with get_list_display, but needs to remain because of "buggy" requirement of list_editable
    list_editable = ('enabled', )
    list_filter = ('enabled', UserFilterOnServerList)
    list_select_related = True

    def queryset(self, request):
        qs = super(ServerAdmin, self).queryset(request) # default queryset
        qs = qs.annotate(service_count=Count('service')) # add column with number of services

        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user) # filter server's for only those own by the user

    def get_list_display(self, request):
        if request.user.is_superuser:
            return self.list_display + ('get_username',)
        else:
            return self.list_display

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.user = request.user
        obj.save()

    def get_readonly_fields(self, request, obj=None):
        return tuple() if request.user.is_superuser else ('user',)

    def show_service_count(self, obj):
        """ Returns number of services previously calculated by annotate aggreagation (in queryset method) """
        return obj.service_count
    show_service_count.admin_order_field='service_count'  # this column is added using annotation
    show_service_count.short_description='Number of services'





####################################################################################################################################################################################
# DBCleanupPolicyAdmin
####################################################################################################################################################################################

class DBCleanupPolicyAdmin(admin.ModelAdmin):
    list_display = ('__unicode__', 'archive_results_for', 'archive_status_summary_for')
    fieldsets = (
            (None, {
                'fields': ('service', ),
                'classes': ('wide', ),
                }),
            ('Archivation period', {
                'description': 'All records will be automatically removed from the database after time specified below has elapsed.',
                'fields': ('archive_results_for', 'archive_status_summary_for'),
                'classes': ('wide', ),
                })
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs): # used for filtering list of services displayed as option for cleanup policy
        if db_field.name == 'service' and not request.user.is_superuser: # common users will see only their services in <select> options
            kwargs["queryset"] = Service.objects.filter(server__user=request.user)
        return super(DBCleanupPolicyAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def queryset(self, request): # filtering Cleanup Policies according to logged-in user
        qs = super(DBCleanupPolicyAdmin, self).queryset(request) # default queryset
        if not request.user.is_superuser:
            qs = qs.filter(service__server__user=request.user) # display only testresults owned by user
        return qs

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if obj.service.server.user != request.user: # should never happen: user has no "legal" way to get in this, because he doesn't see servers not owned by him
                obj.service = None # TODO: ?
        obj.save()


#######################################################################################################################################################################################
#######################################################################################################################################################################################
#######################################################################################################################################################################################


admin.site.register(Service, ServiceAdmin)
admin.site.register(Server, ServerAdmin)
admin.site.register(TestResult, TestResultAdmin)
admin.site.register(ServiceStatusSummary, ServiceStatusSummaryAdmin)
admin.site.register(DBCleanupPolicy, DBCleanupPolicyAdmin)
admin.site.register(TestingPlan, TestingPlanAdmin)
# admin.site.register(ServiceRequirements)
# admin.site.register(ConditionCalculationCoeficients)


class STCAdmin(admin.ModelAdmin):
    # TODO: Make service to be showed on top
    # TODO: Change template to display link to related Service

    readonly_fields = ('service', )

#     actions_on_bottom = False
#     actions_on_top = False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None): # TODO: enable? (nic vazne by sa nestalo, vsetko by fungovalo ako dalej. Len user by mohol mat pocit, ze sa zmazala aj sluzba samotna)
        return False

    def changelist_view(self, request, extra_context=None):
#         class_name = self.model.__name__.lower()
#         app_name = self.model._meta.app_label.lower()
#         redirect_view = 'admin:{}_{}_changelist'.format(app_name, class_name)
        redirect_view = 'admin:serviceconfig_service_changelist'
        return redirect(redirect_view)

#         if request.user.is_superuser:
#             return super(STCAdmin, self).changelist_view(request, extra_context)
#         else: # Common user is redirected to general Service's list view
#             return redirect(redirect_view)

#         app_label = stc_class._meta.app_label
#         stc_model_name = stc_class.__name__
# 
#         module_name = self.model._meta.verbose_name_plural.capitalize() # priprave pre template (na breadcrumbs)
#         app_label = self.model._meta.app_label.capitalize()
#         str_object = unicode(get_object_or_404(self.model, pk=id))
# 
#         class_name = self.model.__name__.lower()
#         app_name = self.model._meta.app_label.lower()
#         template = 'admin/{}/{}/service_status.html'.format(app_name, class_name)

# class STC_SMTP_Admin(STCAdmin):
#     pass

# for STC_*...
admin.site.register(STC_HTTP, STCAdmin)
admin.site.register(STC_HTTPS, STCAdmin)
admin.site.register(STC_FTP, STCAdmin)
admin.site.register(STC_FTP_TLS, STCAdmin)
admin.site.register(STC_TFTP, STCAdmin)
admin.site.register(STC_Telnet, STCAdmin)
admin.site.register(STC_SSH, STCAdmin)
admin.site.register(STC_SFTP, STCAdmin)
admin.site.register(STC_IMAP, STCAdmin)
admin.site.register(STC_IMAP_SSL, STCAdmin)
admin.site.register(STC_POP, STCAdmin)
admin.site.register(STC_POP_SSL, STCAdmin)
admin.site.register(STC_SMTP, STCAdmin)
admin.site.register(STC_SMTP_SSL, STCAdmin)
admin.site.register(STC_DNS, STCAdmin)
admin.site.register(STC_LDAP, STCAdmin)
admin.site.register(STC_Ping, STCAdmin)


