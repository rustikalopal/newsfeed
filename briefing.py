#!/usr/bin/env python3
"""
Morgenlage – tägliches Briefing-Skript.

Recherchiert einmal die wichtigsten Nachrichten (Politik, Weltwirtschaft,
Börse) über die Anthropic-API mit Web-Suche und schreibt ein fertiges
docs/briefing.json. Das Frontend lädt nur noch diese statische Datei.

Aufruf:  ANTHROPIC_API_KEY=... python briefing.py
"""

import os
import re
import sys
import json
import datetime
import locale

import anthropic

MODEL = os.environ.get("MORGENLAGE_MODEL", "claude-sonnet-4-6")
OUT_PATH = os.environ.get("MORGENLAGE_OUT", "docs/briefing.json")

RESSORTS = [
    {"id": "politik",    "label": "Politik & Welt",  "emoji": "🏛️",
     "feld": "globale Politik, internationale Beziehungen, Geopolitik"},
    {"id": "wirtschaft", "label": "Weltwirtschaft",  "emoji": "🌍",
     "feld": "Weltwirtschaft, Konjunktur, Notenbanken, Inflation, Handel"},
    {"id": "boerse",     "label": "Märkte & Börse",  "emoji": "📈",
     "feld": "Finanzmärkte, Aktienindizes, Anleihen, Rohstoffe, Kryptowährungen"},
]

PER_RESSORT = int(os.environ.get("MORGENLAGE_PER_RESSORT", "3"))


def german_date(d: datetime.date) -> str:
    """Langes deutsches Datum, mit Fallback ohne Locale."""
    try:
        locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
        return d.strftime("%A, %-d. %B %Y")
    except Exception:
        wd = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"][d.weekday()]
        mon = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"][d.month - 1]
        return f"{wd}, {d.day}. {mon} {d.year}"


def build_prompt(date_label: str) -> str:
    return f"""Du bist Redakteur eines hochwertigen täglichen Morgen-Briefings im Stil zwischen Nachrichtenagentur und Magazin. Heutiges Datum: {date_label}.

Recherchiere im Web die wichtigsten, global relevanten Nachrichten der letzten 24–48 Stunden für drei Ressorts:
- "politik": {RESSORTS[0]['feld']}
- "wirtschaft": {RESSORTS[1]['feld']}
- "boerse": {RESSORTS[2]['feld']}

Wähle pro Ressort die {PER_RESSORT} bedeutendsten Meldungen. Fasse jede Meldung KURZ und in EIGENEN Worten zusammen – keine wörtlichen Zitate, keine übernommenen Formulierungen. Schreibe für jede Meldung zusätzlich einen Hintergrund von 1–2 kurzen Absätzen (Kontext, knappe Vorgeschichte, mögliche Folgen).

Antworte AUSSCHLIESSLICH mit gültigem JSON, ohne Markdown, ohne Text davor oder danach:
{{"meldungen":[{{"ressort":"politik","titel":"prägnante Überschrift, max. 9 Wörter","zusammenfassung":"2 knappe Sätze","bedeutung":"ein Satz: warum es zählt","hintergrund":"1–2 kurze Absätze, Absätze durch Leerzeile getrennt","tag":"ein bis zwei Wörter Schlagwort","emoji":"ein einzelnes, inhaltlich passendes Emoji","quelle":"Hauptquelle"}}]}}"""


def extract_text(response) -> str:
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "\n".join(parts)


def salvage_objects(text: str):
    """Sammelt vollständige Objekte aus dem ersten JSON-Array – robust gegen
    abgeschnittene Antworten oder Zusatztext."""
    t = text.replace("```json", "").replace("```", "")
    start = t.find("[")
    if start < 0:
        return []
    out, depth, obj_start = [], 0, -1
    for i in range(start + 1, len(t)):
        c = t[i]
        if c == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and obj_start >= 0:
                try:
                    out.append(json.loads(t[obj_start:i + 1]))
                except json.JSONDecodeError:
                    pass
                obj_start = -1
        elif c == "]" and depth == 0:
            break
    return out


def parse_meldungen(text: str):
    items = salvage_objects(text)
    if items:
        return items
    # Notfall: ganzes Objekt
    t = text.replace("```json", "").replace("```", "").strip()
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        try:
            obj = json.loads(t[a:b + 1])
            if isinstance(obj.get("meldungen"), list):
                return obj["meldungen"]
        except json.JSONDecodeError:
            pass
    return []


def group(items):
    by_id = {r["id"]: [] for r in RESSORTS}
    for it in items:
        rid = str(it.get("ressort", "")).lower()
        if rid in by_id:
            by_id[rid].append(it)
    ressorts = []
    for r in RESSORTS:
        stories = []
        for i, a in enumerate(by_id[r["id"]][:PER_RESSORT]):
            stories.append({
                "id": f"{r['id']}-{i}",
                "titel": (a.get("titel") or "Ohne Titel").strip(),
                "zusammenfassung": (a.get("zusammenfassung") or "").strip(),
                "bedeutung": (a.get("bedeutung") or "").strip(),
                "hintergrund": (a.get("hintergrund") or "").strip(),
                "tag": (a.get("tag") or r["label"]).strip(),
                "emoji": (a.get("emoji") or r["emoji"]).strip(),
                "quelle": (a.get("quelle") or "").strip(),
            })
        ressorts.append({"id": r["id"], "label": r["label"],
                         "emoji": r["emoji"], "stories": stories})
    return ressorts


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEHLER: ANTHROPIC_API_KEY ist nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today = datetime.date.today()
    date_label = german_date(today)

    last_err = None
    items = []
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                messages=[{"role": "user", "content": build_prompt(date_label)}],
                tools=[{"type": "web_search_20250305",
                        "name": "web_search", "max_uses": 6}],
            )
            items = parse_meldungen(extract_text(response))
            if items:
                break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"Versuch {attempt + 1} fehlgeschlagen: {e}", file=sys.stderr)

    if not items:
        print(f"FEHLER: keine Meldungen erhalten. {last_err or ''}", file=sys.stderr)
        sys.exit(2)

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "datum": date_label,
        "ressorts": group(items),
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total = sum(len(r["stories"]) for r in payload["ressorts"])
    print(f"OK: {total} Meldungen geschrieben nach {OUT_PATH}")


if __name__ == "__main__":
    main()
