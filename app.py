import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import anthropic
import json

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .exec-summary { background: #1e1e2e; border-radius: 12px; padding: 24px; border: 1px solid #374151; line-height: 1.7; }
    div[data-testid="stMetric"] { background: #1e1e2e; border-radius: 10px; padding: 12px; border-left: 4px solid #7c3aed; }
</style>
""", unsafe_allow_html=True)

# ── Countries ─────────────────────────────────────────────────────────────────
COUNTRIES = {
    "UK":          {"world_bank": "GB", "oecd": "GBR", "flag": "🇬🇧"},
    "Germany":     {"world_bank": "DE", "oecd": "DEU", "flag": "🇩🇪"},
    "Netherlands": {"world_bank": "NL", "oecd": "NLD", "flag": "🇳🇱"},
    "France":      {"world_bank": "FR", "oecd": "FRA", "flag": "🇫🇷"},
    "Poland":      {"world_bank": "PL", "oecd": "POL", "flag": "🇵🇱"},
    "Belgium":     {"world_bank": "BE", "oecd": "BEL", "flag": "🇧🇪"},
    "Australia":   {"world_bank": "AU", "oecd": "AUS", "flag": "🇦🇺"},
    "New Zealand": {"world_bank": "NZ", "oecd": "NZL", "flag": "🇳🇿"},
    "Mexico":      {"world_bank": "MX", "oecd": "MEX", "flag": "🇲🇽"},
    "Denmark":     {"world_bank": "DK", "oecd": "DNK", "flag": "🇩🇰"},
}

# FRED series IDs for confidence indicators (primary source)
# These are the official OECD BCI/CCI series republished on FRED — much more reliable
FRED_CONFIDENCE = {
    "UK":          {"Business Confidence": "BSCIUKM",  "Consumer Confidence": "CSCIUKM"},
    "Germany":     {"Business Confidence": "BSCIDEA",  "Consumer Confidence": "CSCIDEM"},
    "France":      {"Business Confidence": "BSCIFRA",  "Consumer Confidence": "CSCIFRM"},
    "Australia":   {"Business Confidence": "BSCIAUA",  "Consumer Confidence": "CSCIAUA"},
    "Mexico":      {"Business Confidence": "BSCIMXA",  "Consumer Confidence": "CSCIMXM"},
    "Netherlands": {"Business Confidence": "BSCINLA",  "Consumer Confidence": "CSCINLM"},
    "Poland":      {"Business Confidence": "BSCIPLA",  "Consumer Confidence": "CSCEPLM"},
    "Belgium":     {"Business Confidence": "BSCIBEA",  "Consumer Confidence": "CSCIBEM"},
    "New Zealand": {"Business Confidence": "BSCINZA",  "Consumer Confidence": "CSCINZM"},
    "Denmark":     {"Business Confidence": "BSCIDKA",  "Consumer Confidence": "CSCIDKM"},
}

# Interest rates — updated manually each month
INTEREST_RATES = {
    "UK": 4.25, "Germany": 2.40, "Netherlands": 2.40, "France": 2.40,
    "Poland": 5.25, "Belgium": 2.40, "Australia": 3.85, "New Zealand": 3.50,
    "Mexico": 8.50, "Denmark": 2.35,
}
RATE_DATE = "June 2026"

# ── Data fetching ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def fetch_world_bank(indicator_code, country_code, years=6):
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
def fetch_fred(series_id, fred_api_key, observation_start="2020-01-01"):
    """Fetch monthly series from FRED."""
    if not fred_api_key or not series_id:
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": fred_api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "frequency": "m",
        "sort_order": "asc",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json().get("observations", [])
        return [
            {"date": d["date"], "value": float(d["value"])}
            for d in data if d["value"] not in (".", None)
        ]
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_oecd_confidence(oecd_code, indicator="BSCI"):
    """
    Fallback: pull BCI or CCI from OECD's newer data-explorer API.
    indicator: BSCI (business) or CSCI (consumer)
    """
    url = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
    try:
        path = f"/{oecd_code}.{indicator}.AA.LTRENDIDX/all"
        r = requests.get(
            url + path,
            headers={"Accept": "application/vnd.sdmx.data+json;version=2"},
            params={"startPeriod": "2020-01", "dimensionAtObservation": "TIME_PERIOD"},
            timeout=15,
        )
        if r.status_code == 200:
            j = r.json()
            obs = j["data"]["dataSets"][0]["observations"]
            periods = j["data"]["structures"][0]["dimensions"]["observation"][0]["values"]
            records = []
            for k, v in obs.items():
                idx = int(k)
                if idx < len(periods) and v[0] is not None:
                    records.append({"date": periods[idx]["id"], "value": v[0]})
            return sorted(records, key=lambda x: x["date"])
    except Exception:
        pass
    return []


def fetch_confidence(country, indicator_key, fred_api_key):
    """
    Try FRED first (most reliable). Fall back to OECD API.
    indicator_key: 'Business Confidence' or 'Consumer Confidence'
    """
    fred_id = FRED_CONFIDENCE.get(country, {}).get(indicator_key)
    records = fetch_fred(fred_id, fred_api_key) if fred_id else []

    if not records:
        oecd_code = COUNTRIES[country]["oecd"]
        oecd_ind = "BSCI" if "Business" in indicator_key else "CSCI"
        records = fetch_oecd_confidence(oecd_code, oecd_ind)
        source = "OECD"
    else:
        source = "FRED (OECD series)"

    return records, source


# ── Build all country data ────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def build_country_data(fred_api_key=""):
    all_data = {}
    for country, meta in COUNTRIES.items():
        wb = meta["world_bank"]
        d = {}
        d["GDP Growth (%)"]   = {"data": fetch_world_bank("NY.GDP.MKTP.KD.ZG", wb), "source": "World Bank"}
        d["Inflation (%)"]    = {"data": fetch_world_bank("FP.CPI.TOTL.ZG", wb),    "source": "World Bank"}
        d["Unemployment (%)"] = {"data": fetch_world_bank("SL.UEM.TOTL.ZS", wb),    "source": "World Bank"}

        bci_records, bci_source = fetch_confidence(country, "Business Confidence", fred_api_key)
        cci_records, cci_source = fetch_confidence(country, "Consumer Confidence", fred_api_key)
        d["Business Confidence"] = {"data": bci_records, "source": bci_source}
        d["Consumer Confidence"] = {"data": cci_records, "source": cci_source}

        all_data[country] = d
    return all_data

# ── Helpers ───────────────────────────────────────────────────────────────────

def latest(records, key="value"):
    return records[-1][key] if records else None

def delta(records, key="value"):
    if records and len(records) >= 2:
        return records[-1][key] - records[-2][key]
    return None

def fmt(val, decimals=2, suffix="%"):
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}{suffix}"

# ── AI Executive Summary ──────────────────────────────────────────────────────

def generate_exec_summary(all_data, country, anthropic_key):
    client = anthropic.Anthropic(api_key=anthropic_key)
    snapshot = {}
    for indicator, info in all_data.get(country, {}).items():
        snapshot[indicator] = {
            "latest": latest(info["data"]),
            "change_vs_prior": delta(info["data"]),
        }
    snapshot["Interest Rate (%)"] = INTEREST_RATES.get(country)

    prompt = f"""You are a senior macro analyst writing a concise executive briefing for a credit risk team.

Country: {country}
Data as of: {RATE_DATE}

Indicators:
{json.dumps(snapshot, indent=2)}

Write a 3-paragraph executive summary (max 250 words total):
1. Overall economic health and direction
2. Key risks or concerns for a credit team
3. Notable positives or stabilising factors

Be specific and data-driven — use the actual numbers. Plain English, no bullet points, no headers."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

# ── Chart helper ──────────────────────────────────────────────────────────────

def dark_line(df, x, y, title, color="#7c3aed", hline=None):
    fig = px.line(df, x=x, y=y, title=title, color_discrete_sequence=[color])
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dash", line_color="#6b7280", annotation_text="Neutral")
    fig.update_layout(
        plot_bgcolor="#1e1e2e", paper_bgcolor="#1e1e2e", font_color="#e2e8f0",
        margin=dict(t=40, b=20, l=10, r=10), showlegend=False,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#374151")
    return fig

def dark_bar(df, x, y, title, color="#22c55e"):
    fig = px.bar(df, x=x, y=y, title=title, color_discrete_sequence=[color])
    fig.update_layout(
        plot_bgcolor="#1e1e2e", paper_bgcolor="#1e1e2e", font_color="#e2e8f0",
        margin=dict(t=40, b=20, l=10, r=10), showlegend=False,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#374151")
    return fig

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Macro Dashboard")
    st.caption("Credit Risk | Monthly Macro Monitor")
    st.divider()

    selected_country = st.selectbox(
        "Select Country",
        list(COUNTRIES.keys()),
        format_func=lambda c: f"{COUNTRIES[c]['flag']} {c}",
    )

    st.divider()
    st.markdown("**🔑 API Keys**")
    fred_key = st.secrets.get("FRED_KEY", "") or st.text_input(
        "FRED API Key (optional)", type="password", help="Get free key at fred.stlouisfed.org"
    )
    anthropic_key = st.secrets.get("ANTHROPIC_KEY", "") or st.text_input(
        "Anthropic API Key", type="password", help="Get key at console.anthropic.com"
    )

    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**📚 Sources**")
    st.caption("""
- **World Bank API** — GDP, Inflation, Unemployment
- **FRED API** — Business & Consumer Confidence (primary)
- **OECD API** — Confidence fallback where FRED unavailable
- **Central Banks** — Interest Rates (updated monthly)
- **Anthropic Claude** — AI Executive Summary
    """)
    st.caption(f"Refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}")

# ── Load data ─────────────────────────────────────────────────────────────────
flag = COUNTRIES[selected_country]["flag"]
st.title(f"{flag} {selected_country} — Macro Dashboard")
st.caption(f"Auto-fetched from World Bank, FRED & OECD APIs · Interest rates as of {RATE_DATE}")

with st.spinner("Fetching latest macro data..."):
    all_data = build_country_data(fred_key)

cdata = all_data.get(selected_country, {})

# ── KPI row ───────────────────────────────────────────────────────────────────
st.markdown("### Key Indicators")
cols = st.columns(4)
kpis = [
    ("GDP Growth (%)",   "GDP Growth",   False),
    ("Inflation (%)",    "Inflation",    True),
    ("Unemployment (%)", "Unemployment", True),
]
for i, (key, label, invert) in enumerate(kpis):
    records = cdata.get(key, {}).get("data", [])
    val = latest(records)
    d   = delta(records)
    with cols[i]:
        arrow = "▲" if (d or 0) > 0 else "▼"
        st.metric(
            label=label,
            value=fmt(val),
            delta=f"{arrow} {fmt(abs(d) if d else None)} vs prior" if d is not None else "N/A",
        )
with cols[3]:
    st.metric(label="Interest Rate", value=fmt(INTEREST_RATES.get(selected_country)), delta=f"as of {RATE_DATE}")

# ── Confidence indicators ─────────────────────────────────────────────────────
st.divider()
st.markdown("### Business & Consumer Confidence")

if not fred_key:
    st.warning("Add your FRED API key in the sidebar to load confidence data — it's free at fred.stlouisfed.org")

conf_cols = st.columns(2)
for i, key in enumerate(["Business Confidence", "Consumer Confidence"]):
    info    = cdata.get(key, {})
    records = info.get("data", [])
    source  = info.get("source", "")
    with conf_cols[i]:
        if records:
            df  = pd.DataFrame(records)
            x_col = "date" if "date" in df.columns else "period"
            fig = dark_line(df, x_col, "value", key, hline=100 if source != "OECD" else None)
            st.plotly_chart(fig, use_container_width=True)
            latest_period = records[-1].get("date", records[-1].get("period", ""))
            st.caption(f"Source: {source} · Latest: {latest_period}")
        else:
            st.info(f"No {key} data available for {selected_country}. "
                    f"{'Add your FRED API key above.' if not fred_key else 'Data may not be published for this country.'}")

# ── GDP & Inflation ───────────────────────────────────────────────────────────
st.divider()
st.markdown("### GDP Growth & Inflation Trends")
trend_cols = st.columns(2)
for i, (key, color) in enumerate([("GDP Growth (%)", "#22c55e"), ("Inflation (%)", "#f59e0b")]):
    records = cdata.get(key, {}).get("data", [])
    with trend_cols[i]:
        if records:
            df = pd.DataFrame(records)
            st.plotly_chart(dark_bar(df, "year", "value", key, color), use_container_width=True)
            st.caption(f"Source: World Bank · Latest: {records[-1]['year']}")
        else:
            st.info(f"No data available for {key}")

# ── Unemployment ──────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Unemployment Rate")
unemp_records = cdata.get("Unemployment (%)", {}).get("data", [])
if unemp_records:
    df_u = pd.DataFrame(unemp_records)
    fig_u = dark_line(df_u, "year", "value", "Unemployment (%)", color="#ef4444")
    fig_u.update_layout(height=300)
    st.plotly_chart(fig_u, use_container_width=True)
    st.caption("Source: World Bank")

# ── Cross-country snapshot ────────────────────────────────────────────────────
st.divider()
st.markdown("### Cross-Country Snapshot")
rows = []
for country, meta in COUNTRIES.items():
    cd = all_data.get(country, {})
    bci = cd.get("Business Confidence", {}).get("data", [])
    cci = cd.get("Consumer Confidence", {}).get("data", [])
    rows.append({
        "Country":             f"{meta['flag']} {country}",
        "GDP Growth (%)":      fmt(latest(cd.get("GDP Growth (%)", {}).get("data", []))),
        "Inflation (%)":       fmt(latest(cd.get("Inflation (%)", {}).get("data", []))),
        "Unemployment (%)":    fmt(latest(cd.get("Unemployment (%)", {}).get("data", []))),
        "Interest Rate (%)":   fmt(INTEREST_RATES.get(country)),
        "Business Confidence": fmt(latest(bci), suffix="") if bci else "N/A",
        "Consumer Confidence": fmt(latest(cci), suffix="") if cci else "N/A",
    })
df_comp = pd.DataFrame(rows).set_index("Country")
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
**Data Sources:** World Bank Open Data API · FRED (St. Louis Fed) · OECD API · Central Bank websites · Anthropic Claude  
**Refresh cycle:** Data auto-refreshes every 24 hours · Interest rates updated manually each month  
**Confidence index:** OECD Business/Consumer Confidence Index — values above 100 indicate above-average confidence
""")
