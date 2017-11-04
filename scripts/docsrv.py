"""
Usage:
import docsrv
docsrv.start_session()
# Server will start as part of current process, if not yet
# Current implementation assumes there's no race between
# several processes trying to start the server.
...
[docsrv.submit_job()]
[docsrv.submit_job()]
...
results = docsrv.end_session() # ==> {'errors': [...], 'warnings': [...]}
# Server will exit when all sessions (from all processes) ended
"""

import os
import re
import sys
import time
import socket
import threading
import traceback
import SocketServer
import Queue
import util

import pythoncom
import win32com.client 

HOST, PORT = "localhost", 13053
SOCK_BUFSZ = 4096

class Globals: pass
g = Globals()
g.server = None

############# Common ################

g.enable_log = False
g.print_lock = threading.Lock()
def log(msg):
    if not g.enable_log: return
    with g.print_lock:
        print threading.current_thread().name, msg

def socket_readall(sock):
    rcv = sock.recv(SOCK_BUFSZ)
    data = rcv
    while len(rcv) == SOCK_BUFSZ:
        # By convention, transmitted data length should not be a multiple of SOCK_BUFSZ
        # It's not a good design, but simplifies the code
        # We'll assume all send/recv to the server happens from this very module
        # If not, next line will hang (but that's ok)
        rcv = sock.recv(SOCK_BUFSZ)
        data += rcv
    return data

def socket_sendall(sock, msg):
    # See comment above in socket_readall()
    if len(msg) % SOCK_BUFSZ == 0: msg += ' '
    sock.sendall(msg)

############# Client ################

g.session_started = False
g.pid = os.getpid()

def communicate(msg):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    socket_sendall(sock, msg)
    return socket_readall(sock)
    
def submit_job(cmd):
    assert g.session_started
    rsp = communicate(cmd)
    assert rsp.startswith("OK")
    g.submitted_jobs[rsp.split()[1]] = cmd

def start_session():
    log("start_session()")
    if g.session_started:
        # Allow multiple invocations of start_session(), only first one will take effect
        return
    try:
        assert communicate('PING') == 'PONG'
    except socket.error:
        # Couldn't connect to existing server
        # Start one as part of current process
        start_doc_server()
    # Connected: register itself
    assert communicate("START %d"%g.pid) == "OK"
    g.session_started = True
    g.submitted_jobs = {}

def wait_results():
    results = {'errors': [], 'warnings': []}
    while g.submitted_jobs:
        for job_id in g.submitted_jobs.keys():
            rsp = communicate("JOB_STATUS? %s"%job_id).split('|')
            assert rsp.pop(0) == "OK"
            if rsp[0] == "NOT_READY": continue
            if rsp[0] == 'ERR_OPEN_FAILED':
                results['errors'].append({'status': rsp[0], 'filename': rsp[1], 'errmsg': '|'.join(rsp[2:])})
            else:
                assert rsp.pop(0) == 'OPEN_OK'
                visio_filename = rsp.pop(0)
                while rsp:
                    status = rsp.pop(0)
                    if status == "WARN_NEEDS_PNG":
                        results['warnings'].append({'status': status, 'filename': visio_filename, 'page': rsp.pop(0),
                            'svgname': rsp.pop(0), 'pngname': rsp.pop(0)})
                    elif status == "ERR_EXPORT_FAILED":
                        results['errors'].append({'status': status, 'filename': visio_filename, 'page': rsp.pop(0),
                            'errmsg': rsp.pop(0)})
                    elif status == "ERR_PAGE_NOT_FOUND":
                        results['errors'].append({'status': status, 'filename': visio_filename, 'page': rsp.pop(0),
                            'available_pages': rsp.pop(0)})
                    else:
                        results['errors'].append({'status': "ERR_RESULTS_PARSING_ERROR"})
            del g.submitted_jobs[job_id]
        if g.submitted_jobs: time.sleep(1)
    return results

