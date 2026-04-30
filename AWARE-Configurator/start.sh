#!/bin/sh
set -eu

# Seed the staticfiles volume from the pre-baked build-time copy (fast path).
# Falls back to collectstatic only if the baked directory is somehow missing.
if [ -d /app/staticfiles_baked ] && [ "$(ls -A /app/staticfiles_baked)" ]; then
    cp -rn /app/staticfiles_baked/. /app/staticfiles/
else
    python manage.py collectstatic --noinput
    find reactapp/build -maxdepth 1 -type f ! -name 'index.html' -exec cp {} staticfiles/ \;
fi

exec gunicorn aware_light_config_Django.wsgi:application -c util/gunicorn.conf.py
