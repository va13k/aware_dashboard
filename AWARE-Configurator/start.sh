#!/bin/sh
set -eu

python manage.py collectstatic --noinput
find reactapp/build -maxdepth 1 -type f ! -name 'index.html' -exec cp {} staticfiles/ \;

exec gunicorn aware_light_config_Django.wsgi:application -c util/gunicorn.conf.py