def end_session():
    if not g.session_started:
        return None
    try:
        # If we have submitted jobs in flight, block until finished
        results = wait_results()
        assert communicate("END %d"%g.pid) == "OK"
    finally:
        # If this process is server, block until finished
        if g.server:
            g.server.join()
    return results

############# Server ################

g.shutdown_event = threading.Event()

g.visio_queue = Queue.Queue()
g.excel_queue = Queue.Queue()

g.sessions = set()
g.sessions_lock = threading.Lock()

g.complete_jobs = {}
g.complete_jobs_lock = threading.Lock()

g.job_id = 0
g.job_id_lock = threading.Lock()

def get_job_id():
    with g.job_id_lock:
        g.job_id += 1
        result = "%s"%g.job_id
    return result

def start_doc_server():
    log("start_doc_server()")
    g.server = threading.Thread(target=doc_server)
    g.server.start()

def doc_server():
    """ This thread starts TCP server, Visio and Excel processing threads
        and waits until those are finished """
    tcp_server = ThreadedTCPServer(("localhost", PORT), ThreadedTCPRequestHandler)
    server_thread = threading.Thread(target=tcp_server.serve_forever)
    server_thread.daemon = True # Exit the thread when the main thread terminates
    server_thread.start()

    visio_thread = threading.Thread(target=visio_server)
    visio_thread.daemon = True # Exit the thread when the main thread terminates
    visio_thread.start()

    # Wait until shut down is signalled, then exit
    g.shutdown_event.wait()
    tcp_server.shutdown()
    tcp_server.server_close()

    g.visio_queue.put({'cmd': 'FINISH'})
    visio_thread.join()

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        data = socket_readall(self.request)
        log("handle(%s)"%data)
        if data == "SHUTDOWN":
            # Command to shut down server (is it needed?)
            socket_sendall(self.request, "OK")
            g.shutdown_event.set()
        elif data.startswith('VISIO'):
            # Visio export command
            job_id = get_job_id()
            g.visio_queue.put({'cmd': data, 'id': job_id})
            socket_sendall(self.request, "OK %s"%job_id)
        elif re.search(r'START (\d+)', data):
            # Command to start session
            log("received START request: %s"%data)
            with g.sessions_lock:
                g.sessions.add(data.split()[1])
            log("sessions: %s"%g.sessions)
            socket_sendall(self.request, "OK")
        elif re.search(r'END (\d+)', data):
            # Command to end session
            log("received END request: %s"%data)
            with g.sessions_lock:
                g.sessions.remove(data.split()[1])
                if not g.sessions:
                    g.shutdown_event.set()
            log("sessions: %s"%g.sessions)
            socket_sendall(self.request, "OK")
        elif data.startswith('JOB_STATUS?'):
            # Command to check job status
            job_id = data.split()[1]
            with g.complete_jobs_lock:
                if job_id in g.complete_jobs:
                    socket_sendall(self.request, "OK|%s"%g.complete_jobs[job_id])
                else:
                    socket_sendall(self.request, "OK|NOT_READY")
        elif data.startswith('PING'):
            # Command to check server running
            socket_sendall(self.request, "PONG")
        else:
            socket_sendall(self.request, "CMD_UNKNOWN")


def svg_needs_png(fname):
    """
    Check to see if this SVG needs to be represented as a png
    """
    svg = open(fname).read()
    # Detect metafile foreign objects.  These mess up SVG conversion
    return re.search('<v:foreignData .*?v:data="data:metafile', svg)

def complete_job(job, status):
    with g.complete_jobs_lock:
        g.complete_jobs[job["id"]] = status

