# SSL with Certbot — Mental Model, Concepts & Reference

---

## Part 1 — What Is SSL and Why Does It Matter?

### The problem with plain HTTP

Without SSL, traffic between the browser and your server travels as plain text:

```
Browser ──── Plain Text ────► Server
         "POST /api/predict
          {"PULocationID": 161 ...}"
```

Anyone on the network path — your ISP, a public WiFi router, a middleman —
can read or modify that traffic. For an ML prediction API this means:
- Input data is visible (potentially sensitive trip information)
- Responses can be tampered with
- The browser shows "Not Secure" — users lose trust

With SSL, traffic is encrypted end to end:

```
Browser ──── Encrypted ────► Server
         (unreadable to anyone in between)
```

The browser shows a padlock. Users trust the connection. Sensitive data stays private.

---

### What a certificate actually is

An SSL certificate is a file that proves two things:
1. **Identity** — this server really is `mlops123.duckdns.org`
2. **Public key** — here is the key to encrypt data for this server

The certificate is issued by a **Certificate Authority (CA)** — a trusted third party
that browsers already trust. Let's Encrypt is a free, automated CA.

Without a certificate from a trusted CA, the browser shows a security warning.
With one, the padlock appears and HTTPS works.

---

### What Certbot does

Certbot is a tool that automates the entire certificate process:

```
sudo certbot --nginx -d your-domain.com
      ↓
1. Contacts Let's Encrypt
2. Proves you control the domain
3. Gets the certificate
4. Installs it into nginx automatically
5. Sets up auto-renewal
```

One command. No manual certificate handling.

---

## Part 2 — How Certbot Works

### Step 1 — Domain ownership verification

Before issuing a certificate, Let's Encrypt must verify you control the domain.
Certbot handles this automatically using the HTTP-01 challenge:

```
1. Certbot creates a temporary file on your server at:
   http://your-domain.com/.well-known/acme-challenge/TOKEN

2. Let's Encrypt fetches that URL from the internet

3. If it gets the right file → you control the domain → certificate issued
```

This is why your server must be reachable from the internet on port 80 before
running Certbot. The verification happens over plain HTTP before HTTPS exists.

---

### Step 2 — Certificate files

After verification, Let's Encrypt issues two files stored under `/etc/letsencrypt/`:

```
/etc/letsencrypt/live/your-domain.com/
├── fullchain.pem      ← the certificate (public)
└── privkey.pem        ← the private key (keep secret)
```

`fullchain.pem` — your certificate plus any intermediate certificates.
Browsers need the full chain to verify trust back to a root CA.

`privkey.pem` — the private key. Never share this. If compromised, anyone can
impersonate your server. Certbot sets file permissions to protect it automatically.

---

### Step 3 — What Certbot adds to nginx

Certbot modifies your nginx config automatically. Before and after:

**Before (HTTP only):**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    location / { ... }
}
```

**After (HTTPS + redirect):**
```nginx
server {
    server_name your-domain.com;
    location / { ... }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = your-domain.com) {
        return 301 https://$host$request_uri;   # ← Certbot adds 301 here
    }
    listen 80;
    server_name your-domain.com;
    return 404;
}
```

Nginx now accepts encrypted HTTPS traffic on port 443 and redirects all HTTP
traffic from port 80 to HTTPS.

---

### The 308 fix — critical for POST endpoints

Certbot adds `return 301` in the HTTP→HTTPS redirect block. This causes a real
problem for this project:

```
Browser sends:   POST http://your-domain.com/api/predict
nginx returns:   301 → https://your-domain.com/api/predict
Browser follows: GET https://your-domain.com/api/predict  ← method changed!
FastAPI returns: 405 Method Not Allowed
```

`301 Moved Permanently` allows clients to change the HTTP method when following
the redirect. `308 Permanent Redirect` (RFC 7538) prohibits this.

**After every Certbot run, change `301` to `308` in the redirect block:**

```nginx
server {
    if ($host = your-domain.com) {
        return 308 https://$host$request_uri;   # ← change 301 to 308
    }
    listen 80;
    server_name your-domain.com;
    return 404;
}
```

Verify:
```bash
grep "return 30" /etc/nginx/sites-enabled/mlops_project
# must show 308, not 301
```

---

### Step 4 — Auto-renewal

Let's Encrypt certificates expire after 90 days. Certbot installs a systemd timer
that automatically renews certificates before they expire:

```bash
# Check renewal timer
sudo systemctl status certbot.timer

