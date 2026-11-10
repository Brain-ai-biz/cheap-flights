"""קריאה של לוח המחירים הציבורי של Google Flights, בפייתון נקי, בלי מפתח ובלי חשבון.

שתי בקשות בלבד, אותן בקשות שהאתר עצמו שולח כשפותחים את לוח התאריכים:
- GetCalendarGraph: המחיר הזול ביותר הלוך-חזור לכל תאריך יציאה, עד 61 ימים בבקשה.
- GetShoppingResults: רשימת הטיסות בתאריך מסוים (חברה, שעות, עצירות).

מבנה ההודעות נלמד מהספרייה הפתוחה fli של Punit Arani (רישיון MIT).
הבקשות נשלחות אחת אחרי השנייה עם הפסקה, כמו אדם שגולל בלוח, ולא במקביל.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = "https://www.google.com/_/FlightsFrontendUi/data/travel.frontend.flights.FlightsFrontendService/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")
MAX_CHUNK = 61          # ימים בבקשת לוח אחת
PAUSE = float(os.environ.get("CHEAP_FLIGHTS_PAUSE", "1.5"))  # שניות בין בקשות; אפשר להאט
STOPS = {"any": 0, "direct": 1, "one": 2}


class Blocked(Exception):
    """גוגל ביקש הפסקה (דף sorry או קוד 13). עוצרים, לא מנסים לעקוף. partial = מה שכבר נסרק."""
    partial: list = []


_last = [0.0]
_curl = [None]


def _post(endpoint: str, inner: list, currency: str) -> list | None:
    body = "f.req=" + urllib.parse.quote(json.dumps([None, json.dumps(inner, separators=(",", ":"))],
                                                     separators=(",", ":")))
    url = f"{BASE}{endpoint}?curr={currency}&hl=en"
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    text = None
    for attempt in range(3):
        try:
            text = _send(url, body)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 or (e.code == 302 and "sorry" in str(e.headers.get("location", ""))):
                raise Blocked("גוגל ביקש הפסקה") from e
            if attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))
    _last[0] = time.time()
    return _parse(text)


def _send(url: str, body: str) -> str:
    """בקשה רגילה של פייתון. אם מותקן curl_cffi משתמשים בו, כי הוא נראה לגוגל כמו כרום."""
    if _curl[0] is None:
        try:
            from curl_cffi import requests as cr  # לא חובה
            _curl[0] = cr
        except Exception:
            _curl[0] = False
    headers = {"content-type": "application/x-www-form-urlencoded;charset=UTF-8"}
    if _curl[0]:
        r = _curl[0].post(url, data=body, headers=headers, impersonate="chrome", timeout=40)
        if r.status_code == 429:
            raise Blocked("גוגל ביקש הפסקה")
        r.raise_for_status()
        return r.text
    headers["user-agent"] = UA
    req = urllib.request.Request(url, data=body.encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8")


def _parse(text: str) -> list | None:
    raw = text.lstrip()
    if raw.startswith(")]}'"):
        raw = raw[4:].lstrip()
    # תגובה מרובת חלקים: שורת אורך ואז JSON. לוקחים את החלק הראשון שיש בו wrb.fr.
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        try:
            outer = json.loads(line)
        except ValueError:
            continue
        for item in outer:
            if isinstance(item, list) and item and item[0] == "wrb.fr":
                if item[2] is None:
                    code = item[5] if len(item) > 5 else None
                    if code and code[0] in (13, 7, 8):
                        raise Blocked(f"גוגל החזיר קוד {code[0]}")
                    return None
                return json.loads(item[2])
    return None


def _seg(o: str, d: str, day: str, stops: int, tail: int = 3) -> list:
    return [[[[o, 0]]], [[[d, 0]]], None, stops, None, None, day,
            None, None, None, None, None, None, None, tail]


def _filters(o: str, d: str, out_day: str, back_day: str | None, adults: int, stops: int) -> list:
    trip = 1 if back_day else 2
    segs = [_seg(o, d, out_day, stops)]
    if back_day:
        segs.append(_seg(d, o, back_day, stops))
    return [None, None, trip, None, [], 1, [adults, 0, 0, 0], None, None, None, None, None, None,
            segs, None, None, None, 1]


def calendar_chunk(o: str, d: str, start: date, end: date, nights: int, adults: int = 1,
                   stops: str = "any", currency: str = "ILS") -> list[dict]:
    """מחיר הלוך-חזור זול ביותר לכל יום יציאה בין start ל-end, לחופשה של nights לילות."""
    inner = [None, _filters(o, d, start.isoformat(), (start + timedelta(days=nights)).isoformat(),
                            adults, STOPS[stops]),
             [start.isoformat(), end.isoformat()], None, [nights, nights]]
    data = _post("GetCalendarGraph", inner, currency)
    out = []
    if not data or not isinstance(data[-1], list):
        return out
    for it in data[-1]:
        try:
            price = float(it[2][0][1])
        except (IndexError, TypeError, ValueError):
            continue
        out.append({"out": it[0], "back": it[1], "price": price})
    return out


def calendar_year(o: str, d: str, nights: int, adults: int = 1, stops: str = "any",
                  currency: str = "ILS", days: int = 365, log=print, cache=None) -> tuple[list[dict], str]:
    """כל השנה הקרובה בחלקים של 61 יום. מחזיר את המחירים ואת היום האחרון שגוגל כבר מוכר.

    cache = תיקייה. כל חלק שנסרק נשמר בה לאותו יום, כך שאם גוגל ביקש הפסקה באמצע,
    ההרצה הבאה ממשיכה מאותה נקודה ולא שולחת שוב את מה שכבר נסרק.

    גוגל מוכר כ-330 יום קדימה (לפי יום החזרה). חלק שהסוף שלו מעבר לזה חוזר כשגיאה (קוד 13),
    בדיוק כמו חסימה. לכן בחלקים המאוחרים קוד 13 = "סוף הטווח": מקצרים את החלק ומנסים שוב.
    """
    start = date.today() + timedelta(days=1)
    final = min(date.today() + timedelta(days=days), date.today() + timedelta(days=329 - nights))
    late = date.today() + timedelta(days=240)
    rows, cur, waited = [], start, [False]
    while cur <= final:
        end = min(cur + timedelta(days=MAX_CHUNK - 1), final)
        got, tries = None, 0
        cf = None
        if cache is not None:
            cf = Path(cache) / f"{o}-{d}-{nights}-{adults}-{stops}-{cur}-{date.today()}.part.json"
            if cf.exists():
                c = json.loads(cf.read_text())
                got, end = c["rows"], date.fromisoformat(c["end"])
        while got is None:
            try:
                got = calendar_chunk(o, d, cur, end, nights, adults, stops, currency)
                if not got and cur > start and end - cur > timedelta(days=6) and tries < 4:
                    got, tries, end = None, tries + 1, end - timedelta(days=7)
            except Blocked as e:
                if cur > late and end - cur > timedelta(days=6) and tries < 4:
                    tries, end = tries + 1, end - timedelta(days=7)
                    continue
                if cur > late:  # כנראה סוף הטווח, לא חסימה
                    got = []
                    break
                if not waited[0]:  # הגבלת קצב רגעית: מחכים דקה פעם אחת ומנסים שוב
                    waited[0] = True
                    log("  גוגל מבקש להאט. מחכה דקה וממשיך...")
                    time.sleep(60)
                    continue
                e.partial = rows
                raise
        if cf is not None and not cf.exists() and (got or cur <= late):
            cf.write_text(json.dumps({"rows": got, "end": end.isoformat()}))
        rows.extend(got)
        log(f"  {o}→{d} {nights} לילות: {cur:%d.%m}-{end:%d.%m} · {len(got)} תאריכים")
        if not got and cur > start:
            break
        cur = end + timedelta(days=1)
    last = max((r["out"] for r in rows), default=None)
    return rows, last


def day_flights(o: str, d: str, day: str, adults: int = 1, stops: str = "any",
                currency: str = "ILS", top: int = 3) -> list[dict]:
    """הטיסות בכיוון אחד ביום מסוים, מהזולה. משמש רק לפרטים (חברה, שעות), לא למחיר הראשי."""
    inner = [[], _filters(o, d, day, None, adults, STOPS[stops]) + [None] * 10 + [0], 2, 1, 0, 1]
    data = _post("GetShoppingResults", inner, currency)
    if not data:
        return []
    rows = []
    for i in (2, 3):
        try:
            rows.extend(data[i][0])
        except (IndexError, TypeError):
            pass
    out = []
    for row in rows:
        try:
            det = row[0]
            legs = det[2] or []
            first, last = legs[0], legs[-1]
            price = row[1][0][-1] if row[1] and row[1][0] else None
            names = det[1] if isinstance(det[1], list) else []
            out.append({
                "airline": names[0] if names else (first[22][0] if first[22] else ""),
                "code": f"{first[22][0]}{first[22][1]}" if first[22] else "",
                "dep": datetime(*first[20], *first[8][:2]).strftime("%H:%M"),
                "arr": datetime(*last[21], *(x or 0 for x in last[10][:2])).strftime("%H:%M"),
                "minutes": det[9],
                "stops": max(len(legs) - 1, 0),
                "price": float(price) if isinstance(price, (int, float)) else None,
            })
        except (IndexError, TypeError, ValueError):
            continue
    out.sort(key=lambda f: (f["price"] is None, f["price"] or 0, f["stops"]))
    return out[:top]


def _pb_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _pb(field: int, payload: bytes | int) -> bytes:
    if isinstance(payload, int):
        return _pb_varint(field << 3) + _pb_varint(payload)
    return _pb_varint((field << 3) | 2) + _pb_varint(len(payload)) + payload


def flight_page(o: str, d: str, out_day: str, back_day: str | None = None, adults: int = 1) -> str:
    """קישור ישיר לדף התוצאות של Google Flights: המסלול, התאריכים ומספר הנוסעים כבר מולאו.

    זה הפרמטר tfs שהאתר עצמו שם בכתובת כשמחפשים (אותו מבנה שהספרייה הפתוחה fast-flights משתמשת בו):
    רשימת קטעים (תאריך, מאיפה, לאן), נוסעים, מחלקת תיירים, הלוך-חזור או כיוון אחד.
    """
    leg = lambda a, b, day: _pb(2, day.encode()) + _pb(13, _pb(2, a.encode())) + _pb(14, _pb(2, b.encode()))
    msg = _pb(3, leg(o, d, out_day))
    if back_day:
        msg += _pb(3, leg(d, o, back_day))
    msg += _pb(8, bytes([1]) * max(1, adults)) + _pb(9, 1) + _pb(19, 1 if back_day else 2)
    tfs = base64.urlsafe_b64encode(msg).decode().rstrip("=")
    return f"https://www.google.com/travel/flights/search?tfs={tfs}&hl=he&curr=ILS"


def booking_links(o: str, d: str, out_day: str, back_day: str, adults: int = 1) -> dict:
    return {
        "google": flight_page(o, d, out_day, back_day, adults),
        "kayak": f"https://www.kayak.com/flights/{o}-{d}/{out_day}/{back_day}"
                 + (f"/{adults}adults" if adults > 1 else ""),
    }
