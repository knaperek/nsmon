#!/usr/bin/env python

# TODO: zvazit aj nejaky navratovy kod v pripade chyby (nie len RESULT_ERR), aby admin videl, co je na sluzbe zle # ..mozno to vracat spolu v tej exception ako tuple(code, message), prip. named tupple
# TODO: implementovat aj univerzalneho TCP (mozno aj UDP) clienta na testovanie arbitrary service
# Pozn. timeout je na jedno connection, celkova dlzka moze byt aj dlhsia (ak napr. pozostava z viacerych vymen sprav... napr. SSH)

# TODO: Pouzit curl (v pythone) na protokoly, ktore inak nejdu (mozno aj na ine..ale prerabat to uz asi nejdem.) Takze minimalne na TFTP, prip. ldap

# TODO: to default osetrovanie v TestResult dat asi na return True

GLOBAL_TEST_TIMEOUT = 20 # timeout for service testers

import time
import socket

from constants import *
# RESULT_OK = 0
# RESULT_ERR = 1
# RESULT_ERR_AUTH = 2 # unauthorized
# RESULT_UA = 3 # UNAVAILABLE (simply test result >= RESULT_UA)
# RESULT_UA_NXDOMAIN = 4
# RESULT_UA_SOCK_ERROR = 5 # vseobecne socket error
# RESULT_UA_REFUSED = 6  # Connection refused (napr. zly port)
# RESULT_UA_TIMEOUT = 7
# RESULT_INTERNAL_ERROR = 8 # Problem na strane testeru

str_result_codes = [result_code for result_code in dir() if result_code.startswith('RESULT_')] # zoznam vsetkych nazvov kodov # pre ucely debugovania
def printResult(result):
    for str_result in str_result_codes:
        if eval(str_result) == result:
            print('Decoded Result: {}'.format(str_result))
            return

class ResultCodeException(Exception): # Vynimka na signalizovanie navratoveho kodu testu (aby to vyslo z with...)
    """ Exception for Result code signalization. Optional param is duration. If not specified, auto-measured duration will be used. """
    def __init__(self, result_code, duration=None):
        self.result_code = result_code
        self.duration = duration
    def __str__(self):
        return repr(self.value)


class TestResult:
    """ Obsahuje informacie o vykonani testu (vystup z testera) """

    def __init__(self, testID=None):
        self.testID = testID
        self.result = None # a.k.a. retcode
        self.duration = None
        self.startTime = None

    def __enter__(self):
        self.startTime = time.time()

    def __exit__(self, exc_type, exc_value, traceback):
        self.duration = round(time.time() - self.startTime, 3) # zaokruhlit cas trvania na 3 des. miesta
        self.startTime = round(self.startTime)

        print('Dbg: auto-measured duration: {}'.format(self.duration))

        if exc_type == None: # nebola vyhodena ziadna vynimka
            print('Dbg: Test skoncil OK')
            self.result = RESULT_OK
            return

        # TODO: nasledovne by sa asi dalo robit aj tak, ze by sa tu vyhodila exc_type exception este raz, a zaroven by sa handlila prislusnymi except-ami pre jednotlive typy
        elif exc_type == ResultCodeException: # ide o normalny sposob ukoncenia testu s hlasenim kodu
            print('Dbg: korektne ukonceny test s nahlasenim retcode')
            self.result = exc_value.result_code
            if exc_value.duration != None: # if Service Tester has supplied custom duration value, then will be used instead of default, auto-measured one
                self.duration = exc_value.duration
            return True # vynimka bola osetrena, netraba ju dalej sirit

        elif issubclass(exc_type, socket.gaierror):
            print('Dbg: osetreny socket.gaierror cez with v TestResult. Vysledok: RESULT_NXDOMAIN')
            self.result = RESULT_UA_NXDOMAIN # * nemusi byt nutne NXDOMAIN... (viac socket.gaierror)
            return True

        elif issubclass(exc_type, socket.timeout):
            print('Dbg: osetreny socket.timeout cez with v TestResult. Vysledok: RESULT_UA_TIMEOUT')
            self.result = RESULT_UA_TIMEOUT
            return True

        elif issubclass(exc_type, socket.error): # napr. Connection refused # TODO: mozno osetrit aj IOError (socket.error je subclass of IOError)
            err_msgs = {
                    #'timed out': RESULT_UA_TIMEOUT,
                        '[Errno 111] Connection refused': RESULT_UA_REFUSED,
                        }
            # # TODO: tie chyby by sa dali mozno rozlisovat aj podla exc_value.args[0] - co by malo byt cislo chyby (ak je tam dvojica: cisclo, popis). Treba pozriet este dokumentaciu...
            self.result = err_msgs.get(str(exc_value), RESULT_UA_SOCK_ERROR)
            #self.result = RESULT_UA_SOCK_ERROR
            print('Dbg: osetreny socket.error cez with v TestResult')
            print('Dbg: typ: ', type(exc_value), 'Value: ', exc_value)
            return True

        elif issubclass(exc_type, ImportError): # chyba pri import
            print('Error (ns_test_routines): import error: {}'.format(exc_value))
            self.result = RESULT_INTERNAL_ERROR
            return True

        else:
            print('Dbg: osetrena neznama chyba with v TestResult. Type: {} Value:{}'.format(exc_type, exc_value))
            # self.result = RESULT_UA # neznama chyba # TODO: nedat radsej by default RESULT_ERR? (unavailable je vacsinou spojene s low-level socketmi, a to zachytavam)
            self.result = RESULT_ERR
            return True # todo...
