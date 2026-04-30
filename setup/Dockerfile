FROM alpine:3.21
RUN apk add --no-cache python3 openssl
WORKDIR /wizard
COPY setup.html /wizard/index.html
COPY script.js /wizard/script.js
COPY style.css /wizard/style.css
COPY server.py /wizard/server.py
COPY deploy.sh /wizard/cgi-bin/deploy
COPY deploy_config.py /wizard/deploy_config.py
COPY write_request_env.py /wizard/write_request_env.py
COPY studies_index_template.html /wizard/studies_index_template.html
RUN sed -i 's/\r$//' /wizard/cgi-bin/deploy && \
    chmod +x /wizard/cgi-bin/deploy
EXPOSE 9999
CMD ["python3", "/wizard/server.py"]
