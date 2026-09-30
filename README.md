# Stickatelier

Lokale Motivvorbereitung für Illustrationen und Logos, als Docker-Webapp für Ubuntu. Die fertige Grafik wird anschließend in BERNINA Embroidery Software 9 Creator digitalisiert.

## Schnellstart auf Ubuntu

Voraussetzung: Docker Engine mit Compose-Plugin und SSH-Zugang zum Host. Das Paket entpacken, in den Ordner wechseln und ausführen:

```bash
umask 077
python3 -c "from getpass import getpass; from pathlib import Path; p=getpass('Atelier-Kennwort (8–256 Zeichen): '); assert 8 <= len(p) <= 256, 'Kennwortlänge ungültig'; Path('password.txt').write_text(p, encoding='utf-8')"
chmod 600 password.txt
sudo chown 10001:10001 password.txt
docker compose up -d --build
docker compose ps
```

Auf dem PC mit dem Browser einen SSH-Tunnel öffnen (BENUTZER und UBUNTU-HOST durch eure Zugangsdaten ersetzen):

```bash
ssh -N -L 8080:127.0.0.1:8080 -L 1455:127.0.0.1:1455 BENUTZER@UBUNTU-HOST
```

Das Terminal bleibt offen. Im Browser **http://127.0.0.1:8080** öffnen und mit dem eben festgelegten Atelier-Kennwort anmelden. Der zweite Port wird nur für die optionale ChatGPT-Anmeldung gebraucht. Ohne KI reicht die Weiterleitung von Port 8080. Die Standardkonfiguration veröffentlicht die App auf dem Ubuntu-Host nur auf Loopback. Port 1455 bleibt immer auf Loopback.

Für direkten Zugriff im Heimnetz kann die erste Portzuordnung in `compose.yaml` durch `"8080:8080"` ersetzt und `ATELIER_HOSTS` auf die tatsächlich verwendeten Hostnamen/IPs gesetzt werden. Bei Zugriff über das Netzwerk HTTPS über einen Reverse Proxy verwenden: Das Kennwort schützt den Zugang, HTTP verschlüsselt die Übertragung nicht. Die ChatGPT-Erstanmeldung über `127.0.0.1:8080` und beide SSH-Weiterleitungen durchführen.

## Kennwortschutz

Ein gemeinsames Atelier-Kennwort schützt die Seite, Projekte, Bilder und sämtliche Arbeits- und KI-APIs. Nur die Anmeldeoberfläche, ihre Gestaltung und der minimale Healthcheck bleiben ohne Anmeldung erreichbar. Es gibt keine einzelnen Benutzerkonten oder getrennten Projektbereiche; angemeldete Personen sehen dieselben Projekte und dieselbe ChatGPT-Verbindung.

`password.txt` wird von Docker Compose als Secret-Datei eingebunden. Das Kennwort gehört weder ins Docker-Image noch in Git, Bundle oder ZIP. Auf dem Host liegt die Datei im Klartext; deshalb die im Schnellstart gezeigten Dateirechte verwenden. Die Eigentümer-ID 10001 entspricht dem Anwendungsbenutzer im Container, damit dieser die geschützte Datei lesen kann. Ohne gültige Kennwortdatei startet die Anwendung nicht. Für einen eigenen Dateipfad `ATELIER_PASSWORD_FILE` setzen.

Die Anwendung hält nur einen mit PBKDF2-SHA256 abgeleiteten Kennwortwert im Arbeitsspeicher. Nach der Anmeldung wird die Sitzungskennung erneuert. Sitzungen enden nach zwölf Stunden, bei „Abmelden“ oder beim Neustart. Abmelden trennt die gespeicherte ChatGPT-Verbindung nicht. Nach fünf falschen Kennwörtern innerhalb von fünf Minuten werden weitere Anmeldeversuche derselben Verbindungs-IP bis zum Ende dieses Zeitfensters abgewiesen. Hinter einem Reverse Proxy teilen sich die Zugriffe diese Begrenzung; ungesicherte Forwarded-Header werden nicht als vertrauenswürdige IP übernommen.

