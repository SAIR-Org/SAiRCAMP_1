# Nginx as a Reverse Proxy — Mental Model, Concepts & Reference

---

## Part 1 — What Is a Reverse Proxy? (The Mental Model)

### Start with a hotel reception desk

A hotel has hundreds of rooms. Guests don't walk directly to room 247 — they go to the
reception desk first. The receptionist looks at their request ("I have a reservation for
the spa") and routes them to the right place. The guest never needs to know which floor
the spa is on, what the internal phone extension is, or how the hotel is organised.

**Nginx is the reception desk for your server.**

You have four services running on different ports:
```
Streamlit dashboard  → port 1080
FastAPI online API   → port 1078
Batch API            → port 1079
MLflow UI            → port 1081
```

Without nginx, users would need to know which port each service runs on:
```
http://your-domain.com:1080   ← dashboard
http://your-domain.com:1078   ← api
http://your-domain.com:1079   ← batch
http://your-domain.com:1081   ← mlflow
```

This is a problem:
- Ports above 1024 are non-standard — browsers hide them, firewalls block them
- Users have to remember four different addresses
- You can't use a domain cleanly — `mlops123.duckdns.org:1079` looks broken

With nginx, users see one clean address:
```
http://your-domain.com/           ← dashboard
http://your-domain.com/api/       ← api
http://your-domain.com/batch/     ← batch
http://your-domain.com/mlflow/    ← mlflow
```

Nginx receives all requests on port 80 (standard HTTP) and routes to the right service.
Users never see the port numbers. The internal structure is invisible.

---

### Forward proxy vs reverse proxy — why the name matters

These terms confuse students. The direction refers to which side the proxy is on.

**Forward proxy** — sits in front of clients, on behalf of clients:
```
Clients → [Forward Proxy] → Internet
```
Example: A corporate VPN. The proxy makes outbound requests on behalf of users.
The server sees the proxy's IP, not the user's.

**Reverse proxy** — sits in front of servers, on behalf of servers:
```
Internet → [Reverse Proxy] → Servers
```
Example: Nginx in this project. The proxy receives inbound requests and routes them
to internal services. The client sees one address, not the internal structure.

**In this project:** nginx is a reverse proxy. Every request from the internet hits
nginx first. Nginx decides which container handles it.

---

### What breaks without nginx

When you first deployed the Docker Compose app, it worked locally. You hit
`localhost:1080` and saw the dashboard. Then you added nginx and a domain — and everything broke.

Three separate things broke simultaneously:

**1. Streamlit's WebSocket connection died**

Streamlit doesn't just serve HTML. It maintains a persistent WebSocket connection
(`/_stcore/stream`) between the browser and the server for live updates.
A WebSocket starts as an HTTP request but then upgrades to a different protocol.
Nginx doesn't forward the `Upgrade` header by default — so the upgrade never happens,
and Streamlit loads a blank page.

**2. FastAPI generated wrong internal URLs**

FastAPI was mounted at `/` but was now being served at `/api/`.
When its docs page tried to load `openapi.json`, it requested `/openapi.json`
instead of `/api/openapi.json`. The request hit nginx, which didn't know what to do
with `/openapi.json`, so the docs page was blank.

**3. nginx used `localhost` instead of `127.0.0.1`**

This is the most subtle bug. nginx resolves `localhost` to both `127.0.0.1` (IPv4)
and `::1` (IPv6) and tries both. Docker containers bind to `0.0.0.0` (all IPv4 interfaces)
but not to IPv6. The IPv6 connection attempt fails, nginx gives up, and the browser
sees a 502 Bad Gateway.

All three bugs had different causes and needed different fixes.

---

## Part 2 — Nginx Concepts

### The configuration structure

Nginx is configured in `/etc/nginx/`. The structure on Ubuntu:

```
/etc/nginx/
├── nginx.conf              ← master config (usually don't touch this)
├── sites-available/        ← config files for each site (inactive)
│   └── mlops_project       ← your site config goes here
└── sites-enabled/          ← symlinks to active configs
    └── mlops_project       ← symlink to sites-available/mlops_project
```

The convention: write configs in `sites-available/`, enable them by creating
a symlink in `sites-enabled/`. In practice for a single-site server,
you can write directly to `sites-enabled/` and it works.

---

### The `server` block — one virtual host

```nginx
server {
    listen 80;
    server_name mlops123.duckdns.org;

    location / { ... }
    location /api/ { ... }
}
```

`listen 80` — handle all HTTP traffic on port 80.
`server_name` — only respond to requests for this domain.
`location` blocks — route requests to different upstreams based on URL path.

If you have multiple domains on the same server (e.g., `weatherapp.duckdns.org`
and `mlops123.duckdns.org`), each gets its own `server` block. Nginx reads
`server_name` on each request and routes to the right block.

---

### The `location` block — path routing

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:1078/;
}
```

`location /api/` matches any request whose path starts with `/api/`.
`proxy_pass http://127.0.0.1:1078/` forwards the request to that address.

