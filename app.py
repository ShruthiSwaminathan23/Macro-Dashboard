import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import anthropic
import json

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Macro Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .exec-summary { background: #1e1e2e; border-radius: 12px; padding: 24px; border: 1px solid #374151; line-height: 1.7; }
    div[data-testid="stMetric"] { background: #1e1e2e; border-radius: 10px; padding: 12px; border-left: 4px solid #7c3aed; }
</style>
""", unsafe_allow_html=True)

# ── Countries ─────────────────────────────────────────────────────────────────
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

# ── FRED series IDs for all indicators ───────────────────────────────────────
# All sourced from FRED (St. Louis Fed) — single reliable API with your key
FRED_SERIES = {
    "UK": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQUK",   # Real GDP, rebased to growth below
        "Inflation (%)":       "GBRCPIALLMINMEI",
        "Unemployment (%)":    "UNRTGBR156NSTS",
        "Business Confidence": "BSCIUKM",
        "Consumer Confidence": "CSCIUKM",
    },
    "Germany": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQDEA",
        "Inflation (%)":       "DEUCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTDEM156S",
        "Business Confidence": "BSCIDEA",
        "Consumer Confidence": "CSCIDEM",
    },
    "Netherlands": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQNLA",
        "Inflation (%)":       "NLDCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTNEM156S",
        "Business Confidence": "BSCINLA",
        "Consumer Confidence": "CSCINLM",
    },
    "France": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQFRA",
        "Inflation (%)":       "FRACPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTFRM156S",
        "Business Confidence": "BSCIFRA",
        "Consumer Confidence": "CSCIFRM",
    },
    "Poland": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQPLA",
        "Inflation (%)":       "POLCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTPLM156S",
        "Business Confidence": "BSCIPLA",
        "Consumer Confidence": "CSCEPLM",
    },
    "Belgium": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQBEA",
        "Inflation (%)":       "BELCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTBEM156S",
        "Business Confidence": "BSCIBEA",
        "Consumer Confidence": "CSCIBEM",
    },
    "Australia": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQAUA",
        "Inflation (%)":       "AUSCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTAUM156S",
        "Business Confidence": "BSCIAUA",
        "Consumer Confidence": "CSCIAUA",
    },
    "New Zealand": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQNZA",
        "Inflation (%)":       "NZLCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTNZM156S",
        "Business Confidence": "BSCINZA",
        "Consumer Confidence": "CSCINZM",
    },
    "Mexico": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQMXA",
        "Inflation (%)":       "MEXCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTMXM156S",
        "Business Confidence": "BSCIMXA",
        "Consumer Confidence": "CSCIMXM",
    },
    "Denmark": {
        "GDP Growth (%)":      "CLVMNACSCAB1GQDKA",
        "Inflation (%)":       "DNKCPIALLMINMEI",
        "Unemployment (%)":    "LMUNRRTTDKM156S",
        "Business Confidence": "BSCIDKA",
        "Consumer Confidence": "CSCIDKM",
    },
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
def fetch_fred(series_id, fred_api_key, observation_start="2019-01-01", frequency="q"):
    if not fred_api_key or not series_id:
        return []
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": fred_api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "sort_order": "asc",
        "frequency": frequency,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json().get("observations", [])
        return [
            {"date": d["date"], "value": float(d["value"])}
            for d in data if d.get("value") not in (".", None, "")
        ]
    except Exception:
        return []


def pct_change_yoy(records):
    """Convert index levels to year-over-year % change."""
    if len(records) < 5:
        return records
    result = []
    for i in range(4, len(records)):
        curr = records[i]["value"]
        prev = records[i - 4]["value"]
        if prev and prev != 0:
            result.append({"date": records[i]["date"], "value": round((curr / prev - 1) * 100, 2)})
    return result


@st.cache_data(ttl=86400)
def build_country_data(fred_api_key=""):
    all_data = {}
    for country in COUNTRIES:
        series = FRED_SERIES.get(country, {})
        d = {}

        # GDP — quarterly index, convert to YoY growth
        gdp_raw = fetch_fred(series.get("GDP Growth (%)"), fred_api_key, frequency="q")
        gdp_growth = pct_change_yoy(gdp_raw)
        d["GDP Growth (%)"] = {"data": gdp_growth, "source": "FRED (OECD via St. Louis Fed)"}

        # Inflation — monthly CPI YoY
        cpi = fetch_fred(series.get("Inflation (%)"), fred_api_key, frequency="m")
        # FRED CPI is index level; compute YoY %
        cpi_yoy = []
        for i in range(12, len(cpi)):
            curr = cpi[i]["value"]
            prev = cpi[i - 12]["value"]
            if prev and prev != 0:
                cpi_yoy.append({"date": cpi[i]["date"], "value": round((curr / prev - 1) * 100, 2)})
        d["Inflation (%)"] = {"data": cpi_yoy[-36:] if cpi_yoy else [], "source": "FRED (OECD CPI)"}

        # Unemployment — monthly rate
        unemp = fetch_fred(series.get("Unemployment (%)"), fred_api_key, frequency="m")
        d["Unemployment (%)"] = {"data": unemp[-36:] if unemp else [], "source": "FRED (OECD)"}

        # Business & Consumer Confidence — monthly index
        bci = fetch_fred(series.get("Business Confidence"), fred_api_key, frequency="m")
        cci = fetch_fred(series.get("Consumer Confidence"), fred_api_key, frequency="m")
        d["Business Confidence"] = {"data": bci[-36:] if bci else [], "source": "FRED (OECD BCI)"}
        d["Consumer Confidence"] = {"data": cci[-36:] if cci else [], "source": "FRED (OECD CCI)"}

        all_data[country] = d
    return all_data

# ── Helpers ───────────────────────────────────────────────────────────────────

def latest(records):
    return records[-1]["value"] if records else None

def delta(records):
    if records and len(records) >= 2:
        return records[-1]["value"] - records[-2]["value"]
    return None

def fmt(val, decimals=2, suffix="%"):
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}{suffix}"

def dark_fig(fig):
    fig.update_layout(
        plot_bgcolor="#1e1e2e", paper_bgcolor="#1e1e2e", font_color="#e2e8f0",
        margin=dict(t=40, b=20, l=10, r=10), showlegend=False,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#374151")
    return fig

# ── AI Executive Summary ──────────────────────────────────────────────────────

def generate_exec_summary(all_data, country, anthropic_key):
    client = anthropic.Anthropic(api_key=anthropic_key)
    snapshot = {}
    for indicator, info in all_data.get(country, {}).items():
        snapshot[indicator] = {"latest": latest(info["data"]), "recent_change": delta(info["data"])}
    snapshot["Interest Rate (%)"] = INTEREST_RATES.get(country)

    prompt = f"""You are a senior macro analyst writing a concise executive briefing for a credit risk team.

Country: {country}
Data as of: {RATE_DATE}

Indicators:
{json.dumps(snapshot, indent=2)}

Write a 3-paragraph executive summary (max 250 words):
1. Overall economic health and direction
2. Key risks or concerns for a credit team
3. Notable positives or stabilising factors

Use the actual numbers. Plain English, no bullet points, no headers."""

    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Macro Dashboard")
    st.caption("Credit Risk | Monthly Macro Monitor")
    st.divider()

    selected_country = st.selectbox(
        "Select Country", list(COUNTRIES.keys()),
        format_func=lambda c: f"{COUNTRIES[c]['flag']} {c}",
    )

    st.divider()
    st.markdown("**🔑 API Keys**")
    fred_key = st.secrets.get("FRED_KEY", "") or st.text_input(
        "FRED API Key", type="password", help="Get free key at fred.stlouisfed.org"
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
- **FRED API** — All macro indicators (GDP, CPI, Unemployment, Confidence)
- **Central Banks** — Interest Rates (updated monthly)
- **Anthropic Claude** — AI Executive Summary

All economic data sourced via St. Louis Fed (FRED), which republishes OECD data.
    """)
    st.caption(f"Refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}")

# ── Load data ─────────────────────────────────────────────────────────────────
flag = COUNTRIES[selected_country]["flag"]
st.title(f"{flag} {selected_country} — Macro Dashboard")
st.caption(f"All data via FRED API (St. Louis Fed) · Interest rates as of {RATE_DATE}")

if not fred_key:
    st.warning("⚠️ FRED API key not found. Add it to your Streamlit secrets or enter it in the sidebar. Get a free key at fred.stlouisfed.org")
    st.stop()

with st.spinner("Fetching latest macro data from FRED..."):
    all_data = build_country_data(fred_key)

cdata = all_data.get(selected_country, {})

# ── KPI row ───────────────────────────────────────────────────────────────────
st.markdown("### Key Indicators")
cols = st.columns(4)
kpis = [
    ("GDP Growth (%)",   "GDP Growth (YoY)",  False),
    ("Inflation (%)",    "Inflation (YoY)",   True),
    ("Unemployment (%)", "Unemployment Rate", True),
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
            delta=f"{arrow} {fmt(abs(d) if d is not None else None)} vs prior" if d is not None else "N/A",
        )
with cols[3]:
    st.metric(label="Interest Rate", value=fmt(INTEREST_RATES.get(selected_country)), delta=f"as of {RATE_DATE}")

# ── Confidence ────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Business & Consumer Confidence")
st.caption("OECD Confidence Index via FRED — values above 100 = above-average confidence")

conf_cols = st.columns(2)
for i, key in enumerate(["Business Confidence", "Consumer Confidence"]):
    info    = cdata.get(key, {})
    records = info.get("data", [])
    with conf_cols[i]:
        if records:
            df  = pd.DataFrame(records)
            fig = px.line(df, x="date", y="value", title=key, color_discrete_sequence=["#7c3aed"],
                          labels={"date": "", "value": "Index"})
            fig.add_hline(y=100, line_dash="dash", line_color="#6b7280", annotation_text="Neutral (100)")
            st.plotly_chart(dark_fig(fig), use_container_width=True)
            st.caption(f"Source: {info.get('source', 'FRED')} · Latest: {records[-1]['date'][:7]}")
        else:
            st.info(f"No {key} data returned for {selected_country}. The FRED series may not exist for this country.")

# ── GDP & Inflation ───────────────────────────────────────────────────────────
st.divider()
st.markdown("### GDP Growth & Inflation")
trend_cols = st.columns(2)
for i, (key, color) in enumerate([("GDP Growth (%)", "#22c55e"), ("Inflation (%)", "#f59e0b")]):
    records = cdata.get(key, {}).get("data", [])
    with trend_cols[i]:
        if records:
            df  = pd.DataFrame(records)
            fig = px.line(df, x="date", y="value", title=key,
                          color_discrete_sequence=[color], labels={"date": "", "value": "%"})
            fig.add_hline(y=0, line_dash="dash", line_color="#6b7280")
            st.plotly_chart(dark_fig(fig), use_container_width=True)
            src = cdata.get(key, {}).get("source", "FRED")
            st.caption(f"Source: {src} · Latest: {records[-1]['date'][:7]}")
        else:
            st.info(f"No data available for {key}")

# ── Unemployment ──────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Unemployment Rate")
unemp_records = cdata.get("Unemployment (%)", {}).get("data", [])
if unemp_records:
    df_u = pd.DataFrame(unemp_records)
    fig_u = px.line(df_u, x="date", y="value", color_discrete_sequence=["#ef4444"],
                    labels={"date": "", "value": "Unemployment (%)"})
    fig_u.update_layout(height=300)
    st.plotly_chart(dark_fig(fig_u), use_container_width=True)
    st.caption(f"Source: {cdata.get('Unemployment (%)', {}).get('source', 'FRED')}")

# ── Cross-country snapshot ────────────────────────────────────────────────────
st.divider()
st.markdown("### Cross-Country Snapshot")
rows = []
for country, meta in COUNTRIES.items():
    cd  = all_data.get(country, {})
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
    st.info("Add your Anthropic API key in the sidebar to enable AI-generated executive summaries.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("""
**Data Sources:** All economic data via FRED (Federal Reserve Bank of St. Louis), which republishes OECD datasets.  
Interest rates sourced from central bank websites and updated manually each month.  
**Refresh cycle:** Data auto-refreshes every 24 hours.
""")
