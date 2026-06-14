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
https://your-domain.com/           ← dashboard
https://your-domain.com/api/       ← api
https://your-domain.com/batch/     ← batch
https://your-domain.com/mlflow/    ← mlflow
```

Nginx receives all requests and routes to the right service.
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

Four separate things broke simultaneously:

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

**4. `301` redirect changed POST to GET**

The redirect blocks used `301 Moved Permanently`. When a browser follows a 301,
it is allowed by the HTTP spec to change the method — so POST became GET.
FastAPI received GET on a POST-only endpoint and returned `405 Method Not Allowed`.
This only surfaced after adding HTTPS because Certbot adds its own `301` HTTP→HTTPS
redirect, which also changed POST to GET.

All four bugs had different causes and needed different fixes.

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

> **Watch out for duplicate config files.** If you create `mlops_project` and
> `mlops_projet1` by accident, nginx loads both and the wrong one may take precedence.
> Always verify with `sudo nginx -T | grep "configuration file"`.

---

### The `server` block — one virtual host

```nginx
server {
    listen 443 ssl;
    server_name mlops123.duckdns.org;

    location / { ... }
    location /api/ { ... }
}
```

`listen 443 ssl` — handle HTTPS traffic (added by Certbot).
`server_name` — only respond to requests for this domain.
`location` blocks — route requests to different upstreams based on URL path.

If you have multiple domains on the same server, each gets its own `server` block.
Nginx reads `server_name` on each request and routes to the right block.

> **On a shared VPS**, always check that your `server_name` isn't claimed by
> another config file. Run `sudo nginx -T | grep server_name` to see all active entries.

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

### The `location = /api` exact match and `308` — why both matter

```nginx
location = /api {
    return 308 /api/;
}