Das Session-Cookie ist `HttpOnly` und `SameSite=Lax`. Für einen ausschließlich über HTTPS erreichbaren Betrieb `ATELIER_COOKIE_SECURE: "true"` setzen. Für den dokumentierten lokalen HTTP-SSH-Tunnel bleibt der Wert `"false"`.

Zum Ändern des Kennworts zuerst mit `sudo chown "$(id -u):$(id -g)" password.txt` den Schreibzugriff für euren Host-Benutzer herstellen. Dann Eingabe, Dateirechte und Eigentümer aus dem Schnellstart wiederholen und `docker compose up -d --force-recreate` ausführen. Alle bisherigen Sitzungen werden dadurch ungültig. Eine Wiederherstellung über E-Mail ist nicht vorgesehen; der Host-Zugang erlaubt das Ersetzen der Kennwortdatei.

## Ohne KI arbeiten

1. Bild öffnen oder das technische Testmotiv laden. Unterstützt: PNG, JPG, WEBP, BMP; maximal 20 MB und 24 Millionen Pixel. SVG-Import ist in dieser Version noch nicht enthalten. Vorhandene SVGs deshalb zunächst als PNG rasterisieren.
2. „Logo“ oder „Illustration“ wählen. Logo startet mit ausgeschalteter Glättung, Kleinstflächenfilterung und Verbreiterung. Der Modus sperrt keine Regionen: Anpassungen können auch Text verändern.
3. **Lange Seite des Motivs** zwischen 10 und 260 mm einstellen. Im Hochformat bestimmt der Wert die Höhe, im Querformat die Breite, bei quadratischen Motiven beide Seiten. Die kürzere Seite folgt proportional: 160 mm ergeben bei einem 1:2-Motiv 80 × 160 mm, bei einem 2:1-Motiv 160 × 80 mm. Die Größe bezieht sich auf die gesamte Bildfläche einschließlich vorhandener Ränder. Die Zielgröße unter der Vorschau aktualisiert sich sofort, auch ohne Live-Vorschau. Die Ansicht passt das Motiv weiterhin an das Fenster an; sie zeigt keine reale Zentimetergröße am Bildschirm. Ungültige Werte wie 400 mm zeigen einen Hinweis und sperren Vorschau, Export und KI-Aufträge bis zur Korrektur. Das Tool skaliert die Geometrie nicht unterschiedlich in Breite und Höhe.
4. Maximale Farbanzahl einstellen. Keine Rasterung/Dithering, keine halbtransparenten Randpixel. Gezählt werden sichtbare Motivfarben; vollständig transparente Bereiche belegen keine Farbe. Wenn die sichtbare Grafik bereits innerhalb der Farbgrenze liegt, bleiben ihre exakten RGB-Farben bei der Farbreduktion erhalten – auch sehr kleine Farbakzente. Glättung, Kontrast oder Größenanpassung können davor bereits Farben ändern.
5. Weitere Regler verwenden:
   - **Glättung:** Medianfilter gegen Rauschen; Stärke wird näherungsweise an die physische Bildgröße angepasst.
   - **Kleine Farbflächen:** zusammenhängende Farbflächen unter `(Reglerwert in mm)²` werden in die häufigste Nachbarfarbe überführt; isolierte Flecken können transparent werden. Das garantiert keine Mindeststrichbreite. Nicht jeder Rest einer Fläche verschwindet durch einmalige Nachbarzuweisung.
   - **Dunkle Details verbreitern:** vergrößert bereits vorhandene dunkle Bereiche; erzeugt keine neue automatische Außenkontur. Bei Schrift vorsichtig einsetzen.
   - **Kontrast:** vor der Farbreduktion.
   - **Hintergrund:** entfernt passende Farbflächen, die mit dem Bildrand verbunden sind. Geschlossene Innenräume, z. B. das Innere eines Buchstabens, bleiben erhalten. Bestehende PNG-Transparenz bleibt grundsätzlich nutzbar; ihre Alpha-Kante wird auf transparent/undurchsichtig reduziert.
   - **Hintergrund-Pipette:** „Hintergrund entfernen“ einschalten und „Pipette: Farbe aufnehmen“ aktivieren. Danach einen sichtbaren Bildpunkt oder eine Palettenfarbe anklicken. Im Vergleich wird die Farbe aus der angeklickten Original- oder Ergebnisseite aufgenommen. Transparente Bereiche werden übersprungen; Esc oder „Beenden“ bricht ab. Bei ausgeschalteter Live-Vorschau anschließend „Vorschau aktualisieren“ verwenden. Die Farbtoleranz gilt weiterhin; eine Palettenfarbe kann durch die Farbreduktion vom Original abweichen.
