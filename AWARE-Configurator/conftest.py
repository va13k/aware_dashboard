"""Pytest bootstrap for the Configurator's Django-backed tests.

Importing ``App01.general`` executes ``aware_light_config_Django.settings`` at
module load, which needs a settings module and a secret key. We set both here
(before any test module is imported) and put the Configurator root on the path
so ``App01`` / ``aware_light_config_Django`` are importable. ``settings.py``
resolves PROJECT_ROOT to the repo root when ``/project`` is absent, so no
container mount is required.
"""
import os
import pathlib
import sys

_CONFIGURATOR_ROOT = pathlib.Path(__file__).resolve().parent
if str(_CONFIGURATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONFIGURATOR_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aware_light_config_Django.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
