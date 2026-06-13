# Deploying on a VPS

> **Prerequisite:** You must have access to a VPS (Virtual Private Server) to deploy this application.
>
> - SSH key setup reference: [Medium article on SSH key-based authentication](https://medium.com/@infosecnubes/ssh-key-based-authentication-5816d6238c2)
> - Contabo VPS initial configuration: [vps-initial-configurations](https://github.com/context-community/vps-initial-configurations)

---

## ⚠️ Scope of this deployment

This guide gets the system **running end-to-end on a VPS** — it is **not a full production deployment**. Notably missing:

- **CI/CD pipeline** — no automated build/test/deploy on push; images are built manually via `docker compose up --build`.
- **Monitoring & observability** — no metrics/log aggregation, alerting, or tracing stack (e.g. Prometheus/Grafana, Evidently, ELK) is wired in yet.

**The goal here is validation, not finalization**: confirm the system runs correctly on a real server, with a real remote MLflow registry, so that a CI/CD pipeline and monitoring stack can be layered on top of a working foundation in a later module.

---

## Local dev vs. semi-prod (VPS) docker-compose

The compose file in this module differs from the previous module's (local dev) in a few key ways, reflecting the shift from a **local, file-based MLflow** to a **remote, server-based MLflow registry**.

| | Local dev (previous module) | Semi-prod / VPS (this module) |
|---|---|---|
| **MLflow** | Not a separate service — `api`/`batch` read a local sqlite DB + `/mlruns` directory directly via shared volumes | Runs as its own `mlflow` service/container, exposing a tracking server over HTTP (port `1081`) |
| **MLFLOW_TRACKING_URI** | Implicit — points at a local sqlite file via `MLFLOW_ARTIFACTS_ROOT` | Explicit — `http://mlflow:1081`, an HTTP tracking server reachable from training machines too |
| **MLFLOW_ARTIFACTS_ROOT** | Set on `api`/`batch` (`/app/pipeline`) — artifacts read directly from a shared filesystem path | **Removed** — artifacts are fetched via the MLflow server's `mlflow-artifacts://` proxy, not direct file access |
| **Artifact storage** | Plain local path (`/mlruns`), read by all containers via volume mounts | `--default-artifact-root mlflow-artifacts:/` + `--artifacts-destination /mlruns`, served through the tracking server's API |
| **Security middleware** | N/A (no exposed server) | `--allowed-hosts "*"` and `--uvicorn-opts "--forwarded-allow-ips=*"` required to avoid DNS-rebinding rejections when accessed via `mlflow:1081` or through an SSH tunnel |
| **Training location** | Local machine, writing directly to the shared local MLflow files | Local machine **or** any remote host — as long as `MLFLOW_TRACKING_URI` points at the VPS's `mlflow` service (directly or via SSH tunnel) |
| **Ports** | `<api_port>`, `<batch_port>`, `<dashboard_port>` only — no `<mlflow_port>` (not a separate service) | `<api_port>`, `<batch_port>`, `<dashboard_port>`, and `<mlflow_port>` — all remapped from local-dev defaults to avoid conflicts with other services on the shared VPS |

**Why this matters:** decoupling the registry from the filesystem is what makes it possible to train on your laptop and serve from the VPS — the previous module's setup assumed training and serving shared the same disk, which doesn't hold once they're on different machines.

---

## 1. Set up SSH access

### 1.1 Generate an SSH key pair on your local machine

```bash
ssh-keygen -t ed25519 -C "your_email_or_label"
```

`ed25519` is faster and more secure than the traditional RSA algorithm. If your tooling requires RSA instead, use:

```bash
ssh-keygen -t rsa -b 4096 -C "your_email_or_label"
```

Expected output:

```text
Generating public/private ed25519 key pair.
Enter file in which to save the key (~/.ssh/id_ed25519):
Enter passphrase (empty for no passphrase):
Enter same passphrase again:

Your identification has been saved in ~/.ssh/id_ed25519
Your public key has been saved in ~/.ssh/id_ed25519.pub

The key fingerprint is:
SHA256:<your-key-fingerprint>
```

### 1.2 Copy your public key

```bash
cat ~/.ssh/id_ed25519.pub
```

### 1.3 Add the key to the server

```bash
ssh username@server_ip_address
nano ~/.ssh/authorized_keys
```

Paste the public key contents into this file, save, and exit.

### 1.4 Generate an SSH key pair *on the server* (for GitHub access)

```bash
ssh-keygen -t ed25519 -C "your_email_or_label"
```

### 1.5 Configure SSH for GitHub (server-side)

```bash
nano ~/.ssh/config
```

```text
Host <appname>
  HostName github.com
  User git
  IdentityFile ~/.ssh/<app_ssh_key_file_name>
```

### 1.6 Add the server's public key as a GitHub Deploy Key

GitHub repo → **Settings → Deploy keys** → paste the server's public key.

### 1.7 Clone the repository

```bash
git clone git@github.com:username/repository.git
```

---

## 2. Configure ports and firewall

If the ports in `docker-compose.yml` conflict with services already running on the server, update them in the compose file, then open the new ports in the firewall:

```bash
sudo ufw allow <port_number>,<port_number>,<port_number>/tcp
```

Verify the firewall is active and the ports are allowed:

```bash
sudo ufw status
```

---

## 3. Start MLflow on the server

The `api` and `batch` services depend on MLflow being available to load the registered model, so start it first:

```bash
docker compose up -d mlflow
```

---

## 4. Connect your local machine to the server's MLflow

### 4.1 Set the tracking URI on the server side

```bash
export MLFLOW_TRACKING_URI=http://localhost:<mlflow_port>
```

### 4.2 Open an SSH tunnel from your local machine

In a terminal on your **local machine**:

```bash
ssh -N -L <mlflow_port>:localhost:<mlflow_port> user@<server_ip_address>
```

- `-N`: don't open a shell — tunnel only (this terminal will appear idle, that's expected)
- Leave this terminal running

### 4.3 Verify the tunnel

In a **different local terminal**:

```bash
curl http://localhost:<mlflow_port>
```

A successful response confirms the tunnel is working and MLflow is reachable.

---

## 5. Train locally against the remote MLflow

In the same terminal where you verified the tunnel:

```bash
export MLFLOW_TRACKING_URI=http://localhost:<mlflow_port>
```

Now run your training/tuning pipeline locally — all runs, artifacts, and registered models are logged to the **server's** MLflow instance. You can view the MLflow UI at:

```
http://localhost:<mlflow_port>
```

---

## 6. Start the full system on the server

If MLflow is already running and a champion model is registered:

```bash
docker compose up --build api batch
```

Or to (re)build and start everything:

```bash
docker compose up --build
```

> **Note:** Compare `docker-compose.yml` in `7-Deployment` with the one in `6-Full-System` — they differ in how they're configured for local vs. VPS deployment.

---

## 7. Access the dashboard

Visit:

```
http://<server_ip_address>:<dashboard_port>
```

---

## 8. End-to-end testing via curl

```bash
# 1. MLflow health
curl -s http://localhost:<mlflow_port>/health

# 2. API health
curl -s http://localhost:<api_port>/health

# 3. Batch health
curl -s http://localhost:<batch_port>/health

# 4. Dashboard reachable
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:<dashboard_port>

# 5. Online prediction
curl -s -X POST http://localhost:<api_port>/predict \
  -H "Content-Type: application/json" \
  -d '{
    "tpep_pickup_datetime": "2019-01-15T14:30:00",
    "PULocationID": 161,
    "DOLocationID": 237,
    "trip_distance": 2.5,
    "passenger_count": 1,
    "VendorID": 1,
    "RatecodeID": 1,
    "payment_type": 1
  }'

# 6. Trigger batch scoring for a period
curl -s -X POST "http://localhost:<batch_port>/score?year=2019&month=4"

# 7. Check batch results after ~1 minute
curl -s http://localhost:<batch_port>/health
```