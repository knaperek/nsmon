from django.template import RequestContext
from django.shortcuts import render_to_response, render, get_object_or_404, redirect

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from django.contrib.admin.views.decorators import staff_member_required

from serviceconfig.models import *

# @login_required
# def report(request):
#     return render(request, 'admin/serviceconfig/report.html', {'obj_list': TestResult.objects.all()})
# # report = staff_member_required(report)

def manager_overview(request):
    """ Renders table with columns Current Status | From | For how long | Is OK? | Enabled ?  for each service """

    user = request.user
    services = Service.objects.filter(server__user=user).order_by('server')

    return render(request, 'admin/serviceconfig/manager_overview.html', {'services':services})
manager_overview = staff_member_required(manager_overview)



def root_page(request):
    user = request.user
    if user.is_staff:
        return redirect('admin:index')
    return render(request, 'admin/root_page.html')