#             return False # todo...


class ServiceTester(): # Hlavna abstraktna trieda pre Testovace sluzieb
    def __init__(self, timeout, host, port=None, target=None, user=None, password=None, **params):
        self.timeout = timeout
        self.host = host
        self.port = port
        self.target = target
        self.user = user
        self.password = password

        self.__params = params # custom service parameters

    def __getattr__(self, name): # vsetky kwargs dane pri vytvarani (init) budu dostupne ako clenske variables
        return self.__params.get(name) # default: None

    def runTest(self):
        ''' abstraktna metoda. Konci vyhodenim prislusnej vynimky vyjadrujucej navratovy kod '''
        raise NotImplementedError()


class ST_HTTP(ServiceTester):
    """ Service Tester: HTTP """
    # Params: host, port, target, timeout
    def runTest(self):
        import httplib
        h = httplib.HTTPConnection(self.host, port=self.port, timeout=self.timeout)
        h.request('GET', self.target) # todo nastavit method, prip. aj headers
        resp = h.getresponse()

        if resp.status != 200: # TODO: nastavit povolene kody
            print('Dbg: HTTP status={}'.format(resp.status))
            raise ResultCodeException(RESULT_ERR)


class ST_HTTPS(ServiceTester):
    """ Service Tester: HTTPS """
    # Params: host, port, target, timeout
    def runTest(self):
        import httplib
        h = httplib.HTTPSConnection(self.host, port=self.port, timeout=self.timeout)
        h.request('GET', self.target) # todo nastavit method, prip. aj headers
        resp = h.getresponse()

        if resp.status != 200: # TODO: nastavit povolene kody
            raise ResultCodeException(RESULT_ERR)


class ST_FTP(ServiceTester):
    """ Service Tester: FTP """
    # Params: host, port, user, password, timeout # TODO: pridat "target" na stiahnutie konkretneho suboru
    # For anonymous FTP, use user='anonymous' and password=''
    def runTest(self):
        import ftplib
        try:
            f = ftplib.FTP() # v konstruktore sa neda nastavit port
            f.connect(host=self.host, port=self.port, timeout=self.timeout)
            f.login(user=self.user, passwd=self.password)
            resp = f.getwelcome()
            status = int(resp.strip().split()[0])
            if status != 220:
                raise ResultCodeException(RESULT_ERR)
#             resp = f.retrlines('LIST')
#             status = int(resp.strip().split()[0])
#             if status != 226:
#                 raise ResultCodeException(RESULT_ERR) 

            print('dbg: resp je: {} a status je: {}'.format(resp, status)) 
        except ftplib.Error: # error_reply, error_temp, error_perm, error_proto
            print('Dbg: FTP error')
            raise ResultCodeException(RESULT_ERR)

