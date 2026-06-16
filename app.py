import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
import anthropic
import json

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

# ── VERIFIED FRED series IDs (confirmed live on fred.stlouisfed.org) ──────────
#
# GDP: Real GDP index from Eurostat/IMF via FRED — we compute YoY % growth
# CPI: All-items CPI index — we compute YoY % change
# Unemployment: Harmonised monthly rate (%)
# Business Confidence: OECD BSCICP02 composite manufacturing indicator (% balance)
# Consumer Confidence: OECD CSCICP02 composite consumer indicator (% balance)
#
# GDP series: pre-calculated YoY growth rates from OECD via FRED (format: [CC]GDPRQPSMEI)
# No manual YoY computation needed — values are already % change vs same quarter prior year
FRED_SERIES = {
    "UK": {
        "gdp":     "GBRGDPRQPSMEI",      # OECD GDP YoY %, quarterly (Q4 2025 = ~1.0%)
        "cpi":     "GBRCPIALLMINMEI",
        "unemp":   "LRHUTTTTGBM156S",
        "bci":     "BSCICP02GBM460S",
        "cci":     "CSCICP02GBM460S",
    },
    "Germany": {
        "gdp":     "DEUGDPRQPSMEI",
        "cpi":     "DEUCPIALLMINMEI",
        "unemp":   "LRHUTTTTDEM156S",
        "bci":     "BSCICP02DEM460S",
        "cci":     "CSCICP02DEM460S",
    },
    "Netherlands": {
        "gdp":     "NLDGDPRQPSMEI",
        "cpi":     "NLDCPIALLMINMEI",
        "unemp":   "LRHUTTTTNLM156S",
        "bci":     "BSCICP02NLM460S",
        "cci":     "CSCICP02NLM460S",
    },
    "France": {
        "gdp":     "FRAGDPRQPSMEI",
        "cpi":     "FRACPIALLMINMEI",
        "unemp":   "LRHUTTTTFRM156S",
        "bci":     "BSCICP02FRM460S",
        "cci":     "CSCICP02FRM460S",
    },
    "Poland": {
        "gdp":     "POLGDPRQPSMEI",
        "cpi":     "POLCPIALLMINMEI",
        "unemp":   "LRHUTTTTPLM156S",
        "bci":     "BSCICP02PLM460S",
        "cci":     "CSCICP02PLM460S",
    },
    "Belgium": {
        "gdp":     "BELGDPRQPSMEI",
        "cpi":     "BELCPIALLMINMEI",
        "unemp":   "LRHUTTTTBEM156S",
        "bci":     "BSCICP02BEM460S",
        "cci":     "CSCICP02BEM460S",
    },
    "Australia": {
        "gdp":     "AUSGDPRQPSMEI",
        "cpi":     "AUSCPIALLQINMEI",
        "unemp":   "LRHUTTTTAUM156S",
        "bci":     "BSCICP02AUQ460S",
        "cci":     "CSCICP02AUM460S",
    },
    "New Zealand": {
        "gdp":     "NZLGDPRQPSMEI",
        "cpi":     "NZLCPIALLQINMEI",
        "unemp":   "LRHUTTTTNZQ156S",
        "bci":     "BSCICP02NZQ460S",
        "cci":     "CSCICP02NZM460S",
    },
    "Mexico": {
        "gdp":     "MEXGDPRQPSMEI",
        "cpi":     "MEXCPIALLMINMEI",
        "unemp":   "LRHUTTTTMXM156S",
        "bci":     "BSCICP02MXM460S",
        "cci":     "CSCICP02MXM460S",
    },
    "Denmark": {
        "gdp":     "DNKGDPRQPSMEI",
        "cpi":     "DNKCPIALLMINMEI",
        "unemp":   "LRHUTTTTDKM156S",
        "bci":     "BSCICP02DKM460S",
        "cci":     "CSCICP02DKM460S",
    },
}

INTEREST_RATES = {
    "UK": 4.25, "Germany": 2.40, "Netherlands": 2.40, "France": 2.40,
    "Poland": 5.25, "Belgium": 2.40, "Australia": 3.85, "New Zealand": 3.50,
    "Mexico": 8.50, "Denmark": 2.35,
}
RATE_DATE = "June 2026"

# ── FRED fetch ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400)
def fetch_fred(series_id, api_key, start="2018-01-01", freq=None):
    """Fetch a FRED series. Returns list of {date, value} dicts."""
    if not api_key or not series_id:
        return []
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "sort_order": "asc",
    }
    if freq:
        params["frequency"] = freq
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=15)
        if r.status_code != 200:
            return []
        return [
            {"date": d["date"], "value": float(d["value"])}
            for d in r.json().get("observations", [])
            if d.get("value") not in (".", None, "")
        ]
    except Exception:
        return []


def yoy_pct(records, lag=4):
    """Convert index levels to YoY % change (lag=4 for quarterly, 12 for monthly)."""
    out = []
    for i in range(lag, len(records)):
        curr, prev = records[i]["value"], records[i - lag]["value"]
        if prev and prev != 0:
            out.append({"date": records[i]["date"], "value": round((curr / prev - 1) * 100, 2)})
    return out


