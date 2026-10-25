"""Horimarket prediction engine.

Data -> indicators -> simple ML model -> signal + honest backtest accuracy.
This is a decision-support tool, NOT a guarantee of future prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# Friendly name -> Yahoo Finance ticker
SYMBOLS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "nifty": "^NSEI",
    "banknifty": "^NSEBANK",
    "sensex": "^BSESN",
    "reliance": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infy": "INFY.NS",
    "hdfcbank": "HDFCBANK.NS",
    "sbin": "SBIN.NS",
}

FEATURES = ["rsi", "macd_hist", "sma_ratio", "ret_1", "ret_5", "vol_10", "bb_pos"]


def resolve_ticker(name: str) -> str:
    key = name.strip().lower()
    if key in SYMBOLS:
        return SYMBOLS[key]
    # Allow raw tickers like TATAMOTORS.NS or AAPL
    return name.strip().upper()


def fetch_history(ticker: str, period: str = "3y") -> pd.DataFrame:
    import yfinance as yf  # imported here so tests can run without network

    df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"Data nahi mila: {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    close = d["Close"]

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    d["rsi"] = (100 - 100 / (1 + rs)).fillna(50)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    d["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / close

    d["sma20"] = close.rolling(20).mean()
    d["sma50"] = close.rolling(50).mean()
    d["sma_ratio"] = d["sma20"] / d["sma50"] - 1

    d["ret_1"] = close.pct_change(1)
    d["ret_5"] = close.pct_change(5)
    d["vol_10"] = d["ret_1"].rolling(10).std()

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    d["bb_pos"] = (close - mid) / (2 * std.replace(0, np.nan))

    return d


def _rule_score(last: pd.Series) -> tuple[float, list[str]]:
    """Transparent rule-based score in [-1, 1] plus reasons."""
    score = 0.0
    why = []
    if last["rsi"] < 30:
        score += 0.4
        why.append(f"RSI {last['rsi']:.0f} (oversold)")
    elif last["rsi"] > 70:
        score -= 0.4
        why.append(f"RSI {last['rsi']:.0f} (overbought)")
    else:
        why.append(f"RSI {last['rsi']:.0f} (neutral)")

    if last["macd_hist"] > 0:
        score += 0.3
        why.append("MACD positive")
    else:
        score -= 0.3
        why.append("MACD negative")

    if last["sma_ratio"] > 0:
        score += 0.3
        why.append("SMA20 > SMA50 (uptrend)")
    else:
        score -= 0.3
        why.append("SMA20 < SMA50 (downtrend)")
    return max(-1.0, min(1.0, score)), why


def _ml_probability(d: pd.DataFrame) -> tuple[float, float]:
    """Train on past data, return (P(up tomorrow), walk-forward accuracy)."""
    data = d.dropna(subset=FEATURES).copy()
    data["target"] = (data["Close"].shift(-1) > data["Close"]).astype(int)
    train_all = data.iloc[:-1]  # last row has no known next-day target
    if len(train_all) < 200:
        raise ValueError("Kam data hai (200 din se kam), prediction nahi ho sakti.")

    X = train_all[FEATURES].values
    y = train_all["target"].values

    # Walk-forward backtest: train on first 70%, test on rest
    split = int(len(X) * 0.7)
    scaler_bt = StandardScaler().fit(X[:split])
    model_bt = LogisticRegression(max_iter=500).fit(scaler_bt.transform(X[:split]), y[:split])
    acc = float((model_bt.predict(scaler_bt.transform(X[split:])) == y[split:]).mean())

    scaler = StandardScaler().fit(X)
    model = LogisticRegression(max_iter=500).fit(scaler.transform(X), y)
    latest = data[FEATURES].iloc[[-1]].values
    p_up = float(model.predict_proba(scaler.transform(latest))[0, 1])
    return p_up, acc


def predict(df: pd.DataFrame) -> dict:
    d = add_indicators(df)
    last = d.dropna(subset=FEATURES).iloc[-1]
    rule, why = _rule_score(last)
    p_up, acc = _ml_probability(d)

    # Blend: rules (-1..1 -> 0..1) and ML probability
    blended = 0.5 * ((rule + 1) / 2) + 0.5 * p_up
    if blended >= 0.58:
        signal = "BULLISH (upar ka jhukav)"
    elif blended <= 0.42:
        signal = "BEARISH (neeche ka jhukav)"
    else:
        signal = "NEUTRAL (saaf signal nahi)"

    price = float(df["Close"].iloc[-1])
    atr_like = float(d["Close"].pct_change().rolling(14).std().iloc[-1]) * price
    return {
        "price": price,
        "signal": signal,
        "blended": blended,
        "p_up_ml": p_up,
        "rule_score": rule,
        "backtest_acc": acc,
        "reasons": why,
        "daily_move_est": atr_like,
        "asof": str(df.index[-1].date()),
    }


def format_report(name: str, r: dict) -> str:
    acc = r["backtest_acc"] * 100
    lines = [
        f"*{name.upper()}*  ({r['asof']})",
        f"Price: {r['price']:.2f}",
        f"Signal: *{r['signal']}*",
        f"Kal upar jaane ka ML anuman: {r['p_up_ml'] * 100:.0f}%",
        f"Typical daily hilna: ±{r['daily_move_est']:.2f}",
        "",
        "Wajah:",
        *[f"• {w}" for w in r["reasons"]],
        "",
        f"Backtest accuracy (purane data par): {acc:.0f}%",
        "_Ye sirf madad hai, guarantee nahi. Financial advice nahi hai._",
    ]
    if acc < 55:
        lines.insert(-1, "_Dhyan do: accuracy 55% se kam hai, signal par zyada bharosa mat karo._")
    return "\n".join(lines)
