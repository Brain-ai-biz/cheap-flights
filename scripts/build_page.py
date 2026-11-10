#!/usr/bin/env python3
"""בונה את result.html מתוך result.json: קובץ אחד שעובד בלי רשת, עם הפונט והמפה בפנים.

  python3 build_page.py RESULT.json [OUT.html]
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def build(result: dict, out: Path) -> Path:
    html = (ASSETS / "result.html").read_text(encoding="utf-8")
    font = lambda n: base64.b64encode((ASSETS / n).read_bytes()).decode()
    data = json.dumps(result, ensure_ascii=False).replace("</", "<\\/")
    html = (html.replace("__FONT_HE__", font("rubik-hebrew.woff2"))
                .replace("__FONT_LA__", font("rubik-latin.woff2"))
                .replace("__TITLE__", result["winner"]["name"])
                .replace("/*__DATA__*/null", data)
                .replace("/*__LAND__*/[]", (ASSETS / "land.json").read_text()))
    out = Path(out).expanduser().resolve()
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name("result.html")
    print(build(json.loads(src.read_text(encoding="utf-8")), dst))
