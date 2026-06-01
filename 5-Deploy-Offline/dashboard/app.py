"""
NYC Taxi Trip Duration — MLOps Dashboard

Four tabs:
  Tab 1 — Predict       Try the model live (calls online API)
  Tab 2 — Batch Results Scored periods with drift metrics
  Tab 3 — Drift Chart   MAE over time — the drift story
  Tab 4 — System Health Model registry status + trigger retrain

Run:
  streamlit run app.py
"""
import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import requests
import streamlit as st


# ── Config ────────────────────────────────────────────────────────────────────
_DASH_DIR   = Path(__file__).parent
_OFFLINE    = _DASH_DIR.parent
_ONLINE     = _OFFLINE.parent / "4-Deploy-Online"

BATCH_DB    = _OFFLINE / "batch" / "batch_results.db"
PRED_DIR    = _OFFLINE / "batch" / "predictions"
ONLINE_API  = "http://localhost:8000"
BATCH_API   = "http://localhost:8001"

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
    df["period"] = df["year"].astype(str) + "-" + df["month"].apply(lambda m: f"{m:02d}")
    return df


def api_health(url: str) -> dict:
    try:
        r = requests.get(f"{url}/health", timeout=3)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NYC Taxi MLOps Dashboard",
    page_icon="🚕",
    layout="wide",
)

st.title("🚕 NYC Taxi Trip Duration — MLOps Dashboard")
st.caption("Module 5 — Deploy Offline | Training data: 2019 TLC | Drift story: 2020 → 2024")

