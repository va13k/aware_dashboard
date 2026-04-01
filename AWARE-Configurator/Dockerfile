FROM node:18-alpine AS frontend
WORKDIR /app/reactapp

COPY reactapp/package*.json ./
RUN npm install

COPY reactapp/ .

ARG SERVER_PROTOCOL=http
ARG SERVER_IP=localhost
ARG SERVER_PORT=80
ARG SERVER_BASE_PATH=/configurator

RUN sed -i "s|\[REPLACEABLE_PROTOCOL\]|${SERVER_PROTOCOL}|g"   src/settings.js && \
    sed -i "s|\[REPLACEABLE_IP_ADDR\]|${SERVER_IP}|g"          src/settings.js && \
    sed -i "s|\[REPLACEABLE_PORT_NUM\]|${SERVER_PORT}|g"        src/settings.js && \
    sed -i "s|\[REPLACEABLE_BASE_PATH\]|${SERVER_BASE_PATH}|g"  src/settings.js

ENV DISABLE_ESLINT_PLUGIN=true
RUN PUBLIC_URL=/configurator npm run build



FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
COPY --from=frontend /app/reactapp/build ./reactapp/build

ENV DJANGO_ALLOWED_HOSTS="localhost"
ENV DJANGO_STATIC_ROOT="/app/staticfiles"

RUN python manage.py collectstatic --noinput && \
    find reactapp/build -maxdepth 1 -type f ! -name 'index.html' -exec cp {} staticfiles/ \;

RUN useradd -r -s /bin/false appuser && \
    mkdir -p /app/saved_json_files && \
    chown -R appuser:appuser /app/saved_json_files
USER appuser

EXPOSE 8000
CMD ["gunicorn", "aware_light_config_Django.wsgi:application", "-c", "util/gunicorn.conf.py"]