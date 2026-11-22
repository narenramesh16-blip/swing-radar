# Swing Radar v2.0

Local Streamlit dashboard. From this folder, with Python 3.10+ and internet access:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL Streamlit prints. Click **Check Nifty 50 feed** for daily OHLC, or **Scan Nifty 500** for all current constituents. The dashboard uses the official Nifty Indices constituent CSV and unadjusted Yahoo daily OHLC via yfinance. It does not place trades.

## Rules and examples

- Day 0 is the first close where +DI(14) is above −DI(14) after being at or below it. Days 0 through 5 inclusive are eligible.
- Example pass: on day 0, ADX rises from 21 to 22 and the close is above both EMAs. Record one trigger, then display the next session's open and a target 3% above it as soon as that bar is available. The open is a reference price, not a fill.
- Example forming: on day 2, ADX is flat or close equals either EMA. The setup remains active if +DI is still above −DI. A bearish reversal or equality invalidates the setup before any trigger.
- Example fail: the first qualifying close is on day 6. The setup is expired. RSI(14) is display-only; no stop-loss is inferred.

## Data and alerts

The dashboard uses Nifty 50 daily dates as its session reference. It excludes today's price candle from signal math before the normal NSE cash-market close at 15:30 IST. Special trading hours and Yahoo publication delays are not independently verified; check the displayed date. If a ticker is missing reference sessions or has bad OHLC, the dashboard reports it instead of silently counting it as a clean result. Historical rows use today's constituent list; this is not a point-in-time backtest.

Triggered history defaults to 20 sessions; change it before scanning to see more or fewer. The in-app toast alerts only on the latest completed session and deduplicates by ticker and crossover date within the current browser session. No background polling or external delivery. The animated radar, chart, magnifier and signal icons can be turned off in the sidebar.

Run deterministic tests with `python -m unittest -v`.