class ST_FTP_TLS(ServiceTester):
    """ Service Tester: FTP_TLS (FTPS) """
    # Params: host, port, user, password, timeout # TODO: pridat "target" na stiahnutie konkretneho suboru
    def runTest(self):
        import ftplib
        try:
            f = ftplib.FTP_TLS(host=self.host, timeout=self.timeout)  # v konstruktore sa neda nastavit port
            f.connect(host=self.host, port=self.port, timeout=self.timeout)
            f.login(user=self.user, passwd=self.password)

            try:
                f.prot_p() # set up secure data connection
            except ftplib.Error: # ignorovanie, ak nie je sifrovanie datoveho kanalu podporovane (TODO: *neodskusane, ci to naozaj funguje)
                pass
            resp = f.getwelcome()
            status = int(resp.strip().split()[0])
            if status != 220:
                raise ResultCodeException(RESULT_ERR)
#             resp = f.retrlines('LIST')
#             status = int(resp.strip().split()[0])
#             if status != 226:
#                 raise ResultCodeException(RESULT_ERR) 

            print('Dbg: resp je: {} a status je: {}'.format(resp, status)) 
        except ftplib.Error as error: # error_reply, error_temp, error_perm, error_proto
            print('Dbg: zachyteny Error: {}'.format(error))
            print('Dbg: type: {}'.format(type(error)))
            status = int(str(error).strip().split()[0])
            if status == 530: # 530 Login incorrect
                raise ResultCodeException(RESULT_ERR_AUTH)
            else:
                raise ResultCodeException(RESULT_ERR)


class ST_TFTP(ServiceTester):
    """ Service Tester: TFTP (cez curl) """
    # Params: host, port, target, timeout

    def runTest(self):
        import curl
        import pycurl
        try:
            url_str = 'tftp://{}:{}/{}'.format(self.host, self.port, self.target.lstrip('/'))
            c = curl.Curl(url_str)
            c.set_timeout(int(self.timeout))
            response = c.get()
            c.close()

        except pycurl.error as err:
            err_code = err[0]

            # obecne curl errory
            if err_code in (pycurl.E_UNSUPPORTED_PROTOCOL, pycurl.E_FAILED_INIT, pycurl.E_URL_MALFORMAT):
                raise ResultCodeException(RESULT_INTERNAL_ERROR)
            elif err_code == pycurl.E_COULDNT_RESOLVE_HOST:
                raise ResultCodeException(RESULT_UA_NXDOMAIN)
            elif err_code in (pycurl.E_COULDNT_CONNECT, pycurl.E_OPERATION_TIMEOUTED): # timeout
                raise ResultCodeException(RESULT_UA_TIMEOUT)
            
            # specificke TFTP errory
            elif err_code == pycurl.E_TFTP_PERM:
                raise ResultCodeException(RESULT_ERR_AUTH)
            elif err_code in (pycurl.E_TFTP_NOTFOUND, pycurl.E_TFTP_ILLEGAL, pycurl.E_TFTP_UNKNOWNID, pycurl.E_TFTP_NOSUCHUSER):
                raise ResultCodeException(RESULT_ERR)
            else:
                print('Dbg: pycurl.error: {}'.format(err))
                raise ResultCodeException(RESULT_ERR)

            