6. Vorher/nachher vergleichen. Mit ausgeschalteter Live-Vorschau „Vorschau aktualisieren“ klicken. Export ist erst möglich, wenn die Vorschau zu den aktuellen Einstellungen passt. Beim Verstellen werden überholte Vorschauanfragen im Browser abgebrochen; eine auf dem Host bereits laufende Berechnung kann trotzdem noch bis zu ihrem Ende laufen.
7. **Palette nachbearbeiten:** Eine Farbe anklicken und im Dialog eine neue Farbe über Farbwähler oder Hex-Wert angeben. „Farbe übernehmen“ färbt alle zugehörigen Flächen um. Eine bereits zusammengefasste Farbe lässt sich ebenfalls gemeinsam umfärben.
   **Farbe lokalisieren:** Unter jedem Paletteneintrag „Lokalisieren“ wählen. Alle sichtbaren Pixel dieser Farbe werden im vorbereiteten Bild mit der frei wählbaren „Indikatorfarbe“ hervorgehoben. Das Tool wechselt dafür zur Ergebnisansicht und stellt nach „Markierung ausblenden“, einem erneuten Klick auf denselben Eintrag oder Esc die vorige Ansicht wieder her. Ein Wechsel der Ansicht oder der Bildregler beendet die Markierung. Die Markierung ist eine Anzeigehilfe und verändert weder Motivfarben noch Export. Auch nach Umfärben oder Zusammenfassen wird die aktuelle sichtbare Farbe markiert.
8. **Farben bewusst zusammenfassen:** „Farben zusammenfassen“ aktivieren, zuerst die **Zielfarbe** anklicken, dann die Farbe, die sie übernehmen soll. Die erste Farbe bleibt exakt erhalten; die zweite verschwindet aus der Palette, ihre Pixelanteile werden addiert. Erneuter Klick auf die Zielfarbe hebt deren Auswahl auf. „Zusammenfassen abbrechen“ beendet den Modus ohne Änderung.
9. „Rückgängig“ nimmt jeweils die letzte Farbänderung zurück. „Farbänderungen zurücksetzen“ entfernt alle manuellen Zuordnungen. Die Farbaktionen aktualisieren das Bild auch bei ausgeschalteter Live-Vorschau direkt. Während einer veralteten Vorschau ist die Palettenbearbeitung gesperrt.
10. Vorlage als ZIP exportieren. Originale und exportierte Varianten bleiben auf dem Host gespeichert. Die letzten Projekte können erneut geöffnet werden; Reglereinstellungen und Farbzuordnungen können aus dem Export nachvollzogen werden, ein automatischer Einstellungsimport fehlt noch.

Bei manueller Farbbearbeitung wird die Basispalette fixiert, damit Vorschau und Export dieselben Farbzuordnungen verwenden. Änderungen an den Bildreglern, der Wechsel der Motivart, „Zurücksetzen“ und das Übernehmen eines KI-Vorschlags berechnen die Palette neu und setzen manuelle Farbänderungen mit einem Hinweis zurück. Bei erneutem Öffnen eines Projekts werden die Farbzuordnungen nicht automatisch geladen. Mehrfachänderungen können innerhalb der aktuellen Bearbeitung schrittweise rückgängig gemacht werden.

