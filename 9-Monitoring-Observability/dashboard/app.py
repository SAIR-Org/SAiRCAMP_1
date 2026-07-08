
"""
NYC Taxi — Full System Dashboard (Simplified)

Five tabs:
  Tab 1 — Predict        Try the model live (online API)
  Tab 2 — Batch Results  Scored periods + trigger new scoring
  Tab 3 — Drift Monitor  Performance drift + Feature drift (merged)
  Tab 4 — Analytics      Per-trip error analysis
  Tab 5 — System         Health of all services + retrain instructions

Run locally:
  ONLINE_API_URL=http://localhost:8000 \\
  BATCH_API_URL=http://localhost:8001  \\
  streamlit run app.py

Run via Docker (recommended):
  cd 6-Full-System && docker compose up
  → http://localhost:8501
"""
import os
import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import requests
import streamlit as st


# ── Config ────────────────────────────────────────────────────────────────────
ONLINE_API  = os.getenv("ONLINE_API_URL", "http://localhost:8000")
BATCH_API   = os.getenv("BATCH_API_URL",  "http://localhost:8001")
_DATA_DIR   = Path(os.getenv("BATCH_DATA_DIR",
              str(Path(__file__).parent.parent / "batch")))
BATCH_DB    = _DATA_DIR / "batch_results.db"
PRED_DIR    = _DATA_DIR / "predictions"

TRAIN_MAE   = 3.07
ALERT_RATIO = 1.5
ALERT_VOL   = 500_000


# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_batch_results() -> pd.DataFrame:
    if not BATCH_DB.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(BATCH_DB)
    df   = pd.read_sql("SELECT * FROM batch_results ORDER BY year, month", conn)
    conn.close()
    df["period"] = df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)
    return df


def check_service(url: str) -> dict:
    try:
        r = requests.get(f"{url}/health", timeout=3)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NYC Taxi — Full System",
    page_icon="🚕",
    layout="wide",
)

st.title("🚕 Taxi Trip Duration — Full MLOps System")
st.caption(
    "Module 6 — Online + Offline  |  "
    "Online API (port 8000)  +  Batch API (port 8001)  |  "
    "Training data: 2019 TLC  |  Champion: @champion"
)

# Quick status bar
online_h = check_service(ONLINE_API)
batch_h  = check_service(BATCH_API)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Online API",    "🟢 Online" if online_h else "🔴 Offline",
            online_h.get("model_version", "—") if online_h else "not running")
col2.metric("Batch API",     "🟢 Online" if batch_h  else "🔴 Offline",
            f"{batch_h.get('periods_scored', 0)} periods scored" if batch_h else "not running")
col3.metric("Alerts fired",  batch_h.get("alerts", "—") if batch_h else "—")
col4.metric("Running jobs",  batch_h.get("running_jobs", "—") if batch_h else "—")

st.divider()

