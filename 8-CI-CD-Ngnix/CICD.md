# CI/CD with GitHub Actions — Mental Model, Concepts & Reference

---

## Part 1 — What Is CI/CD? (The Mental Model)

### Start with a newspaper printing press

Before modern printing, every newspaper issue required someone to manually set the
type, check it, ink the press, and run the print. If a letter was wrong, someone
had to catch it before 10,000 copies went out.

Modern presses have automated quality checks. A sensor checks registration. A camera
checks ink density. If anything is wrong, the press stops before the run — not after.

**CI/CD is the automated press for software.**

Without CI/CD, deploying a code change looks like:
```
Developer writes code on laptop
         ↓
Manually SSH into server
         ↓
git pull (hope nothing breaks)
         ↓
docker compose up -d --build
         ↓
Check logs manually
         ↓
Remember to do this every time you push
```

With CI/CD:
```
Developer pushes to main branch
         ↓
GitHub detects the push
         ↓
Automatically SSHs into server
         ↓
git pull + docker compose up -d --build
         ↓
Done — no manual steps, no forgetting, no SSH sessions
```

The code goes from your laptop to production in seconds, automatically, every time.

---

### CI vs CD — what the letters mean

Students often see these used interchangeably. They're two distinct ideas:

**CI — Continuous Integration**
Every push is automatically validated before it reaches the main branch.
The "integration" is testing whether your code integrates with the rest of the codebase.
```
Push to branch
    ↓
Run tests automatically
    ↓
Run linters, type checkers
    ↓
If all pass → merge allowed
If any fail → merge blocked
```
This project doesn't have automated tests (that's a natural next step), so we don't
have true CI — we have CD only.

**CD — Continuous Deployment**
Every push to main is automatically deployed to the server.
No manual steps between commit and live.
```
Push to main
    ↓
Automated deployment runs
    ↓
Server is updated
    ↓
New code is live
```
This is what we build. Every `git push origin main` → server updates automatically.

**The full pipeline in production:**
```
Push to feature branch → CI tests run → merge to main → CD deploys
```

---

### Why bother? The two failure modes without CI/CD

**Failure mode 1 — Drift between code and server**

You fix a bug on your laptop. You're in a meeting. You forget to SSH and deploy.
Two days later a user reports the bug. It's already fixed in the code — but never deployed.
The server is running stale code that nobody noticed.

With CD: push = deploy. The server is always running the latest main. No drift possible.

**Failure mode 2 — Deployment is high-effort so it happens rarely**

Manual deployment is annoying. SSH, type commands, check logs, exit. Takes 5 minutes.
So you batch changes and deploy weekly. Bugs sit in production for a week.
When you do deploy, five things changed at once — if something breaks, which change caused it?

With CD: deployment is free. You deploy small changes constantly. If something breaks,
you know exactly which commit caused it.

---

## Part 2 — GitHub Actions Concepts

### The three components: events, jobs, steps

A GitHub Actions workflow file describes three things:

**Event** — what triggers the workflow:
```yaml
on:
  push:
    branches:
      - main        # runs when anything is pushed to main
```

Other common triggers: `pull_request`, `schedule` (cron), `workflow_dispatch` (manual button).

**Job** — a unit of work that runs on a machine:
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest   # GitHub spins up a fresh Ubuntu VM for this job
```

Jobs run in parallel by default. If you need one job to wait for another, use `needs`.

**Step** — one action within a job:
```yaml
steps:
  - uses: actions/checkout@v4      # clone the repo
  - name: Deploy
    run: echo "hello"              # run a shell command
```

Steps run sequentially within a job, top to bottom.

---

### The runner — where your code actually runs

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
```

GitHub spins up a fresh virtual machine for each job. It's a clean Ubuntu install
with common tools pre-installed (Docker, Python, Node, git). Your steps run on this VM.

The VM:
- Is completely isolated — no state from previous runs
- Exists only for the duration of the job
- Is destroyed when the job finishes
- Costs nothing on GitHub's free tier up to 2,000 minutes/month

Because the runner is a fresh VM, it doesn't have your SSH key, your server's IP,
or any secrets. These come from **GitHub Secrets**.

---

### GitHub Secrets — credentials without hardcoding

Never put passwords, SSH keys, or server addresses in your code. Anyone with repo access
can see committed files — and git history is forever.

GitHub Secrets store sensitive values encrypted and inject them into workflows at runtime:

```yaml
steps:
  - name: Deploy
    with:
      host: ${{ secrets.HOST }}        # injected from GitHub Secrets
      key:  ${{ secrets.PRIVATE_KEY }} # never visible in logs or code
```

