#!/usr/bin/env python
#
# Planovac spustania testov (verzia 2.1). Pouziva 2 prioritne fronty, s prioritami cas spustenia testu
#
# Pouzivane oznacenia:
# testID - jednoznacne ID testu (PK of TestingPlan)
# runFrom/runTill - seconds since Epoch
#
# FIFO command syntax (one line per one job):
# a) testID                     # runs immediately
# b) testID runTill             # runs till runTill
# c) testID runFrom runTill     # runs between runFrom and runTill
# Note: testID != serviceID
#
# UPDATE: now using unix dgram socket instead of named pipes, because of non-blocking sending possibility

INPUT_SOCKET_FILENAME = 'scheduler_input_socket'
PREQ_PEEK_MAX_WAIT = 60 # (sec.)
RUN_TESTS_SPACING = 1 # time to wait between subsequent tests execution (sec.)
THREAD_WATCHDOG_TIMEOUT = 60 # interval for checking if all threads are alive
JOB_DEFAULT_ALLOWED_DELAY = 60 # (sec.) Default allowed delay - will be used when runTill argument is not specified

import Queue
import time
import datetime
import threading
import os
import socket
# import sys

g_mainQ = Queue.PriorityQueue() # main Q for launching test. Priority is last time for launching it. Content: tuple(runTill, job) # when job is instance of TestJob
g_preQ = Queue.PriorityQueue() # secondary (auxiliary) Q for items that have to wait some time for first allowed time to launch, when they're moved into main Q. Content: tuple(runFrom, runTill, job) # when job is instance of TestJob
g_preQchanged = threading.Event() # provides signalization of secondary Q changes. This solves the problem of long waiting for 1st job execution while new more urgent job is added to the Q


####################################################################################################################################################
########################### Setting Django Enviroment ##############################################################################################
####################################################################################################################################################

# def set_django_enviroment():
#     print('Dbg: scheduler: setting django enviroment')
#     NSMON_ROOT = os.path.realpath(os.path.dirname(__file__))
#     NSMON_PARENTDIR = os.path.abspath(os.path.join(NSMON_ROOT, os.pardir))
# 
#     for path in (NSMON_ROOT, NSMON_PARENTDIR):
#         if path not in sys.path:
#             sys.path.append(path)
# 
#     os.environ['DJANGO_SETTINGS_MODULE'] = 'nsmon.settings'
# 
# set_django_enviroment()

import set_django_enviroment

from serviceconfig.models import Service, TestingPlan

####################################################################################################################################################
########################### TestJob class. (Used as item in all Queues in scheduler) ###############################################################
####################################################################################################################################################

class TestJob:
    """ TestJob class. Instances of this class are used as "main" items in Queues """

    def __init__(self, function, *args, **kwargs):
        """ Argument is the function to be called (with *args and **kwargs) when the Time comes """
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        return self.function(*self.args, **self.kwargs)

    def __str__(self):
        return 'Job {} {}'.format(self.args, self.kwargs)


####################################################################################################################################################
########################### Scheduler's API ###############################################################
####################################################################################################################################################

def plan_job(job, runTill=None, runFrom=None, allowed_delay=None):
    """
    Plans job for later execution (adds it to appropriate Queue).
    If runTill is not specified, default will be calculated with delta = JOB_DEFAULT_ALLOWED_DELAY or allowed_delay (if specified).
    If runFrom is not specified, it will be run right now.
    """
    now = int(time.time())

    if runFrom == None:
        runFrom = now

    if runTill == None: # use default runTill value
        if allowed_delay == None:
            runTill = runFrom + JOB_DEFAULT_ALLOWED_DELAY
        else: # allowed_delay was passed
            runTill = runFrom + allowed_delay

    if runFrom <= now: # Pass directly to g_mainQ for execution
        put_to_mainQ(job, runTill)
    else: # Pass it to g_preQ to wait for the proper time for execution
        put_to_preQ(job, runFrom, runTill)


# Wrappers for my models
def plan_service(service, runTill=None, runFrom=None, allowed_delay=None, **kwargs):
    """
    Wrapper of plan_job for planning service. TestJob is generated automatically for service supplied as arg. (can be Service or ID of Service).
    Service callback will be run with service as first argument, and also optional keyword arguments (**kwargs).    
    """
    try:
        service = service if isinstance(service, Service) else Service.objects.select_related().get(pk=service)
    except Service.DoesNotExist:
        print('Dbg: plan_service Error: Service DoesNotExist')
        return

    job = TestJob(Service.test_oneself_callback, service, **kwargs) # TODO: ktoru funkciu volat?
    plan_job(job, runTill, runFrom, allowed_delay)

