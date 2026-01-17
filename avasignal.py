import requests
import time
import pandas as pd
from datetime import datetime

# ================= CONFIG =================
TELEGRAM_TOKEN = "8319077719:AAEYx9Owl3abeDIUh5L9Jov9f62Yj57Gsjo"
CHAT_ID = "2090736815"

TIMEFRAME_ENTRY = "15m"   # فريم الصفقة
TIMEFRAME_CONFIRM = "1h"  # فريم أعلى لتأكيد الاتجاه
LIMIT = 200
SCAN_INTERVAL = 300       # كل 5 دقائق
MIN_SCORE = 5

MEXC_API = "https://api.mexc.com"

sent_signals = set()

# =============== TELEGRAM =================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=data, timeout=10)
    except:
        pass

# =============== MEXC =====================
def get_symbols():
    data = requests.get(f"{MEXC_API}/api/v3/exchangeInfo", timeout=10).json()
    return [s["symbol"] for s in data["symbols"] 
            if s["quoteAsset"]=="USDT" and s["status"]=="ENABLED"]

def get_klines(symbol, interval):
    data = requests.get(f"{MEXC_API}/api/v3/klines",
                        params={"symbol": symbol, "interval": interval, "limit": LIMIT},
                        timeout=10).json()
    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "_","_","_","_","_","_"
    ])
    df[["open","high","low","close","volume"]] = df[["open","high","low","close","volume"]].astype(float)
    return df

# =============== INDICATORS =================
def EMA(series, period): return series.ewm(span=period, adjust=False).mean()
def RSI(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
def ATR(df, period=14):
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# =============== ICT LOGIC =================
def BOS(df): return df["close"].iloc[-1] > df["high"].rolling(20).max().iloc[-2]
def FVG(df): return df["low"].iloc[-1] > df["high"].iloc[-3]

# =============== SIGNAL CHECK =================
def check_signal(symbol):
    # بيانات فريم الدخول
    df_entry = get_klines(symbol, TIMEFRAME_ENTRY)
    df_entry["EMA50"] = EMA(df_entry["close"], 50)
    df_entry["EMA200"] = EMA(df_entry["close"], 200)
    df_entry["RSI"] = RSI(df_entry["close"])
    df_entry["ATR"] = ATR(df_entry)
    df_entry["VOL_MA"] = df_entry["volume"].rolling(20).mean()

    last = df_entry.iloc[-1]
    score = 0
    reasons = []

    # Trend
    if last["EMA50"] > last["EMA200"]:
        score += 1; reasons.append("EMA Trend")

    # Breakout
    if last["close"] > df_entry["high"].iloc[-20:-1].max():
        score += 2; reasons.append("Breakout")

    # Volume
    if last["volume"] > last["VOL_MA"] * 2:
        score += 2; reasons.append("High Volume")

    # RSI
    if 45 < last["RSI"] < 80:
        score += 1; reasons.append("RSI OK")

    # Candle strength
    if (last["close"] - last["open"]) > last["ATR"] * 0.8:
        score += 1; reasons.append("Strong Candle")

    # ICT
    if BOS(df_entry):
        score += 1; reasons.append("BOS")
    if FVG(df_entry):
        score += 1; reasons.append("FVG")

    # فلتر اتجاه BTC
    df_btc = get_klines("BTCUSDT", TIMEFRAME_CONFIRM)
    last_btc = df_btc.iloc[-1]
    btc_trend = EMA(df_btc["close"],50).iloc[-1] > EMA(df_btc["close"],200).iloc[-1]
    if not btc_trend:
        score -= 1  # يقلل من قوة الإشارة إذا BTC هابط

    return score, reasons, last["close"], last["ATR"]

# =============== SEND SIGNAL =================
def send_signal(symbol, price, atr, score, reasons):
    stop = price - atr * 1.3
    tp1 = price * 1.10
    tp2 = price * 1.20
    tp3 = price * 1.35

    msg = (
        f"🔥 BUY SIGNAL (SMART EXPLOSION)\n\n"
        f"📌 Symbol: {symbol}\n"
        f"⏱ TF: {TIMEFRAME_ENTRY}\n"
        f"⭐ Score: {score}/9\n"
        f"🧠 Reasons: {', '.join(reasons)}\n\n"
        f"💰 Entry: {price:.6f}\n"
        f"🛑 Stop: {stop:.6f}\n\n"
        f"🎯 Targets:\n"
        f"TP1: {tp1:.6f}\n"
        f"TP2: {tp2:.6f}\n"
        f"TP3: {tp3:.6f}\n\n"
        f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}"
    )
    send_telegram(msg)

# ================= RUN BOT =================
send_telegram("✅ SMART EXPLOSION BOT STARTED")
symbols = get_symbols()

while True:
    for sym in symbols:
        if sym in sent_signals:
            continue
        try:
            score, reasons, price, atr = check_signal(sym)
            if score >= MIN_SCORE:
                send_signal(sym, price, atr, score, reasons)
                sent_signals.add(sym)
        except:
            continue
    time.sleep(SCAN_INTERVAL)