### Export und Creator 9

Das ZIP enthält:

- `motiv-vorbereitet.png`: transparente Grafik, maximal 2.400 Pixel an der längsten Kante, ohne Hochskalieren kleiner Vorlagen. Eine DPI-Angabe beschreibt die Zielgröße.
- `einstellungen.json`: Einstellungen, tatsächliche Palette und Zielgröße des Exports.
- `creator-9-hinweise.txt`: Farbübersicht und kurzer Importablauf.

Creator: **Insert Artwork → Zielgröße ausdrücklich einstellen → Prepare Bitmap prüfen → Auto-Digitize oder Magic Wand → Stichplanung korrigieren → Probestick**. Transparente Bereiche nicht mitsticken. Das Tool erzeugt keine ART-/EXP-/PES-Stichdateien und kann Stoff, Garn, Dichte, Unterlagen und Zugausgleich nicht abschließend beurteilen. Pixelanteile sind kein Garnverbrauch.

Die Vorschau wird bei maximal 1.200 Pixeln berechnet; beim Export mit bis zu 2.400 Pixeln erfolgt eine neue Berechnung. Sehr kleine Details und Flächenanteile können sich deshalb etwas unterscheiden. Ohne manuelle Farbänderungen kann sich auch die automatisch ermittelte Palette unterscheiden; bei aktiver Farbbearbeitung bleiben die Basispalette und ihre Zuordnungen fixiert. Die Exportübersicht enthält die tatsächlichen Exportwerte. Die Originaldatei wird nie durch Filter überschrieben, beim Speichern als PNG jedoch von Metadaten befreit.

## KI-Werkstatt mit ChatGPT Plus

Implementiert ist die offizielle **Sign in with ChatGPT**-Anbindung für berechtigte persönliche/lokal betriebene Clients. Sie verwendet OAuth mit PKCE, State, Nonce und verifizierter OpenAI-Identität; keine Cookies aus ChatGPT, keine privaten Backend-Endpunkte und keinen API-Key. Eine feste Host-ID bleibt im Datenvolume erhalten. Die App verwendet die für das Konto gelieferte Modellliste.

1. Beide SSH-Weiterleitungen starten und die Oberfläche über `http://127.0.0.1:8080` öffnen (nicht `localhost`).
2. „ChatGPT verbinden“ und „Continue with ChatGPT“ wählen.
3. Bei OpenAI anmelden und der Tarifnutzung zustimmen. Im Rücksprungfenster wird das Ergebnis angezeigt.
4. Im Atelier „Verbindungsstatus aktualisieren“ wählen und ein verfügbares bildfähiges Modell auswählen.
5. Über **KI-Werkstatt → Analysieren** das Motiv öffnen, Wunsch eingeben und **Motiv analysieren** klicken. Nur dieser Schritt überträgt Original und mit den aktuellen Einstellungen vorbereitete Grafik als zwei maximal 768 px große Bildkopien, Reglerwerte, tatsächliche Palette, Zielgröße und euren Wunsch an OpenAI. Er nutzt das freigegebene ChatGPT-Kontingent. Das ausgewählte Modell muss Bildeingaben unterstützen; die Kontomodellliste garantiert dies nicht für jedes Modell.
6. Beobachtungen, Hinweise und konkrete Regleränderungen prüfen. **Reglervorschlag ansehen** berechnet eine lokale Vorschau, ohne eure aktuellen Einstellungen zu ändern. Erst danach wird **Regler übernehmen** freigeschaltet. Die KI darf Farbgrenze und Zielgröße nicht erhöhen bzw. verändern. Beim Übernehmen werden manuelle Farbzuordnungen zurückgesetzt. **Bildbearbeitung vorbereiten** übernimmt den vorgeschlagenen Bearbeitungswunsch in den entsprechenden Bereich; es startet keine automatische Bildgenerierung.

