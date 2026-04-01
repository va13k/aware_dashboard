FROM alpine:3.21
RUN apk add --no-cache busybox-extras python3
WORKDIR /wizard
COPY setup.html /wizard/index.html
COPY deploy.sh /wizard/cgi-bin/deploy
RUN sed -i 's/\r$//' /wizard/cgi-bin/deploy && \
    chmod +x /wizard/cgi-bin/deploy
EXPOSE 9999
CMD ["httpd", "-f", "-p", "9999", "-h", "/wizard"]