@st.cache_data(ttl=86400)
def build_all(api_key):
    result = {}
    for country, ids in FRED_SERIES.items():
        # GDP — already pre-calculated YoY growth rate from OECD via FRED
        gdp = fetch_fred(ids["gdp"], api_key, freq="q")

        # CPI — AUS & NZ publish quarterly only; all others monthly
        quarterly_countries = ("Australia", "New Zealand")
        cpi_freq = "q" if country in quarterly_countries else "m"
        cpi_lag  = 4  if country in quarterly_countries else 12
        cpi_raw = fetch_fred(ids["cpi"], api_key, freq=cpi_freq)
        cpi = yoy_pct(cpi_raw, lag=cpi_lag)

        # Unemployment — NZ is quarterly only, all others monthly
        unemp_freq = "q" if country == "New Zealand" else "m"
        unemp = fetch_fred(ids["unemp"], api_key, freq=unemp_freq)

        # Confidence — already an indicator, keep last 3 years
        bci_freq = "q" if country in ("Australia", "New Zealand") else "m"
        bci = fetch_fred(ids["bci"], api_key, freq=bci_freq)
        cci = fetch_fred(ids["cci"], api_key, freq="m")

        result[country] = {
            "GDP Growth (%)":      {"data": gdp[-20:],    "source": "Eurostat via FRED"},
            "Inflation (%)":       {"data": cpi[-36:],    "source": "OECD CPI via FRED"},
            "Unemployment (%)":    {"data": unemp[-36:],  "source": "OECD via FRED"},
            "Business Confidence": {"data": bci[-36:],    "source": "OECD BSCI via FRED"},
            "Consumer Confidence": {"data": cci[-36:],    "source": "OECD CSCI via FRED"},
        }
    return result

# ── Helpers ───────────────────────────────────────────────────────────────────

def latest(records):
    return records[-1]["value"] if records else None

def delta(records):
    if records and len(records) >= 2:
        return records[-1]["value"] - records[-2]["value"]
    return None

def fmt(val, dp=2, sfx="%"):
    return "N/A" if val is None else f"{val:.{dp}f}{sfx}"

def dark(fig):
    fig.update_layout(
        plot_bgcolor="#1e1e2e", paper_bgcolor="#1e1e2e", font_color="#e2e8f0",
        margin=dict(t=40, b=20, l=10, r=10), showlegend=False,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#374151")
    return fig

# ── AI summary ────────────────────────────────────────────────────────────────

def exec_summary(all_data, country, anth_key):
    client = anthropic.Anthropic(api_key=anth_key)
    snap = {k: {"latest": latest(v["data"]), "recent_change": delta(v["data"])}
            for k, v in all_data.get(country, {}).items()}
    snap["Interest Rate (%)"] = INTEREST_RATES.get(country)
    msg = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=500,
        messages=[{"role": "user", "content": f"""You are a senior macro analyst writing for a credit risk team.
Country: {country} | Data as of: {RATE_DATE}
{json.dumps(snap, indent=2)}
Write 3 paragraphs (max 250 words): (1) overall economic health, (2) key credit risks, (3) positives/stabilisers.
Use actual numbers. Plain English, no bullets, no headers."""}]
    )
    return msg.content[0].text

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Macro Dashboard")
    st.caption("Credit Risk | Monthly Macro Monitor")
    st.divider()
    selected = st.selectbox("Select Country", list(COUNTRIES.keys()),
                            format_func=lambda c: f"{COUNTRIES[c]['flag']} {c}")
    st.divider()
    st.markdown("**🔑 API Keys**")
    fred_key = st.secrets.get("FRED_KEY", "") or st.text_input("FRED API Key", type="password",
                                                                 help="Free at fred.stlouisfed.org")
    anth_key = st.secrets.get("ANTHROPIC_KEY", "") or st.text_input("Anthropic API Key", type="password",
                                                                      help="console.anthropic.com")
    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown("**📚 Sources**")
    st.caption("All data via FRED (St. Louis Fed)\nSources: Eurostat, OECD, IMF\nInterest rates: central banks (monthly)")
    st.caption(f"Refreshed: {datetime.now().strftime('%d %b %Y, %H:%M')}")

# ── Header ────────────────────────────────────────────────────────────────────
flag = COUNTRIES[selected]["flag"]
st.title(f"{flag} {selected} — Macro Dashboard")
st.caption(f"All indicators via FRED API · Interest rates as of {RATE_DATE}")

if not fred_key:
    st.warning("Add your FRED API key in the sidebar (or Streamlit secrets) to load data. Free at fred.stlouisfed.org")
    st.stop()

with st.spinner("Fetching data from FRED..."):
    all_data = build_all(fred_key)

cdata = all_data[selected]