# Test renewal (dry run — doesn't actually renew)
sudo certbot renew --dry-run
```

You never need to manually renew. Certbot handles it.

---

## Part 3 — Running Certbot in This Project

### Prerequisites

Before running Certbot:

```bash
# 1. Verify nginx is running
sudo systemctl status nginx

# 2. Verify your domain resolves to this server
curl http://your-domain.com/api/health
# should return {"status": "ok", ...}

# 3. Verify ports 80 and 443 are open
sudo ufw allow 80
sudo ufw allow 443
```

### Run Certbot

```bash
sudo certbot --nginx -d your-domain.com
```

If a certificate already exists for the domain:
```
1: Attempt to reinstall this existing certificate   ← choose this
2: Renew & replace the certificate
```

Choose `1` — it reinstalls the existing certificate into nginx without
requesting a new one (avoids Let's Encrypt rate limits).

### Fix the 308 redirect

```bash
sudo nano /etc/nginx/sites-enabled/mlops_project
# find: return 301 https://$host$request_uri;
# change to: return 308 https://$host$request_uri;

sudo nginx -t && sudo systemctl reload nginx
```

### Verify

```bash
# Test HTTPS prediction endpoint
curl -X POST https://your-domain.com/api/predict \
  -H "Content-Type: application/json" \
  -d '{"tpep_pickup_datetime": "2019-01-15T14:30:00",
       "PULocationID": 161, "DOLocationID": 237,
       "passenger_count": 1, "VendorID": 1,
       "RatecodeID": 1, "trip_distance": 2.5, "payment_type": 1}'
# should return {"predicted_duration_minutes": 19.93, ...}
```

Open `https://your-domain.com` in the browser — padlock should appear.

---

## Part 4 — The Bigger Picture

### Where SSL fits in the deployment stack

```
Browser
    ↓ HTTPS (encrypted)
Nginx — SSL termination    ← Certbot manages the certificate here
    ↓ HTTP (plain, internal)
Docker containers
    (never exposed to internet directly)
```

SSL is terminated at nginx. The internal traffic between nginx and the Docker
containers stays plain HTTP — that's fine because it never leaves the server.
Only the external-facing connection needs encryption.

---

### What changes after adding SSL

| Before SSL | After SSL |
|---|---|
| `http://your-domain.com` | `https://your-domain.com` |
| Port 80 | Port 443 |
| "Not Secure" in browser | Padlock in browser |
| Plain text traffic | Encrypted traffic |
| HTTP→HTTPS redirect needed | Certbot adds it automatically |

The application code doesn't change. The Docker containers don't change.
Only nginx gains the SSL configuration. Everything else stays the same.

---

## Quick Reference

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Fix 308 after Certbot runs
grep "return 30" /etc/nginx/sites-enabled/mlops_project   # verify
# edit if shows 301:
sudo nano /etc/nginx/sites-enabled/mlops_project
sudo nginx -t && sudo systemctl reload nginx

# Check certificate status
sudo certbot certificates

# Test auto-renewal
sudo certbot renew --dry-run

# Check renewal timer
sudo systemctl status certbot.timer
```

### Common errors

| Error | Cause | Fix |
|---|---|---|
| `405 Method Not Allowed` after adding HTTPS | Certbot added `301` redirect | Change `301` → `308` in HTTP→HTTPS redirect block |
| Certificate not issued | Port 80 not reachable | Check `ufw allow 80`, verify domain DNS points to server |
| `Connection refused` on port 443 | nginx not listening on 443 | Re-run `sudo certbot --nginx -d your-domain.com` |
| Wrong site showing on HTTPS | No 443 block for your domain | Certbot adds it — run certbot if missing |
| Rate limit error | Too many certificate requests | Use option `1` (reinstall existing) not option `2` (new certificate) |