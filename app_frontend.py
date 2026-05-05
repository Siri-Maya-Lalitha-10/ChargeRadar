import os
import sys
import pandas as pd
import streamlit as st
from datetime import datetime, date, time

sys.path.append(os.path.abspath("."))

from app.api.routes import simulate

st.set_page_config(page_title="ChargeRadar", page_icon="⚡", layout="wide")

# ---------------- UI STYLE ----------------
st.markdown(
    """
    <style>
    .stApp { background: #0b1020; color: #f8fafc; }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    .main-title {
        font-size: clamp(1.8rem, 3vw, 2.7rem);
        font-weight: 900;
        line-height: 1.15;
        letter-spacing: -0.04em;
        margin-bottom: 0.25rem;
    }

    .subtitle {
        color: #94a3b8;
        margin-bottom: 1rem;
        font-size: 0.98rem;
    }

    .glass-card {
        padding: 1rem 1rem;
        border-radius: 18px;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 10px 30px rgba(0,0,0,0.16);
        margin-bottom: 1rem;
    }

    .zone-card {
        padding: 1rem;
        border-radius: 18px;
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 10px 24px rgba(0,0,0,0.10);
        margin-bottom: 1rem;
    }

    .zone-title {
        font-size: 1.12rem;
        font-weight: 850;
        margin-bottom: 0.35rem;
    }

    .muted {
        color: #94a3b8;
        font-size: 0.92rem;
    }

    .pill {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        margin-right: 0.35rem;
        margin-top: 0.25rem;
    }

    .red { background: rgba(248,113,113,0.16); color: #fca5a5; }
    .orange { background: rgba(251,191,36,0.16); color: #fcd34d; }
    .green { background: rgba(74,222,128,0.16); color: #86efac; }
    .blue { background: rgba(96,165,250,0.16); color: #93c5fd; }

    .station-box {
        padding: 0.85rem;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.08);
        background: rgba(255,255,255,0.03);
        margin-bottom: 0.5rem;
    }

    .spill-box {
        padding: 0.75rem;
        border-radius: 12px;
        background: rgba(59,130,246,0.08);
        border: 1px dashed rgba(59,130,246,0.35);
        margin-bottom: 0.45rem;
    }

    .info-card {
        padding: 0.85rem 0.95rem;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.08);
        background: rgba(255,255,255,0.03);
        min-height: 86px;
    }

    .info-label {
        font-size: 0.9rem;
        color: #cbd5e1;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }

    .info-value {
        font-size: 1.05rem;
        color: #f8fafc;
        font-weight: 800;
        word-break: break-word;
        overflow-wrap: anywhere;
        line-height: 1.15;
    }

    .bar-track {
        width: 100%;
        height: 10px;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        overflow: hidden;
        margin-top: 0.6rem;
    }

    .bar-fill {
        height: 100%;
        border-radius: 999px;
    }

    .focus-box {
        padding: 1rem;
        border-radius: 18px;
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 1rem;
    }

    div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        padding: 0.6rem 0.75rem;
        border-radius: 14px;
    }

    section[data-testid="stSidebar"] {
        background: #101625;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
st.markdown('<div class="main-title">⚡ ChargeRadar</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">EV Charging Intelligence for BESCOM and normal users</div>', unsafe_allow_html=True)

# ---------------- Sidebar ----------------
with st.sidebar:
    role = st.radio("Who are you?", ["Govt / BESCOM", "Normal user"], index=0)

    if role == "Govt / BESCOM":
        mode = st.radio("View", ["Current", "Later"], index=0)
        today = date.today()
        if mode == "Later":
            selected_date = st.date_input("Date", value=today)
            selected_time = st.time_input("Time", value=time(19, 0))
        else:
            now = datetime.now()
            selected_date = today
            selected_time = time(now.hour, 0)
        run = st.button("Run Simulation", use_container_width=True)
    else:
        run = True

# ---------------- Helpers ----------------
def fetch(day: int, hour: int):
    return simulate(day=day, hour=hour)


def color(status: str):
    if status == "HIGH_LOAD":
        return "🔴", "red"
    if status == "MEDIUM_LOAD":
        return "🟠", "orange"
    return "🟢", "green"


def user_advice(status: str, recommended_action: str, zone_type: str) -> str:
    if status == "HIGH_LOAD" and zone_type == "residential":
        return "This residential area is busy. Charge later if possible."
    if recommended_action == "DEFER":
        return "This area is stressed. Try later or choose another station."
    if status == "MEDIUM_LOAD":
        return "Some wait is possible."
    return "Charging looks available here."


# ---------------- State ----------------
if "data" not in st.session_state:
    st.session_state.data = None

# ---------------------------------------------
# Build inputs
# ---------------------------------------------
if role == "Govt / BESCOM":
    day = (selected_date - date.today()).days % 14
    hour = selected_time.hour
else:
    day = 0
    hour = datetime.now().hour

# ---------------------------------------------
# Fetch
# ---------------------------------------------
if run:
    try:
        st.session_state.data = fetch(day, hour)
    except Exception:
        st.error("Backend not running or not reachable.")
        st.stop()

if st.session_state.data is None:
    try:
        st.session_state.data = fetch(day, hour)
    except Exception:
        st.error("Backend not running or not reachable.")
        st.stop()

data = st.session_state.data
results = data["results"]
zone_map = {z["zone"]["id"]: z for z in results}
zone_list = list(zone_map.keys())

# ============================================================
# ===================== GOVT VIEW =============================
# ============================================================
if role == "Govt / BESCOM":

    st.subheader("City Overview")
    st.caption("Green = safe, orange = watch, red = stressed")

    # Summary metrics
    o = data.get("overview", {})
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Zones", o.get("zones", len(results)))
    m2.metric("High Load", o.get("high_load_zones", 0))
    m3.metric("Deferred", o.get("defer_zones", 0))
    m4.metric("Build Needed", o.get("build_zones", 0))
    m5.metric("Full Stations", o.get("full_stations", 0))
    m6.metric("Spillovers", o.get("spillover_flows", 0))

    st.divider()

    hottest = max(results, key=lambda r: (r["zone"]["load_ratio"], r["zone"]["score"])) if results else None
    if hottest:
        hz = hottest["zone"]
        if hz["status"] == "HIGH_LOAD":
            st.warning(f"Peak alert: Zone {hz['id']} is the current hotspot.")
        elif hz["status"] == "MEDIUM_LOAD":
            st.info(f"Early warning hotspot: Zone {hz['id']} may become stressed soon.")

    st.markdown("### Zone Heatmap")
    cols = st.columns(2)
    for i, zdata in enumerate(results):
        z = zdata["zone"]
        emoji, c = color(z["status"])
        with cols[i % 2]:
            st.markdown(
                f"""
                <div class="zone-card">
                    <div class="zone-title">{emoji} Zone {z['id']} ({z['type']})</div>
                    <span class="pill {c}">{z['status']}</span>
                    <span class="pill blue">Risk: {z['risk_level']}</span>
                    <span class="pill blue">Action: {z['recommended_action']}</span>
                    <div style="margin-top:0.55rem;">
                        Demand: <b>{z['demand']:.1f} kW</b><br>
                        Load Ratio: <b>{z['load_ratio']:.2f}</b><br>
                        Suggested Window: <b>{z['suggested_window']}</b>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill" style="width:{min(100, z['load_ratio']*100)}%; background:{'#f87171' if z['status']=='HIGH_LOAD' else '#fbbf24' if z['status']=='MEDIUM_LOAD' else '#4ade80'};"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    st.subheader("Zone Drill-down")
    selected_zone = st.selectbox(
        "Select zone",
        zone_list,
        format_func=lambda x: f"{x} — {zone_map[x]['zone']['type']}",
    )

    zdata = zone_map[selected_zone]
    z = zdata["zone"]
    stations = zdata.get("stations", [])
    emoji, c = color(z["status"])

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown(
            f"""
            <div class="glass-card">
                <div class="zone-title">{emoji} Zone {z['id']} ({z['type']})</div>
                <span class="pill {c}">{z['status']}</span>
                <span class="pill blue">Risk: {z['risk_level']}</span>
                <span class="pill blue">Action: {z['recommended_action']}</span>
                <div style="margin-top:0.75rem;">
                    Demand: <b>{z['demand']:.1f} kW</b><br>
                    Capacity: <b>{z['capacity']:.1f} kW</b><br>
                    Suggested Window: <b>{z['suggested_window']}</b><br>
                    Infrastructure: <b>{z['infrastructure_recommendation']}</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("#### What BESCOM should do")
        st.markdown(
            f"""
            <div class="info-card">
                <div class="info-label">Decision</div>
                <div class="info-value">{z['recommended_action']}</div>
            </div>
            <div style="height:10px"></div>
            <div class="info-card">
                <div class="info-label">Infrastructure planning</div>
                <div class="info-value">{z['infrastructure_recommendation']}</div>
            </div>
            <div style="height:10px"></div>
            <div class="info-card">
                <div class="info-label">Explanation</div>
                <div class="info-value" style="font-size:0.95rem; font-weight:700;">{zdata['explanation']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Stations in this zone")
    if stations:
        for s in stations:
            emo = "🔴" if s["status"] == "full" else "🟠" if s["status"] == "near_full" else "🟢"
            st.markdown(
                f"""
                <div class="station-box">
                    <b>{emo} {s['station_id']}</b><br>
                    Status: <b>{s['status']}</b><br>
                    Occupancy: <b>{s['occupancy']:.2f}</b><br>
                    Queue Risk: <b>{s.get('queue_risk', 0):.2f}</b><br>
                    Time to Full: <b>{s['time_to_full_minutes']} min</b><br>
                    Time to Free: <b>{s['time_to_free_minutes']} min</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if s.get("spillover"):
                st.markdown("#### Spillover")
                for sp in s["spillover"]:
                    icon = "🔴" if sp.get("target_status") == "full" else "🟠" if sp.get("target_status") == "near_full" else "🟢"
                    st.markdown(
                        f"""
                        <div class="spill-box">
                            <b>{sp['from_station']} → {icon} {sp['to_station']}</b><br>
                            To Zone: <b>{sp.get('to_zone', 'N/A')}</b><br>
                            Spillover: <b>{sp['spillover_kw']} kW</b><br>
                            Confidence: <b>{sp.get('confidence', 0)}</b><br>
                            Reason: {sp.get('reason', 'N/A')}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
    else:
        st.info("No stations found in this zone.")

    st.markdown("### Demand Graph")
    try:
        demand_hist = pd.read_csv("data/demand_timeseries.csv")
        if not demand_hist.empty and "zone_id" in demand_hist.columns:
            hist = demand_hist[demand_hist["zone_id"] == selected_zone].copy()
            if "hour" in hist.columns:
                dcol = None
                for col in ["actual_demand_kw", "predicted_demand_kw", "demand_kw", "baseline_demand_kw"]:
                    if col in hist.columns:
                        dcol = col
                        break
                if dcol:
                    st.line_chart(hist.sort_values("hour").set_index("hour")[[dcol]])
    except Exception:
        st.info("Demand history not available.")

# ============================================================
# ===================== USER VIEW =============================
# ============================================================
else:
    st.subheader("Find Charging")
    st.caption("Select your area to see station availability and simple charging advice.")

    selected_zone = st.selectbox(
        "Select your area",
        zone_list,
        format_func=lambda z: f"{z} — {zone_map[z]['zone']['type']}",
    )

    zdata = zone_map[selected_zone]
    z = zdata["zone"]
    stations = zdata.get("stations", [])

    emoji, c = color(z["status"])

    st.markdown(
        f"""
        <div class="glass-card">
            <div class="zone-title">{emoji} {z['id']} Area</div>
            <span class="pill {c}">{z['status']}</span>
            <div style="margin-top:0.65rem;">
                Recommendation: <b>{z['recommended_action']}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Advice")
    advice = user_advice(z["status"], z["recommended_action"], z["type"])
    if z["status"] == "HIGH_LOAD":
        st.error(advice)
    elif z["status"] == "MEDIUM_LOAD":
        st.warning(advice)
    else:
        st.success(advice)

    st.markdown("### Stations in your area")
    if stations:
        for s in stations:
            emo = "🔴" if s["status"] == "full" else "🟠" if s["status"] == "near_full" else "🟢"
            st.markdown(
                f"""
                <div class="station-box">
                    <b>{emo} {s['station_id']}</b><br>
                    Status: <b>{s['status']}</b><br>
                    Time to Free: <b>{s['time_to_free_minutes']} min</b>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No charging stations found in this area.")

    if z["recommended_action"] == "DEFER":
        st.error("Avoid charging now. Try later during off-peak hours.")
    elif z["recommended_action"] == "MONITOR":
        st.warning("Charging is possible, but there may be some waiting.")
    else:
        st.success("You can charge now without much waiting.")