class ST_Telnet(ServiceTester):
    """ Service Tester: Telnet """
    # Params: host, port, user, password, timeout

    def runTest(self):
        import telnetlib
        try:
            telnet = telnetlib.Telnet(self.host, port=self.port, timeout=self.timeout)

            def assert_resp(response):
                if response[1] == None: # nebolo nic match-nute regexom
                    enough_lines = bool(response[2].count('\n') >= 2) # moze sa stat, ze nejaka odpoved prisla, ale nematchuje s nicim ocakavanym (takze je to ERR, nie UA_TIMEOUT)
                    if not enough_lines:
                        print('Dbg: assert_resp: not enough lines')
                        raise ResultCodeException(RESULT_UA_TIMEOUT)
                    else:
                        print('Dbg: assert_resp: bad response')
                        raise ResultCodeException(RESULT_ERR)

            #telnet.read_until('login: ')
            assert_resp(telnet.expect(['login: '], timeout=self.timeout))
            #if resp[1] == None:
            #    raise ResultCodeException(RESULT_UA_TIMEOUT)

            telnet.write(self.user + '\n')

            #telnet.read_until('\n')
            assert_resp(telnet.expect(['\n'], timeout=self.timeout))
            
            print('Dbg: Telnet: waitnig for "Password: " prompt')
            #telnet.read_until('Password: ')
            resp = telnet.expect(['Password: ', 'Login incorrect'], timeout=self.timeout)
            assert_resp(resp)
            if resp[0] == 1: # 'Login incorrect'
                raise ResultCodeException(RESULT_ERR_AUTH)
            print('Dbg: Telnet #2: {}'.format(resp))

            telnet.write(self.password + '\n')

            #telnet.read_until('\n')
            assert_resp(telnet.expect(['\n'], timeout=self.timeout))

            print('Dbg: Telnet: waiting for logging in')
            #resp = telnet.read_until('Login incorrect')
            #resp = telnet.expect(['\n.+\n'], timeout=self.timeout)
            #resp = telnet.expect(['\n[^\n]+\n'], timeout=self.timeout)
            resp = telnet.expect(['\w+.*\n'], timeout=self.timeout)
            #print('Dbg: resp:', resp)
            #if resp[1] == None: # nestihlo sa nic precitat
            #    raise ResultCodeException(RESULT_UA_TIMEOUT)
            assert_resp(resp)
            if 'Login incorrect' in resp[2]:
                print('Dbg: Telnet: Login incorrect. resp: {}'.format(resp))
                raise ResultCodeException(RESULT_ERR_AUTH)
            else: # login OK
                print('Dbg: Telnet: Login OK')
                telnet.write('exit\n')
                telnet.read_all()

        except EOFError as eof:
            print('Dbg: EOFError', eof)
            raise ResultCodeException(RESULT_ERR)


class ST_SSH(ServiceTester):
    """ Service Tester: SSH """
    # Params: host, port, user, password, timeout
    def runTest(self):
        import paramiko
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, port=self.port, username=self.user, password=self.password, look_for_keys=False, allow_agent=False, timeout=self.timeout)
            ssh.close()
        except paramiko.AuthenticationException as error:
            print('Dbg: paramiko.AuthenticationException: {}'.format(error))
            raise ResultCodeException(RESULT_ERR_AUTH)
        #except Exception as error:
        #    print('Dbg: unknown error: {}'.format(type(error)))

class ST_SFTP(ServiceTester):
    """ Service Tester: SFTP (SSH-FTP) """
    # Params: host, port, user, password, timeout # Todo: pridat subor (target) na stiahnutie
    def runTest(self):
        import paramiko
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, port=self.port, username=self.user, password=self.password, look_for_keys=False, allow_agent=False, timeout=self.timeout)
            sftp = ssh.open_sftp()
            sftp.listdir()
            sftp.close()
            ssh.close()
        except paramiko.AuthenticationException as error:
            print('Dbg: paramiko.AuthenticationException: {}'.format(error))
            raise ResultCodeException(RESULT_ERR_AUTH)
        #except Exception as error:
        #    print('Dbg: unknown error: {}'.format(type(error)))



class ST_IMAP(ServiceTester):
    """ Service Tester: IMAP """
    # Params: host, port, user, password, timeout # TODO: timeout nie je kniznicou podporovany!
    def runTest(self):
        import imaplib
        try:
            if not self.port:
                self.port = imaplib.IMAP4_PORT # blby default konstruktor...
            imap = imaplib.IMAP4(host=self.host, port=self.port)
            imap.login(self.user, self.password)
            imap.select()
            imap.close()
            imap.logout()
        except imaplib.IMAP4.error as err:
            print('Dbg: imap error')
            if '[AUTHENTICATIONFAILED]' in str(err):
                raise ResultCodeException(RESULT_ERR_AUTH)
            raise ResultCodeException(RESULT_ERR)

