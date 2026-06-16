#!/usr/bin/env python3
"""
Morgenlage – tägliches Briefing (kostengünstige RSS-Variante).

Statt des teuren agentischen Web-Search-Tools werden die Schlagzeilen per
RSS-Feed seriöser Quellen in Python geholt (praktisch gratis). Das Modell
bekommt nur eine kompakte Kandidatenliste, wählt die wichtigsten Meldungen
und schreibt Zusammenfassung, "Warum es zählt" und "mehr"-Hintergrund.
Ein einziger, kleiner Modell-Aufruf – kein Such-Tool.

Aufruf:  ANTHROPIC_API_KEY=... python briefing.py
"""

import os
import re
import sys
import json
import html
import time
import datetime

import requests
import feedparser
import anthropic

MODEL = os.environ.get("MORGENLAGE_MODEL", "claude-sonnet-4-6")
OUT_PATH = os.environ.get("MORGENLAGE_OUT", "docs/briefing.json")
PER_RESSORT = int(os.environ.get("MORGENLAGE_PER_RESSORT", "3"))
MAX_AGE_H = int(os.environ.get("MORGENLAGE_MAX_AGE_H", "48"))
MAX_CANDIDATES = 10         # je Ressort an das Modell übergeben
USER_AGENT = "MorgenlageBot/1.0 (+https://github.com/)"

# --- Quellen je Ressort -----------------------------------------------------
# (ressort, feed-URL, Quellen-Label). Beliebig anpassbar/erweiterbar.
# International ausgewählt für global relevante Abdeckung. Feeds sind überwiegend
# englischsprachig – die Meldungen werden trotzdem auf Deutsch verfasst.
# Hinweis: Beim ersten Lauf zeigt das Log je Feed die Trefferzahl. Liefert eine
# Quelle 0, die URL hier austauschen.
FEEDS = [
    # Politik & Welt
    ("politik",    "https://feeds.bbci.co.uk/news/world/rss.xml",          "BBC"),
    ("politik",    "https://www.theguardian.com/world/rss",                "The Guardian"),
    ("politik",    "https://www.aljazeera.com/xml/rss/all.xml",            "Al Jazeera"),
    # Weltwirtschaft
    ("wirtschaft", "https://feeds.bbci.co.uk/news/business/rss.xml",       "BBC"),
    ("wirtschaft", "https://www.theguardian.com/business/rss",             "The Guardian"),
    # Märkte & Börse
    ("boerse",     "https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC"),
    ("boerse",     "https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC"),
    ("boerse",     "https://www.theguardian.com/business/rss",             "The Guardian"),
]

RESSORTS = [
    {"id": "politik",    "label": "Politik & Welt", "emoji": "🏛️"},
    {"id": "wirtschaft", "label": "Weltwirtschaft",  "emoji": "🌍"},
    {"id": "boerse",     "label": "Märkte & Börse",  "emoji": "📈"},
]
RLABEL = {r["id"]: r["label"] for r in RESSORTS}


def german_date(d):
    wd = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][d.weekday()]
    mon = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"][d.month - 1]
    return f"{wd}, {d.day}. {mon} {d.year}"


