#!/usr/bin/env python3
"""צייד הטיסות: סורק את כל התאריכים שאפשר להזמין בשנה הקרובה ומחזיר את הזולים ביותר.

דוגמה:
  python3 hunt.py --from "תל אביב" --to "אתונה" --nights 4 --depart חמישי --return שני --out ~/cheap-flights/athens

פייתון 3.9 ומעלה, בלי התקנות, בלי מפתח. התוצרים בתיקיית --out:
  result.json  כל המספרים, עם שעת הבדיקה
  result.html  הדף המונפש (נפתח לבד עם --open)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gflights as gf  # noqa: E402

ASSETS = HERE.parent / "assets"
DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]  # לפי weekday() של פייתון
DAY_KEYS = {
    0: ["שני", "ב", "ב'", "mon", "monday"], 1: ["שלישי", "ג", "ג'", "tue", "tuesday"],
    2: ["רביעי", "ד", "ד'", "wed", "wednesday"], 3: ["חמישי", "ה", "ה'", "thu", "thursday"],
    4: ["שישי", "ו", "ו'", "fri", "friday"], 5: ["שבת", "ש", "מוצ\"ש", "sat", "saturday"],
    6: ["ראשון", "א", "א'", "sun", "sunday"],
}
MAX_REQUESTS = 160
IL = lambda d: (d + 1) % 7  # שבוע ישראלי: ראשון קודם


def say(*a):
    print(*a, flush=True)


def load_places():
    p = json.loads((ASSETS / "places.json").read_text(encoding="utf-8"))
    airports = json.loads((ASSETS / "airports.json").read_text(encoding="utf-8"))
    return p, airports


def resolve(name: str, places: dict, airports: dict, role: str = "יעד") -> str:
    n = name.strip().strip('"').strip("'").lower().replace("־", " ").replace("-", " ")
    n = " ".join(n.split())
    if n.upper() in airports and len(n) == 3 and n.isascii():
        return n.upper()
    cands = [n]
    if n[:1] in "לבמהו" and len(n) > 3:  # "לאתונה", "מתל אביב", "ברומא"
        cands.append(n[1:])
    for c in cands:
        for code, info in places["places"].items():
            if c in [a.lower().replace("-", " ") for a in info["aliases"]] or c == info["he"]:
                return code
    ex = "TLV" if role == "נקודת יציאה" else "ATH"
    sys.exit(f"לא מכיר את \"{name}\" בתור {role}. אפשר לכתוב שם עיר אחר, או קוד שדה תעופה בן 3 אותיות באנגלית (למשל {ex}).")


def parse_days(text: str | None) -> set[int]:
    if not text:
        return set()
    out = set()
    for part in text.replace("،", ",").replace(" או ", ",").replace("/", ",").split(","):
        p = part.strip().lower().replace("יום ", "").replace("ביום ", "")
        if not p:
            continue
        hit = [d for d, keys in DAY_KEYS.items() if p in keys]
        if not hit:
            sys.exit(f"לא הבנתי את היום \"{part.strip()}\". כותבים למשל: חמישי, שישי או thu,fri")
        out.update(hit)
    return out


WORDS = {"שבוע": 7, "שבועיים": 14, "סופש": 3, "סופ\"ש": 3, "שניים": 2, "שתיים": 2, "שלושה": 3, "שלוש": 3,
         "ארבעה": 4, "ארבע": 4, "חמישה": 5, "חמש": 5, "שישה": 6, "שש": 6, "שבעה": 7, "שבע": 7,
         "שמונה": 8, "תשעה": 9, "תשע": 9, "עשרה": 10, "עשר": 10, "week": 7}


def _num(x: str) -> int:
    x = x.strip()
    if x.isdigit():
        return int(x)
    if x in WORDS:
        return WORDS[x]
    sys.exit(f"לא הבנתי את האורך \"{x}\". כותבים מספר, למשל 4, או טווח כמו 3-5.")


def _range(text: str, shift: int = 0) -> list[int]:
    if "-" in text.strip("-"):
        a, b = [_num(x) for x in text.split("-", 1)]
        return [n - shift for n in range(min(a, b), max(a, b) + 1)]
    return sorted({_num(x) - shift for x in text.split(",") if x.strip()})


def parse_nights(text: str | None, days: str | None, dep: set, ret: set) -> list[int]:
    if text:
        nights = _range(text)
    elif days:
        nights = _range(days, 1)
    elif dep and ret:
        return sorted({((r - d) % 7) or 7 for d in dep for r in ret})
    else:
        sys.exit("חסר אורך החופשה: --nights 4 (לילות), או --days 5 (ימים), או יום יציאה ויום חזרה.")
    nights = [n for n in nights if 1 <= n <= 30]
    if not nights:
        sys.exit("אורך החופשה צריך להיות בין לילה אחד ל-30 לילות.")
    if dep and ret:  # האורך חייב להתאים לימים שביקשו
        fit = [n for n in nights if any((d + n) % 7 in ret for d in dep)]
        if not fit:
            want = sorted({((r - d) % 7) or 7 for d in dep for r in ret})
            say(f"שימו לב: {' או '.join(map(str, nights))} לילות לא מסתדרים עם ימי היציאה והחזרה שביקשת. "
                f"לפי הימים זה {' או '.join(map(str, want))} לילות, אז ממשיך עם זה.")
            return want
        return fit
    return nights


def he_date(s: str) -> str:
    d = date.fromisoformat(s)
    return f"{DAYS_HE[d.weekday()]} {d.day}.{d.month}"


def scan(origin, dests, nights, args, cache_dir):
    rows, horizon, requests, partial = {}, None, 0, False
    for d in dests:
        rows[d] = []
        for n in nights:
            key = cache_dir / f"{origin}-{d}-{n}-{args.adults}-{args.stops}-{date.today()}.json"
            if key.exists():
                got, last = json.loads(key.read_text())
                say(f"  {origin}→{d} {n} לילות: מהשמירה של היום ({len(got)} תאריכים)")
            else:
                if requests >= MAX_REQUESTS:
                    say("  עצרתי כאן כדי לא להעמיס על גוגל. אפשר לצמצם יעדים או אורכי חופשה ולהריץ שוב.")
                    partial = True
                    break
                try:
                    got, last = gf.calendar_year(origin, d, n, args.adults, args.stops, log=say)
                except gf.Blocked as e:
                    say(f"  גוגל ביקש הפסקה. ממשיך עם מה שכבר נסרק ({len(e.partial)} תאריכים).")
                    for r in e.partial:
                        r["nights"] = n
                    rows[d].extend(e.partial)
                    return rows, None, True, True
                requests += 7
                key.write_text(json.dumps([got, last]))
            for r in got:
                r["nights"] = n
            rows[d].extend(got)
            if last and (horizon is None or last > horizon):
                horizon = last
    return rows, horizon, partial, False


def main():
    ap = argparse.ArgumentParser(description="צייד הטיסות")
    ap.add_argument("--from", dest="origin", default="TLV")
    ap.add_argument("--to", required=True, help='יעד, כמה יעדים מופרדים בפסיק, או "anywhere" / "לאן שזול"')
    ap.add_argument("--nights", help="לילות: 4 או 3-5 או 4,6")
    ap.add_argument("--days", help="ימים כולל יום היציאה והחזרה: 5 = 4 לילות")
    ap.add_argument("--depart", help="ימי יציאה: חמישי,שישי")
    ap.add_argument("--return", dest="ret", help="ימי חזרה: ראשון,שני")
    ap.add_argument("--adults", type=int, default=1)
    ap.add_argument("--stops", choices=["any", "direct", "one"], default="any")
    ap.add_argument("--out", required=True)
    ap.add_argument("--open", action="store_true", help="לפתוח את הדף בדפדפן בסוף")
    ap.add_argument("--details", type=int, default=2, help="לכמה מהתאריכים הזולים להביא חברה ושעות (2 בקשות לכל אחד, 0 = בלי)")
    ap.add_argument("--dry-run", action="store_true", help="רק להדפיס מה הובן, בלי לסרוק")
    args = ap.parse_args()

    places, airports = load_places()
    origin = resolve(args.origin, places, airports, "נקודת יציאה")
    anywhere = args.to.strip().lower() in ("anywhere", "לאן שזול", "לכל מקום", "כל מקום", "הכי זול", "*")
    dests = [c for c in places["anywhere"] if c != origin] if anywhere else \
        [resolve(x, places, airports) for x in args.to.split(",") if x.strip()]
    dep, ret = parse_days(args.depart), parse_days(args.ret)
    nights = parse_nights(args.nights, args.days, dep, ret)
    if anywhere:
        gf.PAUSE = max(gf.PAUSE, 3.0)  # הרבה בקשות: לאט יותר
    if anywhere and len(nights) > 1:
        say(f"ביעד פתוח סורקים אורך אחד כדי לא להעמיס: {nights[0]} לילות.")
        nights = nights[:1]
    if dep and ret:  # מה שבאמת אפשרי עם האורכים שנשארו
        ret = {r for r in ret if any((d + n) % 7 == r for d in dep for n in nights)} or ret

    out = Path(args.out).expanduser()
    name = lambda c: places["places"].get(c, {}).get("he") or airports.get(c, [0, 0, c])[2]
    say(f"הבנתי: מ{name(origin)} אל {str(len(dests)) + ' יעדים פופולריים' if anywhere else ', '.join(name(d) for d in dests)}, "
        f"{' או '.join(str(n) for n in nights)} לילות"
        + (f", יציאה ב{'/'.join(DAYS_HE[d] for d in sorted(dep, key=IL))}" if dep else "")
        + (f", חזרה ב{'/'.join(DAYS_HE[d] for d in sorted(ret, key=IL))}" if ret else "")
        + (f", {args.adults} נוסעים" if args.adults > 1 else "") + (", רק ישירות" if args.stops == "direct" else ""))
    if args.dry_run:
        say(f"(בדיקה בלבד, בלי סריקה. בערך {len(dests) * len(nights) * 6} בקשות לגוגל בהרצה אמיתית.)")
        return
    (out / "cache").mkdir(parents=True, exist_ok=True)
    say("סורק את לוח המחירים של Google Flights, חלק אחרי חלק...")

    rows, horizon, partial, blocked = scan(origin, dests, nights, args, out / "cache")

    def ok(r):
        return (not dep or date.fromisoformat(r["out"]).weekday() in dep) and \
               (not ret or date.fromisoformat(r["back"]).weekday() in ret)

    per_dest = []
    for d in dests:
        el = [r for r in rows.get(d, []) if ok(r)]
        if not el:
            continue
        prices = [r["price"] for r in el]
        best = min(el, key=lambda r: (r["price"], r["out"]))
        per_dest.append({"code": d, "name": name(d), "country": places["places"].get(d, {}).get("country", ""),
                         "best": best, "avg": round(statistics.mean(prices)), "median": round(statistics.median(prices)),
                         "max": max(prices), "count": len(el)})
    if not per_dest:
        if blocked:
            say("\nגוגל ביקש הפסקה לפני שנאסף מספיק. זה זמני ולא נוגע בחשבון שלך: מחכים 30 דקות ומריצים שוב את אותה פקודה.")
            sys.exit(2)
        say("\nלא נמצאו טיסות שמתאימות לימים שביקשת. אפשר לנסות ימים אחרים או אורך אחר.")
        sys.exit(3)
    per_dest.sort(key=lambda x: x["best"]["price"])
    win = per_dest[0]
    W = win["code"]

    elig = sorted([r for r in rows[W] if ok(r)], key=lambda r: (r["price"], r["out"]))
    top, seen = [], set()
    for r in elig:
        if r["out"] in seen:
            continue
        seen.add(r["out"])
        top.append(dict(r))
        if len(top) == 5:
            break
    for r in top:
        r["links"] = gf.booking_links(origin, W, r["out"], r["back"], args.adults)
        r["label"] = f"{he_date(r['out'])} עד {he_date(r['back'])}"

    if args.details > 0 and not blocked:
        say("בודק חברות ושעות לתאריכים הזולים...")
        for r in top[:args.details]:
            try:
                r["out_flights"] = gf.day_flights(origin, W, r["out"], args.adults, args.stops, top=2)
                r["back_flights"] = gf.day_flights(W, origin, r["back"], args.adults, args.stops, top=2)
            except gf.Blocked:
                say("  גוגל ביקש הפסקה, ממשיך בלי פרטי הטיסות.")
                break
            except Exception as e:  # פרטים הם תוספת; לא מפילים בגללם את התוצאה
                say(f"  לא הצלחתי למשוך פרטים ל-{r['out']}: {type(e).__name__}")

    # לוח של 365 יום: לכל יום יציאה, המחיר הזול באורכי החופשה שביקשת
    today = date.today()
    by_day = {}
    for r in rows[W]:
        cur = by_day.get(r["out"])
        if cur is None or r["price"] < cur["price"]:
            by_day[r["out"]] = {"price": r["price"], "back": r["back"], "nights": r["nights"]}
    cal = []
    for i in range(1, 366):
        d = (today + timedelta(days=i)).isoformat()
        x = by_day.get(d)
        cal.append({"d": d, "p": x["price"] if x else None, "ok": bool(x) and ok({"out": d, "back": x["back"]}),
                    "future": horizon is not None and d > horizon})
    months = {}
    for r in elig:
        m = r["out"][:7]
        if m not in months or r["price"] < months[m]["price"]:
            months[m] = {"price": r["price"], "out": r["out"], "back": r["back"]}

    o_ap, w_ap = airports.get(origin), airports.get(W)
    result = {
        "checked_at": datetime.now().astimezone().isoformat(timespec="minutes"),
        "source": "Google Flights, לוח המחירים הציבורי (GetCalendarGraph)",
        "currency": "ILS",
        "query": {"origin": origin, "origin_name": name(origin), "dests": dests, "anywhere": anywhere,
                  "nights": nights, "depart": sorted(dep), "return": sorted(ret),
                  "depart_he": [DAYS_HE[d] for d in sorted(dep, key=IL)], "return_he": [DAYS_HE[d] for d in sorted(ret, key=IL)],
                  "adults": args.adults, "stops": args.stops},
        "origin_geo": o_ap[:2] if o_ap else None,
        "dest_geo": {d["code"]: airports[d["code"]][:2] for d in per_dest if d["code"] in airports},
        "winner": {"code": W, "name": win["name"], "country": win["country"], "price": win["best"]["price"],
                   "avg": win["avg"], "median": win["median"], "max": win["max"], "count": win["count"],
                   "saving_vs_avg": round(win["avg"] - win["best"]["price"]),
                   "saving_vs_max": round(win["max"] - win["best"]["price"])},
        "top": top,
        "destinations": per_dest,
        "calendar": cal,
        "months": dict(sorted(months.items())),
        "horizon": horizon,
        "scanned_days": len(by_day),
        "partial": partial,
        "disclaimer": "המחירים נלקחו מלוח המחירים של Google Flights בשעת הבדיקה, "
                      + ("למבוגר אחד" if args.adults == 1 else f"ל-{args.adults} נוסעים, כפי שגוגל מציג אותם") + " הלוך-חזור במחלקת תיירים, "
                      "ומשתנים כל הזמן. לפני הזמנה בודקים את המחיר הסופי באתר, כולל כבודה ומושבים.",
    }
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    import build_page
    page = build_page.build(result, out / "result.html")

    b = top[0]
    say("\n=== התוצאה ===")
    say(f"היעד: {win['name']}" + (f" (הזול מבין {len(per_dest)} יעדים)" if anywhere else ""))
    say(f"התאריך הכי זול: {b['label']} · {b['price']:,.0f} ₪ הלוך-חזור")
    say(f"ממוצע לאותם ימים בשנה הקרובה: {win['avg']:,} ₪ · חוסכים {result['winner']['saving_vs_avg']:,} ₪ מול הממוצע"
        f" ו-{result['winner']['saving_vs_max']:,} ₪ מול היקר ביותר")
    say("עוד תאריכים זולים:")
    for r in top[1:]:
        say(f"  {r['label']} · {r['price']:,.0f} ₪")
    if len(result["months"]) > 1:
        cm = sorted(result["months"].items(), key=lambda kv: kv[1]["price"])[:3]
        say("החודשים הכי זולים: " + " · ".join(f"{int(k[5:])}/{k[2:4]} מ-{v['price']:,.0f} ₪" for k, v in cm))
    if b.get("out_flights"):
        f = b["out_flights"][0]
        say(f"הטיסה בהלוך: {f['airline']} {f['dep']}→{f['arr']}, " + ("ישירה" if f["stops"] == 0 else "עצירה אחת" if f["stops"] == 1 else f"{f['stops']} עצירות"))
    if b.get("back_flights"):
        f = b["back_flights"][0]
        say(f"הטיסה בחזור: {f['airline']} {f['dep']}→{f['arr']}, " + ("ישירה" if f["stops"] == 0 else "עצירה אחת" if f["stops"] == 1 else f"{f['stops']} עצירות"))
    say(f"לטיסה ב-Google Flights (המסלול והתאריכים כבר מסומנים): {b['links']['google']}")
    say(f"נסרקו {result['scanned_days']} ימי יציאה, עד {he_date(horizon)} (מעבר לזה עוד אין מכירה)." if horizon else "")
    if partial:
        say("שימו לב: הסריקה חלקית, גוגל ביקש הפסקה באמצע. התאריכים שלמעלה הם הזולים מתוך מה שנסרק." if blocked
            else "שימו לב: הסריקה חלקית, חלק מהיעדים או מהחודשים לא נבדקו.")
        if blocked:
            say("כדי להשלים: מחכים 30 דקות ומריצים שוב. מה שנסרק עד ההפסקה לא נשמר, אז ההרצה הבאה מתחילה מחדש.")
    say(result["disclaimer"])
    say(f"\nהדף: {page}")
    if args.open:
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
