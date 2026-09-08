# Nginx

The deployment's only public surface. Every request from a browser or a phone
arrives here, and nothing else in the stack publishes a port a participant or a
researcher can reach.

The routes themselves are listed in
[docs/dev/architecture.md](../docs/dev/architecture.md#what-nginx-does-with-a-request),
sorted by what the caller proves. This document is about the files in this
directory: which of them a deployment writes, why there are two configurations, and
the two idioms every location is built on.

---

## Two configurations, one of them mounted

[`http.conf`](http.conf) and [`https.conf`](https.conf) carry the same routes. The
deploy mounts one of them as `default.conf`, chosen by the study's protocol:

```yaml
- ./nginx/${PROTOCOL:-http}.conf:/etc/nginx/conf.d/default.conf:ro
```

What the HTTPS one adds is the transport and nothing about routing: a `listen 80`
server that answers every request with a 301, a `listen 443 ssl` server holding the
certificate paths and the cipher settings, and `Strict-Transport-Security` beside
the headers both of them send.

Both files therefore have to be edited together. A route added to one and not the
other is a deployment that works until somebody turns on TLS.

---

## What the deploy writes, and what happens without it

Two files here are generated, and neither is in git.

**`study-key.conf`** carries the key a phone presents, as a `map` the routes compare
against. It is mounted as `00-study-key.conf`, and the prefix is load order: nginx
reads `conf.d` alphabetically, so the map exists before `default.conf` uses it.

Without it nginx does not start:

```
nginx: [emerg] unknown "study_key" variable
```

That is the intended failure. The alternative to refusing would be serving the study
configuration to anyone who asked, and that file carries the broker credential and,
on the direct dataflow, the database account a phone opens.

**`auth/.htpasswd`** carries the researcher's login, in Apache's `$apr1$` form,
which is what `auth_basic` reads. The deploy computes the hash itself rather than
calling a tool for it, so a deployment needs nothing installed beyond Docker and
Python.

---

## The two idioms every location uses

**An upstream is named through a variable.**

```nginx
set $dashboard_upstream http://dashboard:80;
proxy_pass $dashboard_upstream;
```

Written as a literal, `proxy_pass http://dashboard:80` is resolved when nginx reads
its configuration, and a container that is not up yet is a proxy that refuses to
start. Through a variable it is resolved per request, by the resolver at the top of
the file:

```nginx
resolver 127.0.0.11 ipv6=off valid=30s;
```

`127.0.0.11` is Docker's own DNS on the compose network. This is what lets nginx come
up first and answer as each service behind it becomes ready, rather than the whole
public surface waiting on the slowest container.

**A session is proved by a subrequest.**

```nginx
auth_request /auth/validate;
error_page 401 = @require_login;
```

`/auth/validate` is an internal location that asks the API, with the body dropped,
before the real request is proxied. Every researcher-facing route carries both
lines. The one deliberate exception is the live WebSocket, which carries the
`auth_request` and omits the `error_page`: a socket cannot render a login page, so
the handshake is refused and the page handles it.

---

## The pages served from here

These are served as files rather than proxied. The three that live here take their
stylesheets and scripts from [`assets/`](assets); the fourth is written by the deploy.

| File | At | Is |
| --- | --- | --- |
[`index.html`](index.html) | `/` | The landing page, public, linking to the four parts of the deployment |
[`backup.html`](backup.html) | `/backup/` | Backup and restore, behind the researcher login |
[`setup-loading.html`](setup-loading.html) | `/setup-launch/` | A page that polls port 9999 and redirects to the setup wizard as soon as it answers, for reopening the wizard from the deployment itself |
`studies/index.html` | `/studies/` | The join page, written by the deploy from the study, not from this directory |

---

## Working on it

- **Edit both configurations.** There is no include shared between them, and the
  test suite does not compare them.
- **A new route reachable by a phone compares `$study_key`.** A phone holds no
  session, so the key in its path is the credential, and it is compared rather than
  captured and dropped.
- **A new researcher-facing route carries the two `auth_request` lines**, or it is
  public whether that was intended or not.
- **Check a change before deploying it**, which needs the generated map beside it:

  ```bash
  docker run --rm -v "$PWD/nginx/http.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "$PWD/nginx/study-key.conf:/etc/nginx/conf.d/00-study-key.conf:ro" \
    nginx:alpine nginx -t
  ```
