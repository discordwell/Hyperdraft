"""WSGI entrypoint that wraps giftless with ProxyFix.

Fly.io terminates TLS at the edge and forwards as plain HTTP with
X-Forwarded-Proto: https. Without ProxyFix, giftless generates verify
URLs with scheme=http, which git-lfs may reject when the original LFS
URL was https.
"""
from werkzeug.middleware.proxy_fix import ProxyFix

from giftless.wsgi_entrypoint import app

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
