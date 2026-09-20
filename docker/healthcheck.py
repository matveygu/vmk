"""Probe the existing HTTP worker without booting another Django process."""
import os
import sys
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check():
    hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
    host = next((value.strip().lstrip('.') for value in hosts.split(',')
                 if value.strip() and value.strip() != '*'), 'localhost')
    # Only connect to loopback; Host supports production's explicit domain allowlist.
    # HTTPS is terminated by Nginx in production, just as for normal requests.
    request = Request('http://127.0.0.1:8000/_health/', headers={
        'Host': host, 'X-Forwarded-Proto': 'https',
    })
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            return response.status == 200 and response.read(16) == b'ok'
    except (URLError, OSError):
        return False


if __name__ == '__main__':
    sys.exit(0 if check() else 1)