Die offizielle Vorschau unterstützt auf dieser Route **keine Bildgenerierung oder generative Bildbearbeitung**. Für diese Aufgaben nutzt diese Version deshalb den folgenden manuellen ChatGPT-Plus-Ablauf. Das Tool enthält keine separat abgerechnete API-Key-Anbindung. Die Benutzeroberfläche zeigt keine erfundene Restguthabenanzeige. Tarifberechtigung, Credits und Limits werden von OpenAI verwaltet.

### Vorhandenes Bild bearbeiten

1. Motiv laden, gewünschte Farbgrenze und lange Seite einstellen. Bei Bedarf bereits die Palette manuell anpassen.
2. **KI-Werkstatt → Bild bearbeiten** öffnen und den Änderungswunsch beschreiben. Als Referenz das Originalbild oder die vorbereitete Grafik mit euren Farben wählen. Schrift-/Geometrieerhalt und den Wunsch nach einem transparenten Hintergrund einstellen.
3. **Bildbearbeitung für ChatGPT vorbereiten** klicken. Das Atelier erstellt lokal eine Anweisung und eine PNG-Referenz mit höchstens 2.048 px. Die Farbgrenze, lange Seite und bei der vorbereiteten Grafik die tatsächlichen Referenzfarben werden berücksichtigt. Dieser Schritt ruft kein KI-Modell auf und lädt nichts zu OpenAI hoch.
4. **Anweisung kopieren**, **Referenzbild herunterladen**, dann **ChatGPT öffnen**. In ChatGPT die Anweisung einfügen und das heruntergeladene Bild anhängen. Dort die Bearbeitung ausführen lassen und das Ergebnis als PNG herunterladen.
5. Im Atelier **ChatGPT-Ergebnis laden** verwenden. Der Import erzeugt eine eigene Variante, verknüpft sie mit der Ausgangsvorlage und übernimmt Farbgrenze und lange Seite aus dem vorbereiteten Auftrag. Die übrigen Bildfilter starten neutral. **Ausgangsvorlage** öffnet wieder das ursprüngliche Bild. Der ursprüngliche Bildinhalt wird nicht überschrieben.
6. Die Variante mit Reglern und Palette kontrollieren und für Creator 9 exportieren. ChatGPT kann Schrift, Konturen oder Transparenz anders als gewünscht darstellen; die Anweisung ist keine Garantie für exakte Geometrie oder Farben.

### Neues Motiv generieren

1. **KI-Werkstatt → Neues Motiv** funktioniert auch ohne vorhandenes Bild. Farbgrenze und lange Seite einstellen, Motiv beschreiben und Illustration, Emblem oder Logo wählen.
2. **Motiv-Anweisung für ChatGPT vorbereiten** erstellt lokal die passende Anweisung. **Anweisung kopieren** und **ChatGPT öffnen** verwenden; dort das neue Bild erzeugen lassen und als PNG herunterladen.
3. **ChatGPT-Ergebnis laden** erzeugt ein neues Projekt ohne Ausgangsvorlage. Anschließend stehen dieselben manuellen Regler, Palette und Exporte zur Verfügung.

Für die lokale Vorbereitung und den Ergebnisimport ist keine OAuth-Anmeldung im Atelier nötig. Die Bildgenerierung/-bearbeitung wird von euch im ChatGPT-Fenster ausgeführt und unterliegt dort eurem Tarif. Es gibt keine automatische Übergabe, kein automatisches Auslesen von ChatGPT, keinen zusätzlichen API-Key und keine versteckten API-Aufrufe. Anweisungen und noch nicht importierte Aufträge bestehen nur in der aktuellen Browseransicht; vor dem Schließen bei Bedarf kopieren. Importierte Motive und ihre Variantenbeziehung bleiben auf dem Host erhalten.

