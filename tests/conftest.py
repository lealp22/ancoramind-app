"""Shared pytest configuration for unit and integration suites.

``Settings.app_env`` defaults to ``production`` (specs/023 T2), which requires
production-only secrets such as ``AGENT_OS_SECURITY_KEY``. The test suites run
as an explicit development environment, the same opt-in a local developer
declares in ``.env``. Set before any test module imports ``src.main``, which
builds the app at import time. Tests asserting production behaviour override
``APP_ENV`` explicitly via ``monkeypatch``.
"""

import os

os.environ.setdefault("APP_ENV", "development")
