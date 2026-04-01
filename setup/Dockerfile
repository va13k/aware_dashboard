FROM alpine:3.21
RUN apk add --no-cache busybox-extras curl \
    && ARCH=$(uname -m) \
    && case "$ARCH" in x86_64) ARCH=x86_64;; aarch64) ARCH=aarch64;; *) echo "Unsupported arch: $ARCH" && exit 1;; esac \
    && curl -fsSL "https://download.docker.com/linux/static/stable/${ARCH}/docker-27.5.1.tgz" -o /tmp/docker.tgz \
    && tar xzf /tmp/docker.tgz --strip-components=1 -C /usr/local/bin docker/docker \
    && rm /tmp/docker.tgz \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-${ARCH}" -o /usr/local/lib/docker/cli-plugins/docker-compose \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
WORKDIR /wizard
COPY setup.html /wizard/index.html
COPY deploy.sh /wizard/cgi-bin/deploy
COPY status.sh /wizard/cgi-bin/status
RUN chmod +x /wizard/cgi-bin/deploy /wizard/cgi-bin/status
EXPOSE 9999
CMD ["httpd", "-f", "-p", "9999", "-h", "/wizard"]