**The trailing slash on `proxy_pass` matters:**

```nginx
# With trailing slash — strips the matched prefix
location /api/ {
    proxy_pass http://127.0.0.1:1078/;
}
# Request: GET /api/predict
# Forwarded: GET /predict       ← /api/ is stripped, replaced by /

# Without trailing slash — keeps the full path
location /api/ {
    proxy_pass http://127.0.0.1:1078;
}
# Request: GET /api/predict
# Forwarded: GET /api/predict   ← full path kept
```

This project uses the trailing slash. FastAPI receives `/predict`, not `/api/predict`.
FastAPI only needs to define its routes as `/predict`, `/health`, etc.
The `/api/` prefix is handled entirely by nginx.

---

### The `location = /api` exact match — why it's needed

```nginx
location = /api {
    return 301 /api/;
}

location /api/ {
    proxy_pass http://127.0.0.1:1078/;
}
```

`location = /api` matches only the exact path `/api` (no trailing slash).
`location /api/` matches paths starting with `/api/` (with trailing slash).

Without the exact match redirect, a request to `http://your-domain.com/api`
(no slash) doesn't match `location /api/` and falls through to `location /`
(the dashboard). The API appears unreachable from the exact URL.

The `301` redirect sends the browser from `/api` to `/api/` — which then
matches the correct location block.

---

### Proxy headers — why every block has them

```nginx
proxy_set_header Host               $host;
proxy_set_header X-Real-IP          $remote_addr;
proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto  $scheme;
```

When nginx forwards a request, the upstream service (FastAPI, Streamlit) receives
a request that appears to come from `127.0.0.1` — the nginx process. It loses
information about the original request:
- What was the original domain?
- What was the client's real IP?
- Was it HTTP or HTTPS?

These headers pass that information along:

| Header | Value | What it tells the upstream |
|---|---|---|
| `Host` | `mlops123.duckdns.org` | Original domain the client requested |
| `X-Real-IP` | `89.123.45.67` | Client's actual IP address |
| `X-Forwarded-For` | `89.123.45.67` | Chain of IPs (client + any proxies) |
| `X-Forwarded-Proto` | `http` | Original protocol (http or https) |

FastAPI reads `X-Forwarded-Proto` to know whether to generate `http://` or `https://`
URLs in redirects. Without it, FastAPI might generate `http://` links when the
client connected via `https://`.

---

### WebSocket proxying — what Streamlit needs

```nginx
location / {
    proxy_pass http://127.0.0.1:1080;
    proxy_http_version 1.1;

    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_read_timeout 86400;
}
```

Streamlit uses WebSockets. A WebSocket starts as an HTTP/1.1 request with an
`Upgrade: websocket` header. The server responds with `101 Switching Protocols`
and the connection upgrades.

Three things are required for this to work through nginx:

**`proxy_http_version 1.1`** — WebSocket requires HTTP/1.1. Nginx defaults to HTTP/1.0
for upstream connections. HTTP/1.0 doesn't support the `Connection` header semantics
needed for protocol upgrades.