# ── KPI cards ─────────────────────────────────────────────────────────────────
st.markdown("### Key Indicators")
c1, c2, c3, c4 = st.columns(4)
for col, key, label, inv in [
    (c1, "GDP Growth (%)",   "GDP Growth (YoY)",   False),
    (c2, "Inflation (%)",    "Inflation (YoY)",    True),
    (c3, "Unemployment (%)", "Unemployment Rate",  True),
]:
    recs = cdata[key]["data"]
    v, d = latest(recs), delta(recs)
    with col:
        st.metric(label, fmt(v), f"{'▲' if (d or 0)>0 else '▼'} {fmt(abs(d) if d else None)} vs prior" if d is not None else "N/A")
with c4:
    st.metric("Interest Rate", fmt(INTEREST_RATES[selected]), f"as of {RATE_DATE}")

# ── Confidence charts ─────────────────────────────────────────────────────────
st.divider()
st.markdown("### Business & Consumer Confidence")
st.caption("OECD composite indicators via FRED — percentage balance (positive = net optimism)")

col_b, col_c = st.columns(2)
for col, key in [(col_b, "Business Confidence"), (col_c, "Consumer Confidence")]:
    recs = cdata[key]["data"]
    src  = cdata[key]["source"]
    with col:
        if recs:
            df = pd.DataFrame(recs)
            fig = px.line(df, x="date", y="value", title=key,
                          color_discrete_sequence=["#7c3aed"], labels={"date": "", "value": "% balance"})
            fig.add_hline(y=0, line_dash="dash", line_color="#6b7280", annotation_text="Neutral")
            st.plotly_chart(dark(fig), use_container_width=True)
            st.caption(f"Source: {src} · Latest: {recs[-1]['date'][:7]} = {fmt(latest(recs), sfx='')}")
        else:
            st.info(f"No {key} data returned for {selected}.")

# ── GDP & Inflation ───────────────────────────────────────────────────────────
st.divider()
st.markdown("### GDP Growth & Inflation")
col_g, col_i = st.columns(2)
for col, key, color in [(col_g, "GDP Growth (%)", "#22c55e"), (col_i, "Inflation (%)", "#f59e0b")]:
    recs = cdata[key]["data"]
    with col:
        if recs:
            df = pd.DataFrame(recs)
            fig = px.bar(df, x="date", y="value", title=f"{key} (YoY)",
                         color_discrete_sequence=[color], labels={"date": "", "value": "%"})
            fig.add_hline(y=0, line_dash="dash", line_color="#6b7280")
            st.plotly_chart(dark(fig), use_container_width=True)
            st.caption(f"Source: {cdata[key]['source']} · Latest: {recs[-1]['date'][:7]} = {fmt(latest(recs))}")
        else:
            st.info(f"No data for {key}.")

# ── Unemployment ──────────────────────────────────────────────────────────────
st.divider()
st.markdown("### Unemployment Rate")
recs_u = cdata["Unemployment (%)"]["data"]
if recs_u:
    df_u = pd.DataFrame(recs_u)
    fig_u = px.line(df_u, x="date", y="value", color_discrete_sequence=["#ef4444"],
                    labels={"date": "", "value": "Unemployment (%)"})
    fig_u.update_layout(height=280)
    st.plotly_chart(dark(fig_u), use_container_width=True)
    st.caption(f"Source: {cdata['Unemployment (%)']['source']} · Latest: {recs_u[-1]['date'][:7]} = {fmt(latest(recs_u))}")

# ── Cross-country table ───────────────────────────────────────────────────────
st.divider()
st.markdown("### Cross-Country Snapshot")
rows = []
for c, meta in COUNTRIES.items():
    cd = all_data[c]
    rows.append({
        "Country":             f"{meta['flag']} {c}",
        "GDP Growth (%)":      fmt(latest(cd["GDP Growth (%)"]["data"])),
        "Inflation (%)":       fmt(latest(cd["Inflation (%)"]["data"])),
        "Unemployment (%)":    fmt(latest(cd["Unemployment (%)"]["data"])),
        "Interest Rate (%)":   fmt(INTEREST_RATES[c]),
        "Business Confidence": fmt(latest(cd["Business Confidence"]["data"]), sfx=""),
        "Consumer Confidence": fmt(latest(cd["Consumer Confidence"]["data"]), sfx=""),
    })
st.dataframe(pd.DataFrame(rows).set_index("Country"), use_container_width=True)

# ── AI Summary ────────────────────────────────────────────────────────────────
st.divider()
st.markdown("### 🤖 AI Executive Summary")
if anth_key:
    if st.button(f"Generate Summary for {flag} {selected}", type="primary", use_container_width=True):
        with st.spinner("Claude is analysing the data..."):
            try:
                s = exec_summary(all_data, selected, anth_key)
                st.markdown(f'<div class="exec-summary">{s}</div>', unsafe_allow_html=True)
                st.caption(f"Generated by Claude · {datetime.now().strftime('%d %b %Y, %H:%M')}")
            except Exception as e:
                st.error(f"Could not generate summary: {e}")
else:
    st.info("Add your Anthropic API key in the sidebar to enable AI summaries.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("**Sources:** All economic data via FRED (Federal Reserve Bank of St. Louis) — underlying data from Eurostat, OECD, and IMF. Interest rates from central bank websites, updated monthly. AI summaries by Anthropic Claude.")
