# Morgenlage – Backend + PWA

Tägliches Nachrichten-Briefing (Politik, Weltwirtschaft, Börse). Ein GitHub-Actions-Cron
holt morgens **einmal** die Schlagzeilen per RSS-Feed, lässt ein Sprachmodell die wichtigsten
auswählen und in eigenen Worten aufbereiten (inkl. „Warum es zählt" und „mehr"-Hintergrund),
und schreibt ein fertiges `docs/briefing.json`. Das statische Frontend (`docs/index.html`)
lädt nur noch diese Datei.

Dadurch: kein API-Key im Browser, öffentliches Hosting unbedenklich, App startet **sofort**,
die „mehr"-Hintergründe sind vorberechnet, und jede Meldung hat einen prüfbaren Quell-Link.

## So wird recherchiert (kostengünstig)

Statt des teuren agentischen Web-Search-Tools werden die Schlagzeilen per **RSS-Feed** seriöser
Quellen direkt in Python geholt (praktisch gratis). Das Modell bekommt nur eine kompakte
Kandidatenliste und wählt daraus aus – **ein einziger, kleiner Modell-Aufruf ohne Such-Tool**.
Das senkt die Kosten von ~30 Cent auf wenige Cent pro Lauf.

Die Quellen stehen oben in `briefing.py` in der Liste `FEEDS` und sind frei anpassbar/erweiterbar
(Format: `(ressort, feed-url, label)`). Standard sind international ausgewählte Feeds für global
relevante Abdeckung: BBC, The Guardian und Al Jazeera (Politik & Welt), BBC und The Guardian
(Weltwirtschaft) sowie CNBC (Märkte & Börse). Die Feeds sind überwiegend englischsprachig – die
Meldungen werden trotzdem auf Deutsch verfasst. Feed-URLs gelegentlich prüfen und bei Bedarf
austauschen. Beim Lauf wird im Log ausgegeben, wie viele Schlagzeilen je Feed geladen wurden –
so siehst du sofort, falls eine Quelle nicht mehr liefert.

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

2. **API-Key als Secret:** Repo → Settings → *Secrets and variables* → *Actions* → *New
   repository secret*: Name `ANTHROPIC_API_KEY`, Wert = dein Schlüssel.
   (Optional Variable `MORGENLAGE_MODEL`, Standard `claude-sonnet-4-6`. Noch günstiger:
   ein Haiku-Modell eintragen.)
   Ein Web-Search-Freischalten in der Console ist **nicht mehr nötig**, da kein Such-Tool
   verwendet wird.

3. **Schreibrechte für Actions:** Settings → Actions → General → *Workflow permissions* →
   „Read and write permissions" aktivieren (damit der Cron das JSON committen darf).

4. **GitHub Pages:** Settings → Pages → *Source: Deploy from a branch* → Branch `main`,
   Ordner `/docs`. Nach kurzer Zeit ist die Seite unter
   `https://DEINNAME.github.io/REPONAME/` erreichbar.

5. **Ersten Lauf auslösen:** Actions-Tab → „Morgenlage Briefing" → *Run workflow*.
   Danach enthält `docs/briefing.json` echte Inhalte.

6. **Aufs iPhone:** Die Pages-URL in **Safari** öffnen → Teilen → **Zum Home-Bildschirm**.
   Die App startet im Vollbild mit eigenem Icon – ganz ohne Anmeldung, da keine API im Client.

## Uhrzeit anpassen

Der Cron in `.github/workflows/briefing.yml` läuft in **UTC**:
`cron: "30 4 * * *"` ≈ 06:30 Uhr deutscher Sommerzeit. Für eine andere Uhrzeit den Wert ändern
(z. B. `0 5 * * *` = 05:00 UTC). GitHub-Cron kann sich um einige Minuten verzögern.

## Kosten

Pro Lauf nur **ein** kleiner Modell-Aufruf ohne Such-Tool – wenige Cent statt ~30. Die
RSS-Abrufe sind kostenlos. Weitere Stellschrauben: `MORGENLAGE_PER_RESSORT` (Meldungen je
Ressort), `MORGENLAGE_MAX_AGE_H` (max. Alter der Schlagzeilen in Stunden), und ein günstigeres
Modell über `MORGENLAGE_MODEL`.

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
