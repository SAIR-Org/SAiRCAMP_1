"""
NYC Taxi — Offline Deployment Dashboard

Three tabs:
  Tab 1 — Batch Results   Scored periods, drift metrics, trigger new scoring
  Tab 2 — Drift Chart     MAE over time — the drift story visualized
  Tab 3 — System Health   API status, prediction files available

Run locally:
  streamlit run app.py

Run via Docker:
  cd 5-Deploy-Offline && docker compose up
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
BATCH_API   = os.getenv("BATCH_API_URL", "http://localhost:8001")
_DATA_DIR   = Path(os.getenv("BATCH_DATA_DIR", str(Path(__file__).parent.parent / "batch")))
BATCH_DB    = _DATA_DIR / "batch_results.db"
PRED_DIR    = _DATA_DIR / "predictions"

TRAIN_MAE   = 3.07   # 2019 training baseline
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
    df["period"] = df["year"].astype(str) + "-" + df["month"].apply(lambda m: f"{m:02d}")
    return df


def batch_api_health() -> dict:
    try:
        r = requests.get(f"{BATCH_API}/health", timeout=3)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NYC Taxi — Offline Dashboard",
    page_icon="🚕",
    layout="wide",
)

st.title("🚕 NYC Taxi — Offline Deployment Dashboard")
st.caption(
    "Module 5 — Deploy Offline  |  "
    "Batch scoring for analytics + drift monitoring  |  "
    "Training data: 2019 TLC"
)

tab1, tab2, tab3 = st.tabs(["📊 Batch Results", "📈 Drift Chart", "🏥 System Health"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Batch Results
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Batch Scoring Results")

    health = batch_api_health()
    if health:
        col1, col2, col3 = st.columns(3)
        col1.success(f"Batch API online")
        col2.metric("Periods scored", health.get("periods_scored", 0))
        col3.metric("Alerts fired",   health.get("alerts", 0))
    else:
        st.warning(
            f"Batch API not reachable at `{BATCH_API}`.  \n"
            "Results shown from local files.  \n"
            "Start: `cd 5-Deploy-Offline && docker compose up batch -d`"
        )

    df = load_batch_results()

    if df.empty:
        st.info(
            "No batch results yet.  \n"
            "Run: `cd 5-Deploy-Offline/batch && python main.py`"
        )
    else:
        # Summary row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Periods scored", len(df))
        col2.metric("Alerts fired",   int(df["alert"].sum()))
        col3.metric("Best MAE",        f"{df['mae'].min():.2f} min")
        col4.metric("Worst MAE",       f"{df['mae'].max():.2f} min")

        st.divider()

        # Results table
        display = df[["period", "total_rows", "mae", "mae_ratio", "alert"]].copy()
        display["total_rows"] = display["total_rows"].apply(lambda x: f"{int(x):,}")
        display["mae"]        = display["mae"].apply(lambda x: f"{x:.2f} min")
        display["mae_ratio"]  = display["mae_ratio"].apply(lambda x: f"{x:.2f}x")
        display["alert"]      = display["alert"].apply(lambda x: "⚠️ ALERT" if x else "✅ OK")
        display.columns       = ["Period", "Volume", "MAE", "MAE Ratio", "Status"]
        st.dataframe(display, use_container_width=True, hide_index=True)

        st.divider()

        # Trigger new scoring
        st.subheader("Score a new period")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            score_year  = st.number_input("Year",  2019, 2024, 2023)
        with col2:
            score_month = st.number_input("Month", 1, 12, 6)
        with col3:
            st.write("")
            st.write("")
            if st.button("▶️ Trigger scoring", type="primary"):
                if health:
                    r = requests.post(
                        f"{BATCH_API}/score",
                        params={"year": score_year, "month": score_month},
                        timeout=5,
                    )
                    data = r.json()
                    st.info(data.get("message", str(data)))
                    st.cache_data.clear()
                else:
                    st.error("Batch API not running — start it first")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Drift Chart
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Drift Story — MAE Over Time")
    st.caption(
        "Train on 2019 → deploy → batch score by period → watch model degrade.  \n"
        "**Red** = alert fired  |  **Green** = within acceptable range"
    )

    df = load_batch_results()

    if df.empty:
        st.info("No batch results yet. Run the batch scorer first.")
    else:
        colors = ["#e74c3c" if a else "#2ecc71" for a in df["alert"]]

        fig, axes = plt.subplots(1, 3, figsize=(14, 5))

        # MAE over time
        axes[0].bar(df["period"], df["mae"], color=colors, edgecolor="white")
        axes[0].axhline(TRAIN_MAE, color="steelblue", linestyle="--",
                        linewidth=2, label=f"Train MAE ({TRAIN_MAE} min)")
        axes[0].axhline(TRAIN_MAE * ALERT_RATIO, color="#e74c3c", linestyle="--",
                        linewidth=2, label=f"Alert ({ALERT_RATIO}x = {TRAIN_MAE * ALERT_RATIO:.2f} min)")
        axes[0].set_title("MAE over time", fontweight="bold", fontsize=12)
        axes[0].set_ylabel("MAE (minutes)")
        axes[0].tick_params(axis="x", rotation=15)
        axes[0].legend(fontsize=8)

        # MAE ratio
        axes[1].bar(df["period"], df["mae_ratio"], color=colors, edgecolor="white")
        axes[1].axhline(1.0, color="steelblue", linestyle="--",
                        linewidth=2, label="Baseline (1.0x)")
        axes[1].axhline(ALERT_RATIO, color="#e74c3c", linestyle="--",
                        linewidth=2, label=f"Alert ({ALERT_RATIO}x)")
        axes[1].set_title("MAE ratio vs training", fontweight="bold", fontsize=12)
        axes[1].set_ylabel("Ratio")
        axes[1].tick_params(axis="x", rotation=15)
        axes[1].legend(fontsize=8)

        # Volume
        axes[2].bar(df["period"], df["total_rows"], color=colors, edgecolor="white")
        axes[2].axhline(ALERT_VOL, color="#e74c3c", linestyle="--",
                        linewidth=2, label=f"Alert threshold ({ALERT_VOL:,})")
        axes[2].set_title("Monthly trip volume", fontweight="bold", fontsize=12)
        axes[2].set_ylabel("Total trips")
        axes[2].tick_params(axis="x", rotation=15)
        axes[2].legend(fontsize=8)

        ok_p    = mpatches.Patch(color="#2ecc71", label="OK")
        alert_p = mpatches.Patch(color="#e74c3c", label="Alert")
        fig.legend(handles=[ok_p, alert_p], loc="upper right",
                   bbox_to_anchor=(1.0, 1.0), fontsize=9)
        plt.suptitle(
            "NYC Taxi Model Drift  |  Train: 2019  |  Scored: batch periods",
            fontsize=13, fontweight="bold"
        )
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

        # Alert details
        alerts = df[df["alert"] == 1]
        if not alerts.empty:
            st.divider()
            st.subheader("⚠️ Alert details")
            for _, row in alerts.iterrows():
                with st.expander(
                    f"{row['period']}  —  MAE {row['mae']:.2f} min "
                    f"({row['mae_ratio']:.2f}x training baseline)"
                ):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("MAE",    f"{row['mae']:.2f} min",
                                delta=f"+{row['mae'] - TRAIN_MAE:.2f} vs train",
                                delta_color="inverse")
                    col2.metric("Volume", f"{int(row['total_rows']):,}")
                    col3.metric("Ratio",  f"{row['mae_ratio']:.2f}x")

                    st.markdown("**What happened:**")
                    if row["mae_ratio"] > ALERT_RATIO:
                        st.markdown(f"- Model accuracy degraded to {row['mae_ratio']:.1f}x training baseline")
                    if row["total_rows"] < ALERT_VOL:
                        st.markdown(f"- Trip volume collapsed to {int(row['total_rows']):,} "
                                    f"(threshold: {ALERT_VOL:,})")
                    st.markdown("**Next step:** investigate distribution shift → consider retraining")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — System Health
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("System Health")

    # Batch API
    st.subheader("Batch API")
    health = batch_api_health()
    if health:
        st.success(f"Running at `{BATCH_API}`")
        col1, col2, col3 = st.columns(3)
        col1.metric("Periods scored",  health.get("periods_scored", 0))
        col2.metric("Alerts",          health.get("alerts", 0))
        col3.metric("Running jobs",    health.get("running_jobs", 0))
    else:
        st.error(f"Offline — not reachable at `{BATCH_API}`")
        st.code(
            "# Start the full stack\n"
            "cd 5-Deploy-Offline\n"
            "docker compose up\n\n"
            "# Or batch API only\n"
            "docker compose up batch -d"
        )

    st.divider()

    # Prediction files
    st.subheader("Prediction files (analytics)")
    parquets = sorted(PRED_DIR.glob("*.parquet")) if PRED_DIR.exists() else []
    if parquets:
        total_mb = sum(f.stat().st_size for f in parquets) / 1024 / 1024
        st.caption(f"{len(parquets)} files  |  {total_mb:.1f} MB total")
        for f in parquets:
            col1, col2, col3 = st.columns([3, 1, 2])
            col1.text(f.name)
            col2.text(f"{f.stat().st_size / 1024 / 1024:.1f} MB")
            if col3.button("Preview", key=f.name):
                df_prev = pd.read_parquet(f).head(5)
                st.dataframe(df_prev, use_container_width=True)
    else:
        st.info(
            "No prediction files yet.  \n"
            "Run: `cd 5-Deploy-Offline/batch && python main.py`"
        )

    st.divider()

    # Data directory
    st.subheader("Data paths")
    st.json({
        "batch_db":       str(BATCH_DB),
        "predictions_dir": str(PRED_DIR),
        "batch_api":      BATCH_API,
    })
