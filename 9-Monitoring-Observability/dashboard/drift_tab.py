"""
Evidently Drift Tab - Tab 6 for the Streamlit Dashboard
"""
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import requests

BATCH_API = os.getenv("BATCH_API_URL", "http://localhost:8001")


def render_drift_tab():
    """Render the Evidently drift monitoring tab."""
    
    st.header("🔬 Feature Drift Monitoring (Evidently)")
    st.caption("Track how input data distributions change over time.")
    
    try:
        response = requests.get(f"{BATCH_API}/drift/summary", timeout=5)
        if response.status_code != 200:
            st.warning("No drift data available. Run batch scoring first.")
            st.code("curl -X POST 'http://localhost:1079/score?year=2020&month=4'", language="bash")
            return
        data = response.json()
        summary = data.get('summary', [])
    except Exception as e:
        st.warning(f"Batch API not reachable: {e}")
        return
    
    if not summary:
        st.info("No drift data yet. Run batch scoring with drift detection.")
        st.code("curl -X POST 'http://localhost:1079/score?year=2020&month=4'", language="bash")
        return
    
    df = pd.DataFrame(summary)
    df['period'] = df['year'].astype(str) + '-' + df['month'].astype(str).str.zfill(2)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Periods Analyzed", len(df))
    col2.metric("Drift Detected", df['drift_detected'].sum())
    col3.metric("Avg Drift Score", f"{df['drift_score'].mean():.3f}")
    col4.metric("Max Drift Score", f"{df['drift_score'].max():.3f}")
    
    st.divider()
    st.subheader("Drift Score Over Time")
    
    fig = px.bar(
        df,
        x='period',
        y='drift_score',
        color='drift_detected',
        color_discrete_map={0: '#2ecc71', 1: '#e74c3c'},
        title='Feature Drift by Period',
        labels={'drift_score': 'Drift Score', 'period': 'Period'}
    )
    fig.add_hline(y=0.5, line_dash="dash", line_color="red", annotation_text="🚨 Drift Threshold (0.5)")
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    st.subheader("Drift Details")
    
    display_df = df[['period', 'drift_score', 'drift_detected', 'mae', 'alert']].copy()
    display_df['drift_detected'] = display_df['drift_detected'].map({0: '✅ OK', 1: '⚠️ Drift'})
    display_df['alert'] = display_df['alert'].map({0: '✅ OK', 1: '⚠️ Alert'})
    display_df['drift_score'] = display_df['drift_score'].apply(lambda x: f"{x:.3f}")
    display_df['mae'] = display_df['mae'].apply(lambda x: f"{x:.2f} min")
    display_df.columns = ['Period', 'Drift Score', 'Drift Status', 'MAE', 'Alert Status']
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.divider()
    st.subheader("📄 View Full Drift Report")
    periods = df['period'].tolist()
    if periods:
        selected = st.selectbox("Select Period", periods, index=len(periods)-1)
        if selected:
            year, month = selected.split('-')
            st.markdown(f"[📊 Open HTML Report for {selected}]({BATCH_API}/drift/html/{year}/{month})")
    
    with st.expander("ℹ️ What does this mean?"):
        st.markdown("""
        **Drift Score (0.0 - 1.0):**
        - **0.0 - 0.3**: ✅ OK - Data similar to training
        - **0.3 - 0.5**: ⚠️ Warning - Some features changing
        - **0.5 - 1.0**: 🚨 Drift Detected - Significant changes
        
        **What to do when drift is detected:**
        1. Investigate which features are drifting
        2. Check if drift is expected (e.g., seasonal)
        3. Consider retraining with newer data
        """)