Secrets are:
- Encrypted at rest by GitHub
- Never printed in workflow logs (shown as `***`)
- Available only to workflows in your repository
- Set once and reused across all workflows

**Setting secrets:** Repository → Settings → Secrets and variables → Actions → New repository secret.

---

### The SSH action — how the runner reaches your server

The runner VM (GitHub's Ubuntu machine) needs to SSH into your VPS to run deployment commands.
This requires two things:

1. **The private SSH key** — authorizes the runner to connect
2. **The server's IP and username** — tells the runner where to connect

```yaml
- uses: webfactory/ssh-agent@v0.9.0
  with:
    ssh-private-key: ${{ secrets.PRIVATE_KEY }}   # loads key into SSH agent

- uses: matheusvanzan/sshpass-action@v2
  with:
    host: ${{ secrets.HOST }}
    user: ${{ secrets.USERNAME }}
    key:  ${{ secrets.PRIVATE_KEY }}
    run: |
      cd ${{ secrets.PROJECT_PATH }}
      git pull origin main
      docker compose up -d --build
```

`webfactory/ssh-agent` loads the private key into the runner's SSH agent — same as
running `ssh-add ~/.ssh/id_rsa` on your laptop before SSHing somewhere.

`matheusvanzan/sshpass-action` SSHs into the server and runs the commands in `run:`.
The `|` means multi-line — each line is a separate shell command.

---

### The deployment commands — what runs on your server

```bash
cd ${{ secrets.PROJECT_PATH }}    # go to project directory
git pull origin main              # pull latest code
docker compose up -d --build      # rebuild changed images, restart containers
```

`git pull` — fetches and merges the latest commits from GitHub.
After this, the server has the exact same code as your laptop just pushed.

`docker compose up -d --build` — the key flag is `--build`.
Without `--build`, Docker Compose would start existing containers without rebuilding images.
New code would never reach the running containers.
With `--build`, Docker rebuilds any image whose source files changed, then restarts
only the affected containers. Unchanged services keep running — no unnecessary downtime.

`-d` — detached mode. The command returns immediately after starting the containers.
Without `-d`, the GitHub Action would wait forever for the containers to stop.

---

## Part 3 — Connecting Concepts to Code

### The full workflow file — annotated

```yaml
name: CI/CD

# Trigger: any push to the main branch
on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest   # fresh Ubuntu VM on GitHub's infrastructure

    steps:
      # Step 1: clone the repo onto the runner VM
      # (not the server — this is the GitHub runner)
      - uses: actions/checkout@v4

      # Step 2: load the SSH private key into the runner's SSH agent
      # enables subsequent SSH connections without password prompts
      - uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.PRIVATE_KEY }}

      # Step 3: SSH into the VPS and run deployment commands
      - name: Deploy to production
        uses: matheusvanzan/sshpass-action@v2
        with:
          host: ${{ secrets.HOST }}          # VPS IP address
          user: ${{ secrets.USERNAME }}      # VPS login username
          key:  ${{ secrets.PRIVATE_KEY }}   # same key as above
          run: |
            cd ${{ secrets.PROJECT_PATH }}   # go to project dir on VPS
            git pull origin main             # pull latest code
            docker compose up -d --build     # rebuild + restart changed services
```

### The full sequence when you push

```
1. Developer: git push origin main
      ↓
2. GitHub detects push to main
      ↓
3. GitHub starts a fresh Ubuntu runner VM
      ↓
4. Runner: actions/checkout@v4
   → clones your repo onto the runner (not the server)
      ↓
5. Runner: webfactory/ssh-agent
   → loads PRIVATE_KEY into ssh-agent
   → runner can now SSH to your server
      ↓
6. Runner: matheusvanzan/sshpass-action
   → SSHs into HOST as USERNAME
   → runs:
       cd /home/silva/Project/8-CI-CD-Ngnix
       git pull origin main
       docker compose up -d --build
      ↓
7. VPS: git pull
   → fetches latest commits from GitHub
   → your code changes are now on the server
      ↓
8. VPS: docker compose up -d --build
   → Docker detects which Dockerfiles/source files changed
   → rebuilds only the affected images (e.g., api-server if api/main.py changed)
   → restarts only the rebuilt containers
   → unchanged containers keep running
      ↓
9. Deployment complete — new code is live
   Runner VM is destroyed
```

Total time from push to live: typically 60-120 seconds.

---

### What the four secrets contain

| Secret | Example value | Where to get it |
|---|---|---|
| `PRIVATE_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----...` | `cat ~/.ssh/id_rsa` on your VPS |
| `HOST` | `5.189.155.145` | Your VPS IP address |
| `USERNAME` | `silva` | Your VPS login username |
| `PROJECT_PATH` | `/home/silva/Project/8-CI-CD-Ngnix` | Full path to project on VPS |

**Getting the private key from your VPS:**
```bash
cd ~/.ssh
ls                   # look for id_rsa, id_ed25519, or similar
cat id_rsa           # copy everything including -----BEGIN and -----END lines
```

The private key authorizes the GitHub runner to connect to your VPS.
This works because your VPS's `~/.ssh/authorized_keys` already contains
the corresponding public key — that's how you SSH into the VPS yourself.

---

### Connecting the VPS to GitHub

The VPS pulls code from GitHub using `git pull origin main`.
For this to work, the VPS must be connected to your GitHub repository.

If you cloned the repo to the VPS initially:
```bash
git clone https://github.com/yourusername/your-repo.git
cd your-repo
git remote -v
# origin  https://github.com/yourusername/your-repo.git (fetch)
# origin  https://github.com/yourusername/your-repo.git (push)
```

The remote is already set. `git pull origin main` will work.

If you uploaded files manually (no git clone):
```bash
cd /path/to/project
git init
git remote add origin https://github.com/yourusername/your-repo.git
git pull origin main
```

---

## Part 4 — The Bigger Picture

### Where CI/CD sits in the MLOps lifecycle

```
Code change on laptop
      ↓
git push → GitHub
      ↓
GitHub Actions (CI/CD)    ← this layer
      ↓
VPS: git pull + rebuild
      ↓
New containers running
      ↓
nginx routes traffic to new containers
      ↓
Users see updated app
```

CI/CD closes the loop between development and production. Without it,
code lives in two places — your laptop and the server — and they drift apart.
With it, main branch = what's running in production. Always.

---

### What this setup doesn't have (and what production adds)

This setup deploys on every push to main. It's simple and effective for a course project.
In production, a more complete CI/CD pipeline adds:

| What | Why |
|---|---|
| Automated tests (pytest) | Catch bugs before they reach the server |
| Linting (ruff, mypy) | Enforce code quality automatically |
| Test environment | Deploy to staging first, verify, then promote to prod |
| Rollback mechanism | Automatic revert if deployment fails |
| Deployment notifications | Slack/email alert on success or failure |
| Branch protection rules | Require passing CI before merging to main |

Each addition makes deployment more reliable. The pattern — trigger on push, run commands
on a server — stays the same. The pipeline just grows more checks around it.

---

### The natural progression from here

```
1. Manual deployment          SSH + run commands manually
2. Automated deployment       GitHub Actions deploys on push        ← you are here
3. CI + CD                    Tests must pass before deployment
4. Staging environment        Test in staging, promote to prod
5. Blue/green deployment      New version alongside old, switch traffic
6. Canary releases            Route 5% of traffic to new version first
7. Kubernetes                 Orchestrate many containers at scale
```

Each step reduces risk and increases confidence in deployments.
Step 2 alone eliminates most deployment failures by removing the human.

---

## Quick Reference

### Workflow file location

```
your-project/
└── .github/
    └── workflows/
        └── deploy.yml    ← must be exactly here
```

### The four secrets to add

Go to: Repository → Settings → Secrets and variables → Actions

```
PRIVATE_KEY    → your VPS private SSH key (cat ~/.ssh/id_rsa)
HOST           → your VPS IP (e.g. 5.189.155.145)
USERNAME       → your VPS login (e.g. silva)
PROJECT_PATH   → full project path (e.g. /home/silva/Project/8-CI-CD-Ngnix)
```

### Test the pipeline

```bash
# make any change
echo "# test" >> README.md
git add .
git commit -m "test ci/cd"
git push origin main
# → watch the Actions tab on GitHub
```

### Debugging a failed workflow

GitHub → your repo → Actions tab → click the failed run → click the failed step → read logs.

Common failures:

| Error | Cause | Fix |
|---|---|---|
| `Permission denied (publickey)` | Wrong private key | Check `cat ~/.ssh/id_rsa` matches what's in GitHub Secrets |
| `No such file or directory` | Wrong `PROJECT_PATH` | Verify `cd /your/path` works when SSHing manually |
| `git pull` fails | VPS not connected to GitHub | Run `git remote -v` on VPS, add remote if missing |
| `docker compose` not found | Not installed on VPS | `sudo apt install docker-compose-plugin` |
| Containers don't update | Missing `--build` flag | Ensure `docker compose up -d --build` in the workflow |