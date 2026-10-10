"""
wsgi.py - Entry point for PythonAnywhere (or any WSGI host).
In PythonAnywhere's WSGI file, the setup guide shows the two lines to use.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp.app import app as application  # noqa: E402