def plan_testingplan(testing_plan, runTill=None, runFrom=None): #Pozn.do buducna, ak TestingPlan bude mat viacej Service-s (many-to-many), treba naplanovat vsetky! (for service in ..)
    """ Wrapper of plan_service (and plan_job) for planning testing_plan. TestJob is generated automatically for TestingPlan supplied as arg. (can be TestingPlan or ID of TestingPlan) """
    try:
        testing_plan = testing_plan if isinstance(testing_plan, TestingPlan) else TestingPlan.objects.select_related().get(pk=testing_plan)
    except TestingPlan.DoesNotExist:
        print('Dbg: plan_testingplan Error: TestingPlan DoesNotExist')
        return

    allowed_delay = testing_plan.allowed_delay * 60 # minutes to seconds
    service = testing_plan.service # get related service
    plan_service(service, runTill, runFrom, allowed_delay)


####################################################################################################################################################
########################### Queues manipulation routines ###############################################################
####################################################################################################################################################

def put_to_mainQ(job, runTill):
    """ Wrapper for g_mainQ.put() """
    g_mainQ.put((runTill, job))

def put_to_preQ(job, runFrom, runTill):
    """ Wrapper for g_preQ.put() """
    g_preQ.put((runFrom, runTill, job))
    g_preQchanged.set()


####################################################################################################################################################
########################### Test job execution. ####################################################################################################
####################################################################################################################################################

def spawnTest(job):
    """ Spawns thread for passed job (launches test execution). Not blocking. """

    print('Dbg: Scheduler.spawnTest: [{}] Spustam job: {}'.format(datetime.datetime.now().strftime('%H:%M:%S'), job)) # for general info in "human format"

    # Thread for testing the Service (test.service)
    thread_name = 'Thread for doing test job: {}'.format(job) # name for new thread
    hTestThread = threading.Thread(target = execTest, name = thread_name, kwargs = {'job': job})
    hTestThread.daemon = True
    hTestThread.start()

def execTest(job): # helper function for spawnTest
    """ (Immediatelly) executes test job in current thread (is blocking). """

    new_jobs = job.run() # Note: there's not TestJob instances returned, but list of 4-tuples specifying new jobs plans creation. [ tuple(runFrom, runTill, service, kwargs), ... ]
    print('Dbg: Scheduler.execTest: job.run() finished and returned these new_jobs to plan: {}'.format(new_jobs))
#### returning list of tuples: (runFrom, runTill, service, kwargs) # kwargs is dict with extra params (e.g. is_repeated, is_triggered) that callback wish (and will) to be called with
    for new_job in new_jobs:
        runFrom, runTill, service, kwargs = new_job
        plan_service(service=service, runTill=runTill, runFrom=runFrom, **kwargs)


###################################################################################################################################################
############################# 3 infinite loop functions ###########################################################################################
###################################################################################################################################################

def doAcceptInputs():
    """ Reads and dispatchs inputs from unix dgram socket. Works in standalone thread """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind(INPUT_SOCKET_FILENAME)
    while True:
        line = s.recv(100)
        try:
            print('Dbg: Scheduler: Read input: {0}'.format(line))
            args = line.split()
            n = len(args)

            # switching by number of params supplied
            if n == 1: # Run job with auto-fetching allowed_delay config from DB
                plan_testingplan(int(args[0]))

            elif n == 2: # Run till.
                testID, runTill = ( int(x) for x in args ) # generator for convertion str params to int
                plan_testingplan(testID, runTill)

            elif n == 3: # Run from---till. Job goes to g_preQ
                testID, runFrom, runTill = ( int(x) for x in args )
                if runFrom > runTill:
                    print('Dbg: doAcceptInputs: wrong interval supplied')
                    continue
                plan_testingplan(testID, runTill, runFrom)

            else: # error on input
                print('Scheduler: Error! Too many arguments supplied. Ignoring job request.')
                continue
        except ValueError: # arguments cannot be converted to int-s
            print('Scheduler: Error! Invalid arguments supplied. Ignoring job request')

    s.close()  # TODO: make sure this will be called (for example after interrupt)
    # except IOError as err:
    #     print('Scheduler: Error: Cannot open input named pipe "{}" ({})'.format(INPUT_FIFO_FILENAME, err))
    #     print('Scheduler: Trying to create new named pipe...')
    #     try:
    #         import subprocess
    #         if subprocess.call(['mkfifo', INPUT_FIFO_FILENAME]):
    #             raise Exception('mkfifo failed!')
    #     except Exception as err:
    #         print('Scheduler: Could not create new named pipe! {}. Exiting thread.'.format(err))
    #         return
    #     else:
    #         print('Scheduler: New named pipe "{}" created. Awaiting inputs...'.format(INPUT_FIFO_FILENAME))

def doAcceptInputs_pipe():  # abandoned
    """ Reads and dispatchs inputs from named pipe. Works in standalone thread """
    while True:
