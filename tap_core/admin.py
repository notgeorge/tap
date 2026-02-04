"""
TAP Core Admin Configuration
=============================================================================
Registers core models with Django's admin interface.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from tap_core.models import User

# Register the custom User model with Django's built-in UserAdmin
# This gives us the full user management UI (password hashing, permissions, etc.)
admin.site.register(User, UserAdmin)
