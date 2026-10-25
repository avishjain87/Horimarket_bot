"""Horimarket Telegram bot.

Commands:
  /start, /help
  /predict <name>   e.g. /predict gold, /predict nifty, /predict RELIANCE.NS
  /price <name>
  /watch <name>     get a daily signal at 09:00 IST
  /unwatch <name>
  /list
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

import holidays as mh
import predictor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("horimarket")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
IST = ZoneInfo("Asia/Kolkata")
WATCH_FILE = os.environ.get("WATCH_FILE", "watchlist.json")  # use a Railway volume to persist
SUBS_FILE = os.environ.get("SUBS_FILE", "alert_subs.json")  # holiday-alert subscribers

HELP = (
    "*Horimarket* - gold, silver, stock signals\n\n"
    "/predict gold\n/predict silver\n/predict nifty\n/predict reliance\n"
    "/price gold\n/watch gold  (roz 9 baje signal)\n/unwatch gold\n/list\n\n"
    "/market  (aaj khula ya band, is hafte ka haal)\n"
    "/holidays  (aane wali chhuttiyan, kitne din band)\n"
    "/alerts on  (holiday alert roz 9 baje + Ravivar shaam ko agle hafte ka haal)\n"
    "/alerts off\n\n"
    "Koi bhi Yahoo ticker chalega, jaise /predict TATAMOTORS.NS\n\n"
    "_Ye guarantee nahi hai, sirf madad hai._"
)


def load_watch() -> dict:
    try:
        with open(WATCH_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_watch(data: dict) -> None:
    with open(WATCH_FILE, "w") as f:
        json.dump(data, f)


def load_subs() -> list:
    try:
        with open(SUBS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_subs(data: list) -> None:
    with open(SUBS_FILE, "w") as f:
        json.dump(data, f)


def today_ist() -> dt.date:
    return dt.datetime.now(IST).date()


async def market_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = today_ist()
    await update.message.reply_text(
        mh.market_status(t) + "\n\n" + mh.week_view(t), parse_mode=ParseMode.MARKDOWN
    )


async def holidays_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(mh.upcoming_text(today_ist()), parse_mode=ParseMode.MARKDOWN)


async def alerts_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    subs = set(load_subs())
    arg = (ctx.args[0].lower() if ctx.args else "")
    if arg == "on":
        subs.add(chat)
        save_subs(sorted(subs))
        await update.message.reply_text("Holiday alert chalu. Roz 9 baje (jab chhutti paas ho) aur Ravivar shaam ko hafte ka haal.")
    elif arg == "off":
        subs.discard(chat)
        save_subs(sorted(subs))
        await update.message.reply_text("Holiday alert band.")
    else:
        await update.message.reply_text(f"Holiday alert abhi {'ON' if chat in subs else 'OFF'} hai. /alerts on ya /alerts off likho.")


async def holiday_job(ctx: ContextTypes.DEFAULT_TYPE):
    text = mh.daily_alert(today_ist())
    if not text:
        return
    chats = set(load_subs()) | {int(c) for c in load_watch()}
    for chat in chats:
        try:
            await ctx.bot.send_message(chat, text, parse_mode=ParseMode.MARKDOWN)
        except Exception:  # noqa: BLE001
            log.exception("holiday alert failed for %s", chat)


async def weekly_job(ctx: ContextTypes.DEFAULT_TYPE):
    t = today_ist() + dt.timedelta(days=1)  # Sunday evening -> look at the coming week
    text = "*Agle hafte ki taiyari*\n" + mh.week_view(t) + "\n\n" + mh.upcoming_text(t, 30)
    chats = set(load_subs()) | {int(c) for c in load_watch()}
    for chat in chats:
        try:
            await ctx.bot.send_message(chat, text, parse_mode=ParseMode.MARKDOWN)
        except Exception:  # noqa: BLE001
            log.exception("weekly summary failed for %s", chat)


async def _report(name: str) -> str:
    ticker = predictor.resolve_ticker(name)
    df = await asyncio.to_thread(predictor.fetch_history, ticker)
    result = await asyncio.to_thread(predictor.predict, df)
    return predictor.format_report(name, result)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP, parse_mode=ParseMode.MARKDOWN)


async def predict_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Naam likho, jaise: /predict gold")
        return
    name = ctx.args[0]
    msg = await update.message.reply_text("Data la raha hoon...")
    try:
        text = await _report(name)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:  # noqa: BLE001
        log.exception("predict failed")
        await msg.edit_text(f"Error: {e}")


async def price_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Naam likho, jaise: /price silver")
        return
    name = ctx.args[0]
    try:
        df = await asyncio.to_thread(predictor.fetch_history, predictor.resolve_ticker(name), "5d")
        await update.message.reply_text(f"{name.upper()}: {float(df['Close'].iloc[-1]):.2f} ({df.index[-1].date()})")
    except Exception as e:  # noqa: BLE001
        await update.message.reply_text(f"Error: {e}")


async def watch_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Naam likho, jaise: /watch gold")
        return
    chat = str(update.effective_chat.id)
    data = load_watch()
    items = set(data.get(chat, []))
    items.add(ctx.args[0].lower())
    data[chat] = sorted(items)
    save_watch(data)
    await update.message.reply_text(f"Watchlist: {', '.join(data[chat])}\nRoz subah 9 baje signal aayega.")


async def unwatch_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Naam likho, jaise: /unwatch gold")
        return
    chat = str(update.effective_chat.id)
    data = load_watch()
    data[chat] = [x for x in data.get(chat, []) if x != ctx.args[0].lower()]
    save_watch(data)
    await update.message.reply_text(f"Watchlist: {', '.join(data[chat]) or 'khali'}")


async def list_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = load_watch().get(str(update.effective_chat.id), [])
    await update.message.reply_text(f"Watchlist: {', '.join(items) or 'khali'}")


async def daily_job(ctx: ContextTypes.DEFAULT_TYPE):
    for chat, items in load_watch().items():
        for name in items:
            try:
                text = await _report(name)
                await ctx.bot.send_message(int(chat), text, parse_mode=ParseMode.MARKDOWN)
            except Exception:  # noqa: BLE001
                log.exception("daily job failed for %s %s", chat, name)


def main():
    if not TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN set nahi hai.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("predict", predict_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("watch", watch_cmd))
    app.add_handler(CommandHandler("unwatch", unwatch_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("holidays", holidays_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.job_queue.run_daily(daily_job, time=dt.time(9, 0, tzinfo=IST))
    app.job_queue.run_daily(holiday_job, time=dt.time(9, 0, tzinfo=IST))
    app.job_queue.run_daily(weekly_job, time=dt.time(18, 0, tzinfo=IST), days=(6,))  # Sunday
    log.info("Horimarket bot chal raha hai")
    app.run_polling()


if __name__ == "__main__":
    main()