class ST_IMAP_SSL(ServiceTester):
    """ Service Tester: IMAP_SSL (IMAPS) """
    # Params: host, port, user, password, timeout # TODO: timeout nie je kniznicou podporovany!
    def runTest(self):
        import imaplib
        try:
            if not self.port:
                self.port = imaplib.IMAP4_SSL_PORT # blby default konstruktor...
            imap = imaplib.IMAP4_SSL(host=self.host, port=self.port)
            imap.login(self.user, self.password)
            imap.select()
            imap.close()
            imap.logout()
        except imaplib.IMAP4.error as err:
            print('Dbg: imap_ssl error')
            if '[AUTHENTICATIONFAILED]' in str(err):
                raise ResultCodeException(RESULT_ERR_AUTH)
            raise ResultCodeException(RESULT_ERR)


class ST_POP(ServiceTester):
    """ Service Tester: POP """
    # Params: host, port, user, password, timeout
    def runTest(self):
        import poplib
        try:
            if not self.port:
                self.port = poplib.POP3_PORT # blby default konstruktor...
            pop = poplib.POP3(host=self.host, port=self.port, timeout=self.timeout)
            pop.user(self.user)
            pop.pass_(self.password)
            pop.list()
            pop.quit()
        except poplib.error_proto as err:
            print('Dbg: POP3 error')
            if '[AUTH]' in str(err):
                raise ResultCodeException(RESULT_ERR_AUTH)
            raise ResultCodeException(RESULT_ERR)

class ST_POP_SSL(ServiceTester):
    """ Service Tester: POP_SSL (POPS) """
    # Params: host, port, user, password, timeout # TODO: timeout nie je kniznicou podporovany!
    def runTest(self):
        import poplib
        try:
            if not self.port:
                self.port = poplib.POP3_SSL_PORT # blby default konstruktor...
            pop = poplib.POP3_SSL(host=self.host, port=self.port)
            pop.user(self.user)
            pop.pass_(self.password)
            pop.list()
            pop.quit()
        except poplib.error_proto as err:
            if '[AUTH]' in str(err):
                raise ResultCodeException(RESULT_ERR_AUTH)
            raise ResultCodeException(RESULT_ERR)


class ST_SMTP(ServiceTester):
    """ Service Tester: SMTP """
    # Params: host, port, user, password, timeout
    def runTest(self):
        import smtplib
        try:
            smtp = smtplib.SMTP(self.host, port=self.port, timeout=self.timeout)

            # HELO # TODO: HELO vs EHLO? ked sa pouzije HELO, nejde TLS
#             status = smtp.helo()[0]
#             if status != 250:
#                 raise ResultCodeException(RESULT_ERR)

            # AUTH
            if self.user or self.password:
#                 smtp.starttls() # moze sa stat, ze server dovoli autentifikaciu iba ak je zapnute tls # TODO: bud dat tuto moznost do nastaveni, alebo to ponechat tak, ze ak je to treba, tak sa pouzije SMTP_SSL, ktore robi sifrovany kanal od zaciatku komunikacie

#                 smtp.ehlo() # po vytvoreni TLS kanalu by sa malo znovu poslat ehlo
                smtp.login(self.user, self.password)
#             smtp.sendmail('jknaperek@gmail.com', ['shift@centrum.sk'], 'skuska z testera')
            smtp.quit()
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused) as err:
            print('Dbg: SMTP AUTH error')
            print(err)
            raise ResultCodeException(RESULT_ERR_AUTH)
        except smtplib.SMTPException as err:
            print('Dbg: SMTP error')
            print(err)
            raise ResultCodeException(RESULT_ERR)

class ST_SMTP_SSL(ServiceTester):
    """ Service Tester: SMTP """
    # Params: host, port, user, password, timeout
    def runTest(self):
        import smtplib
        try:
            smtp = smtplib.SMTP_SSL(self.host, port=self.port, timeout=self.timeout)

            # HELO # TODO: HELO vs EHLO?
#             status = smtp.helo()[0]
#             if status != 250:
#                 raise ResultCodeException(RESULT_ERR)

            # AUTH
            if self.user or self.password:
                smtp.login(self.user, self.password)