def clean(text, limit=280):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = html.unescape(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def collect_candidates():
    """Holt RSS-Feeds, baut je Ressort eine Kandidatenliste mit eindeutiger id."""
    now = time.time()
    per_ressort = {r["id"]: [] for r in RESSORTS}
    seen_titles = set()
    next_id = 1

    for ressort, url, source in FEEDS:
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:  # noqa: BLE001
            print(f"WARN: Feed nicht ladbar ({url}): {e}", file=sys.stderr)
            continue

        loaded = 0
        for entry in feed.entries:
            title = clean(getattr(entry, "title", ""), 200)
            if not title or title.lower() in seen_titles:
                continue
            # Aktualität prüfen (falls Datum vorhanden)
            pp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
            if pp:
                age_h = (now - time.mktime(pp)) / 3600.0
                if age_h > MAX_AGE_H:
                    continue
            per_ressort[ressort].append({
                "id": next_id,
                "ressort": ressort,
                "title": title,
                "summary": clean(getattr(entry, "summary", ""), 280),
                "source": source,
                "link": getattr(entry, "link", ""),
            })
            seen_titles.add(title.lower())
            next_id += 1
            loaded += 1
        print(f"  {ressort}: {loaded} Schlagzeilen aus {url}", file=sys.stderr)

    for rid in per_ressort:
        per_ressort[rid] = per_ressort[rid][:MAX_CANDIDATES]
    return per_ressort


def build_prompt(date_label, per_ressort):
    blocks = []
    for r in RESSORTS:
        lines = [f"[{r['label'].upper()}]"]
        for c in per_ressort[r["id"]]:
            snippet = f" – {c['summary']}" if c["summary"] else ""
            lines.append(f"[{c['id']}] {c['title']}{snippet} (Quelle: {c['source']})")
        if len(lines) == 1:
            lines.append("(keine Kandidaten)")
        blocks.append("\n".join(lines))
    candidates = "\n\n".join(blocks)

    return f"""Du bist Redakteur eines hochwertigen täglichen Morgen-Briefings im Stil zwischen Nachrichtenagentur und Magazin. Heutiges Datum: {date_label}.

Unten stehen aktuelle Schlagzeilen-Kandidaten aus seriösen internationalen Quellen, nach Ressort gruppiert. Die Kandidaten können englischsprachig sein – verfasse die Meldungen dennoch durchgängig auf DEUTSCH. Wähle pro Ressort die {PER_RESSORT} wichtigsten und global relevantesten aus (Vorrang für Themen mit weltweiter Bedeutung, nicht rein lokale Einzelfälle) und verfasse daraus die Meldungen. Verwende KEINE Schlagzeile doppelt – auch nicht zwischen Wirtschaft und Börse. Für "boerse" bevorzuge Themen zu Märkten, Indizes, Zinsen, Rohstoffen; für "wirtschaft" die breitere Konjunktur.

KANDIDATEN:
{candidates}

Schreibe alles in EIGENEN Worten – keine wörtlichen Zitate. Antworte AUSSCHLIESSLICH mit gültigem JSON, ohne Markdown, ohne Text davor oder danach:
{{"meldungen":[{{"ressort":"politik","ref":12,"titel":"prägnante Überschrift, max. 9 Wörter","zusammenfassung":"2 knappe Sätze","bedeutung":"ein Satz: warum es zählt","hintergrund":"1–2 kurze Absätze, Absätze durch Leerzeile getrennt","tag":"ein bis zwei Wörter Schlagwort","emoji":"ein einzelnes, inhaltlich passendes Emoji"}}]}}

"ref" ist die Nummer [n] der zugrunde liegenden Schlagzeile, damit die Originalquelle verlinkt werden kann."""


def extract_text(response):
    return "\n".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text")


def salvage_objects(text):
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


def parse_meldungen(text):
    items = salvage_objects(text)
    if items:
        return items
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


def build_output(items, per_ressort):
    by_id = {c["id"]: c for cs in per_ressort.values() for c in cs}
    grouped = {r["id"]: [] for r in RESSORTS}
    for it in items:
        rid = str(it.get("ressort", "")).lower()
        if rid in grouped:
            grouped[rid].append(it)

    ressorts = []
    for r in RESSORTS:
        stories = []
        for i, a in enumerate(grouped[r["id"]][:PER_RESSORT]):
            cand = by_id.get(a.get("ref"))
            stories.append({
                "id": f"{r['id']}-{i}",
                "titel": (a.get("titel") or (cand["title"] if cand else "Ohne Titel")).strip(),
                "zusammenfassung": (a.get("zusammenfassung") or "").strip(),
                "bedeutung": (a.get("bedeutung") or "").strip(),
                "hintergrund": (a.get("hintergrund") or "").strip(),
                "tag": (a.get("tag") or r["label"]).strip(),
                "emoji": (a.get("emoji") or r["emoji"]).strip(),
                "quelle": cand["source"] if cand else (a.get("quelle") or "").strip(),
                "quelle_url": cand["link"] if cand else "",
            })
        ressorts.append({"id": r["id"], "label": r["label"], "emoji": r["emoji"], "stories": stories})
    return ressorts


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEHLER: ANTHROPIC_API_KEY ist nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    print("Hole RSS-Schlagzeilen …", file=sys.stderr)
    per_ressort = collect_candidates()
    total_cand = sum(len(v) for v in per_ressort.values())
    if total_cand == 0:
        print("FEHLER: keine Schlagzeilen geladen – Feed-URLs prüfen.", file=sys.stderr)
        sys.exit(2)

    today = datetime.date.today()
    date_label = german_date(today)
    client = anthropic.Anthropic(api_key=api_key)

    items = []
    last_err = None
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=6000,
                messages=[{"role": "user", "content": build_prompt(date_label, per_ressort)}],
            )
            items = parse_meldungen(extract_text(response))
            if items:
                break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"Versuch {attempt + 1} fehlgeschlagen: {e}", file=sys.stderr)

    if not items:
        print(f"FEHLER: keine Meldungen erzeugt. {last_err or ''}", file=sys.stderr)
        sys.exit(3)

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "datum": date_label,
        "ressorts": build_output(items, per_ressort),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    total = sum(len(r["stories"]) for r in payload["ressorts"])
    print(f"OK: {total} Meldungen geschrieben nach {OUT_PATH}")


if __name__ == "__main__":
    main()
