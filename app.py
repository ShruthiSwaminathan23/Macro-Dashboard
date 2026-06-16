import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
import anthropic
import json

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 16px;
        margin: 4px 0;
        border-left: 4px solid #7c3aed;
    }
    .metric-label { color: #a0a0b0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { color: #ffffff; font-size: 24px; font-weight: 700; margin: 4px 0; }
    .metric-delta-pos { color: #22c55e; font-size: 13px; }
    .metric-delta-neg { color: #ef4444; font-size: 13px; }
    .section-header { font-size: 18px; font-weight: 600; color: #e2e8f0; margin: 20px 0 10px 0; }
    .source-tag { font-size: 11px; color: #6b7280; margin-top: 4px; }
    .exec-summary { background: #1e1e2e; border-radius: 12px; padding: 24px; border: 1px solid #374151; }
    div[data-testid="stMetric"] { background: #1e1e2e; border-radius: 10px; padding: 12px; border-left: 4px solid #7c3aed; }
</style>
""", unsafe_allow_html=True)

# ── Countries & indicators ────────────────────────────────────────────────────
COUNTRIES = {
    "UK": {"world_bank": "GB", "oecd": "GBR", "flag": "🇬🇧"},
    "Germany": {"world_bank": "DE", "oecd": "DEU", "flag": "🇩🇪"},
    "Netherlands": {"world_bank": "NL", "oecd": "NLD", "flag": "🇳🇱"},
    "France": {"world_bank": "FR", "oecd": "FRA", "flag": "🇫🇷"},
    "Poland": {"world_bank": "PL", "oecd": "POL", "flag": "🇵🇱"},
    "Belgium": {"world_bank": "BE", "oecd": "BEL", "flag": "🇧🇪"},
    "Australia": {"world_bank": "AU", "oecd": "AUS", "flag": "🇦🇺"},
    "New Zealand": {"world_bank": "NZ", "oecd": "NZL", "flag": "🇳🇿"},
    "Mexico": {"world_bank": "MX", "oecd": "MEX", "flag": "🇲🇽"},
    "Denmark": {"world_bank": "DK", "oecd": "DNK", "flag": "🇩🇰"},
}

# ── Data fetching ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)  # Cache for 24 hours
def fetch_world_bank(indicator_code, country_code, years=5):
    """Fetch data from World Bank API."""
    url = f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}"
    params = {"format": "json", "mrv": years, "per_page": 10}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if len(data) > 1 and data[1]:
            records = [
                {"year": int(d["date"]), "value": d["value"]}
                for d in data[1] if d["value"] is not None
            ]
            return sorted(records, key=lambda x: x["year"])
    except Exception:
        pass
    return []

@st.cache_data(ttl=86400)
def fetch_oecd(dataset, subject, country_code, measure="PC_CHNG"):
    """Fetch data from OECD API."""
    url = f"https://stats.oecd.org/SDMX-JSON/data/{dataset}/{subject}.{country_code}.{measure}/all"
    params = {"startTime": "2020", "endTime": "2025", "dimensionAtObservation": "TimeDimension"}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            j = r.json()
            obs = j.get("dataSets", [{}])[0].get("observations", {})
            time_periods = list(j.get("structure", {}).get("dimensions", {}).get("observation", [{}])[0].get("values", []))
            records = []
            for k, v in obs.items():
                idx = int(k)
                if idx < len(time_periods) and v[0] is not None:
                    records.append({"period": time_periods[idx]["id"], "value": v[0]})
            return sorted(records, key=lambda x: x["period"])
    except Exception:
        pass
    return []

@st.cache_data(ttl=86400)
def fetch_fred(series_id, fred_api_key, observation_start="2020-01-01"):
    """Fetch data from FRED API."""
    if not fred_api_key:
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": fred_api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "frequency": "m",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json().get("observations", [])
        return [{"date": d["date"], "value": float(d["value"])} for d in data if d["value"] != "."]
    except Exception:
        return []

# World Bank indicator codes
WB_INDICATORS = {
    "GDP Growth (%)": "NY.GDP.MKTP.KD.ZG",
    "Inflation (%)": "FP.CPI.TOTL.ZG",
    "Unemployment (%)": "SL.UEM.TOTL.ZS",
}

# ── Build country data ────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def build_country_data(fred_api_key=""):
    """Fetch all data for all countries."""
    all_data = {}
    for country, meta in COUNTRIES.items():
        wb_code = meta["world_bank"]
        country_data = {}

        # GDP Growth
        gdp = fetch_world_bank("NY.GDP.MKTP.KD.ZG", wb_code)
        country_data["GDP Growth (%)"] = {"data": gdp, "source": "World Bank"}

        # Inflation
        inf = fetch_world_bank("FP.CPI.TOTL.ZG", wb_code)
        country_data["Inflation (%)"] = {"data": inf, "source": "World Bank"}

        # Unemployment
        unemp = fetch_world_bank("SL.UEM.TOTL.ZS", wb_code)
        country_data["Unemployment (%)"] = {"data": unemp, "source": "World Bank"}

        # Business Confidence (OECD)
        bci = fetch_oecd("MEI_BTS_COS", "BSCI", meta["oecd"], "BLSA")
        country_data["Business Confidence"] = {"data": bci, "source": "OECD"}

        # Consumer Confidence (OECD)
        cci = fetch_oecd("MEI_BTS_COS", "CSCI", meta["oecd"], "BLSA")
        country_data["Consumer Confidence"] = {"data": cci, "source": "OECD"}

        all_data[country] = country_data

    return all_data

# ── Interest rates (static fallback with note) ─────────────────────────────
INTEREST_RATES = {
    "UK": 4.25, "Germany": 2.40, "Netherlands": 2.40, "France": 2.40,
    "Poland": 5.25, "Belgium": 2.40, "Australia": 3.85, "New Zealand": 3.50,
    "Mexico": 8.50, "Denmark": 2.35,
}
RATE_DATE = "June 2026"

# ── Helper: latest value ──────────────────────────────────────────────────────
def latest(records, value_key="value"):
    if records:
        return records[-1][value_key]
    return None

def delta(records, value_key="value"):
    if records and len(records) >= 2:
        return records[-1][value_key] - records[-2][value_key]
    return None

def fmt(val, decimals=2, suffix="%"):
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}{suffix}"

def delta_color(d, invert=False):
    if d is None:
        return ""
    if invert:
        return "metric-delta-pos" if d < 0 else "metric-delta-neg"
    return "metric-delta-pos" if d > 0 else "metric-delta-neg"

# ── AI Executive Summary ──────────────────────────────────────────────────────
def generate_exec_summary(country_data, selected_country, anthropic_key):
    """Call Claude API to generate executive summary."""
    client = anthropic.Anthropic(api_key=anthropic_key)

    # Build data snapshot for the prompt
    snapshot = {}
    cdata = country_data.get(selected_country, {})
    for indicator, info in cdata.items():
        val = latest(info["data"])
        d = delta(info["data"])
        snapshot[indicator] = {"latest": val, "change": d}

    snapshot["Interest Rate (%)"] = INTEREST_RATES.get(selected_country)

    prompt = f"""You are a senior macro analyst writing a concise executive briefing for a credit risk team.

Country: {selected_country}
Data as of: {RATE_DATE}

Indicators:
{json.dumps(snapshot, indent=2)}

Write a 3-paragraph executive summary (max 250 words total):
1. Overall economic health and direction
2. Key risks or concerns for credit teams
3. Notable positives or stabilising factors

Be specific, data-driven, and use the actual numbers. Write in plain English — no bullet points, no headers."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Macro Dashboard")
    st.caption("Credit Risk | Monthly Macro Monitor")
    st.divider()

    selected_country = st.selectbox(
        "Select Country",
        list(COUNTRIES.keys()),
        format_func=lambda c: f"{COUNTRIES[c]['flag']} {c}"
    )

    st.divider()
    st.markdown("**🔑 API Keys**")
    fred_key = st.secrets.get("FRED_KEY", "") or st.text_input(
        "FRED API Key (optional)", type="password",
        help="Get free key at fred.stlouisfed.org"
    )
    anthropic_key = st.secrets.get("ANTHROPIC_KEY", "") or st.text_input(
        "Anthropic API Key", type="password",
        help="Get key at console.anthropic.com"
    )

    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**📚 Sources**")
    st.caption("""
- **World Bank API** — GDP, Inflation, Unemployment
- **OECD API** — Business & Consumer Confidence
- **Central Banks** — Interest Rates (manual, updated monthly)
- **AI Summary** — Anthropic Claude
    """)
    st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}")

# ── Main content ──────────────────────────────────────────────────────────────
flag = COUNTRIES[selected_country]["flag"]
st.title(f"{flag} {selected_country} — Macro Dashboard")
st.caption(f"Data sourced automatically from World Bank & OECD APIs · Interest rates as of {RATE_DATE}")

# Load data
with st.spinner("Fetching latest macro data..."):
    all_data = build_country_data(fred_key)

cdata = all_data.get(selected_country, {})

# ── KPI row ───────────────────────────────────────────────────────────────────
st.markdown("### Key Indicators")
cols = st.columns(4)

indicators_kpi = [
    ("GDP Growth (%)", "GDP Growth", False),
    ("Inflation (%)", "Inflation", True),
    ("Unemployment (%)", "Unemployment", True),
]

for i, (key, label, invert) in enumerate(indicators_kpi):
    info = cdata.get(key, {})
    records = info.get("data", [])
    val = latest(records)
    d = delta(records)
    with cols[i]:
        arrow = "▲" if (d or 0) > 0 else "▼"
        delta_cls = delta_color(d, invert)
        st.metric(
            label=label,
            value=fmt(val),
            delta=f"{arrow} {fmt(abs(d) if d else None)} vs prior yr" if d else "N/A"
        )

with cols[3]:
    rate = INTEREST_RATES.get(selected_country)
    st.metric(label="Interest Rate", value=fmt(rate), delta=f"as of {RATE_DATE}")

# ── Confidence indicators ─────────────────────────────────────────────────────
st.divider()
st.markdown("### Business & Consumer Confidence")
conf_cols = st.columns(2)

for i, key in enumerate(["Business Confidence", "Consumer Confidence"]):
    info = cdata.get(key, {})
    records = info.get("data", [])
    with conf_cols[i]:
        if records:
            df = pd.DataFrame(records)
            fig = px.line(
                df, x="period", y="value",
                title=key,
                labels={"period": "", "value": "Index (balance of opinion)"},
                color_discrete_sequence=["#7c3aed"]
            )
            fig.add_hline(y=0, line_dash="dash", line_color="#6b7280", annotation_text="Neutral")
            fig.update_layout(
                plot_bgcolor="#1e1e2e",
                paper_bgcolor="#1e1e2e",
                font_color="#e2e8f0",
                margin=dict(t=40, b=20, l=20, r=20),
                showlegend=False,
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(gridcolor="#374151")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Source: OECD · Latest: {records[-1]['period'] if records else 'N/A'}")
        else:
            st.info(f"No {key} data available for {selected_country}")

# ── GDP & Inflation trends ────────────────────────────────────────────────────
st.divider()
st.markdown("### GDP Growth & Inflation Trends")
trend_cols = st.columns(2)

for i, key in enumerate(["GDP Growth (%)", "Inflation (%)"]):
    info = cdata.get(key, {})
    records = info.get("data", [])
    with trend_cols[i]:
        if records:
            df = pd.DataFrame(records)
            color = "#22c55e" if key == "GDP Growth (%)" else "#f59e0b"
            fig = px.bar(
                df, x="year", y="value",
                title=key,
                labels={"year": "", "value": "%"},
                color_discrete_sequence=[color]
            )
            fig.update_layout(
                plot_bgcolor="#1e1e2e",
                paper_bgcolor="#1e1e2e",
                font_color="#e2e8f0",
                margin=dict(t=40, b=20, l=20, r=20),
                showlegend=False,
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(gridcolor="#374151")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Source: World Bank · Latest: {records[-1]['year']}")
        else:
            st.info(f"No data available for {key}")

# ── Unemployment trend ────────────────────────────────────────────────────────
st.divider()
st.markdown("### Unemployment Rate")
unemp_info = cdata.get("Unemployment (%)", {})
unemp_records = unemp_info.get("data", [])
if unemp_records:
    df_u = pd.DataFrame(unemp_records)
    fig_u = px.line(
        df_u, x="year", y="value",
        labels={"year": "", "value": "Unemployment (%)"},
        color_discrete_sequence=["#ef4444"]
    )
    fig_u.update_layout(
        plot_bgcolor="#1e1e2e",
        paper_bgcolor="#1e1e2e",
        font_color="#e2e8f0",
        margin=dict(t=20, b=20, l=20, r=20),
        showlegend=False,
        height=300,
    )
    fig_u.update_xaxes(showgrid=False)
    fig_u.update_yaxes(gridcolor="#374151")
    st.plotly_chart(fig_u, use_container_width=True)
    st.caption("Source: World Bank")

# ── Cross-country comparison ───────────────────────────────────────────────────
st.divider()
st.markdown("### Cross-Country Snapshot")

comparison_rows = []
for country, meta in COUNTRIES.items():
    cdata_c = all_data.get(country, {})
    row = {
        "Country": f"{meta['flag']} {country}",
        "GDP Growth (%)": fmt(latest(cdata_c.get("GDP Growth (%)", {}).get("data", []))),
        "Inflation (%)": fmt(latest(cdata_c.get("Inflation (%)", {}).get("data", []))),
        "Unemployment (%)": fmt(latest(cdata_c.get("Unemployment (%)", {}).get("data", []))),
        "Interest Rate (%)": fmt(INTEREST_RATES.get(country)),
    }
    comparison_rows.append(row)

df_comp = pd.DataFrame(comparison_rows).set_index("Country")
st.dataframe(df_comp, use_container_width=True)

# ── AI Executive Summary ──────────────────────────────────────────────────────
st.divider()
st.markdown("### 🤖 AI Executive Summary")

if anthropic_key:
    if st.button(f"Generate Summary for {flag} {selected_country}", type="primary", use_container_width=True):
        with st.spinner("Claude is analysing the data..."):
            try:
                summary = generate_exec_summary(all_data, selected_country, anthropic_key)
                st.markdown(f'<div class="exec-summary">{summary}</div>', unsafe_allow_html=True)
                st.caption(f"Generated by Claude (Anthropic) · {datetime.now().strftime('%d %b %Y, %H:%M')}")
            except Exception as e:
                st.error(f"Could not generate summary: {e}")
else:
    st.info("Enter your Anthropic API key in the sidebar to enable AI-generated executive summaries.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("""
**Data Sources:** World Bank Open Data API · OECD.Stat API · Central Bank websites (interest rates) · Anthropic Claude API (executive summaries)  
**Refresh cycle:** Economic data updates automatically every 24 hours · Interest rates updated manually monthly  
**Notes:** GDP & inflation figures reflect latest available annual data. Confidence indices are balance-of-opinion scores (positive = net optimism).
""")
