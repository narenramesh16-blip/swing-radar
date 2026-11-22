from datetime import time

import pandas as pd

OHLC = ["Open", "High", "Low", "Close"]


def validate(frame):
    bars = frame[OHLC].copy().dropna(how="all").sort_index()
    dates = pd.DatetimeIndex(bars.index)
    if dates.tz is not None:
        dates = dates.tz_convert("Asia/Kolkata").tz_localize(None)
    bars.index = dates.normalize()
    if bars.empty or not bars.index.is_unique:
        raise ValueError("Missing bars or duplicate session dates")
    if ((~bars.gt(0)) | bars.eq(float("inf"))).any().any():
        raise ValueError("Missing or invalid OHLC")
    if (bars.High.lt(bars.max(axis=1)) | bars.Low.gt(bars.min(axis=1))).any():
        raise ValueError("Inconsistent OHLC range")
    return bars


def completed(bars, now):
    today = pd.Timestamp(now.date())
    return bars.loc[bars.index <= today] if now.time() >= time(15, 30) else bars.loc[bars.index < today]


def wilder(series, length=14):
    valid = series.dropna()
    result = pd.Series(float("nan"), index=series.index)
    if len(valid) >= length:
        seeded = valid.iloc[length - 1:].copy()
        seeded.iloc[0] = valid.iloc[:length].mean()
        result.loc[seeded.index] = seeded.ewm(alpha=1 / length, adjust=False).mean()
    return result


def indicators(bars):
    result = bars.copy()
    previous = bars.Close.shift()
    true_range = pd.concat(
        [bars.High - bars.Low, (bars.High - previous).abs(), (bars.Low - previous).abs()],
        axis=1,
    ).max(axis=1).where(previous.notna())
    up, down = bars.High.diff(), -bars.Low.diff()
    atr = wilder(true_range)
    for label, move, opposite in [("+DI", up, down), ("−DI", down, up)]:
        movement = move.where((move > opposite) & (move > 0), 0).where(previous.notna())
        result[label] = (100 * wilder(movement) / atr).mask(atr.eq(0), 0)
    total = result["+DI"] + result["−DI"]
    dx = (100 * (result["+DI"] - result["−DI"]).abs() / total).mask(total.eq(0), 0)
    result["ADX"] = wilder(dx)
    for span in (20, 50):
        result[f"EMA {span}"] = bars.Close.ewm(span=span, adjust=False, min_periods=span).mean()
    gain = wilder(bars.Close.diff().clip(lower=0))
    loss = wilder(-bars.Close.diff().clip(upper=0))
    result["RSI"] = (100 * gain / (gain + loss)).mask((gain + loss).eq(0), 50)
    return result


def evaluate(values, raw, sessions, ticker, recent, pending_session=None):
    sessions = sessions[sessions >= values.index[0]]
    if not sessions.isin(values.index).all():
        raise ValueError("Missing daily bars relative to Nifty 50 sessions")
    values = values.reindex(sessions)
    if len(values) < 50 or pd.isna(values["EMA 50"].iloc[-1]):
        raise ValueError("Insufficient indicator history")
    triggered, forming, cross = [], None, None
    for position in range(2, len(values)):
        current, prior, earlier = [values.iloc[index] for index in (position, position - 1, position - 2)]
        date = sessions[position]
        bullish = current["+DI"] > current["−DI"]
        if bullish and prior["+DI"] <= prior["−DI"]:
            cross = position
        if cross is None:
            continue
        age = position - cross
        if not bullish or age > 5:
            cross = None
            continue
        rising = current.ADX > prior.ADX
        above20 = current.Close > current["EMA 20"]
        above50 = current.Close > current["EMA 50"]
        row = {"Ticker": ticker, "Bar date": date.date(), "Crossover": sessions[cross].date(),
               "Sessions since cross": age, **current[["Close", "+DI", "−DI", "ADX", "RSI", "EMA 20", "EMA 50"]].to_dict(),
               "ADX −1": prior.ADX, "ADX −2": earlier.ADX, "ADX rising": rising}
        if rising and above20 and above50:
            if position >= len(values) - recent:
                next_date = sessions[position + 1] if position + 1 < len(sessions) else pending_session
                entry = raw.at[next_date, "Open"] if next_date in raw.index else None
                triggered.append({**row, "Entry session": next_date.date() if next_date is not None else None,
                                  "Entry open": entry, "Target +3%": entry * 1.03 if entry else None})
            cross = None
        elif position == len(values) - 1 and age < 5:
            missing = [name for name, passed in [("ADX rise", rising), ("Above EMA 20", above20),
                                                 ("Above EMA 50", above50)] if not passed]
            forming = {**row, "Still needed": ", ".join(missing), "Sessions remaining": 5 - age}
    return triggered, forming
