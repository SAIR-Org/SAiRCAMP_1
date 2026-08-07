# Debugging Postmortem: FastAPI + MLflow + uv — Folder Rename Cascade

**Context:** A FastAPI app (`main.py`) failed to start with `uvicorn`. Root cause tracing led through three seemingly unrelated bugs, all stemming from a single event: **the project folder was renamed** from `mlops-zoomcamp` to `SAiRCAMP`.

This doc explains each bug, how it was diagnosed, and how it was fixed — as a reference for the general pattern: *absolute paths baked into generated files don't survive a folder rename.*

---

## TL;DR — The Root Cause

Renaming a project's parent folder breaks anything that stored an **absolute path** to something inside it at creation time:

1. Virtual environment scripts (shebang lines)
2. Nothing to do with the rename directly, but surfaced alongside it — a **dependency version mismatch** between environments
3. Database records (MLflow's tracking DB storing absolute artifact paths)

Same underlying theme, three different subsystems, three different-looking error messages.

---

## Bug #1: `uv run uvicorn` → `Failed to spawn: uvicorn` / "command not found"

### Symptom
```
error: Failed to spawn: `uvicorn`
  Caused by: No such file or directory (os error 2)
```
Even though:
- `uvicorn` was confirmed installed (`ls .venv/bin | grep uvicorn` showed it)
- `uv run python -c "import sys; print(sys.executable)"` pointed to the correct venv Python
- `uv run python -m uvicorn main:app --reload` worked perfectly fine

### Root cause
`uv` (like `pip`/`venv` generally) creates executable scripts in `.venv/bin/` for installed console tools. Each script starts with a **shebang line**:
```
#!/home/silva/.../mlops-zoomcamp/.venv/bin/python
```
This is an *absolute path*, written at the time the venv was created/synced. When the parent folder was renamed to `SAiRCAMP`, that exact path stopped existing. Running the script directly (or via `uv run <toolname>`, which shells out to it) failed because the **interpreter referenced in the shebang no longer existed** — not because `uvicorn` itself was missing.

Running via `python -m uvicorn` worked because `-m` finds the package through the *already-running* Python's `sys.path`, bypassing the shebang entirely.

### How it was diagnosed
```bash
cat .venv/bin/uvicorn
```
This showed the broken shebang line pointing at the old (renamed) path — smoking gun.

### The fix
Rebuild the venv from scratch so every script gets regenerated with the *current* correct path:
```bash
cd /path/to/project
rm -rf .venv
uv sync
```
After this, `uv run uvicorn main:app --reload` worked directly with no workaround needed.

### Lesson
**Virtual environments are not portable.** They bake in absolute paths at creation time (shebangs, sometimes `pyvenv.cfg`, activation scripts, etc.). If you move or rename a project directory, always rebuild the venv — don't assume it'll "just work."

---

## Bug #2: MLflow — "Detected out-of-date database schema"

### Symptom
```
mlflow.exceptions.MlflowException: Detected out-of-date database schema
(found version da6fb0208061, but expected d3e4f5a6b7c8).
```
This happened during FastAPI's startup lifespan, when `MlflowClient()` tried to connect to the SQLite tracking database.

### Root cause
This one was **not** about the folder rename directly — it was a **dependency version mismatch between environments**:

- The project's root `pyproject.toml` declared `mlflow>=3.0.0`, which `uv` resolved down to a *specific* installed version: **3.9.0**.
- However, a *separate* `requirements.txt` used for the API's Docker image pinned **`mlflow==3.13.0`**.
- The SQLite tracking database (`mlflow_trip_duration.db`) had been created/migrated under mlflow 3.13.0 at some point, so its schema included a migration revision (`da6fb0208061`) that only exists in 3.13.0's Alembic migration history.
- When the *older* 3.9.0 tried to read the DB, it recognized the schema as "ahead" of what it understood → refused to proceed for safety.

Attempting a direct fix (`mlflow db upgrade`) made this worse initially, producing:
```
alembic.util.exc.CommandError: Can't locate revision identified by 'da6fb0208061'
```
This confirmed it wasn't a simple "run pending migrations" situation — the installed mlflow genuinely didn't know that revision existed at all, because it was older, not just behind.

### How it was diagnosed
```bash
uv run mlflow --version              # confirmed 3.9.0 installed
cat api/requirements.txt             # confirmed mlflow==3.13.0 pinned there
```
Comparing the two revealed the real mismatch: two different parts of the project (local dev env vs. Docker/API deployment env) pinned mlflow independently, and they'd drifted apart.

### The fix
Align the local dev environment with the version that actually created the DB schema:
```bash
uv add "mlflow>=3.13.0"
```
This updated `pyproject.toml` and resynced `.venv` with a matching (or newer) mlflow version. No destructive database changes were needed — once the *reading* environment matched the *writing* environment, the schema was recognized correctly.

### Lesson
When multiple parts of a project pin dependencies independently (e.g., a root `pyproject.toml` for dev, a separate `requirements.txt` for a Docker image), they can silently drift. **Any stateful file with a schema (like a tracking DB) is tied to whichever version wrote it.** A loose constraint like `mlflow>=3.0.0` doesn't guarantee compatibility with data written by a *specific* newer version — pin more precisely, or keep environments in sync deliberately.

---

## Bug #3: `mlflow.exceptions.MlflowException: No such artifact: ''`

### Symptom
After Bug #2 was fixed, mlflow could talk to the DB and resolve the model alias (`@champion`) fine — but loading the actual model file failed:
```python
_state.model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{MODEL_ALIAS}")
```
```
mlflow.exceptions.MlflowException: No such artifact: ''
```

### Root cause
Same root cause as Bug #1 (the folder rename), but manifesting inside the **MLflow tracking database's own records** this time.

MLflow's local filesystem backend (`sqlite:///` + a local `mlruns/` folder) stores **absolute paths** in its tables:
- `model_versions.storage_location`
- `runs.artifact_uri`

These were written when the project folder was still called `mlops-zoomcamp`:
```
/home/silva/.../mlops-zoomcamp/4-Deploy-Online/pipeline/mlruns/1/models/m-.../artifacts
```
After the rename, this path pointed nowhere. MLflow tried to resolve the artifact location, got nothing, and gave the (fairly unhelpful) error `No such artifact: ''`.

### How it was diagnosed
Queried the SQLite tables directly:
```bash
sqlite3 mlflow_trip_duration.db
```
```sql
SELECT name, version, storage_location, run_id
FROM model_versions
WHERE name = 'trip_duration_model';

SELECT * FROM registered_model_aliases WHERE name = 'trip_duration_model';
```
This revealed the stale `mlops-zoomcamp` path in `storage_location`. Confirmed the actual model files did still exist, just under the renamed folder:
```bash
ls /path/SAiRCAMP/4-Deploy-Online/pipeline/mlruns/1/models/m-.../artifacts
# → conda.yaml  MLmodel  model.pkl  python_env.yaml  ...
```
So this was purely a stale-reference problem, not missing data.

### The fix
Directly patch the stale paths in the SQLite database:
```bash
cp mlflow_trip_duration.db mlflow_trip_duration.db.backup2   # always back up first

sqlite3 mlflow_trip_duration.db <<'EOF'
UPDATE model_versions
SET storage_location = REPLACE(storage_location, '/MLOps/mlops-zoomcamp/', '/MLOps/SAiRCAMP/');

UPDATE runs
SET artifact_uri = REPLACE(artifact_uri, '/MLOps/mlops-zoomcamp/', '/MLOps/SAiRCAMP/');
EOF
```
Verified with:
```bash
sqlite3 mlflow_trip_duration.db \
  "SELECT version, storage_location FROM model_versions WHERE name='trip_duration_model' AND version=12;"
```
Restarted the API — model and preprocessor both loaded successfully.

### Lesson
MLflow's local filesystem tracking backend stores **absolute paths by design** — simple for solo/local use, but it means renaming or moving your project directory silently breaks the model registry. Options for the future:
- Avoid renaming project folders once MLflow has logged runs against them.
- Or use a tracking setup with relocatable/remappable paths (this project's own `MLFLOW_ARTIFACTS_ROOT` + `_remap()` logic in `model_loader.py` exists for exactly this reason — to handle the Docker case where host paths don't match container paths).
- If a rename does happen, patch the DB paths directly (as above) rather than re-registering everything from scratch — it's non-destructive and preserves run history.

---

## General Debugging Pattern Used Throughout

1. **Read the actual error traceback fully** — each one pointed to a specific file and line where resolution failed (a shebang, a migration lookup, an artifact path).
2. **Don't trust "it should work" — inspect the actual file/data.** `cat .venv/bin/uvicorn` and querying the SQLite tables directly were the two moves that cracked this open. Guessing from higher-level symptoms wouldn't have found the stale paths.
3. **Compare versions across every place a dependency is pinned** (root `pyproject.toml` vs. `api/requirements.txt` vs. `pipeline/requirements.txt`) — drift between them is a common source of "works on one machine, not another" bugs.
4. **Always back up before mutating state** (`cp file file.backup`) — especially before running schema migrations or hand-editing a database.
5. **Trace symptoms back to a single root cause when possible.** Three different error messages, two different subsystems (venv + MLflow DB), one shared cause: the folder rename.