#             smtp.sendmail('jknaperek@gmail.com', 'shift@centrum.sk', 'skuska z testera (SSL)') # TODO: otestovat aj bez posielania mailu, ci som autorizovany
            smtp.quit()
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPSenderRefused) as err:
            print('Dbg: SMTP_SSL AUTH error')
            print(err)
            raise ResultCodeException(RESULT_ERR_AUTH)
        except smtplib.SMTPException as err:
            print('Dbg: SMTP_SSL error')
            print(err)
            raise ResultCodeException(RESULT_ERR)


class ST_DNS(ServiceTester):
    """ Service Tester: DNS """
    # Params: host, port, target, timeout
    # Pozor: zavisi na externej kniznici dnspython (http://www.dnspython.org/) Pouzita verzia: 1.9.4 # Licencia: "open sourced under a BSD-style license"
    def runTest(self): # todo: recursive/non-recursive
        import dns.resolver
        try:
            r = dns.resolver.Resolver()
            ns = socket.gethostbyname(self.host)
            print('Dbg: Asking nameserver: {}'.format(ns))
            r.nameservers = [ns]
            r.port = self.port if self.port else 53
            r.timeout = self.timeout # asi nefunguje
            a = r.query(self.target)
        except ImportError:
            print('Dbg: Error: Cannot import external dns library!')
            raise ResultCodeException(RESULT_INTERNAL_ERROR)
        except dns.exception.Timeout:
            raise ResultCodeException(RESULT_UA_TIMEOUT)
        except dns.resolver.NXDOMAIN:
            print('Dbg: DNS response: NXDOMAIN')
            raise ResultCodeException(RESULT_ERR) # return code: NXDOMAIN # poz.: To ale neznamena, ze vysledok testu je NXDOMAIN (to by bolo vtedy, keby nebola najdena IP samotneho DNS serveru)
        except dns.resolver.NoAnswer:
            raise ResultCodeException(RESULT_ERR)
        except dns.resolver.NoNameservers as err: # NoNameservers je vyhodena aj ked server vrati 'recursion requested but not available' -cize pytame sa na domenu mimo jeho zony (a server nerobi rekurziu)
            print(type(err))
            #raise ResultCodeException(RESULT_UA_SOCK_ERROR)
            raise ResultCodeException(RESULT_ERR)


class ST_LDAP(ServiceTester): # zatial bez zabezpecenia # TODO: nejake zabezpecenie (kerberos, etc...)
    """ Service Tester: LDAP """
    # Params: host, port, target, timeout

    def runTest(self):
        import curl
        import pycurl
        try:
            url_str = 'ldap://{}:{}/{}'.format(self.host, self.port, self.target.lstrip('/'))
            c = curl.Curl(url_str)
            c.set_timeout(int(self.timeout))
            response = c.get()
            c.close()
        except pycurl.error as err:
            err_code = err[0]

            # obecne curl errory
            if err_code in (pycurl.E_UNSUPPORTED_PROTOCOL, pycurl.E_FAILED_INIT, pycurl.E_URL_MALFORMAT):
                raise ResultCodeException(RESULT_INTERNAL_ERROR)
            elif err_code == pycurl.E_COULDNT_RESOLVE_HOST:
                raise ResultCodeException(RESULT_UA_NXDOMAIN)
            elif err_code in (pycurl.E_COULDNT_CONNECT, pycurl.E_OPERATION_TIMEOUTED): # timeout
                raise ResultCodeException(RESULT_UA_TIMEOUT)

# TODO: 'successful connection ("bind") implies the user knew the correct password.' ==> raise ERR_AUTH ??? (mozno)
            elif err_code in (pycurl.E_LDAP_CANNOT_BIND, pycurl.E_LDAP_SEARCH_FAILED, pycurl.E_LDAP_INVALID_URL):
                print('Dbg: LDAP error')
                raise ResultCodeException(RESULT_ERR)


