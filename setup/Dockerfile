FROM alpine:3.21
# docker-cli so the wizard can put a MySQL client on the deployment's network
# before it writes anything: an external database is checked where the services
# will reach it, which is not this container.
RUN apk add --no-cache python3 openssl docker-cli
WORKDIR /wizard
COPY setup.html /wizard/index.html
COPY script.js /wizard/script.js
COPY style.css /wizard/style.css
COPY server.py /wizard/server.py
COPY deploy.sh /wizard/cgi-bin/deploy
COPY deploy_response.py /wizard/deploy_response.py
COPY deploy_config.py /wizard/deploy_config.py
COPY verify_database.py /wizard/verify_database.py
COPY verify_ingest.py /wizard/verify_ingest.py
COPY write_request_env.py /wizard/write_request_env.py
COPY studies_index_template.html /wizard/studies_index_template.html
RUN sed -i 's/\r$//' /wizard/cgi-bin/deploy && \
    chmod +x /wizard/cgi-bin/deploy
EXPOSE 9999
CMD ["python3", "/wizard/server.py"]