**`proxy_set_header Upgrade $http_upgrade`** — forwards the client's `Upgrade` header
to the upstream. If the client says `Upgrade: websocket`, the upstream needs to see that.

**`proxy_set_header Connection "upgrade"`** — tells the upstream that this connection
is requesting a protocol change. Without this, the upstream ignores the `Upgrade` header.

**`proxy_read_timeout 86400`** — WebSocket connections are long-lived (hours or days).
Nginx's default read timeout is 60 seconds — it would kill the WebSocket connection
after one minute of no new data. `86400` = 24 hours. This keeps the Streamlit
UI alive across long browser sessions.

---

### `sub_filter` — rewriting MLflow's HTML

```nginx
location /mlflow/ {
    proxy_pass http://127.0.0.1:1081/;

    sub_filter 'href="/'  'href="/mlflow/';
    sub_filter 'src="/'   'src="/mlflow/';
    sub_filter_once off;
}
```

MLflow's UI generates HTML with asset links like:
```html
<link href="/static/main.css" ...>
<script src="/static/bundle.js" ...>
```

These paths start with `/` — they're absolute from the server root.
When the browser sees `href="/static/main.css"`, it requests `http://your-domain.com/static/main.css`.
Nginx has no `location /static/` block → 404 → broken UI.

`sub_filter` rewrites these paths in the HTML response before sending to the browser:
```html
<!-- Before sub_filter -->
<link href="/static/main.css" ...>

<!-- After sub_filter -->
<link href="/mlflow/static/main.css" ...>
```

Now the browser requests `http://your-domain.com/mlflow/static/main.css` →
nginx matches `location /mlflow/` → forwards to MLflow → works.

`sub_filter_once off` applies the replacement to all occurrences in the response,
not just the first.

> **Note:** `sub_filter` requires the `ngx_http_sub_module`. Check with:
> `nginx -V 2>&1 | grep sub_filter`
> If missing: `sudo apt install nginx-extras`

---

### `127.0.0.1` vs `localhost` — the IPv6 trap

```nginx
# WRONG — resolves to both 127.0.0.1 and ::1
proxy_pass http://localhost:1078/;

# CORRECT — explicit IPv4 only
proxy_pass http://127.0.0.1:1078/;
```

On modern Linux, `localhost` resolves to both `127.0.0.1` (IPv4) and `::1` (IPv6).
Nginx tries both. Docker containers bind ports to `0.0.0.0` — which covers all IPv4
interfaces, including `127.0.0.1`. But they don't bind to the IPv6 loopback `::1`.

When nginx tries `::1:1078` first and gets "Connection refused", it may fail entirely
rather than falling back to `127.0.0.1`. The result is a 502 Bad Gateway.

Using `127.0.0.1` explicitly bypasses DNS resolution entirely. Nginx connects directly
to the IPv4 loopback — which Docker ports are always listening on.

---

## Part 3 — Connecting Concepts to Code

### The complete nginx config — annotated

```nginx
server {
    listen 80;
    server_name your-domain.com;   # replace with your domain

    # ────────────────────────────────────────────────────────────
    # Dashboard (Streamlit)
    # Catch-all / — must be last in matching priority but first in file
    # Needs WebSocket headers for live UI updates
    # ────────────────────────────────────────────────────────────
    location / {
        proxy_pass http://127.0.0.1:1080;
        proxy_http_version 1.1;

        # WebSocket upgrade
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;

        proxy_read_timeout 86400;   # keep WebSocket alive for 24h
    }

    # ────────────────────────────────────────────────────────────
    # Online API (FastAPI)
    # Exact match redirect prevents /api falling through to dashboard
    # Trailing slash on proxy_pass strips /api/ prefix before forwarding
    # ────────────────────────────────────────────────────────────
    location = /api {
        return 301 /api/;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:1078/;
        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
    }

    # ────────────────────────────────────────────────────────────
    # Batch API (FastAPI)
    # Same pattern as online API
    # ────────────────────────────────────────────────────────────
    location = /batch {
        return 301 /batch/;
    }

    location /batch/ {
        proxy_pass http://127.0.0.1:1079/;
        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
    }

    # ────────────────────────────────────────────────────────────
    # MLflow UI
    # proxy_redirect rewrites redirect responses from MLflow
    # sub_filter rewrites asset paths in HTML responses
    # ────────────────────────────────────────────────────────────
    location /mlflow/ {
        proxy_pass http://127.0.0.1:1081/;
        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;

        proxy_redirect http://127.0.0.1:1081/ /mlflow/;

        sub_filter 'href="/'  'href="/mlflow/';
        sub_filter 'src="/'   'src="/mlflow/';
        sub_filter_once off;
    }
}
```