tab1, tab2, tab3, tab4 = st.tabs([
    "🔮 Predict", "📊 Batch Results", "📈 Drift Chart", "🏥 System Health"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Predict
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Try the Model")
    st.caption(f"Calls the online API at `{ONLINE_API}/predict`")

    health = api_health(ONLINE_API)
    if health:
        st.success(f"API online — serving {health.get('model_version', '?')} "
                   f"@{health.get('model_alias', '?')}")
    else:
        st.error(f"Online API not reachable at {ONLINE_API}. "
                 "Start it: `cd 4-Deploy-Online && docker compose up api -d`")

    col1, col2 = st.columns(2)
    with col1:
        pickup_dt  = st.text_input("Pickup datetime", "2019-01-15T14:30:00")
        pu_zone    = st.number_input("Pickup zone (PULocationID)", 1, 265, 161)
        do_zone    = st.number_input("Dropoff zone (DOLocationID)", 1, 265, 237)
        distance   = st.number_input("Trip distance (miles)", 0.1, 50.0, 2.5)
    with col2:
        passengers = st.number_input("Passenger count", 1, 6, 1)
        vendor     = st.selectbox("VendorID", [1, 2])
        ratecode   = st.selectbox("RatecodeID", [1, 2, 3, 4, 5, 6])
        payment    = st.selectbox("Payment type", [1, 2, 3, 4])

    if st.button("Predict duration", type="primary"):
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
            else:
                st.error(f"API error {r.status_code}: {r.text}")
        except Exception as e:
            st.error(f"Could not reach API: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Batch Results
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Batch Scoring Results")

    batch_health = api_health(BATCH_API)
    if batch_health:
        st.success(f"Batch API online — {BATCH_API}")
    else:
        st.warning(f"Batch API offline. Results shown from local DB. "
                   "Start: `cd 5-Deploy-Offline && docker compose up batch -d`")

    df = load_batch_results()
    if df.empty:
        st.info("No results yet. Run: `cd 5-Deploy-Offline/batch && python main.py`")
    else:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Periods scored", len(df))
        col2.metric("Alerts fired",   int(df["alert"].sum()))
        col3.metric("Best MAE",  f"{df['mae'].min():.2f} min")
        col4.metric("Worst MAE", f"{df['mae'].max():.2f} min")

        st.divider()

        # Results table
        display = df[["period", "total_rows", "mae", "mae_ratio", "alert"]].copy()
        display["total_rows"] = display["total_rows"].apply(lambda x: f"{x:,}")
        display["mae"]        = display["mae"].apply(lambda x: f"{x:.2f}")
        display["mae_ratio"]  = display["mae_ratio"].apply(lambda x: f"{x:.2f}x")
        display["alert"]      = display["alert"].apply(lambda x: "⚠️ ALERT" if x else "✅ OK")
        display.columns       = ["Period", "Volume", "MAE", "Ratio", "Status"]

        st.dataframe(display, use_container_width=True, hide_index=True)

        # Trigger new batch run via API
        st.divider()
        st.subheader("Score a new period")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            score_year  = st.number_input("Year",  2019, 2024, 2023)
        with col2:
            score_month = st.number_input("Month", 1, 12, 6)
        with col3:
            st.write("")
            if st.button("Trigger batch scoring"):
                if batch_health:
                    r = requests.post(
                        f"{BATCH_API}/score",
                        params={"year": score_year, "month": score_month},
                        timeout=5
                    )
                    st.info(r.json().get("message", "Started"))
                else:
                    st.error("Batch API not running — start it first")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Drift Chart
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Drift Story — MAE Over Time")
    st.caption("Train on 2019 → deploy → watch what happens")

    df = load_batch_results()
    if df.empty:
        st.info("No batch results yet.")
    else:
        colors = ["#e74c3c" if a else "#2ecc71" for a in df["alert"]]

        fig, axes = plt.subplots(1, 3, figsize=(14, 4))

        # MAE
        axes[0].bar(df["period"], df["mae"], color=colors)
        axes[0].axhline(TRAIN_MAE, color="steelblue", linestyle="--",
                        linewidth=2, label=f"Train MAE ({TRAIN_MAE} min)")
        axes[0].axhline(TRAIN_MAE * ALERT_RATIO, color="#e74c3c", linestyle="--",
                        linewidth=2, label=f"Alert ({ALERT_RATIO}x)")
        axes[0].set_title("MAE over time", fontweight="bold")
        axes[0].set_ylabel("MAE (minutes)")
        axes[0].tick_params(axis="x", rotation=15)
        axes[0].legend(fontsize=8)

        # MAE ratio
        axes[1].bar(df["period"], df["mae_ratio"], color=colors)
        axes[1].axhline(1.0, color="steelblue", linestyle="--",
                        linewidth=2, label="Baseline (1.0x)")
        axes[1].axhline(ALERT_RATIO, color="#e74c3c", linestyle="--",
                        linewidth=2, label=f"Alert ({ALERT_RATIO}x)")
        axes[1].set_title("MAE ratio vs training", fontweight="bold")
        axes[1].set_ylabel("Ratio")
        axes[1].tick_params(axis="x", rotation=15)
        axes[1].legend(fontsize=8)

        # Volume
        axes[2].bar(df["period"], df["total_rows"], color=colors)
        axes[2].axhline(ALERT_VOL, color="#e74c3c", linestyle="--",
                        linewidth=2, label=f"Alert ({ALERT_VOL:,})")
        axes[2].set_title("Monthly trip volume", fontweight="bold")
        axes[2].set_ylabel("Total trips")
        axes[2].tick_params(axis="x", rotation=15)
        axes[2].legend(fontsize=8)

        ok_p    = mpatches.Patch(color="#2ecc71", label="OK")
        alert_p = mpatches.Patch(color="#e74c3c", label="Alert")
        fig.legend(handles=[ok_p, alert_p], loc="upper right", fontsize=9)
        plt.suptitle("NYC Taxi Model Drift — Train: 2019 | Scored: batch periods",
                     fontsize=12, fontweight="bold")
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

        # Alert details
        alerts = df[df["alert"] == 1]
        if not alerts.empty:
            st.divider()
            st.subheader("⚠️ Alert details")
            for _, row in alerts.iterrows():
                with st.expander(f"{row['period']} — MAE {row['mae']:.2f} min "
                                 f"({row['mae_ratio']:.2f}x training)"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("MAE",    f"{row['mae']:.2f} min")
                    col2.metric("Volume", f"{int(row['total_rows']):,}")
                    col3.metric("Ratio",  f"{row['mae_ratio']:.2f}x")
                    st.markdown("**Recommended actions:**")
                    if row["mae_ratio"] > ALERT_RATIO:
                        st.markdown("- MAE degraded significantly → consider retraining")
                    if row["total_rows"] < ALERT_VOL:
                        st.markdown("- Volume collapsed → investigate data source")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — System Health
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("System Health")

    # API status
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Online API")
        h = api_health(ONLINE_API)
        if h:
            st.success("Running")
            st.json(h)
        else:
            st.error("Offline")
            st.code("cd 4-Deploy-Online\ndocker compose up api -d")

    with col2:
        st.subheader("Batch API")
        h = api_health(BATCH_API)
        if h:
            st.success("Running")
            st.json(h)
        else:
            st.error("Offline")
            st.code("cd 5-Deploy-Offline\ndocker compose up batch -d")

    st.divider()

    # Prediction files
    st.subheader("Prediction files")
    parquets = sorted(PRED_DIR.glob("*.parquet")) if PRED_DIR.exists() else []
    if parquets:
        for f in parquets:
            col1, col2 = st.columns([3, 1])
            col1.text(f.name)
            col2.text(f"{f.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        st.info("No prediction files yet.")

    st.divider()

    # Trigger retrain
    st.subheader("🔄 Trigger Retrain")
    st.caption("Trains a challenger on 2019+2020 data, compares against champion, "
               "promotes only if it wins.")

    col1, col2 = st.columns(2)
    with col1:
        retrain_sample = st.selectbox(
            "Sample size", [50_000, 100_000, 200_000, 500_000],
            index=2, format_func=lambda x: f"{x:,} rows"
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("🚀 Run retrain", type="primary"):
            st.warning(
                "Retrain takes ~10-15 min. Run in a terminal:\n\n"
                f"```\ncd 5-Deploy-Offline/retrain\n"
                f"python main.py --sample-size {retrain_sample}\n```"
            )
