# Securing Your Domain with SSL Using Certbot

To secure your domain and enable HTTPS, you can use **Certbot** to automatically obtain and install an SSL/TLS certificate from Let's Encrypt.

## Install SSL Certificate

Run the following command:

```bash
sudo certbot --nginx -d your-domain.com
```

Once the process completes successfully, your application should be accessible via:

```text
https://your-domain.com
```

The browser's **"Not Secure"** warning should disappear, and a secure lock icon should be displayed.

---

# How It Works

## 1. Certbot Requests a Certificate

Certbot contacts Let's Encrypt and requests an SSL certificate for the specified domain:

```bash
-d your-domain.com
```

The `-d` flag specifies the domain name for which the certificate should be issued.

---

## 2. Domain Ownership Verification

Before issuing a certificate, Let's Encrypt must verify that you control the domain.

Using the `--nginx` option allows Certbot to automatically configure Nginx and create a temporary validation endpoint:

```text
http://your-domain.com/.well-known/acme-challenge/...
```

Let's Encrypt accesses this endpoint to confirm ownership of the domain.

---

## 3. Certificate Generation

After successful validation, Let's Encrypt issues:

* SSL Certificate
* Private Key

These files are typically stored under:

```bash
/etc/letsencrypt/
```

---

## 4. Automatic Nginx Configuration

### Before SSL

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:5000;
    }
}
```

### After SSL

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate ...;
    ssl_certificate_key ...;

    location / {
        proxy_pass http://localhost:5000;
    }
}
```

Nginx now accepts encrypted HTTPS traffic on port `443`.

---

## 5. HTTP to HTTPS Redirection

Certbot typically adds an automatic redirect:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    return 301 https://$host$request_uri;
}
```

This ensures all users visiting:

```text
http://your-domain.com
```

are redirected to:

```text
https://your-domain.com
```

---

# Why HTTPS Matters

## Without SSL

```text
Browser <-- Plain Text --> Server
```

Traffic can potentially be intercepted or modified.

## With SSL

```text
Browser <-- Encrypted --> Server
```

Traffic is encrypted, and the browser verifies the server's identity.

Benefits:

* Encrypted communication
* Secure authentication
* Improved user trust
* No "Not Secure" browser warnings

---

# Prerequisites

Before running Certbot, ensure:

1. A registered domain name exists.
2. DNS records point to your server's public IP.

```text
example.com -> 123.45.67.89
```

3. Nginx is installed and running.
4. Ports `80` and `443` are open.

```bash
sudo ufw allow 80
sudo ufw allow 443
```

5. The application is accessible from the public internet.

---

# Deployment Architecture

```text
User Browser
      |
      | HTTPS (443)
      v
    Nginx
      |
      | HTTP
      v
 FastAPI / Flask / Node.js
      |
      v
   Database
```

The SSL certificate is managed by **Nginx**. The application itself can continue running locally (for example on `localhost:5000` or `localhost:8000`), while Nginx handles HTTPS termination and forwards requests to the application.