### The full request path for each service

```
Browser: GET http://mlops123.duckdns.org/api/predict
  ↓
DNS: mlops123.duckdns.org → 5.189.155.145
  ↓
nginx on port 80 receives request
  matches location /api/
  strips /api/ prefix
  forwards: GET /predict to http://127.0.0.1:1078/
  ↓
FastAPI api-server container on port 1078
  receives GET /predict
  root_path="/api" → knows its public prefix
  runs prediction
  returns {"predicted_duration_minutes": 18.74}
  ↓
nginx forwards response to browser
  ↓
Browser receives {"predicted_duration_minutes": 18.74}
```

---

## Part 4 — The Bigger Picture

### Where nginx sits in the MLOps stack

```
Internet
    ↓
Nginx (port 80)           ← this layer
    ├── /           → Streamlit  :1080
    ├── /api/       → FastAPI    :1078
    ├── /batch/     → Batch API  :1079
    └── /mlflow/    → MLflow UI  :1081
    ↓
Docker containers on the same host
```

Nginx is the only process that faces the internet. Everything else is internal.
This is the correct security posture — internal services are not directly exposed.
Only nginx talks to the outside world.

---

### What nginx is NOT doing in this setup

- **Not load balancing** — one upstream per location. In production you'd have multiple
  API replicas behind a load balancer.
- **Not terminating SSL** — this setup is HTTP only. In production you'd add a TLS
  certificate (Let's Encrypt / Certbot) and redirect HTTP → HTTPS.
- **Not rate limiting** — in production you'd add `limit_req_zone` to prevent abuse.
- **Not caching** — prediction responses are unique per request, caching wouldn't help.

These are natural next steps once the basic setup works.

---

## Quick Reference

### Install

```bash
sudo apt update
sudo apt install nginx
sudo apt install nginx-extras   # needed for sub_filter module
```

### Create config

```bash
sudo nano /etc/nginx/sites-enabled/mlops_project
# paste config, replace your-domain.com
```

### Test and reload

```bash
sudo nginx -t                    # test for syntax errors
sudo systemctl reload nginx      # apply changes (no downtime)
sudo systemctl restart nginx     # full restart (brief downtime)
```

### Debug

```bash
# Check nginx is running
sudo systemctl status nginx

# Live error log
sudo tail -f /var/log/nginx/error.log

# Live access log
sudo tail -f /var/log/nginx/access.log

# Test a specific endpoint
curl -v http://your-domain.com/api/health

# Check what's listening on a port
ss -tlnp | grep 1078
```

### Common errors

| Error | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` | nginx can't reach the upstream | Check container is running + use `127.0.0.1` not `localhost` |
| `connection refused` on `::1` | IPv6 path failing | Replace `localhost` with `127.0.0.1` in `proxy_pass` |
| Streamlit loads blank | WebSocket not upgrading | Add `Upgrade` + `Connection` headers + `proxy_http_version 1.1` |
| MLflow assets 404 | Asset paths missing prefix | Add `sub_filter` + `proxy_redirect` in `/mlflow/` block |
| FastAPI docs broken | FastAPI missing `root_path` | Add `root_path=os.getenv("ROOT_PATH","")` to `FastAPI(...)` |
| `unknown directive sub_filter` | Module not installed | `sudo apt install nginx-extras` |