def visio_job_queue_process(app):
    while True:
        job = g.visio_queue.get()
        log("visio_job_queue_process() received job: %s"%job)
        a = job["cmd"].split("|")
        cmd = a.pop(0)
        if cmd == "FINISH":
            # We are told to wrap up
            break
        if cmd == "VISIO_EXPORT_PAGES_BY_NAME":
            # VISIO_EXPORT_PAGES_BY_NAME|visio_filename|pagename1|outfilename1|pagename2|...
            visio_filename = os.path.abspath(a.pop(0))
            log("Opening Visio: %s"%visio_filename)
            try:
                doc = app.Documents.OpenEx(visio_filename, 1+2+8+0x80+0x100) # Copy | RO | DontList | MacrosDisabled | NoWorkSpace
            except:
                complete_job(job, "ERR_OPEN_FAILED|%s|%s"%(visio_filename, traceback.format_exc()))
                continue
            status = "OPEN_OK|%s"%visio_filename
            try:
                page_names = [page.name for page in doc.Pages]
                while a:
                    page_name, outname = a.pop(0), os.path.abspath(a.pop(0))
                    if page_name in page_names or page_name.isdigit() or page_name == "-1":
                        page = None
                        if (page_name in page_names):
                            page = doc.Pages[page_names.index(page_name)]
                        elif page_name == "-1":
                            # -1 means "default" page (usually in .vsd imported from MS Word)
                            page = app.ActivePage
                        else:
                            page = doc.Pages[int(page_name)]
                        try:
                            # Select all items on a page and export them
                            # If we would export the page itself, its margins would be preserved
                            # (that's not desired since many users leave unruly margins)
                            page.CreateSelection(1, 0x100).Export(outname)
                            if outname.endswith('.svg') and svg_needs_png(outname):
                                pngname = outname[:-3] + 'png'
                                page.CreateSelection(1, 0x100).Export(pngname)
                                status += "|WARN_NEEDS_PNG|%s|%s|%s"%(page_name, outname, pngname)
                        except:
                            status += "|ERR_EXPORT_FAILED|%s|%s"%(page_name, traceback.format_exc())
                    else:
                        status += "|ERR_PAGE_NOT_FOUND|%s|%s"%(page_name, ', '.join(page_names))
            finally:
                doc.Saved = True # Prevent "Save" dialog box
                doc.Close()
                doc = None
                complete_job(job, status)

def visio_server():
    log("visio_server()")
    # Log pm_doc usage
    g.app_usage_thread = threading.Thread(target=util.get_toolconfig()['app_usage'])
    g.app_usage_thread.start()
    #
    pythoncom.CoInitialize() # pythoncom calls CoInitialize (apartment_threaded)
                             # on import, but that happens in main thread.
                             # So here we call it for visio server thread 
    app = win32com.client.Dispatch('Visio.InvisibleApp')
    # Need to be careful not to give away 'app', since any stray references to it
    # will prevent Visio COM object to be garbage collected and destroyed
    try:
        app.AlertResponse = 1 # Auto-respond IDOK on all dialog boxes
        visio_job_queue_process(app)
    finally:
        app.Quit()
        app = None
        pythoncom.CoUninitialize()
    log("visio_server() finished")

############# Test/Debug ############

if __name__ == "__main__":
    g.enable_log = True
    start_session()
    # Should be started from "tests" directory
    submit_job("VISIO_EXPORT_PAGES_BY_NAME|src/assets/test.vsdx|Small test picture|c:/temp/outfile.svg")
    submit_job("VISIO_EXPORT_PAGES_BY_NAME|src/assets/png_overview.vsdx|Die Strategy|c:/temp/outfile2.svg")
    submit_job("VISIO_EXPORT_PAGES_BY_NAME|src/assets/embedded_emf.vsdx|emf|c:/temp/outfile3.svg")
    submit_job("VISIO_EXPORT_PAGES_BY_NAME|src/assets/SVG_Block_diagram.vsd|SVG Superset|c:/temp/outfile4.svg")
    submit_job("VISIO_EXPORT_PAGES_BY_NAME|src/assets/SVG_Block_diagram.vsd|Revision info|c:/temp/outfile5.svg")
    log("waiting for end_session()")
    result = end_session()
    log("end_session() returned: %s"%result)
    log("waiting for g.serverjoin()")
    g.server.join()
    pythoncom.CoUninitialize() # Main thread's CoUninitialize
    log("main() finished")
    if result["errors"]:
        print "ERROR"
        print result
        exit(1)
