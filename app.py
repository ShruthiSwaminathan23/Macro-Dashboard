import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import anthropic
import json

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Macro Risk Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# DESIGN SYSTEM
# Palette: deep navy base, slate surfaces, indigo accent, RAG signals
# Signature: RAG glow on KPI cards — risk readable before numbers are read
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

/* ── Base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0a0f1e; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: #0d1226;
    border-right: 1px solid #1e2d4a;
}
section[data-testid="stSidebar"] * { color: #94a3b8 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] strong { color: #e2e8f0 !important; }
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label { color: #64748b !important; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }

/* ── Page header ── */
.page-header {
    padding: 28px 0 20px 0;
    border-bottom: 1px solid #1e2d4a;
    margin-bottom: 28px;
}
.page-header .country-name {
    font-size: 32px;
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -0.5px;
    line-height: 1.1;
}
.page-header .subtitle {
    font-size: 13px;
    color: #475569;
    margin-top: 4px;
    font-family: 'DM Mono', monospace;
}

/* ── Section labels ── */
.section-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #334155;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1e2d4a;
}

/* ── KPI cards ── */
.kpi-card {
    background: #111827;
    border-radius: 10px;
    padding: 18px 20px;
    border: 1px solid #1e2d4a;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 10px 10px 0 0;
}
.kpi-card.green::before  { background: linear-gradient(90deg, #10b981, #34d399); }
.kpi-card.amber::before  { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.kpi-card.red::before    { background: linear-gradient(90deg, #ef4444, #f87171); }
.kpi-card.neutral::before { background: linear-gradient(90deg, #4f6272, #64748b); }

.kpi-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #475569;
    margin-bottom: 8px;
}
.kpi-value {
    font-family: 'DM Mono', monospace;
    font-size: 28px;
    font-weight: 500;
    color: #f1f5f9;
    line-height: 1;
    margin-bottom: 6px;
}
.kpi-delta {
    font-size: 12px;
    color: #475569;
}
.kpi-delta.pos { color: #10b981; }
.kpi-delta.neg { color: #ef4444; }

/* ── Info box ── */
.info-box {
    background: #111827;
    border: 1px solid #1e2d4a;
    border-left: 3px solid #3b82f6;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 13px;
    color: #64748b;
    line-height: 1.6;
}

/* ── Methodology note ── */
.methodology {
    background: #0d1226;
    border: 1px solid #1e2d4a;
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 12px;
    color: #475569;
    line-height: 1.7;
    margin-bottom: 16px;
}
.methodology strong { color: #64748b; }

/* ── AI summary box ── */
.exec-summary {
    background: #111827;
    border: 1px solid #1e2d4a;
    border-radius: 10px;
    padding: 28px 32px;
    font-size: 14px;
    line-height: 1.85;
    color: #cbd5e1;
}
.exec-summary-header {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #4f46e5;
    margin-bottom: 16px;
}

/* ── Data table ── */
.stDataFrame { border-radius: 10px; overflow: hidden; }
.stDataFrame thead th {
    background: #111827 !important;
    color: #475569 !important;
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Streamlit overrides ── */
div[data-testid="stMetric"] { display: none; }
hr { border-color: #1e2d4a !important; }
.stButton button {
    background: #4f46e5 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 13px !important;
    letter-spacing: 0.02em !important;
    padding: 10px 20px !important;
    transition: background 0.2s !important;
}
.stButton button:hover { background: #4338ca !important; }
.stAlert { border-radius: 8px !important; }

/* ── Spinner ── */
.stSpinner { color: #4f46e5 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA CONFIG
# ─────────────────────────────────────────────────────────────────────────────
COUNTRIES = {
    "UK":          {"flag": "🇬🇧"},
    "Germany":     {"flag": "🇩🇪"},
    "Netherlands": {"flag": "🇳🇱"},
    "France":      {"flag": "🇫🇷"},
    "Poland":      {"flag": "🇵🇱"},
    "Belgium":     {"flag": "🇧🇪"},
    "Australia":   {"flag": "🇦🇺"},
    "New Zealand": {"flag": "🇳🇿"},
    "Mexico":      {"flag": "🇲🇽"},
    "Denmark":     {"flag": "🇩🇰"},
}

FRED_SERIES = {
    "UK":          {"gdp": "GBRGDPRQPSMEI",  "cpi": "GBRCPIALLMINMEI",  "unemp": "LRHUTTTTGBM156S", "bci": "BSCICP02GBM460S", "cci": "CSCICP02GBM460S"},
    "Germany":     {"gdp": "DEUGDPRQPSMEI",  "cpi": "DEUCPIALLMINMEI",  "unemp": "LRHUTTTTDEM156S", "bci": "BSCICP02DEM460S", "cci": "CSCICP02DEM460S"},
    "Netherlands": {"gdp": "NLDGDPRQPSMEI",  "cpi": "NLDCPIALLMINMEI",  "unemp": "LRHUTTTTNLM156S", "bci": "BSCICP02NLM460S", "cci": "CSCICP02NLM460S"},
    "France":      {"gdp": "FRAGDPRQPSMEI",  "cpi": "FRACPIALLMINMEI",  "unemp": "LRHUTTTTFRM156S", "bci": "BSCICP02FRM460S", "cci": "CSCICP02FRM460S"},
    "Poland":      {"gdp": "POLGDPRQPSMEI",  "cpi": "POLCPIALLMINMEI",  "unemp": "LRHUTTTTPLM156S", "bci": "BSCICP02PLM460S", "cci": "CSCICP02PLM460S"},
    "Belgium":     {"gdp": "BELGDPRQPSMEI",  "cpi": "BELCPIALLMINMEI",  "unemp": "LRHUTTTTBEM156S", "bci": "BSCICP02BEM460S", "cci": "CSCICP02BEM460S"},
    "Australia":   {"gdp": "AUSGDPRQPSMEI",  "cpi": "AUSCPIALLQINMEI",  "unemp": "LRHUTTTTAUM156S", "bci": "BSCICP02AUQ460S", "cci": "CSCICP02AUM460S"},
    "New Zealand": {"gdp": "NZLGDPRQPSMEI",  "cpi": "NZLCPIALLQINMEI",  "unemp": "LRHUTTTTNZQ156S", "bci": "BSCICP02NZQ460S", "cci": None},
    "Mexico":      {"gdp": "MEXGDPRQPSMEI",  "cpi": "MEXCPIALLMINMEI",  "unemp": "LRHUTTTTMXM156S", "bci": "BSCICP02MXM460S", "cci": "CSCICP02MXM460S"},
    "Denmark":     {"gdp": "DNKGDPRQPSMEI",  "cpi": "DNKCPIALLMINMEI",  "unemp": "LRHUTTTTDKM156S", "bci": "BSCICP02DKM460S", "cci": "CSCICP02DKM460S"},
}

INTEREST_RATES = {
    "UK": 4.25, "Germany": 2.40, "Netherlands": 2.40, "France": 2.40,
    "Poland": 5.25, "Belgium": 2.40, "Australia": 3.85, "New Zealand": 3.50,
    "Mexico": 8.50, "Denmark": 2.35,
}
RATE_DATE = "June 2026"

EUROSTAT_CODES = {
    "UK": None, "Germany": "DE", "Netherlands": "NL", "France": "FR",
    "Poland": "PL", "Belgium": "BE", "Denmark": "DK",
    "Australia": None, "New Zealand": None, "Mexico": None,
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def fetch_fred(series_id, api_key, start="2018-01-01", freq=None):
    if not api_key or not series_id:
        return []
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json",
              "observation_start": start, "sort_order": "asc"}
    if freq:
        params["frequency"] = freq
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=15)
        if r.status_code != 200:
            return []
        return [{"date": d["date"], "value": float(d["value"])}
                for d in r.json().get("observations", [])
                if d.get("value") not in (".", None, "")]
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_eurostat_bankruptcy(geo_code, sinceTimePeriod="2019-Q1"):
    if not geo_code:
        return []
    param_sets = [
        {"indic_bt": "BKRT", "nace_r2": "TOTAL", "s_adj": "SCA", "unit": "I15"},
        {"indic_bt": "BKRT", "nace_r2": "TOTAL", "s_adj": "NSA", "unit": "I15"},
        {"indic_bt": "BKRT", "nace_r2": "B-E",   "s_adj": "NSA", "unit": "I15"},
    ]
    base = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_rb_q"
    for params in param_sets:
        try:
            query = (f"{base}?format=JSON&lang=en&indic_bt={params['indic_bt']}"
                     f"&nace_r2={params['nace_r2']}&s_adj={params['s_adj']}"
                     f"&unit={params['unit']}&geo={geo_code}&sinceTimePeriod={sinceTimePeriod}")
            r = requests.get(query, timeout=15)
            if r.status_code != 200:
                continue
            j = r.json()
            dims, values, ids, sizes = j.get("dimension", {}), j.get("value", {}), j.get("id", []), j.get("size", [])
            if not ids or not sizes or not values:
                continue
            strides = [1] * len(sizes)
            for i in range(len(sizes) - 2, -1, -1):
                strides[i] = strides[i+1] * sizes[i+1]
            fixed_positions = {}
            for dim_name, stride in zip(ids, strides):
                cat_index = dims.get(dim_name, {}).get("category", {}).get("index", {})
                if len(cat_index) == 1:
                    fixed_positions[dim_name] = 0
            time_dim_name = ids[-1] if ids[-1] == "time" else next((n for n in ids if n == "time"), None)
            if time_dim_name is None:
                continue
            time_index = dims[time_dim_name]["category"]["index"]
            time_stride = strides[ids.index(time_dim_name)]
            base_offset = sum(fixed_positions.get(d, 0) * s for d, s in zip(ids, strides) if d != time_dim_name)
            records = []
            for period, t_pos in time_index.items():
                val = values.get(str(base_offset + t_pos * time_stride))
                if val is not None:
                    records.append({"date": period, "value": round(float(val), 1)})
            if records:
                return sorted(records, key=lambda x: x["date"])
        except Exception:
            continue
    return []


def yoy_pct(records, lag=4):
    out = []
    for i in range(lag, len(records)):
        curr, prev = records[i]["value"], records[i-lag]["value"]
        if prev and prev != 0:
            out.append({"date": records[i]["date"], "value": round((curr/prev - 1)*100, 2)})
    return out


@st.cache_data(ttl=86400)
def build_all(api_key):
    result = {}
    for country, ids in FRED_SERIES.items():
        gdp = fetch_fred(ids["gdp"], api_key, freq="q")
        qt  = ("Australia", "New Zealand")
        cpi_raw = fetch_fred(ids["cpi"], api_key, freq="q" if country in qt else "m")
        cpi = yoy_pct(cpi_raw, lag=4 if country in qt else 12)
        unemp = fetch_fred(ids["unemp"], api_key, freq="q" if country == "New Zealand" else "m")
        bci = fetch_fred(ids["bci"], api_key, freq="q" if country in qt else "m")
        cci = fetch_fred(ids["cci"], api_key, freq="m")
        bkr = fetch_eurostat_bankruptcy(EUROSTAT_CODES.get(country))
        result[country] = {
            "GDP Growth (%)":      {"data": gdp[-20:],   "source": "OECD via FRED"},
            "Inflation (%)":       {"data": cpi[-36:],   "source": "OECD CPI via FRED"},
            "Unemployment (%)":    {"data": unemp[-36:], "source": "OECD via FRED"},
            "Business Confidence": {"data": bci[-36:],   "source": "OECD BSCI via FRED"},
            "Consumer Confidence": {"data": cci[-36:],   "source": "OECD CSCI via FRED"},
            "Bankruptcy Index":    {"data": bkr[-20:],   "source": "Eurostat (sts_rb_q)"},
        }
    return result

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def latest(records):
    return records[-1]["value"] if records else None

def delta(records):
    if records and len(records) >= 2:
        return records[-1]["value"] - records[-2]["value"]
    return None

def fmt(val, dp=2, sfx="%"):
    return "N/A" if val is None else f"{val:.{dp}f}{sfx}"

def rag(val, key):
    """Return green/amber/red/neutral based on indicator thresholds."""
    if val is None:
        return "neutral"
    if key == "GDP Growth (%)":
        return "green" if val >= 1.5 else "amber" if val >= 0 else "red"
    if key == "Inflation (%)":
        return "green" if 1.5 <= val <= 3.0 else "amber" if val <= 5.0 else "red"
    if key == "Unemployment (%)":
        return "green" if val <= 5.0 else "amber" if val <= 8.0 else "red"
    if key == "Interest Rate":
        return "neutral"
    return "neutral"

def chart(df, x, y, color, title="", hline=None, hline_label="", kind="line", height=280):
    if kind == "line":
        fig = px.line(df, x=x, y=y, color_discrete_sequence=[color])
    else:
        fig = px.bar(df, x=x, y=y, color_discrete_sequence=[color])
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dot", line_color="#334155",
                      annotation_text=hline_label, annotation_font_color="#475569",
                      annotation_font_size=11)
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#64748b", family="Inter"), x=0),
        plot_bgcolor="#111827", paper_bgcolor="#111827",
        font=dict(color="#475569", family="Inter", size=11),
        margin=dict(t=36, b=16, l=4, r=4),
        showlegend=False, height=height,
        xaxis=dict(showgrid=False, showline=False, tickfont=dict(size=10, color="#334155")),
        yaxis=dict(gridcolor="#1e2d4a", showline=False, tickfont=dict(size=10, color="#334155")),
    )
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>%{y:.2f}<extra></extra>",
    )
    if kind == "line":
        fig.update_traces(line_width=2)
    return fig

def kpi_card(label, value, d, key, suffix="%"):
    signal = rag(latest([{"value": float(value.replace("%","").replace("N/A","0"))}]) if value != "N/A" else None, key)
    delta_class = ""
    delta_html  = ""
    if d is not None:
        arrow = "▲" if d > 0 else "▼"
        delta_class = "pos" if d > 0 else "neg"
        delta_html  = f'<div class="kpi-delta {delta_class}">{arrow} {abs(d):.2f}{suffix} vs prior</div>'
    return f"""
    <div class="kpi-card {signal}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>"""

# ─────────────────────────────────────────────────────────────────────────────
# AI SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def exec_summary(all_data, country, anth_key):
    client = anthropic.Anthropic(api_key=anth_key)
    snap = {k: {"latest": latest(v["data"]), "recent_change": delta(v["data"])}
            for k, v in all_data.get(country, {}).items()}
    snap["Interest Rate (%)"] = INTEREST_RATES.get(country)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=500,
        messages=[{"role": "user", "content":
            f"You are a senior macro analyst writing for a credit risk team.\n"
            f"Country: {country} | Data as of: {RATE_DATE}\n{json.dumps(snap, indent=2)}\n"
            f"Write 3 paragraphs (max 250 words): (1) overall economic health, "
            f"(2) key credit risks, (3) positives/stabilisers. "
            f"Use actual numbers. Plain English, no bullets, no headers."}]
    )
    return msg.content[0].text

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Macro Risk Monitor")
    st.markdown('<div style="font-size:11px;color:#334155;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:20px;">Credit Risk · Monthly</div>', unsafe_allow_html=True)

    selected = st.selectbox(
        "COUNTRY",
        list(COUNTRIES.keys()),
        format_func=lambda c: f"{COUNTRIES[c]['flag']}  {c}",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="font-size:10px;color:#334155;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;">API Keys</div>', unsafe_allow_html=True)
    fred_key = st.secrets.get("FRED_KEY", "") or st.text_input("FRED Key", type="password", help="fred.stlouisfed.org — free")
    anth_key = st.secrets.get("ANTHROPIC_KEY", "") or st.text_input("Anthropic Key", type="password", help="console.anthropic.com")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("↺  Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="font-size:10px;color:#1e2d4a;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;">Sources</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:11px;color:#334155;line-height:1.9;">
    FRED (St. Louis Fed)<br>
    OECD · Eurostat · IMF<br>
    Central banks (rates)<br>
    Anthropic Claude (AI)<br>
    <br>
    <span style="color:#1e3a5f;">Updated: {datetime.now().strftime('%d %b %Y %H:%M')}</span>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
flag = COUNTRIES[selected]["flag"]

# Header
st.markdown(f"""
<div class="page-header">
    <div class="country-name">{flag} &nbsp;{selected}</div>
    <div class="subtitle">MACRO RISK MONITOR &nbsp;·&nbsp; DATA AS OF {RATE_DATE.upper()} &nbsp;·&nbsp; FRED + OECD + EUROSTAT</div>
</div>
""", unsafe_allow_html=True)

if not fred_key:
    st.warning("Enter your FRED API key in the sidebar to load data. Get one free at fred.stlouisfed.org.")
    st.stop()

with st.spinner("Pulling latest data..."):
    all_data = build_all(fred_key)

cdata = all_data[selected]

# ── KPI row ──────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Key Indicators</div>', unsafe_allow_html=True)

kpi_cols = st.columns(4)
kpis = [
    ("GDP Growth (%)",   "GDP Growth",        False),
    ("Inflation (%)",    "Inflation (YoY)",   True),
    ("Unemployment (%)", "Unemployment",      True),
]
for col, (key, label, _inv) in zip(kpi_cols[:3], kpis):
    recs = cdata[key]["data"]
    v, d = latest(recs), delta(recs)
    with col:
        st.markdown(kpi_card(label, fmt(v), d, key), unsafe_allow_html=True)

with kpi_cols[3]:
    rate = INTEREST_RATES[selected]
    st.markdown(f"""
    <div class="kpi-card neutral">
        <div class="kpi-label">Interest Rate</div>
        <div class="kpi-value">{fmt(rate)}</div>
        <div class="kpi-delta">Central bank · {RATE_DATE}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Confidence ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Sentiment Indicators</div>', unsafe_allow_html=True)
st.markdown("""
<div class="methodology">
    <strong>How these are calculated:</strong> Monthly surveys of firms (Business) and households (Consumer) asking whether conditions are improving, stable, or deteriorating.
    Result is a <strong>percentage balance</strong> — share of positive responses minus share of negative responses.
    <strong>Above 0 = net optimism · Below 0 = net pessimism · Source: OECD via FRED</strong>
</div>
""", unsafe_allow_html=True)

col_b, col_c = st.columns(2)
for col, key, color in [(col_b, "Business Confidence", "#6366f1"), (col_c, "Consumer Confidence", "#8b5cf6")]:
    recs = cdata[key]["data"]
    with col:
        if recs:
            df = pd.DataFrame(recs)
            fig = chart(df, "date", "value", color, title=key, hline=0, hline_label="Neutral")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown(f'<div style="font-size:11px;color:#334155;margin-top:-8px;">Latest: <strong style="color:#64748b;">{recs[-1]["date"][:7]}</strong> &nbsp;=&nbsp; <strong style="color:#94a3b8;">{fmt(latest(recs), sfx="")}</strong></div>', unsafe_allow_html=True)
        else:
            if selected == "New Zealand" and key == "Consumer Confidence":
                st.markdown('<div class="info-box">Consumer Confidence not published for New Zealand — the OECD does not produce a composite CCI for this country.</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="info-box">No {key} data available for {selected}.</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── GDP & Inflation ───────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Growth & Prices</div>', unsafe_allow_html=True)
col_g, col_i = st.columns(2)

for col, key, color, kind in [
    (col_g, "GDP Growth (%)",  "#10b981", "bar"),
    (col_i, "Inflation (%)",   "#f59e0b", "bar"),
]:
    recs = cdata[key]["data"]
    with col:
        if recs:
            df = pd.DataFrame(recs)
            fig = chart(df, "date", "value", color, title=f"{key} — Year on Year", hline=0, kind=kind)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown(f'<div style="font-size:11px;color:#334155;margin-top:-8px;">Latest: <strong style="color:#64748b;">{recs[-1]["date"][:7]}</strong> &nbsp;=&nbsp; <strong style="color:#94a3b8;">{fmt(latest(recs))}</strong> &nbsp;·&nbsp; {cdata[key]["source"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="info-box">No data available for {key}.</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Unemployment ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Labour Market</div>', unsafe_allow_html=True)
recs_u = cdata["Unemployment (%)"]["data"]
if recs_u:
    df_u = pd.DataFrame(recs_u)
    fig_u = chart(df_u, "date", "value", "#ef4444", title="Unemployment Rate (%)", height=260)
    st.plotly_chart(fig_u, use_container_width=True, config={"displayModeBar": False})
    st.markdown(f'<div style="font-size:11px;color:#334155;margin-top:-8px;">Latest: <strong style="color:#64748b;">{recs_u[-1]["date"][:7]}</strong> &nbsp;=&nbsp; <strong style="color:#94a3b8;">{fmt(latest(recs_u))}</strong> &nbsp;·&nbsp; {cdata["Unemployment (%)"]["source"]}</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Bankruptcy ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Bankruptcy Declarations</div>', unsafe_allow_html=True)
geo = EUROSTAT_CODES.get(selected)
if geo is None:
    uk_note = " The UK stopped reporting to Eurostat after Brexit." if selected == "UK" else ""
    st.markdown(f'<div class="info-box">Bankruptcy data not available for {selected}.{uk_note} Eurostat coverage: Germany, France, Netherlands, Belgium, Poland, Denmark only.</div>', unsafe_allow_html=True)
else:
    bkr = cdata.get("Bankruptcy Index", {}).get("data", [])
    if bkr:
        df_bkr = pd.DataFrame(bkr)
        fig_bkr = chart(df_bkr, "date", "value", "#f97316", title="Bankruptcy Index (2015 = 100)",
                        hline=100, hline_label="2015 baseline", height=260)
        st.plotly_chart(fig_bkr, use_container_width=True, config={"displayModeBar": False})
        latest_bkr = bkr[-1]
        direction = "above" if latest_bkr["value"] > 100 else "below"
        st.markdown(f'<div style="font-size:11px;color:#334155;margin-top:-8px;">Latest: <strong style="color:#64748b;">{latest_bkr["date"]}</strong> &nbsp;=&nbsp; <strong style="color:#94a3b8;">{latest_bkr["value"]:.0f}</strong> &nbsp;({direction} 2015 baseline) &nbsp;·&nbsp; Values above 100 = more bankruptcies than 2015 average · Source: Eurostat</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="info-box">Bankruptcy data not yet returned from Eurostat for this country.</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Cross-country table ───────────────────────────────────────────────────────
st.markdown('<div class="section-label">Cross-Country Snapshot</div>', unsafe_allow_html=True)
rows = []
for c, meta in COUNTRIES.items():
    cd = all_data[c]
    rows.append({
        "":                    f"{meta['flag']} {c}",
        "GDP Growth":          fmt(latest(cd["GDP Growth (%)"]["data"])),
        "Inflation":           fmt(latest(cd["Inflation (%)"]["data"])),
        "Unemployment":        fmt(latest(cd["Unemployment (%)"]["data"])),
        "Rate":                fmt(INTEREST_RATES[c]),
        "Business Conf.":      fmt(latest(cd["Business Confidence"]["data"]), sfx=""),
        "Consumer Conf.":      fmt(latest(cd["Consumer Confidence"]["data"]), sfx=""),
        "Bankruptcy Idx":      fmt(latest(cd.get("Bankruptcy Index", {}).get("data", [])), dp=0, sfx="") if EUROSTAT_CODES.get(c) else "—",
    })
df_comp = pd.DataFrame(rows).set_index("")
st.dataframe(df_comp, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── AI Summary ────────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">AI Executive Summary</div>', unsafe_allow_html=True)
if anth_key:
    if st.button(f"Generate briefing — {flag} {selected}", use_container_width=False):
        with st.spinner("Analysing..."):
            try:
                s = exec_summary(all_data, selected, anth_key)
                st.markdown(f"""
                <div class="exec-summary">
                    <div class="exec-summary-header">Claude · Credit Risk Briefing · {datetime.now().strftime('%d %b %Y %H:%M')}</div>
                    {s}
                </div>""", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not generate summary: {e}")
else:
    st.markdown('<div class="info-box">Add your Anthropic API key in the sidebar to generate AI credit risk briefings.</div>', unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("""
<div style="border-top: 1px solid #1e2d4a; padding-top: 20px; font-size: 11px; color: #1e3a5f; line-height: 2;">
<strong style="color:#334155;">Sources:</strong> Economic data via FRED (Federal Reserve Bank of St. Louis) — Eurostat, OECD, IMF.
Bankruptcy data via Eurostat API (sts_rb_q). Interest rates from central bank websites, updated monthly.
AI summaries by Anthropic Claude.<br>
<strong style="color:#334155;">Coverage note:</strong> Bankruptcy data available for EU countries only (DE, FR, NL, BE, PL, DK).
UK excluded post-Brexit. Australia, New Zealand, Mexico not covered by Eurostat.
Consumer Confidence not published by OECD for New Zealand.
</div>
""", unsafe_allow_html=True)
