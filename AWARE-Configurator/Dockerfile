FROM node:18-alpine AS frontend
WORKDIR /app/reactapp

COPY reactapp/package*.json ./
RUN npm install

COPY reactapp/ .

ARG SERVER_PROTOCOL=http
ARG SERVER_IP=localhost
ARG SERVER_PORT=80
ARG SERVER_BASE_PATH=/configurator

RUN printf "REACT_APP_SERVER_PROTOCOL=%s\nREACT_APP_SERVER_IP=%s\nREACT_APP_SERVER_PORT=%s\nREACT_APP_SERVER_BASE_PATH=%s\n" \
    "${SERVER_PROTOCOL}" "${SERVER_IP}" "${SERVER_PORT}" "${SERVER_BASE_PATH}" > .env.production

RUN PUBLIC_URL=/configurator npm run build



FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
COPY --from=frontend /app/reactapp/build ./reactapp/build

ENV PUBLIC_HOST="localhost"
ENV DJANGO_STATIC_ROOT="/app/staticfiles_baked"

RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

RUN mkdir -p /app/saved_json_files /app/staticfiles_baked /app/staticfiles

# Collect statics at build time into staticfiles_baked so startup is a fast copy
ARG DJANGO_SECRET_KEY=build-time-collectstatic
RUN DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY} python manage.py collectstatic --noinput && \
    find reactapp/build -maxdepth 1 -type f ! -name 'index.html' -exec cp {} staticfiles_baked/ \;

ENV DJANGO_STATIC_ROOT="/app/staticfiles"

EXPOSE 8000
CMD ["/app/start.sh"]