Die Anmeldung und KI-Inferenz sind implementiert, aber ohne eine Anmeldung mit eurem Konto **nicht Ende zu Ende verifiziert**. Die Bildverarbeitung benötigt diese Verbindung nicht. Ist die OAuth-Vorschau für das Konto nicht freigeschaltet oder ändert OpenAI den Vertrag, bleibt der manuelle Modus nutzbar.

Zugangsdaten bleiben im Container-Datenvolume unter `private/`, werden unter Unix mit Dateimodus 0600 atomar gespeichert und nie im Browser oder Log ausgegeben. Trennen versucht zuerst, die erneuerbare Sitzung bei OpenAI zu widerrufen. Falls dies nicht bestätigt wird, zeigt die Oberfläche den notwendigen Hinweis an. Die Zuordnung zur App-Registrierung bleibt für eine spätere Anmeldung erhalten. Die aktuelle Version verwaltet ein verbundenes Konto.

Offizielle Quellen, geprüft am 30.09.2026:

- [Registrierung und Anmeldung](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Modelle und Inferenz](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [Einschränkungen der Vorschau](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
- [Creator-9-Handbuch](https://www.bernina.com/Bernina/media/BoA/Learn%20and%20Create/ebooks/2021/MyBERNINA-Creator-040122-Final.pdf)

## Daten und Betrieb

Originale, Exporte und Verbindung liegen im benannten Volume `atelier-data`. Browserdaten allein enthalten keine vollständige Projektkopie. Regelmäßig das Volume sichern, bei OAuth-Daten als vertrauliches Backup behandeln. Neuöffnen alter Projekte zeigt die Originaldatei, keine gespeicherte Bearbeitungsvorschau. Speicherdaten werden nicht automatisch gelöscht; der Speicherbedarf wächst mit Uploads und Exporten.

Container stoppen, ohne Daten zu löschen:

```bash
docker compose down
```

Änderungen übernehmen:

```bash
docker compose up -d --build
```

Es werden keine GPU und keine externen Schriftarten/CDNs benötigt. Das Image läuft als Benutzer 10001, mit schreibgeschütztem Anwendungsverzeichnis und einem schreibbaren Datenvolume. Zwei Bildverarbeitungen können gleichzeitig laufen; eine KI-Anfrage zur Zeit.

## Lokal entwickeln und prüfen

Python 3.12 oder neuer:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --test tests/test_color_tools.cjs
python app/server.py
```

Vor dem lokalen Serverstart ebenfalls `password.txt` mit der Kennworteingabe aus dem Schnellstart erstellen oder `ATELIER_PASSWORD_FILE` setzen. Bei Entwicklung ohne Docker bleibt die Datei Eigentum eures lokalen Benutzers; die Docker-Eigentümer-ID nicht übernehmen. Für Entwicklung optional `ATELIER_DATA`, `ATELIER_PORT`, `ATELIER_BIND`, `ATELIER_HOSTS` setzen. Der Callback-Port ist für die dokumentierte Anmeldung auf 1455 festgelegt. Es sind keine geheimen Werte im Paket enthalten.

Node.js wird nur für die vier Tests der Pixelwerkzeuge gebraucht; der Docker-Betrieb benötigt weiterhin ausschließlich Python.

## Prüfstand dieser Lieferung

35 automatisierte Tests bestanden, einschließlich Schutz aller privaten Routen, Sitzungswechsel beim Login, Abmeldung und Wiederverwendung alter Cookies, Sitzungsablauf, Cross-Origin-Abweisung und Begrenzung paralleler Fehlversuche. Anmeldung mit richtigem und falschem Kennwort sowie Abmeldung wurden zusätzlich im Browser geprüft.

Die anschließende Korrektur der Stickbreiten-Eingabe wurde im Browser mit gültigen und ungültigen Werten sowie mit ein- und ausgeschalteter Live-Vorschau geprüft. Alle sechs HTTP-Tests bestanden, einschließlich eines zusätzlichen Tests für Zielgröße und PNG-DPI bei 80, 150 und 260 mm sowie Abweisung von 400 mm.

Die Größenangabe verwendet jetzt die lange Seite. Alle 40 Python-Tests und vier JavaScript-Tests bestanden. Geprüft sind Hoch-, Quer- und Quadratformat, schmale Motive, Export-DPI, beide KI-Referenzquellen und Erhalt der Größe bei Analysevorschlägen. Im Browser wurden 80 × 160 mm im Hochformat und 160 × 96 mm im Querformat, sofortige Zielgrößenanzeige ohne Live-Vorschau, Abweisung von 400 mm sowie die Farbmarkierung geprüft.

Für Pipette und Lokalisieren bestanden vier Pixeltests und sechs Authentifizierungstests. Im Browser wurden Aufnahme aus Bild und Palette ohne Live-Vorschau, Abbrechen mit Esc, Wechsel der Indikatorfarbe, Lokalisieren nach manueller Umfärbung und die unveränderten zugrunde liegenden Motivdaten geprüft.

Lokale Bildverarbeitung, HTTP-Upload/Vorschau/Export, Auftragsvorbereitung und Variantenimport wurden geprüft. Die Analysevalidierung und Streambehandlung werden mit simulierten Antworten getestet; auch Vorschau und Übernahme wurden in einer ausdrücklich als Simulation gekennzeichneten Testansicht geprüft. Eine echte Analyse mit eurem ChatGPT-Konto steht noch aus. Hier war kein laufender Docker-Daemon verfügbar; ein echter Docker-Build und ein Start auf eurem Ubuntu-Host sind noch nicht verifiziert. Auch der Creator-Import und ein Probestick müssen mit euren Motiven geprüft werden.

## Lokaler Git-Export

Dieser Quellordner ist ein eigenständiges Git-Repository mit Branch `main`. Es ist kein Remote konfiguriert und nichts auf GitHub veröffentlicht. Kennwortdatei, Projektbilder, OAuth-Zugangsdaten, Python-Caches und lokale Umgebungsdateien sind durch `.gitignore` ausgeschlossen.

Zusätzlich liegt neben dem Ordner `stickatelier.git.bundle`. Das Bundle enthält den Commit-Verlauf und lässt sich als vollständiges Repository klonen. Auf Ubuntu, nachdem das Bundle dorthin kopiert wurde:

```bash
git clone stickatelier.git.bundle stickatelier
cd stickatelier
git remote remove origin
```

`git remote remove origin` entfernt die durch das Klonen entstandene Verknüpfung zur Bundle-Datei. Danach Kennwortdatei erstellen und Docker wie im Schnellstart starten. Einen Server-Remote kann man später gezielt hinzufügen. Für neue Commits zuerst die eigene Identität in diesem Repository konfigurieren:

```bash
git config user.name "Dein Name"
git config user.email "deine-adresse@example.com"
```

Die ursprünglichen Liefer-Commits verwenden die neutrale lokale Identität `Stickatelier <stickatelier@localhost>`, da keine Git-Autorenidentität eingerichtet war. Globale Git-Einstellungen wurden nicht geändert.

### Sinnvolle nächste Verbesserungen

- Garnfarbbibliotheken und geschützte Markenfarben auch beim Ändern der Bildregler beibehalten.
- SVG-Import und geschützte Bildregionen für Logos und Schrift.
- Vorschau in Exportauflösung zum Prüfen feinster Details.
- Eigene Voreinstellungen und vollständiges Wiederherstellen zuletzt verwendeter Reglereinstellungen.

Diese Funktionen sind noch nicht implementiert. Bereits korrigiert wurden der Verlust seltener Logo-Farben durch das Stichprobenraster und der unnötige Empfang veralteter Vorschauantworten.