#         print('Debug: doAcceptInputs: while...')
        try:
            with open(INPUT_FIFO_FILENAME) as fd:
    #             print('Debug: doAcceptInputs: file opened.')
                for line in fd:
                    try:
                        print('Dbg: Scheduler: Read input: {0}'.format(line))
                        args = line.split()
                        n = len(args)

                        # switching by number of params supplied
                        if n == 1: # Run job with auto-fetching allowed_delay config from DB
                            plan_testingplan(int(args[0]))

                        elif n == 2: # Run till.
                            testID, runTill = ( int(x) for x in args ) # generator for convertion str params to int
                            plan_testingplan(testID, runTill)

                        elif n == 3: # Run from---till. Job goes to g_preQ
                            testID, runFrom, runTill = ( int(x) for x in args )
                            if runFrom > runTill:
                                print('Dbg: doAcceptInputs: wrong interval supplied')
                                continue
                            plan_testingplan(testID, runTill, runFrom)

                        else: # error on input
                            print('Scheduler: Error! Too many arguments supplied. Ignoring job request.')
                            continue
                    except ValueError: # arguments cannot be converted to int-s
                        print('Scheduler: Error! Invalid arguments supplied. Ignoring job request')
        except IOError as err:
            print('Scheduler: Error: Cannot open input named pipe "{}" ({})'.format(INPUT_FIFO_FILENAME, err))
            print('Scheduler: Trying to create new named pipe...')
            try:
                import subprocess
                if subprocess.call(['mkfifo', INPUT_FIFO_FILENAME]):
                    raise Exception('mkfifo failed!')
            except Exception as err:
                print('Scheduler: Could not create new named pipe! {}. Exiting thread.'.format(err))
                return
            else:
                print('Scheduler: New named pipe "{}" created. Awaiting inputs...'.format(INPUT_FIFO_FILENAME))


def doProcessPreQ():
    """ Moves jobs from secondary Q (g_preQ) to primary Q (g_mainQ) when their time comes """
    # cakat na signal, ci sa nieco do fronty vlozilo, ale maximalne cas do nadobudnutia aktualnosti prveho jobu v poradi
    while True:
        now = int(time.time())
        g_preQchanged.clear()

        try:
            next_time = g_preQ.queue[0][0]
            while(next_time <= now): # move all ready jobs from preQ to mainQ
                job_entry = g_preQ.get() # job_entry contains tuple(runFrom, runTill, job)
                g_mainQ.put(job_entry[1:]) # removes "runFrom" attribute and adds it to mainQ
                next_time = g_preQ.queue[0][0]
            wait_time = min(next_time - now, PREQ_PEEK_MAX_WAIT) # just for the case sth goes wrong (preventing for waiting forever)
            g_preQchanged.wait(wait_time)
#             g_preQchanged.wait(next_time - now)
#             g_preQchanged.clear()

        except IndexError: # Queue is empty, no job is in there
            g_preQchanged.wait(PREQ_PEEK_MAX_WAIT) # this could be infinity, but just to be sure, give it some max time
#             g_preQchanged.clear()

def doProcessMainQ():
    """ Pops jobs from main Q and starts their tests """
    while True:
        runTill, job = g_mainQ.get()
        spawnTest(job)
        time.sleep(RUN_TESTS_SPACING)



###################################################################################################################################################
############################# Main. Threads starting and Watchdog #################################################################################
###################################################################################################################################################

# constants for thread roles manipulation
ROLE_ACCEPT_INPUTS = 0
ROLE_PROCESS_PREQ = 1
ROLE_PROCESS_MAINQ = 2
def _start_thread_for(role_id):
    """ simple helper function for (re)starting thread """
    roles = {
        ROLE_ACCEPT_INPUTS: doAcceptInputs,
        ROLE_PROCESS_PREQ: doProcessPreQ,
        ROLE_PROCESS_MAINQ: doProcessMainQ
        }
    routine = roles[role_id]
    hThread = threading.Thread(target = routine, name = routine.func_name)
    hThread.daemon = True
    hThread.start()
    print('Dbg: started thread {}'.format(hThread.name))
    return hThread
            
def main():
    """ Starts all threads and do 'watchdog' for them """    

    print(' Starting NSMon Scheduler daemon '.center(80, '*'))
    old_cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    new_cwd = os.getcwd()

    if old_cwd == new_cwd:
        print('Running from working directory: {}'.format(new_cwd))
    else:
        print('Current working directory changed from: {} to {}'.format(old_cwd, new_cwd))

    print('Initializing...')
    try:
        all_threads = dict()
        # initial startup
        for iThread in range(3): # 3 threads
            all_threads[iThread] = _start_thread_for(iThread)

        # Watchdog
        while True:
            time.sleep(THREAD_WATCHDOG_TIMEOUT)
            for iThread, hThread in all_threads.items():
                if not hThread.is_alive():
                    print('[Watchdog] Warning! Detected dead thread {}. Restarting...'.format(hThread.name))
                    all_threads[iThread] = _start_thread_for(iThread)

    except KeyboardInterrupt:
        print('User aborted. Exit daemon.')


if __name__ == '__main__':
    main()

