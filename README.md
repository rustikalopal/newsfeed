# Morgenlage – Backend + PWA

Tägliches Nachrichten-Briefing (Politik, Weltwirtschaft, Börse). Ein GitHub-Actions-Cron
recherchiert morgens **einmal** über die Anthropic-API mit Web-Suche, schreibt ein fertiges
`docs/briefing.json`, und das statische Frontend (`docs/index.html`) lädt nur noch diese Datei.

Dadurch: kein API-Key im Browser, öffentliches Hosting unbedenklich, App startet **sofort**,
und die „mehr"-Hintergründe sind vorberechnet.

```
briefing.py                  Recherche-Skript  -> docs/briefing.json
requirements.txt
.github/workflows/briefing.yml   Cron + Commit
docs/
  index.html                 Frontend (lädt briefing.json)
  manifest.json  icon-192.png  icon-512.png
  briefing.json              wird täglich überschrieben
```

## Einrichtung (einmalig)

1. **Repo anlegen** und alle Dateien hochladen (Struktur beibehalten).

2. **Web-Suche aktivieren:** In der Anthropic Console muss das Web-Search-Tool für deine
   Organisation freigeschaltet sein (Console → Settings). Sonst schlägt der Aufruf fehl.

3. **API-Key als Secret:** Repo → Settings → *Secrets and variables* → *Actions* → *New
   repository secret*: Name `ANTHROPIC_API_KEY`, Wert = dein Schlüssel.
   (Optional Variable `MORGENLAGE_MODEL`, Standard ist `claude-sonnet-4-6`.)

4. **Schreibrechte für Actions:** Settings → Actions → General → *Workflow permissions* →
   „Read and write permissions" aktivieren (damit der Cron das JSON committen darf).

5. **GitHub Pages:** Settings → Pages → *Source: Deploy from a branch* → Branch `main`,
   Ordner `/docs`. Nach kurzer Zeit ist die Seite unter
   `https://DEINNAME.github.io/REPONAME/` erreichbar.

6. **Ersten Lauf auslösen:** Actions-Tab → „Morgenlage Briefing" → *Run workflow*.
   Danach enthält `docs/briefing.json` echte Inhalte.

7. **Aufs iPhone:** Die Pages-URL in **Safari** öffnen → Teilen → **Zum Home-Bildschirm**.
   Die App startet im Vollbild mit eigenem Icon – ganz ohne Anmeldung, da keine API im Client.

## Uhrzeit anpassen

Der Cron in `.github/workflows/briefing.yml` läuft in **UTC**:
`cron: "30 4 * * *"` ≈ 06:30 Uhr deutscher Sommerzeit. Für eine andere Uhrzeit den Wert ändern
(z. B. `0 5 * * *` = 05:00 UTC). GitHub-Cron kann sich um einige Minuten verzögern.

## Kosten

Jeder Lauf ist ein API-Aufruf mit Web-Suche – pro Aufruf abgerechnet (Tokens + Suchen).
Bei einmal täglich ist das sehr gering, aber nicht null. Über die Variable
`MORGENLAGE_PER_RESSORT` lässt sich die Anzahl der Meldungen pro Ressort steuern.

## Lokal testen

```bash
pip install -r requirements.txt
ANTHROPIC_API_KEY=sk-... python briefing.py
# erzeugt docs/briefing.json; dann docs/ lokal mit einem Webserver öffnen:
python -m http.server -d docs 8000   # http://localhost:8000
```

## Später erweiterbar

- **Echte Fotos:** Im `briefing.py` pro Meldung ein Bild über Pexels/Unsplash-API holen
  (Key als weiteres Secret), URL ins JSON schreiben, im Frontend rendern.
- **Zustellung:** Im Workflow nach dem Briefing eine E-Mail/Push verschicken.
