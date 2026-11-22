from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from scanner import OHLC, completed, evaluate, indicators, validate

IST = ZoneInfo("Asia/Kolkata")
UNIVERSE = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
INDEX = "^NSEI"

st.set_page_config(page_title="Swing Radar v2.0", page_icon="📡", layout="wide")
motion = st.sidebar.toggle("Scanner animations", value=True)
recent = st.sidebar.number_input("Triggered history · sessions", 1, 120, 20)


def download(tickers):
    return yf.download(tickers, period="1y", interval="1d", auto_adjust=False,
                       group_by="ticker", multi_level_index=True, threads=4,
                       progress=False, timeout=15)


@st.cache_data(ttl=3600, show_spinner=False)
def universe():
    response = requests.get(UNIVERSE, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    symbols = pd.read_csv(StringIO(response.text))["Symbol"].dropna().str.strip().unique()
    if len(symbols) < 500 or not all(symbols):
        raise ValueError(f"Unexpected constituent list: {len(symbols)} symbols")
    return sorted(f"{symbol}.NS" for symbol in symbols)


def health():
    now = datetime.now(IST)
    raw = validate(download([INDEX])[INDEX])
    bars = completed(raw, now)
    if bars.empty:
        raise ValueError("No completed index bars")
    return now, raw, bars


def scan(progress):
    now, index_raw, index_bars = health()
    symbols = universe()
    sessions = index_bars.index
    pending = index_raw.index[index_raw.index > sessions[-1]]
    pending_session = pending[0] if len(pending) else None
    triggered, forming, errors = [], [], []
    for offset in range(0, len(symbols), 25):
        batch = symbols[offset:offset + 25]
        progress.progress(offset / len(symbols), text=f"Checking {offset} of {len(symbols)} quotes")
        try:
            quotes = download(batch)
        except Exception as error:
            errors.extend({"Ticker": ticker, "Issue": str(error)} for ticker in batch)
            continue
        for ticker in batch:
            try:
                raw = validate(quotes[ticker])
                bars = completed(raw, now).loc[lambda frame: frame.index.isin(sessions)]
                if bars.empty or bars.index[-1] != sessions[-1]:
                    raise ValueError("Missing latest completed Nifty 50 session")
                signals, setup = evaluate(indicators(bars), raw, sessions, ticker, recent, pending_session)
                triggered.extend(signals)
                if setup:
                    forming.append(setup)
            except Exception as error:
                errors.append({"Ticker": ticker, "Issue": str(error) if not isinstance(error, KeyError)
                               else "Yahoo returned no usable OHLC for this symbol"})
    progress.empty()
    return now, index_raw, index_bars, len(symbols), triggered, forming, errors


st.markdown("""
<style>
.stApp {background:#f9f7ff;color:#221c3c}
.radar {background:linear-gradient(105deg,#e5dbff,#d9f7f0 66%,#ffe4ef);
border:1px solid #cec4e9;border-radius:24px;padding:24px 32px;margin:0 0 22px;
display:flex;gap:18px;justify-content:space-between;align-items:center;flex-wrap:wrap;color:#221c3c}
.radar strong {font-size:clamp(28px,5vw,46px);display:block;line-height:1.2}
.radar small {font-size:14px;letter-spacing:.12em;font-weight:700}
.radar p {margin:8px 0 0;font-size:16px}
.tiles {display:flex;gap:8px}
.tiles span {display:grid;place-items:center;background:#ffffffaa;width:54px;height:54px;
border-radius:16px;font-size:28px}
.moving span {animation:sweep 2.6s ease-in-out infinite}
.moving span:nth-child(2) {animation-delay:.2s}
.moving span:nth-child(3) {animation-delay:.4s}
.moving span:nth-child(4) {animation-delay:.6s}
@keyframes sweep {50% {transform:translateY(-6px) rotate(5deg);background:#fff}}
@media(prefers-reduced-motion:reduce) {.moving span {animation:none}}
</style>
""", unsafe_allow_html=True)
st.markdown(f"""
<div class="radar"><div><small>NIFTY 500 · DAILY · LONG ONLY</small>
<strong>Swing Radar <span>v2.0</span></strong>
<p>DI crossover · ADX momentum · EMA trend check</p></div>
<div aria-hidden="true" class="tiles {'moving' if motion else ''}">
<span>📡</span><span>📊</span><span>🔎</span><span>⚡</span></div></div>
""", unsafe_allow_html=True)

run, check = st.columns(2)
if check.button("Check Nifty 50 feed"):
    try:
        st.session_state["health"] = health()
        st.session_state.pop("health_error", None)
    except Exception as error:
        st.session_state.pop("health", None)
        st.session_state["health_error"] = str(error)

if run.button("Scan Nifty 500", type="primary"):
    progress = st.progress(0, text="Checking index feed and constituents")
    try:
        result = scan(progress)
        st.session_state["snapshot"] = result
        st.session_state["health"] = result[:3]
        st.session_state.pop("scan_error", None)
        st.session_state.pop("health_error", None)
        latest = result[2].index[-1].date()
        seen = st.session_state.setdefault("alerted", set())
        fresh = {(row["Ticker"], row["Crossover"]) for row in result[4] if row["Bar date"] == latest} - seen
        if fresh:
            st.toast(f"{len(fresh)} new trigger(s) on {latest}", icon="⚡")
            seen.update(fresh)
    except Exception as error:
        st.session_state["scan_error"] = str(error)
    finally:
        progress.empty()

st.subheader("Nifty 50 · Data checker")
if "health_error" in st.session_state:
    st.error(st.session_state["health_error"])
elif "health" in st.session_state:
    checked, raw_index, index_bars = st.session_state["health"]
    day = index_bars.index[-1].date()
    st.caption(f"Latest completed bar: {day} · Checked {checked:%d %b %H:%M IST}")
    for column, field in zip(st.columns(4), OHLC):
        column.metric(field, f'{index_bars.iloc[-1][field]:,.2f}')
    if raw_index.index[-1] > index_bars.index[-1]:
        st.info("Today's unfinished bar is excluded from signals.")
    elif day != checked.date():
        st.warning("No completed bar dated today. This may be normal before close, on a holiday, or when Yahoo is delayed.")
else:
    st.caption("Check the feed or run a scan to load the latest completed index OHLC.")


def table(rows, sort_key, empty_message):
    if not rows:
        st.info(empty_message)
        return
    data = pd.DataFrame(rows).sort_values([sort_key, "Ticker"], ascending=[False, True])
    data.insert(0, "S.No.", range(1, len(data) + 1))
    st.dataframe(data, hide_index=True, column_config={
        field: st.column_config.NumberColumn(format="%.2f")
        for field in data.select_dtypes(include="float").columns
    })


if "scan_error" in st.session_state:
    st.error(f'Latest scan failed: {st.session_state["scan_error"]}. Any results below are from the previous scan.')
if "snapshot" in st.session_state:
    scanned, _, index_bars, count, triggers, setups, issues = st.session_state["snapshot"]
    st.caption(f"Scan: {scanned:%d %b %H:%M IST} · Through {index_bars.index[-1].date()} · {count - len(issues)}/{count} tickers checked")
    if issues:
        st.warning(f"{len(issues)} tickers could not be evaluated. Results are partial.")
    st.subheader(f"⚡ Triggered · {len(triggers)}")
    st.caption("Blank entry or target means Yahoo has not supplied the next session’s opening price.")
    table(triggers, "Crossover", "No triggers found among evaluated symbols in this scan’s history window.")
    st.subheader(f"🔎 Forming · {len(setups)}")
    table(setups, "Crossover", "No active setups found among evaluated symbols.")
    if issues:
        with st.expander("Quote errors and missing bars"):
            st.dataframe(issues, hide_index=True)
