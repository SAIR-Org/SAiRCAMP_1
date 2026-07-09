# Deploying the MLOps App to a VPS with Nginx and CI/CD

This guide covers everything needed to take a working local Docker Compose app and make it live on a public domain with automatic deployments.

---

## Prerequisites

- A VPS with Docker and Docker Compose installed
- A domain name pointing to your VPS IP — use [DuckDNS](https://www.duckdns.org/domains) for a free subdomain if needed
- Your project cloned on the VPS

---

## Part 1 — Code Changes

Before touching nginx or the server, two changes are needed in the application code itself.

### Why

FastAPI doesn't know it's being served behind a reverse proxy at a sub-path like `/api/`. Without telling it, the auto-generated docs, redirects, and internal URLs all break. We pass this information via an environment variable so the same code works both locally and in production.

### `api/main.py`

Add `root_path=os.getenv("ROOT_PATH", "")` to the `FastAPI(...)` constructor:

```python
app = FastAPI(
    title="NYC Taxi Trip Duration API",
    description="Predict trip duration from pickup/dropoff zone IDs (2019 TLC model)",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),  # ← tells FastAPI its public prefix
)
```

### `batch/main.py`

Same change — add `root_path=os.getenv("ROOT_PATH", "")`:

```python
app = FastAPI(
    title="NYC Taxi Batch Scoring API",
    description="Trigger batch scoring jobs and retrieve drift metrics",
    version="1.0.0",
    lifespan=lifespan,
    root_path=os.getenv("ROOT_PATH", ""),  # ← tells FastAPI its public prefix
)
```

---

## Part 2 — Docker Compose

Compared to the local version, three things change in `docker-compose.yml`:

- `api` and `batch` get a `ROOT_PATH` env var so FastAPI knows its public prefix
- `dashboard` API URLs change from internal Docker hostnames (`http://api:1078`) to the public domain — because Streamlit runs in the browser, which can't resolve Docker-internal hostnames
- Five Streamlit server vars are added to disable CORS/XSRF blocking that would otherwise reject proxied requests

Check the `docker-compose.yml` file in this repo for the exact changes.

---

## Part 3 — Nginx

### Install Nginx (if not already installed on the VPS)

```bash
sudo apt update
sudo apt install nginx
sudo apt install nginx-extras   # required for sub_filter module
```

### Create the config

```bash
sudo nano /etc/nginx/sites-enabled/mlops_project
```

Paste the following, replacing `your-domain.com` with your actual domain:

```nginx
server {
    server_name your-domain.com;

    # ─────────────────────────────────────────────────────────────
    # Dashboard (Streamlit)
    # ─────────────────────────────────────────────────────────────
    location / {
        proxy_pass http://127.0.0.1:1080;
        proxy_http_version 1.1;

        # Required for Streamlit WebSocket
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
        proxy_read_timeout 86400;
    }

    # ─────────────────────────────────────────────────────────────
    # Online API (FastAPI)
    # ─────────────────────────────────────────────────────────────
    location = /api {
        return 308 /api/;    # 308 preserves POST method (301 would change POST to GET)
    }

    location /api/ {
        proxy_pass http://127.0.0.1:1078/;
        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
    }

    # ─────────────────────────────────────────────────────────────
    # Batch API (FastAPI)
    # ─────────────────────────────────────────────────────────────
    location = /batch {
        return 308 /batch/;  # 308 preserves POST method
    }

    location /batch/ {
        proxy_pass http://127.0.0.1:1079/;
        proxy_http_version 1.1;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
    }

    # ─────────────────────────────────────────────────────────────
    # MLflow UI
    # ─────────────────────────────────────────────────────────────
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

server {
    if ($host = your-domain.com) {
        return 308 https://$host$request_uri;  # 308 preserves POST method
    }
    listen 80;
    server_name your-domain.com;
    return 404;
}
```

> **Note:** `127.0.0.1` must be used instead of `localhost`. nginx resolves `localhost` to both IPv4 and IPv6 (`::1`) and fails when the IPv6 path is unreachable. Docker containers bind to `127.0.0.1` on the host, so this is the correct address.

> **Note:** All redirects use `308` not `301`. A `301` redirect allows clients to change POST to GET when following it — which causes `405 Method Not Allowed` on prediction endpoints. `308` preserves the HTTP method through the redirect.

### Apply and test

```bash
sudo nginx -t
sudo systemctl reload nginx
```

You should see:

```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Start the app

> **Note:** If the MLflow artifacts are not there yet, you need to train the model first (see `7-Deployment_test/README.md`) to generate the artifacts and MLflow DB before starting the app.

```bash
docker compose up -d
```

### Verify everything is reachable

```bash
curl http://your-domain.com/api/health
curl http://your-domain.com/batch/health
```

Open the browser at `http://your-domain.com` — the Streamlit dashboard should load.

### Add SSL (HTTPS)

```bash
sudo certbot --nginx -d your-domain.com
```

Certbot will automatically update your nginx config to add the 443 block and HTTP→HTTPS redirect. After it runs, open `https://your-domain.com` — the padlock should appear.

> **Important:** After Certbot runs, check that the HTTP→HTTPS redirect block uses `308` not `301`. Certbot adds `301` by default which breaks POST requests. See `ngnix.md` for details.

```bash
# verify after certbot
grep "return 30" /etc/nginx/sites-enabled/mlops_project
# should show 308, not 301
```

### URL map

| URL | Service |
|---|---|
| `https://your-domain.com/` | Streamlit dashboard |
| `https://your-domain.com/api/health` | Online API health |
| `https://your-domain.com/api/predict` | Prediction endpoint |
| `https://your-domain.com/api/docs` | FastAPI Swagger UI |
| `https://your-domain.com/batch/health` | Batch API health |
| `https://your-domain.com/batch/docs` | Batch API Swagger UI |
| `https://your-domain.com/mlflow/` | MLflow tracking UI |

---

## The app is now LIVE

---

## Part 4 — CI/CD with GitHub Actions

Every push to `main` automatically pulls and redeploys on the VPS.

### 1. Create the workflow file

In the root of your project create `.github/workflows/deploy.yml`:

```yaml
name: CI/CD

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PRIVATE_KEY }}

      - name: Deploy to production
        uses: matheusvanzan/sshpass-action@v2
        with:
          host: ${{ secrets.HOST }}
          user: ${{ secrets.USERNAME }}
          key: ${{ secrets.PRIVATE_KEY }}
          run: |
            cd ${{ secrets.PROJECT_PATH }}
            git pull origin main
            docker compose up -d --build
```

### 2. Add GitHub secrets

In your GitHub repository go to `Settings` → `Secrets and variables` → `Actions` and add:

| Secret | Value |
|---|---|
| `PRIVATE_KEY` | Your VPS private SSH key (see below) |
| `HOST` | Your VPS IP address or domain |
| `USERNAME` | Your VPS login username |
| `PROJECT_PATH` | Full path to the project on the VPS e.g. `/home/user/Project/8-CI-CD-Ngnix` |

To get your private key from the VPS:

```bash
cd ~/.ssh
cat id_rsa       # or id_ed25519 depending on your key type
```

Copy the full output including the `-----BEGIN ... KEY-----` lines and paste it as the `PRIVATE_KEY` secret.

### 3. Connect the VPS to GitHub

On the VPS, navigate to your project and make sure it is connected to your GitHub repository:

```bash
cd /path/to/your/project
git remote -v
```

If not connected yet, clone it first:

```bash
git clone <repository-url>
```

### 4. Test the pipeline

Make any change, commit, and push:

```bash
git add .
git commit -m "Test CI/CD pipeline"
git push origin main
```

This triggers the workflow. Go to the `Actions` tab in your GitHub repository to watch it run. On success, your changes are live within seconds.