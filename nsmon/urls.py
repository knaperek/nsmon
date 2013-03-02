from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'nsmon.views.home', name='home'),
    # url(r'^nsmon/', include('nsmon.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^$', 'serviceconfig.admin_views.root_page', name='root-page'),
    url(r'^admin/overview/$', 'serviceconfig.admin_views.manager_overview', name='manager-overview'),
    url(r'^admin/', include(admin.site.urls)),
    # url(r'^accounts/', include('registration.backends.default.urls')),
)
