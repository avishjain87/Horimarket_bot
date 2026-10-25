"""NSE/BSE equity market holiday calendar + closed-streak helpers.

IMPORTANT: this list is for 2026 and was compiled from public sources
(ClearTax / Angel One). NSE can change dates (e.g. Muhurat timing), so
re-check against nseindia.com and update every year.
MCX (gold/silver futures) has different holiday/session rules - this list is for equities.
"""
from __future__ import annotations

import datetime as dt

# Weekday equity holidays 2026
HOLIDAYS_2026 = {
    dt.date(2026, 1, 15): "Maharashtra municipal elections",
    dt.date(2026, 1, 26): "Republic Day",
    dt.date(2026, 3, 3): "Holi",
    dt.date(2026, 3, 26): "Shri Ram Navami",
    dt.date(2026, 3, 31): "Shri Mahavir Jayanti",
    dt.date(2026, 4, 3): "Good Friday",
    dt.date(2026, 4, 14): "Dr. Ambedkar Jayanti",
    dt.date(2026, 5, 1): "Maharashtra Day",
    dt.date(2026, 5, 28): "Bakri Id",
    dt.date(2026, 6, 26): "Muharram",
    dt.date(2026, 9, 14): "Ganesh Chaturthi",
    dt.date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    dt.date(2026, 10, 20): "Dussehra",
    dt.date(2026, 11, 10): "Diwali - Balipratipada",
    dt.date(2026, 11, 24): "Guru Nanak Jayanti",
    dt.date(2026, 12, 25): "Christmas",
}

# Festival days that fall on a weekend (market already closed) - shown for info
WEEKEND_FESTIVALS_2026 = {
    dt.date(2026, 2, 15): "Mahashivratri",
    dt.date(2026, 3, 21): "Id-Ul-Fitr",
    dt.date(2026, 8, 15): "Independence Day",
    dt.date(2026, 11, 8): "Diwali Laxmi Pujan (Muhurat trading expected, timing NSE batayega)",
}

HOLIDAYS = dict(HOLIDAYS_2026)
DAYNAMES = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]


def is_trading_day(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def closed_reason(d: dt.date) -> str | None:
    if d in HOLIDAYS:
        return HOLIDAYS[d]
    if d.weekday() >= 5:
        return WEEKEND_FESTIVALS_2026.get(d, "Weekend")
    return None


def closed_streaks(start: dt.date, days: int = 30) -> list[dict]:
    """Closed periods (consecutive non-trading days) that begin within the window.

    A streak that already started before `start` is extended backwards so the full
    length is reported. Streaks containing only a plain weekend are skipped unless
    they include a holiday (so we only alert on holiday-linked closures).
    """
    out = []
    d = start
    end = start + dt.timedelta(days=days)
    seen = set()
    while d <= end:
        if not is_trading_day(d) and d not in seen:
            s = d
            while not is_trading_day(s - dt.timedelta(days=1)):
                s -= dt.timedelta(days=1)
            e = d
            while not is_trading_day(e + dt.timedelta(days=1)):
                e += dt.timedelta(days=1)
            span = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
            seen.update(span)
            hols = [(x, HOLIDAYS[x]) for x in span if x in HOLIDAYS]
            if hols and e >= start:
                out.append(
                    {
                        "start": s,
                        "end": e,
                        "length": len(span),
                        "holidays": hols,
                        "reopen": e + dt.timedelta(days=1),
                    }
                )
        d += dt.timedelta(days=1)
    return out


def _fmt(d: dt.date) -> str:
    return f"{d.strftime('%d %b')} ({DAYNAMES[d.weekday()]})"


def market_status(today: dt.date) -> str:
    if is_trading_day(today):
        head = f"Aaj {_fmt(today)}: market *khula* hai (9:15-15:30)."
    else:
        head = f"Aaj {_fmt(today)}: market *band* hai ({closed_reason(today)})."
    nxt = today
    while True:
        nxt += dt.timedelta(days=1)
        if is_trading_day(nxt):
            break
    if not is_trading_day(today):
        head += f"\nAgla trading din: {_fmt(nxt)}."
    return head


def week_view(today: dt.date) -> str:
    monday = today - dt.timedelta(days=today.weekday())
    iso = today.isocalendar()
    lines = [f"*Is hafte ka haal (week {iso[1]})*"]
    for i in range(7):
        d = monday + dt.timedelta(days=i)
        mark = "✅ khula" if is_trading_day(d) else f"❌ band ({closed_reason(d)})"
        pointer = "  ← aaj" if d == today else ""
        lines.append(f"{_fmt(d)}: {mark}{pointer}")
    return "\n".join(lines)


def upcoming_text(today: dt.date, days: int = 45) -> str:
    streaks = closed_streaks(today, days)
    if not streaks:
        return f"Agle {days} din mein koi holiday nahi hai."
    lines = [f"*Aane wali market chhuttiyan (agle {days} din)*"]
    for s in streaks:
        names = ", ".join(f"{n}" for _, n in s["holidays"])
        until = (s["start"] - today).days
        when = "chal rahi hai" if until <= 0 else f"{until} din baad"
        lines.append(
            f"• {names}: {_fmt(s['start'])} se {_fmt(s['end'])} tak, "
            f"*{s['length']} din band* ({when}). Phir khulega: {_fmt(s['reopen'])}"
        )
    extra = [
        f"• {n}: {_fmt(d)}"
        for d, n in sorted(WEEKEND_FESTIVALS_2026.items())
        if today <= d <= today + dt.timedelta(days=days)
    ]
    if extra:
        lines.append("\nWeekend par padne wale tyohar:")
        lines.extend(extra)
    lines.append("\n_Equity ke liye hai. Gold/silver (MCX) ka time alag ho sakta hai. nseindia.com se confirm karo._")
    return "\n".join(lines)


def daily_alert(today: dt.date, lookahead: int = 7) -> str | None:
    """Return alert text if a holiday-linked closure starts within `lookahead` days, else None."""
    out = []
    if not is_trading_day(today) and today in HOLIDAYS:
        out.append(f"Aaj market band hai: {HOLIDAYS[today]}.")
    for s in closed_streaks(today, lookahead):
        if s["start"] <= today:
            continue
        until = (s["start"] - today).days
        names = ", ".join(n for _, n in s["holidays"])
        out.append(
            f"⚠️ {until} din baad {_fmt(s['start'])} se market band: {names}. "
            f"Total *{s['length']} din* band, {_fmt(s['reopen'])} ko khulega."
        )
    return "\n".join(out) if out else None