class ST_Ping(ServiceTester):
    """ Tester: ICMP Echo (pomocou standardnej utility ping) """
    # Params: host, count, rtt_aggregation ? # TODO: skusit pridat podporu pre timeout, prip. aj pocet pingov
    # rtt_aggregation is aggregation function choice (see constants.py: PING_TAKE_RTT_*)

    def runTest(self):
        import subprocess
        import re
        try:
            p = subprocess.Popen(['ping', '-c {}'.format(self.count), self.host], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate()

            if stderr: # if error has occured
                print('Dbg: unknown host check')
                res = re.match(r'ping: unknown host.*', stderr)
                print(res)
                if res:
                    print('Dbg: ping: unknown host...')
                    raise ResultCodeException(RESULT_UA_NXDOMAIN)

                raise ResultCodeException(RESULT_ERR)

            statistics = 0 #
            TXpackets, RXpackets, packet_loss, ping_time = (None,)*4
            rtt_min, rtt_avg, rtt_max, rtt_mdev = (None,)*4
            main_rtt = None

#             for line in p.stdout:
            for line in stdout.splitlines():
#                 print('Dbg: line')
                if statistics == 1: # parsujeme 1. riadok statistik
                    res = re.match(r'(?P<TXpackets>\d+) packets transmitted, (?P<RXpackets>\d+) received, (?P<packet_loss>\d+)% packet loss, time (?P<time>\d+)ms', line.strip())
                    if res:
                        TXpackets = int(res.group('TXpackets'))
                        RXpackets = int(res.group('RXpackets'))
                        packet_loss = int(res.group('packet_loss'))
                        ping_time = int(res.group('time'))
                    statistics = 2
                elif statistics == 2: # prasujeme 2. riadok statistik
                    res = re.match(r'rtt min/avg/max/mdev = (?P<min>[^\\]+)/(?P<avg>[^\\]+)/(?P<max>[^\\]+)/(?P<mdev>[^\\]+) ms', line.strip())
                    if res:
                        rtt_min = float(res.group('min')) # in msec
                        rtt_avg = float(res.group('avg')) # in msec
                        rtt_max = float(res.group('max')) # in msec
                        rtt_mdev = float(res.group('mdev')) # standard deviation

                        # User-choosen aggregation function (will be returned as duration):
                        main_rtt = { PING_TAKE_RTT_MIN: rtt_min, PING_TAKE_RTT_AVG: rtt_avg, PING_TAKE_RTT_MAX: rtt_max }[self.rtt_aggregation]

                else: # este sme nedosli na koniec
#                     print('Dbg: ping: not at the end')
                    res = re.match(r'--- .+ ping statistics ---', line)
                    if res: # budu nasledovat statistiky
                        statistics = 1
                        continue


        except OSError:
            raise ResultCodeException(RESULT_INTERNAL_ERROR)

        print('Ping vysledky:')
        print('TXpackets: {}'.format(TXpackets))
        print('RXpackets: {}'.format(RXpackets))
        print('packet_loss: {}'.format(packet_loss))
        print('ping_time: {}'.format(ping_time))
        print('rtt_min: {}'.format(rtt_min))
        print('rtt_avg: {}'.format(rtt_avg))
        print('rtt_max: {}'.format(rtt_max))
        print('rtt_mdev: {}'.format(rtt_mdev))

        duration = round(float(main_rtt)/1000, 3) if main_rtt else None

        if packet_loss == 100: # No answer
            final_result = RESULT_UA
        elif packet_loss == 0: # Every ping has returned back
            final_result = RESULT_OK
        else: # TODO: ? What if some pings has returned and some not?
            final_result = RESULT_ERR

        raise ResultCodeException(final_result, duration)

############################################################################################################################
##########    Testers summarization, etc.. #################################################################################
############################################################################################################################

SERVICE_TYPES_TESTER_CLASSES = {
    1: ST_HTTP,
    2: ST_HTTPS,
    3: ST_FTP,
    4: ST_FTP_TLS,
    5: ST_TFTP,
    6: ST_Telnet,
    7: ST_SSH,
    8: ST_SFTP,
    9: ST_IMAP,
    10: ST_IMAP_SSL,
    11: ST_POP,
    12: ST_POP_SSL,
    13: ST_SMTP,
    14: ST_SMTP_SSL,
    15: ST_DNS,
    16: ST_LDAP,
    17: ST_Ping,
    };

def doTest(service_type, **kwargs):
    """ Executes test for specified service type with supplied kwargs and returns tuple(retcode, duration) """
    print('Dbg: ns_test_routines: do_test({}, {})'.format(service_type, kwargs))
    service_tester = SERVICE_TYPES_TESTER_CLASSES[service_type](GLOBAL_TEST_TIMEOUT, **kwargs) # instantialization of corresponding ServiceTester
    result = TestResult()
    with result:
        service_tester.runTest()
    return result.result, result.duration



#############################################################################################
#####################  testing examples #####################################################

def check_module():
    result = TestResult()
    with result:

#         testik = ST_Ping(10, 'google.sk', count=5, rtt_aggregation=PING_TAKE_RTT_MAX)
#         testik = ST_SMTP(10, 'dsl.sk', user='ferko', password='mrkvicka', port=25)

        #testik = ST_HTTP(10, 'localhost:8000', target='/polls/delay/2')
        #testik = ST_HTTP(1, 'bqpdwdsfa.eu', target='/polls/delay/2')

        #testik = ST_HTTPS(10, 'csob.sk', target='/')
        #testik = ST_HTTPS(10, 'ib24.csob.sk', target='/')

        #testik = ST_FTP(0.01, 'bqpd.eu')
        #testik = ST_FTP(0.01, '147.175.146.89', user='anonymous')
        #testik = ST_FTP(4, '192.168.122.135', user='anonymous', password='')

        #testik = ST_FTP_TLS(4.01, 'bqpd.eu', user='foo', password='f')

        #testik = ST_SSH(0.1, 'bqpd.eu', user='foo', password='f')
        #testik = ST_SSH(10, '10.8.0.1', user='foo', password='f')

        #testik = ST_DNS(3, 'ns.google.com', target='bqpd.eur')
        #testik = ST_DNS(3, '8.8.8.8', target='bqpd.eu')
        #testik = ST_DNS(3, '193.87.160.242', target='podpora.rirs.sk')
        #testik = ST_DNS(3, 'ns.rirs.sk', target='podpora.rirs.sk')
        #testik = ST_DNS(3, 'ns.rirs.sk', target='public.rirs.sk')

        #testik = ST_Telnet(4, 'cunik', user='root', password='aaa')
        #testik = ST_Telnet(4, '192.168.122.250', user='root', password='raa')
        #testik = ST_Telnet(4, '192.168.122.250', user='jou', password='r')

        #testik = ST_TFTP(5, '192.168.122.250', port=69, target='manual.txt')
        #testik = ST_TFTP(1, '192.168.122.250', port=69, target='skuska.txt')
        #testik = ST_TFTP(1, 'bqpd.eu', port=69, target='fifo')
        #testik = ST_TFTP(4, '192.168.122.250', port=69, target='skuska.txt')

        #testik = ST_LDAP(17, '192.168.122.250', port=389, target='uid=jou,ou=People,dc=debuntu,dc=local')

        #testik = ST_Ping(10, host='google.com')
        #testik = ST_Ping(10, host='google.com')

        #testik = ST_POP(5, 'pop3.centrum.sk', user='shift', password='')
        #testik = ST_POP_SSL(3, 'pop.gmail.com', user='jknaperek', password='')

        #testik = ST_IMAP(10, 'imap.googlemail.com', user='jknaperek', password='')
        #testik = ST_IMAP(3, 'imap.centrum.sk', user='shift', password='')
        #testik = ST_IMAP_SSL(3, 'imap.centrum.sk', user='shift', password='')
        #testik = ST_IMAP_SSL(3, 'imap.gmail.com', user='jknaperek', password='')

        #testik = ST_SMTP(3, '192.168.122.135')
        #testik = ST_SMTP_SSL(3, '192.168.122.135')
        #testik = ST_SMTP_SSL(3, 'smtp.gmail.com', user='jknaperek', password='*')
        #testik = ST_SMTP_SSL(3, 'smtp.gmail.com')
        #testik = ST_SMTP_SSL(3, 'smtp.gmail.com', user='jknaperek', password='')
#         testik = ST_SMTP(3, 'smtp.gmail.com')

#         testik = ST_DNS(3, 'ns.rirs.sk', target='public.rirs.sk')

        res = testik.runTest()

    print('hotovo')
    print('Duration: {}'.format(result.duration))
    print('Result: {}'.format(result.result))
    printResult(result.result)


if __name__ == '__main__':
    check_module()