# ── 5 Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔮 Predict", "📊 Batch Results", "📈 Drift Monitor",
    "🔬 Analytics", "🏥 System"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Predict (Online API)
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Live Prediction")
    st.caption(f"Calls the online API at `{ONLINE_API}/predict` — synchronous, returns in milliseconds")

    if online_h:
        st.success(f"Serving model **{online_h.get('model_version', '?')}** "
                   f"@{online_h.get('model_alias', '?')}")
    else:
        st.error(f"Online API not reachable at `{ONLINE_API}`")

    col1, col2 = st.columns(2)
    with col1:
        pickup_dt  = st.text_input("Pickup datetime (ISO)", "2019-01-15T14:30:00")
        pu_zone    = st.number_input("Pickup zone (PULocationID)", 1, 265, 161)
        do_zone    = st.number_input("Dropoff zone (DOLocationID)", 1, 265, 237)
        distance   = st.number_input("Trip distance (miles)", 0.1, 50.0, 2.5)
    with col2:
        passengers = st.number_input("Passenger count", 1, 6, 1)
        vendor     = st.selectbox("VendorID", [1, 2])
        ratecode   = st.selectbox("RatecodeID", [1, 2, 3, 4, 5, 6])
        payment    = st.selectbox("Payment type", [1, 2, 3, 4])

    if st.button("▶️ Predict", type="primary", disabled=not online_h):
        payload = {
            "tpep_pickup_datetime": pickup_dt,
            "PULocationID":  int(pu_zone),
            "DOLocationID":  int(do_zone),
            "trip_distance": float(distance),
            "passenger_count": int(passengers),
            "VendorID":  int(vendor),
            "RatecodeID": int(ratecode),
            "payment_type": int(payment),
        }
        try:
            r = requests.post(f"{ONLINE_API}/predict", json=payload, timeout=10)
            if r.status_code == 200:
                result = r.json()
                st.metric(
                    "Predicted duration",
                    f"{result['predicted_duration_minutes']} min",
                    help=f"Model {result['model_version']} @{result['model_alias']}"
                )
                st.caption(f"Model: {result['model_version']} @{result['model_alias']}")
            else:
                st.error(f"API error {r.status_code}: {r.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

    st.divider()
    st.caption("**How it works:** POST /predict → FastAPI loads @champion from MLflow → "
               "runs preprocessor + model → returns duration in milliseconds")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Batch Results
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Batch Scoring Results")
    st.caption(f"Calls the batch API at `{BATCH_API}` — async, triggers background jobs")

    if not batch_h:
        st.error(f"Batch API not reachable at `{BATCH_API}`")

    df = load_batch_results()

    if df.empty:
        st.info("No batch results yet. Trigger scoring below or run: "
                "`cd 5-Deploy-Offline/batch && python main.py`")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Periods scored", len(df))
        col2.metric("Alerts fired",   int(df["alert"].sum()))
        col3.metric("Best MAE",  f"{df['mae'].min():.2f} min")
        col4.metric("Worst MAE", f"{df['mae'].max():.2f} min")

        st.divider()

        # Simplified table - removed alert column (shown in Drift tab)
        display = df[["period", "total_rows", "mae"]].copy()
        display["total_rows"] = display["total_rows"].apply(lambda x: f"{int(x):,}")
        display["mae"]        = display["mae"].apply(lambda x: f"{x:.2f} min")
        display.columns       = ["Period", "Volume", "MAE"]
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Score a new period")
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        score_year  = st.number_input("Year",  2019, 2024, 2023)
    with col2:
        score_month = st.number_input("Month", 1, 12, 6)
    with col3:
        st.write("")
        st.write("")
        if st.button("▶️ Trigger scoring", disabled=not batch_h):
            r = requests.post(
                f"{BATCH_API}/score",
                params={"year": score_year, "month": score_month},
                timeout=5,
            )
            st.info(r.json().get("message", str(r.json())))
            st.cache_data.clear()

    st.caption("**How it works:** POST /score → batch API triggers background job (~2 min) → "
               "scores ALL trips → saves predictions.parquet + updates batch_results.db")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Drift Monitor (Performance + Feature Drift merged)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("📈 Drift Monitoring")
    st.caption("Monitor model performance drift and feature drift in one place.")

    # Sub-tabs for drift views
    drift_tab1, drift_tab2 = st.tabs(["📊 Performance Drift", "🔬 Feature Drift"])

    # ─── Performance Drift ───────────────────────────────────────────────────
    with drift_tab1:
        st.subheader("Performance Drift — MAE Over Time")
        st.caption(
            "Train on 2019 → deploy online → batch score monthly → watch what happens.  \n"
            "**Red** = alert fired  |  **Green** = within acceptable range"
        )

        df = load_batch_results()

        if df.empty:
            st.info("No batch results yet. Go to **Batch Results** tab and trigger scoring.")
        else:
            colors = ["#e74c3c" if a else "#2ecc71" for a in df["alert"]]

            fig, axes = plt.subplots(1, 3, figsize=(14, 5))

            axes[0].bar(df["period"], df["mae"], color=colors, edgecolor="white")
            axes[0].axhline(TRAIN_MAE, color="steelblue", linestyle="--", linewidth=2,
                            label=f"Train MAE ({TRAIN_MAE} min)")
            axes[0].axhline(TRAIN_MAE * ALERT_RATIO, color="#e74c3c", linestyle="--",
                            linewidth=2, label=f"Alert threshold ({TRAIN_MAE * ALERT_RATIO:.2f} min)")
            axes[0].set_title("MAE over time", fontweight="bold")
            axes[0].set_ylabel("MAE (minutes)")
            axes[0].tick_params(axis="x", rotation=15)
            axes[0].legend(fontsize=8)

            axes[1].bar(df["period"], df["mae_ratio"], color=colors, edgecolor="white")
            axes[1].axhline(1.0, color="steelblue", linestyle="--", linewidth=2,
                            label="Baseline (1.0x)")
            axes[1].axhline(ALERT_RATIO, color="#e74c3c", linestyle="--", linewidth=2,
                            label=f"Alert ({ALERT_RATIO}x)")
            axes[1].set_title("MAE ratio vs training", fontweight="bold")
            axes[1].set_ylabel("Ratio")
            axes[1].tick_params(axis="x", rotation=15)
            axes[1].legend(fontsize=8)

            axes[2].bar(df["period"], df["total_rows"], color=colors, edgecolor="white")
            axes[2].axhline(ALERT_VOL, color="#e74c3c", linestyle="--", linewidth=2,
                            label=f"Alert ({ALERT_VOL:,})")
            axes[2].set_title("Monthly trip volume", fontweight="bold")
            axes[2].set_ylabel("Total trips")
            axes[2].tick_params(axis="x", rotation=15)
            axes[2].legend(fontsize=8)

            ok_p    = mpatches.Patch(color="#2ecc71", label="OK")
            alert_p = mpatches.Patch(color="#e74c3c", label="Alert")
            fig.legend(handles=[ok_p, alert_p], loc="upper right", fontsize=9)
            plt.suptitle("NYC Taxi Model Drift  |  Train: 2019  |  Scored: batch periods",
                         fontsize=12, fontweight="bold")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close()

            # Alert details (only show if alerts exist)
            alerts = df[df["alert"] == 1]
            if not alerts.empty:
                st.divider()
                st.subheader("⚠️ Alert details")
                for _, row in alerts.iterrows():
                    with st.expander(f"{row['period']} — MAE {row['mae']:.2f} min "
                                     f"({row['mae_ratio']:.2f}x training)"):
                        col1, col2, col3 = st.columns(3)
                        col1.metric("MAE",    f"{row['mae']:.2f} min",
                                    delta=f"+{row['mae'] - TRAIN_MAE:.2f} vs train",
                                    delta_color="inverse")
                        col2.metric("Volume", f"{int(row['total_rows']):,}")
                        col3.metric("Ratio",  f"{row['mae_ratio']:.2f}x")
                        st.info("Model degradation detected → see **System** tab for retrain instructions.")

    # ─── Feature Drift ──────────────────────────────────────────────────────
    with drift_tab2:
        from drift_tab import render_drift_tab
        render_drift_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Analytics (from prediction parquet files)
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Prediction Analytics")
    st.caption("Per-trip predictions from the batch scorer — actual vs predicted, error patterns, worst routes")

    parquets = sorted(PRED_DIR.glob("*.parquet")) if PRED_DIR.exists() else []

    if not parquets:
        st.info(
            "No prediction files yet.  \n"
            "Go to **Batch Results** tab and trigger scoring for at least one period."
        )
    else:
        # Period selector
        period_options = {f.stem.replace("_", "-"): f for f in parquets}
        selected = st.selectbox(
            "Select period to analyse",
            list(period_options.keys()),
            format_func=lambda x: f"{x}  ({period_options[x].stat().st_size / 1024 / 1024:.1f} MB)"
        )
        selected_file = period_options[selected]

        @st.cache_data(ttl=60)
        def load_predictions(path: str) -> pd.DataFrame:
            df = pd.read_parquet(path)
            if len(df) > 100_000:
                df = df.sample(100_000, random_state=42)
            df["abs_error"] = df["error_minutes"].abs()
            df["distance_bucket"] = pd.cut(
                df["trip_distance"],
                bins=[0, 1, 2, 5, 10, 50],
                labels=["<1 mi", "1-2 mi", "2-5 mi", "5-10 mi", ">10 mi"]
            )
            return df

        df_pred = load_predictions(str(selected_file))

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Trips analysed",   f"{len(df_pred):,}")
        col2.metric("MAE",              f"{df_pred['abs_error'].mean():.2f} min")
        col3.metric("Within 2 min",     f"{(df_pred['abs_error'] <= 2).mean()*100:.1f}%")
        col4.metric("Within 5 min",     f"{(df_pred['abs_error'] <= 5).mean()*100:.1f}%")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Prediction error distribution")
            fig, ax = plt.subplots(figsize=(6, 4))
            errors = df_pred["error_minutes"].clip(-15, 15)
            ax.hist(errors, bins=60, color="steelblue", edgecolor="white", alpha=0.8)
            ax.axvline(0, color="green", linestyle="--", linewidth=2, label="Perfect prediction")
            ax.axvline(errors.mean(), color="red", linestyle="--", linewidth=1.5,
                       label=f"Mean error: {errors.mean():.2f} min")
            ax.set_xlabel("Error (minutes) — negative = under-predicted")
            ax.set_ylabel("Count")
            ax.set_title(f"Error distribution — {selected}")
            ax.legend(fontsize=8)
            st.pyplot(fig)
            plt.close()
            st.caption("Negative = model predicted shorter than actual. Positive = predicted longer.")

        with col2:
            st.subheader("MAE by trip distance")
            mae_by_dist = (
                df_pred.groupby("distance_bucket", observed=True)["abs_error"]
                .agg(["mean", "count"])
                .reset_index()
            )
            fig, ax = plt.subplots(figsize=(6, 4))
            bars = ax.bar(
                mae_by_dist["distance_bucket"].astype(str),
                mae_by_dist["mean"],
                color="steelblue", edgecolor="white"
            )
            ax.axhline(df_pred["abs_error"].mean(), color="red", linestyle="--",
                       linewidth=1.5, label=f"Overall MAE: {df_pred['abs_error'].mean():.2f} min")
            for bar, count in zip(bars, mae_by_dist["count"]):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                        f"n={count:,}", ha="center", va="bottom", fontsize=7)
            ax.set_xlabel("Trip distance")
            ax.set_ylabel("MAE (minutes)")
            ax.set_title("Accuracy by trip length")
            ax.legend(fontsize=8)
            st.pyplot(fig)
            plt.close()
            st.caption("Longer trips are harder to predict — more variability in traffic and routing.")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Worst predicted routes (top 10)")
            worst = (
                df_pred.groupby(["PULocationID", "DOLocationID"])
                .agg(mae=("abs_error", "mean"), trips=("abs_error", "count"))
                .reset_index()
                .query("trips >= 10")
                .sort_values("mae", ascending=False)
                .head(10)
            )
            worst["mae"] = worst["mae"].apply(lambda x: f"{x:.2f} min")
            worst["trips"] = worst["trips"].apply(lambda x: f"{x:,}")
            worst.columns = ["Pickup Zone", "Dropoff Zone", "MAE", "Trips"]
            st.dataframe(worst, use_container_width=True, hide_index=True)
            st.caption("Zones with ≥10 trips. High MAE = model struggles on these routes.")

        with col2:
            st.subheader("Best predicted routes (top 10)")
            best = (
                df_pred.groupby(["PULocationID", "DOLocationID"])
                .agg(mae=("abs_error", "mean"), trips=("abs_error", "count"))
                .reset_index()
                .query("trips >= 10")
                .sort_values("mae", ascending=True)
                .head(10)
            )
            best["mae"] = best["mae"].apply(lambda x: f"{x:.2f} min")
            best["trips"] = best["trips"].apply(lambda x: f"{x:,}")
            best.columns = ["Pickup Zone", "Dropoff Zone", "MAE", "Trips"]
            st.dataframe(best, use_container_width=True, hide_index=True)
            st.caption("Zones with ≥10 trips. Low MAE = model knows these routes well.")

        st.divider()

        st.subheader("Trip distance distribution (feature drift indicator)")
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.hist(df_pred["trip_distance"].clip(0, 20), bins=60,
                color="steelblue", edgecolor="white", alpha=0.8, label=selected)
        ax.axvline(2.83, color="green", linestyle="--", linewidth=2,
                   label="2019 training mean (2.83 mi)")
        ax.axvline(df_pred["trip_distance"].mean(), color="orange", linestyle="--",
                   linewidth=2,
                   label=f"{selected} mean ({df_pred['trip_distance'].mean():.2f} mi)")
        ax.set_xlabel("Trip distance (miles)")
        ax.set_ylabel("Count")
        ax.set_title(f"Trip distance distribution — {selected} vs 2019 training")
        ax.legend(fontsize=9)
        st.pyplot(fig)
        plt.close()
        st.caption(
            "If the orange line (batch mean) drifts right of the green line (training mean), "
            "the model is seeing longer trips than it was trained on — feature drift."
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — System
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("System Health & Retrain")

    # ── Service health ────────────────────────────────────────────────────────
    st.subheader("Services")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Online API** — real-time predictions")
        h = check_service(ONLINE_API)
        if h:
            st.success(f"Running at `{ONLINE_API}`")
            st.json(h)
        else:
            st.error("Offline")

    with col2:
        st.markdown("**Batch API** — scoring + drift metrics")
        h = check_service(BATCH_API)
        if h:
            st.success(f"Running at `{BATCH_API}`")
            st.json(h)
        else:
            st.error("Offline")

    st.divider()

    # ── Prediction files ──────────────────────────────────────────────────────
    st.subheader("Prediction files (analytics)")
    parquets = sorted(PRED_DIR.glob("*.parquet")) if PRED_DIR.exists() else []
    if parquets:
        total_mb = sum(f.stat().st_size for f in parquets) / 1024 / 1024
        st.caption(f"{len(parquets)} files  |  {total_mb:.1f} MB total")
        for f in parquets:
            col1, col2, col3 = st.columns([3, 1, 2])
            col1.text(f.name)
            col2.text(f"{f.stat().st_size / 1024 / 1024:.1f} MB")
            if col3.button("Preview", key=f"prev_{f.name}"):
                df_prev = pd.read_parquet(f).head(5)
                st.dataframe(df_prev, use_container_width=True)
    else:
        st.info("No prediction files yet.")

    st.divider()

    # ── Retrain ───────────────────────────────────────────────────────────────
    st.subheader("🔄 Retrain")

    alerts_exist = not load_batch_results().empty and \
                   load_batch_results()["alert"].sum() > 0

    if alerts_exist:
        st.warning(
            "⚠️ Drift alert detected in batch results.  \n"
            "The current champion may be underperforming on recent data.  \n"
            "Consider retraining on expanded data."
        )
    else:
        st.success("✅ No drift alerts. Current champion is performing within acceptable range.")

    st.markdown("**How retraining works:**")
    st.markdown("""
1. The training pipeline runs on **2019 + 2020 data** → trains a new model
2. New model registers as **@challenger** in MLflow (does not replace the champion yet)
3. Both models are evaluated on a neutral **2020-06 holdout** (never seen by either)
4. If challenger MAE is better by > 0.1 min → **promoted to @champion**
5. Online API picks up the new champion on its **next startup**

**The champion/challenger gate** prevents silent degradation —
the new model must genuinely outperform the old one before going live.
    """)

    st.markdown("**Run retrain in a terminal:**")
    st.code(
        "cd 6-Full-System/pipeline\n"
        "python main.py \\\n"
        "  --train-years 2019,2020 \\\n"
        "  --sample-size 200000 \\\n"
        "  --no-tune\n\n"
        "# After retrain completes, restart the online API:\n"
        "cd ..\n"
        "docker compose restart api",
        language="bash"
    )

    st.caption(
        "After restarting the API, refresh this dashboard — "
        "**Predict** tab will show the new model version."
    )