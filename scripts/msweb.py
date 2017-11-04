import os
import urllib
import httplib
import urlparse
from base64 import encodestring, decodestring

if os.name == 'nt':
    import sspi
else:
    import kerberos

cookie_jar = {}

HTTP_TIMEOUT = 15 # seconds, for blocking operations

def get_krb_http_auth(host):
    hostname = host.split(':')[0] # remove port
    if os.name == 'nt':
        s = sspi.ClientAuth('Kerberos', targetspn="HTTP/" + hostname)
        a,b = s.authorize(None)
        auth = encodestring(b[0].Buffer).replace("\012", "")
    else:
        # On Linux need kerberos.so. Getting kerberos.so:
        # git clone https://github.com/apple/ccs-pykerberos.git
        # cd ccs-pykerberos.git
        # python setup.py build
        # --> kerberos.so in build/libxxx/ --> copy to same dir as python code
        __, krb_context = kerberos.authGSSClientInit("HTTP@" + hostname)
        kerberos.authGSSClientStep(krb_context, "")
        auth = kerberos.authGSSClientResponse(krb_context)
    return auth

def http_request(url, headers, body=None, debuglevel=0, auth=True):
    scheme, host, path, params, query, fragment = urlparse.urlparse(url)
    path = urllib.quote(urllib.unquote(path))
    if query: path += '?' + query
    assert not (fragment or params), "not yet supported: (%s:%s)"%(fragment,params)
    fconn = httplib.HTTPConnection if scheme == 'http' else httplib.HTTPSConnection
    method = 'GET' if body is None else 'POST'
    h = fconn(host, timeout=HTTP_TIMEOUT)
    h.set_debuglevel(debuglevel)
    mod_headers = headers.copy()
    try:
        if auth:
            auth = get_krb_http_auth(host)
            mod_headers.update({'Authorization': 'Negotiate ' + auth})
    except sspi.error:
        pass
    if host in cookie_jar:
        # super crude support for cookies (for athentification)
        # neglects cookie path, just looks at the host
        mod_headers.update({'Cookie': cookie_jar[host]})
    h.request(method, path, body, mod_headers)
    resp = h.getresponse()
    if resp.status == httplib.FOUND: # 302 Document Moved
        cookie = resp.getheader('Set-Cookie', None)
        if cookie is not None:
            cookie_jar[host] = cookie
        return http_request(resp.msg['location'], headers) # Always "GET" on 302
    return resp, resp.read()

