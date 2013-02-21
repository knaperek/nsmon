#!/usr/bin/env python
#
# This script is responsible for daily DB cleanup, according to user's settings
#

import datetime
from datetime import timedelta

import set_django_enviroment
from serviceconfig.models import Service, TestResult, ServiceStatusSummary


def main():
    now = datetime.datetime.now()

#     testresult.timestamp < now - timedelta(days=dbcleanuppolicy.archive_results_for)
# 
#     TestResult.objects.filter(service__dbcleanuppolicy__archive_results_for)
#     DBCleanupPolicy.objects.all()


    for service in Service.objects.select_related().all():
        try:
#             old_time_testresult = now - timedelta(minutes=service.dbcleanuppolicy.archive_results_for)
            old_time_testresult = now - timedelta(days=service.dbcleanuppolicy.archive_results_for)
            testresults_to_delete = TestResult.objects.filter(service=service, timestamp__lt=old_time_testresult)

#             old_time_summary = now - timedelta(minutes=service.dbcleanuppolicy.archive_status_summary_for)
            old_time_summary = now - timedelta(days=service.dbcleanuppolicy.archive_status_summary_for)
            summaries_to_delete = ServiceStatusSummary.objects.filter(service=service, timestamp__lt=old_time_summary)

            print('DBCleanupPolicy: about to delete this records for {}'.format(service))
            print('TestResults: {}: StatusSummaries: {}'.format(len(testresults_to_delete), len(summaries_to_delete)))
#             print('first TestResult: {}, last: {}'.format(testresults_to_delete[0].timestamp, testresults_to_delete[len(testresults_to_delete)-1].timestamp))

            # Delete selected...
            testresults_to_delete.delete()
            summaries_to_delete.delete()

        except DBCleanupPolicy.DoesNotExist:
            print('Dbg: DBCleanupPolicy for service {} DoesNotExist. Cannot perform cleanup for this service.'.format(service))



if __name__ == '__main__':
    main()