location /api/ {
    proxy_pass http://127.0.0.1:1078/;
}
```

`location = /api` matches only the exact path `/api` (no trailing slash).
Without it, a request to `/api` falls through to `location /` (the dashboard).

**Why `308` and not `301`:**

| Code | Name | Method preserved |
|---|---|---|
| `301` | Moved Permanently | ❌ No — POST can become GET |
| `308` | Permanent Redirect | ✅ Yes — POST stays POST |

Using `301` causes `405 Method Not Allowed` on any POST endpoint (like `/api/predict`)
because the browser switches POST to GET when following the redirect.
`308` was created specifically to fix this — it means the same thing as `301` but
guarantees the method is never changed.

---

### Proxy headers — why every block has them

```nginx
proxy_set_header Host               $host;
proxy_set_header X-Real-IP          $remote_addr;
proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto  $scheme;
```

When nginx forwards a request, the upstream service receives a request that appears
to come from `127.0.0.1` — losing information about the original request.
These headers pass that information along:

| Header | Value | What it tells the upstream |
|---|---|---|
| `Host` | `mlops123.duckdns.org` | Original domain the client requested |
| `X-Real-IP` | `89.123.45.67` | Client's actual IP address |
| `X-Forwarded-For` | `89.123.45.67` | Chain of IPs (client + any proxies) |
| `X-Forwarded-Proto` | `https` | Original protocol (http or https) |

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

Streamlit uses WebSockets. Three things are required for this to work through nginx:

**`proxy_http_version 1.1`** — WebSocket requires HTTP/1.1. Nginx defaults to HTTP/1.0
for upstream connections which doesn't support protocol upgrades.

**`proxy_set_header Upgrade $http_upgrade`** — forwards the client's `Upgrade` header
to the upstream. If the client says `Upgrade: websocket`, the upstream needs to see that.

**`proxy_set_header Connection "upgrade"`** — tells the upstream that this connection
is requesting a protocol change. Without this, the upstream ignores the `Upgrade` header.

**`proxy_read_timeout 86400`** — WebSocket connections are long-lived. Nginx's default
read timeout is 60 seconds — it would kill the Streamlit UI after one minute of no activity.
`86400` = 24 hours.

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

MLflow's UI generates HTML with asset links like `href="/static/main.css"`.
These are absolute from the server root — the browser requests `/static/main.css`
which nginx has no location block for → 404 → broken UI.

`sub_filter` rewrites these paths in the HTML response before sending to the browser
so `href="/static/main.css"` becomes `href="/mlflow/static/main.css"` — which nginx
correctly routes to MLflow.

`sub_filter_once off` applies the replacement to all occurrences, not just the first.

> **Note:** `sub_filter` requires the `ngx_http_sub_module`.
> Check: `nginx -V 2>&1 | grep sub_filter`
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
Docker containers bind ports to `0.0.0.0` (IPv4 only) — not to `::1`.
When nginx tries `::1:1078` and gets "Connection refused", it returns 502 Bad Gateway.

Using `127.0.0.1` explicitly bypasses DNS resolution. Nginx connects directly to the
IPv4 loopback which Docker ports are always listening on.

---

### SSL and Certbot — adding HTTPS

After the basic nginx config is working on HTTP, add SSL with one command:

```bash
sudo certbot --nginx -d your-domain.com
```

Certbot automatically:
1. Obtains a free certificate from Let's Encrypt
2. Adds `listen 443 ssl` and certificate paths to your config
3. Adds an HTTP→HTTPS redirect block on port 80

**The 308 trap after Certbot runs:**

Certbot adds its HTTP→HTTPS redirect using `301` by default:
```nginx
server {
    if ($host = your-domain.com) {
        return 301 https://$host$request_uri;   # ← Certbot adds this
    }
    listen 80;
    ...
}
```

This `301` changes POST to GET exactly like the location redirect problem.
After Certbot runs, always change it to `308`:

```nginx
server {
    if ($host = your-domain.com) {
        return 308 https://$host$request_uri;   # ← change to 308
    }
    listen 80;
    ...
}
```

Verify after every Certbot run:
```bash
grep "return 30" /etc/nginx/sites-enabled/mlops_project
# should show 308, not 301
```

---

## Part 3 — Connecting Concepts to Code

### The complete nginx config — annotated

```nginx
server {
    server_name your-domain.com;

    # ────────────────────────────────────────────────────────────
    # Dashboard (Streamlit)
    # Needs WebSocket headers for live UI updates
    # ────────────────────────────────────────────────────────────
    location / {
        proxy_pass http://127.0.0.1:1080;
        proxy_http_version 1.1;

        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;

        proxy_read_timeout 86400;
    }

    # ────────────────────────────────────────────────────────────
    # Online API (FastAPI)
    # 308 preserves POST method through redirect
    # Trailing slash on proxy_pass strips /api/ prefix before forwarding
    # ────────────────────────────────────────────────────────────
    location = /api {
        return 308 /api/;
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
        return 308 /batch/;
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

    # Added by Certbot
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

# HTTP → HTTPS redirect (added by Certbot, 308 manually changed from 301)
server {
    if ($host = your-domain.com) {
        return 308 https://$host$request_uri;
    }
    listen 80;
    server_name your-domain.com;
    return 404;
}
```

### The full request path for each service

```
Browser: POST https://mlops123.duckdns.org/api/predict
  ↓
DNS: mlops123.duckdns.org → 5.189.155.145
  ↓
nginx on port 443 receives request
  matches location /api/
  strips /api/ prefix
  forwards: POST /predict to http://127.0.0.1:1078/
  ↓
FastAPI api-server container on port 1078
  receives POST /predict
  root_path="/api" → knows its public prefix
  runs prediction
  returns {"predicted_duration_minutes": 19.93}
  ↓
nginx forwards response to browser
  ↓
Browser receives {"predicted_duration_minutes": 19.93}
```

---

## Part 4 — The Bigger Picture

### Where nginx sits in the MLOps stack

```
Internet
    ↓
Nginx (port 443 SSL)      ← this layer
    ├── /           → Streamlit  :1080
    ├── /api/       → FastAPI    :1078
    ├── /batch/     → Batch API  :1079
    └── /mlflow/    → MLflow UI  :1081
    ↓
Docker containers on the same host
```

Nginx is the only process that faces the internet. Everything else is internal.
This is the correct security posture — internal services are not directly exposed.

---

### What nginx is NOT doing in this setup

- **Not load balancing** — one upstream per location
- **Not rate limiting** — no `limit_req_zone`
- **Not caching** — prediction responses are unique per request

These are natural next steps for a production hardened deployment.

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
```

### Test and reload

```bash
sudo nginx -t                    # test for syntax errors
sudo systemctl reload nginx      # apply changes (no downtime)
sudo systemctl restart nginx     # full restart (brief downtime)
```

### Add SSL

```bash
sudo certbot --nginx -d your-domain.com
# then manually change 301 → 308 in the redirect block
grep "return 30" /etc/nginx/sites-enabled/mlops_project
```

### Debug

```bash
# Check all active configs and server names
sudo nginx -T | grep -E "server_name|configuration file"

# Check nginx is running
sudo systemctl status nginx

# Live error log
sudo tail -f /var/log/nginx/error.log

# Live access log
sudo tail -f /var/log/nginx/access.log

# Test a specific endpoint
curl -v https://your-domain.com/api/health

# Check what's listening on a port
ss -tlnp | grep 1078
```

### Common errors

| Error | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` | nginx can't reach the upstream | Check container is running + use `127.0.0.1` not `localhost` |
| `connection refused` on `::1` | IPv6 path failing | Replace `localhost` with `127.0.0.1` in `proxy_pass` |
| `405 Method Not Allowed` on POST | `301` changes POST to GET | Use `308` in all redirect blocks including Certbot's HTTP→HTTPS block |
| Streamlit loads blank | WebSocket not upgrading | Add `Upgrade` + `Connection` headers + `proxy_http_version 1.1` |
| MLflow assets 404 | Asset paths missing prefix | Add `sub_filter` + `proxy_redirect` in `/mlflow/` block |
| FastAPI docs broken | FastAPI missing `root_path` | Add `root_path=os.getenv("ROOT_PATH","")` to `FastAPI(...)` |
| `unknown directive sub_filter` | Module not installed | `sudo apt install nginx-extras` |
| Wrong site showing on HTTPS | Missing 443 block for your domain | Run `sudo certbot --nginx -d your-domain.com` |
| Duplicate config conflict | Two files with same `server_name` | Run `sudo nginx -T | grep "configuration file"` and remove the duplicate |