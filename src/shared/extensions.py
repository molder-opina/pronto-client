"""
Shared Flask extensions.
"""

from flask_wtf.csrf import CSRFProtect

# CSRF Protection instance (shared across apps)
csrf = CSRFProtect()
