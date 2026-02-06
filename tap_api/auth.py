"""TAP API authentication — v0 uses Django session auth.

Log in via /admin/, session cookie carries to API calls.
Single evolution point: when token auth is needed, add it here.
"""

from ninja.security import django_auth

session_auth = django_auth
