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

ENV PUBLIC_HOST="localhost"
ENV DJANGO_STATIC_ROOT="/app/staticfiles"

RUN chmod +x /app/start.sh

RUN mkdir -p /app/saved_json_files /app/staticfiles

EXPOSE 8000
CMD ["/app/start.sh"]
