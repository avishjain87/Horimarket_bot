# Horimarket

Telegram bot: gold, silver aur stocks ke liye signal (indicators + simple ML + backtest).
Ye madad ke liye hai, guarantee nahi. Financial advice nahi.

## Setup
1. Telegram par @BotFather se `/newbot` karke token lo.
2. GitHub repo `Horimarket` banao aur ye saari files upload karo.
3. Railway: New Project > Deploy from GitHub repo > Horimarket.
4. Railway > Variables mein `TELEGRAM_BOT_TOKEN` daalo.
5. (Optional) Volume lagao, `/data` par mount karo, aur `WATCH_FILE=/data/watchlist.json` set karo.

## Local chalana
```
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
python bot.py
```

## Commands
/predict gold, /price silver, /watch nifty, /unwatch nifty, /list
