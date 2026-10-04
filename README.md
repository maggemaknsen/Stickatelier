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
ssh -N -L 8080:127.0.0.1:8080 BENUTZER@UBUNTU-HOST
```

Das Terminal bleibt offen. Im Browser **http://127.0.0.1:8080** öffnen und mit dem eben festgelegten Atelier-Kennwort anmelden. Die Standardkonfiguration veröffentlicht die App auf dem Ubuntu-Host nur auf Loopback.

Für direkten Zugriff im Heimnetz kann die erste Portzuordnung in `compose.yaml` durch `"8080:8080"` ersetzt und `ATELIER_HOSTS` auf die tatsächlich verwendeten Hostnamen/IPs gesetzt werden. Bei Zugriff über das Netzwerk HTTPS über einen Reverse Proxy verwenden: Das Kennwort schützt den Zugang, HTTP verschlüsselt die Übertragung nicht.

## Kennwortschutz

Ein gemeinsames Atelier-Kennwort schützt die Seite, Projekte, Bilder und sämtliche Arbeits-APIs. Nur die Anmeldeoberfläche, ihre Gestaltung und der minimale Healthcheck bleiben ohne Anmeldung erreichbar. Es gibt keine einzelnen Benutzerkonten oder getrennten Projektbereiche; angemeldete Personen sehen dieselben Projekte.

`password.txt` wird von Docker Compose als Secret-Datei eingebunden. Das Kennwort gehört weder ins Docker-Image noch in Git, Bundle oder ZIP. Auf dem Host liegt die Datei im Klartext; deshalb die im Schnellstart gezeigten Dateirechte verwenden. Die Eigentümer-ID 10001 entspricht dem Anwendungsbenutzer im Container, damit dieser die geschützte Datei lesen kann. Ohne gültige Kennwortdatei startet die Anwendung nicht. Für einen eigenen Dateipfad `ATELIER_PASSWORD_FILE` setzen.

Die Anwendung hält nur einen mit PBKDF2-SHA256 abgeleiteten Kennwortwert im Arbeitsspeicher. Nach der Anmeldung wird die Sitzungskennung erneuert. Sitzungen enden nach zwölf Stunden, bei „Abmelden“ oder beim Neustart. Nach fünf falschen Kennwörtern innerhalb von fünf Minuten werden weitere Anmeldeversuche derselben Verbindungs-IP bis zum Ende dieses Zeitfensters abgewiesen. Hinter einem Reverse Proxy teilen sich die Zugriffe diese Begrenzung; ungesicherte Forwarded-Header werden nicht als vertrauenswürdige IP übernommen.

Das Session-Cookie ist `HttpOnly` und `SameSite=Lax`. Für einen ausschließlich über HTTPS erreichbaren Betrieb `ATELIER_COOKIE_SECURE: "true"` setzen. Für den dokumentierten lokalen HTTP-SSH-Tunnel bleibt der Wert `"false"`.

Zum Ändern des Kennworts zuerst mit `sudo chown "$(id -u):$(id -g)" password.txt` den Schreibzugriff für euren Host-Benutzer herstellen. Dann Eingabe, Dateirechte und Eigentümer aus dem Schnellstart wiederholen und `docker compose up -d --force-recreate` ausführen. Alle bisherigen Sitzungen werden dadurch ungültig. Eine Wiederherstellung über E-Mail ist nicht vorgesehen; der Host-Zugang erlaubt das Ersetzen der Kennwortdatei.

## Motive vorbereiten

1. Bild öffnen oder das technische Testmotiv laden. Unterstützt: PNG, JPG, WEBP, BMP; maximal 20 MB und 24 Millionen Pixel. SVG-Import ist in dieser Version noch nicht enthalten. Vorhandene SVGs deshalb zunächst als PNG rasterisieren.
2. „Logo“ oder „Illustration“ wählen. Logo startet mit ausgeschalteter Glättung, Kleinstflächenfilterung und Verbreiterung. Der Modus sperrt keine Regionen: Anpassungen können auch Text verändern.
3. **Kurze Seite des Motivs** einstellen (mindestens 10 mm, empfohlen höchstens 160 mm). Im Hochformat bestimmt der Wert die Breite, im Querformat die Höhe. Die lange Seite folgt proportional: 100 mm ergeben bei einem 1:2-Motiv 100 × 200 mm, bei einem 2:1-Motiv 200 × 100 mm. Größere Eingaben als 160 mm bleiben erlaubt. Überschreitet die kurze Seite 160 mm oder die lange Seite 260 mm, erscheint sofort ein Rahmenhinweis; Vorschau und PNG-Export bleiben nutzbar. Deshalb kann auch eine kurze Seite unter 160 mm bei sehr schmalen Motiven bereits zu groß für den Rahmen sein. Die Größe bezieht sich auf die gesamte Bildfläche einschließlich vorhandener Ränder. Die Zielgröße aktualisiert sich sofort, auch ohne Live-Vorschau. Die Bildschirmansicht ist keine reale Zentimeterdarstellung. Ungültige oder nicht endliche Werte werden abgewiesen.
4. Farbanzahl für die Farbreduktion einstellen. Unter „Methode der Farbreduktion“ stehen RGB (Voreinstellung) und optional OKLab zur Auswahl. OKLab bildet die Palette und ordnet Bildpunkte anhand wahrnehmungsorientierter Farbunterschiede zu. Es kann Farbtöne besser trennen, erkennt aber keine Motivbereiche und garantiert bei wenigen Farben keine vollständige Trennung von Braun und Grün. Vorschau und Export verwenden dieselbe ausgewählte Methode. Ein Methodenwechsel setzt manuelle Farbänderungen und Füllungen zurück. Die Umrechnung läuft lokal mit NumPy, ohne weitere Abhängigkeiten oder externe Dienste. Formeln: [OKLab von Björn Ottosson](https://bottosson.github.io/posts/oklab/) (Public Domain / MIT). Keine Rasterung/Dithering, keine halbtransparenten Randpixel. Gezählt werden sichtbare Motivfarben; vollständig transparente Bereiche belegen keine Farbe. Wenn die sichtbare Grafik bereits innerhalb der Farbgrenze liegt, bleiben ihre exakten RGB-Farben bei der Farbreduktion erhalten – auch sehr kleine Farbakzente. Glättung, Kontrast oder Größenanpassung können davor bereits Farben ändern.
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
10. **Bereich füllen:** Eine der aktuell verwendeten Bildfarben direkt beim Füllwerkzeug auswählen. „Weitere Farben“ öffnet die freie Farbauswahl. Dann „Bereich füllen“ aktivieren und auf die gewünschte Fläche in der Ergebnisansicht klicken. Nur die zusammenhängende Fläche gleicher Farbe wird ersetzt; diagonale Kontakte verbinden keine Bereiche. Auch transparente Innenräume lassen sich füllen. Der Mauszeiger wird zum Farbeimer. Eine Palettenfarbe anklicken übernimmt sie bei aktivem Füllwerkzeug ebenfalls als Füllfarbe. Rückgängig nimmt Füllungen und Palettenänderungen schrittweise zurück. „Füllungen zurücksetzen“ entfernt alle Füllungen. Zusätzliche Füllfarben dürfen die eingestellte Anzahl der Basisfarben überschreiten. Die Anzeige „Farben im Motiv“ zählt die tatsächlich verwendeten Farben. Der Regler für die Farbreduktion bleibt unverändert; Vorschau und PNG-Export behalten die neuen Farben. Rückgängig und Zurücksetzen berechnen die tatsächliche Farbanzahl erneut.
11. Bild als einzelne PNG-Datei exportieren. Originale und exportierte Bilder bleiben auf dem Host gespeichert. Die letzten Projekte können erneut geöffnet werden; manuelle Änderungen und Reglereinstellungen werden beim Neuöffnen nicht automatisch wiederhergestellt.

Bei manueller Farbbearbeitung wird die Basispalette fixiert, damit Vorschau und Export dieselben Farbzuordnungen verwenden. Änderungen an den Bildreglern, der Wechsel der Motivart, „Zurücksetzen“ berechnen die Palette neu und setzen manuelle Farbänderungen und Füllungen mit einem Hinweis zurück. Bei erneutem Öffnen eines Projekts werden die Farbzuordnungen nicht automatisch geladen. Mehrfachänderungen können innerhalb der aktuellen Bearbeitung schrittweise rückgängig gemacht werden.

### Export und Creator 9

Der Export enthält ausschließlich `stickatelier-motiv.png`: transparente Grafik, maximal 2.400 Pixel an der längsten Kante, ohne Hochskalieren kleiner Vorlagen. Die PNG-DPI beschreibt die Zielgröße; es gibt keine ZIP-Verpackung oder Begleitdateien.

Creator: **Insert Artwork → Zielgröße ausdrücklich einstellen → Prepare Bitmap prüfen → Auto-Digitize oder Magic Wand → Stichplanung korrigieren → Probestick**. Transparente Bereiche nicht mitsticken. Das Tool erzeugt keine ART-/EXP-/PES-Stichdateien und kann Stoff, Garn, Dichte, Unterlagen und Zugausgleich nicht abschließend beurteilen. Pixelanteile sind kein Garnverbrauch.

Vorschau und Export verwenden dieselbe Bildverarbeitung mit maximal 2.400 Pixeln. Dadurch stimmen Bereichsgrenzen und Füllfarben überein. Das Original bleibt unverändert; die PNG-Datei enthält die Ziel-DPI und keine Metadaten aus dem Original.

## Serverupdate

Das Updatepaket `stickatelier-fuellwerkzeug-update.zip` enthält die neue Anwendung und `deploy/update.sh`. Die bestehende `compose.yaml` und die Kennwortdatei sind nicht im Paket enthalten. Dadurch bleiben die auf dem Server eingestellten Hostnamen (einschließlich der Cloudflare-Domain), Port 8080 und Cookie-Einstellungen erhalten.

Nach dem Upload des ZIPs in das Benutzerverzeichnis auf Ubuntu ausführen:

```bash
unzip -o ~/stickatelier-fuellwerkzeug-update.zip -d ~/stickatelier
cd ~/stickatelier
bash deploy/update.sh
```

Das Skript entfernt die bisherigen KI-Module und die ursprüngliche Portzuordnung für 1455. Vor einer Änderung der Compose-Datei legt es `compose.yaml.before-ai-removal` an. Es baut den Container neu und startet ihn mit dem bestehenden Datenvolume. Gespeicherte Motive und frühere Varianten bleiben nutzbar. Bereits vorhandene Verbindungsdateien im Datenvolume werden nicht gelöscht; die neue Anwendung liest sie nicht mehr.

## Daten und Betrieb

Originale und Exporte liegen im benannten Volume `atelier-data`. Browserdaten allein enthalten keine vollständige Projektkopie. Regelmäßig das Volume sichern. Neuöffnen alter Projekte zeigt die Originaldatei, keine gespeicherte Bearbeitungsvorschau. Speicherdaten werden nicht automatisch gelöscht; der Speicherbedarf wächst mit Uploads und Exporten.

Container stoppen, ohne Daten zu löschen:

```bash
docker compose down
```

Änderungen übernehmen:

```bash
docker compose up -d --build
```

Es werden keine GPU und keine externen Schriftarten/CDNs benötigt. Das Image läuft als Benutzer 10001, mit schreibgeschütztem Anwendungsverzeichnis und einem schreibbaren Datenvolume. Zwei Bildverarbeitungen können gleichzeitig laufen.

## Lokal entwickeln und prüfen

Python 3.12 oder neuer:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --test tests/*.cjs
python app/server.py
```

Vor dem lokalen Serverstart ebenfalls `password.txt` mit der Kennworteingabe aus dem Schnellstart erstellen oder `ATELIER_PASSWORD_FILE` setzen. Bei Entwicklung ohne Docker bleibt die Datei Eigentum eures lokalen Benutzers; die Docker-Eigentümer-ID nicht übernehmen. Für Entwicklung optional `ATELIER_DATA`, `ATELIER_PORT`, `ATELIER_BIND`, `ATELIER_HOSTS` setzen. Es sind keine geheimen Werte im Paket enthalten.

Node.js wird nur für die Tests der Pixelwerkzeuge und des Oberflächenstarts gebraucht; der Docker-Betrieb benötigt weiterhin ausschließlich Python.

## Creator-Verknüpfung auf Windows

Unter dem PNG-Export steht „Creator-Verknüpfung einrichten“. Auf dem PC mit Creator V9 den vollständigen Pfad zur EXE eintragen (ohne zusätzliche Argumente; Eigenschaften → Ziel der Verknüpfung). Diese Einstellung wird pro Browser und Stickatelier-Adresse lokal gespeichert, nicht als allgemeine Servereinstellung. Der Server prüft die Syntax des Pfads; die tatsächliche Installation wird erst vom Windows-Helfer geprüft.

„Windows-Helfer herunterladen“ erstellt ein ZIP mit der gewählten EXE und der aktuellen Stickatelier-Adresse. Entpacken, config.json kontrollieren und install.cmd ausführen. Die Einrichtung registriert ausschließlich für den aktuellen Windows-Benutzer das Protokoll stickatelier:// und benötigt keine Administratorrechte, kein Python und keinen Hintergrunddienst. Danach „Windows-Helfer auf diesem PC eingerichtet“ aktivieren und speichern. Ein geänderter Pfad oder eine andere Stickatelier-Adresse benötigt ein neues Einrichtungspaket.

„In Creator V9 öffnen“ bereitet dasselbe PNG wie der normale Export vor. Im anschließenden Dialog „Creator jetzt öffnen“ anklicken und die Browser-Abfrage erlauben. Der Helfer lädt das PNG und startet die fest eingerichtete EXE mit einem lokalen Dateiparameter. Der Browser kann weder die Installation erkennen noch bestätigen, ob Creator die PNG-Datei tatsächlich importiert. Dies muss auf dem Ziel-PC geprüft werden. Falls nur das Programm startet, befindet sich das PNG unter %LOCALAPPDATA%\Stickatelier\CreatorBridge\Exports für den manuellen Bildimport.

Die Download-Übergabe ist einmalig, zwei Minuten gültig und an eine weiterhin angemeldete Atelier-Sitzung gebunden. Das Atelier-Passwort wird nicht im Helfer gespeichert. Download-URLs dürfen nur auf den eingerichteten Server und den vorgesehenen PNG-Endpunkt verweisen; Weiterleitungen sind deaktiviert. Der Link selbst kann keinen anderen Programmpfad oder zusätzliche Startargumente bestimmen. Der Helfer ist unter %LOCALAPPDATA%\Stickatelier\CreatorBridge installiert; uninstall.ps1 deaktiviert das Protokoll und lässt PNG-Dateien erhalten.

Die Creator-Verknüpfung wurde nicht auf dem anderen PC getestet; die tatsächliche Übernahme des Dateiparameters in Creator ist unbestätigt.

## Füllvorschau und Farbe unter dem Mauszeiger

Bei aktivem Füllwerkzeug wird die zusammenhängende Fläche unter dem Mauszeiger halbtransparent mit der gewählten Farbe markiert. Erst der Klick füllt sie. Die Vorschau verwendet dieselbe Vierer-Nachbarschaft und exakte sichtbare RGB-Farbe wie die eigentliche Füllung; transparente Bereiche werden ebenfalls erkannt. Die Berechnung läuft in einem lokalen Web Worker und ist leicht verzögert, damit Mausbewegungen und Zeichnen bedienbar bleiben. Während wartende Korrekturen verarbeitet werden, wird keine veraltete Füllfläche markiert. Nach der Bildaktualisierung wird die Vorschau neu berechnet.

Unter dem Bild erscheinen Farbmuster, Hex-Wert und RGB-Werte des Bildpunkts. Im Vergleichsmodus wird die Original- oder Ergebnisseite unter dem Mauszeiger berücksichtigt. Sichtbare lokale Pinselkorrekturen werden ebenfalls aufgenommen. Bei Ergebnisfarben wird, soweit vorhanden, die Nummer der aktuellen Farbpalette angezeigt; transparente Bildpunkte werden als transparent bezeichnet. Die halbtransparente Füllmarkierung verändert weder die Farbmessung noch den PNG-Export.

## Korrekturpinsel und kompakte Oberfläche

„Bereich füllen & Korrekturpinsel“ steht unter dem Vorher/Nachher-Regler. Dieser Bereich und die Farbpalette sind zunächst eingeklappt und lassen sich über ihre Überschrift öffnen. Beim Schließen des Werkzeugbereichs wird das aktive Malwerkzeug beendet.

Eine vorhandene Bildfarbe oder unter „Weitere Farben“ eine neue Korrekturfarbe wählen, dann den Korrekturpinsel aktivieren. Mit gedrückter linker Maustaste oder einem Stift/Finger auf dem Ergebnis malen. Die Pinselgröße beträgt 0,2–15 % der kurzen Bildkante, unabhängig vom Zoom. Der Kreis am Mauszeiger zeigt den Durchmesser. Jeder Strich wird in der Vorschau direkt angezeigt und beim Loslassen als eigene Änderung übernommen. Pinselstriche, Füllungen und Rückgängig aktualisieren das Ergebnis automatisch im Hintergrund, ohne den Vorschau-Ladehinweis einzublenden. Während Bereichsfüllungen übernommen werden, zeigt ein schmaler Ladebalken unter dem Bild die Verarbeitung an. Weitere Klicks bleiben möglich. Reine Pinselstriche zeigen diesen Balken nicht. Schnelle Füllklicks und aufeinanderfolgende Pinselstriche werden in einer gemeinsamen Warteschlange in ihrer Reihenfolge verarbeitet, jeweils mit der beim Klick oder Strich gewählten Farbe und Pinselgröße. Während der Server ältere Striche verarbeitet, können weitere gezeichnet werden. Noch nicht angezeigte Striche bleiben als lokale Vorschau sichtbar, bis sie im aktualisierten Ergebnis enthalten sind. Farbe und Pinselgröße können zwischen Strichen weiterhin geändert werden. Export und Rückgängig sind erst nach Abschluss der Warteschlange verfügbar. Esc und Beenden stoppen das Werkzeug und verwerfen nur einen noch nicht abgeschlossenen Strich. Bereits abgeschlossene Striche und Füllklicks werden weiter übernommen. Bildregler oder Projektwechsel verwerfen noch wartende Korrekturen. Bei einem Fehler wird die Warteschlange angehalten und die Fehlermeldung angezeigt. Fehler werden weiterhin angezeigt; Export ist erst nach Übernahme der Korrektur möglich. Die endgültige Verarbeitung verwendet harte Kanten ohne zusätzliche Zwischenfarben und malt nur auf sichtbare Pixel; Transparenz bleibt erhalten.

„Rückgängig“ im Werkzeugbereich oder in der Farbpalette nimmt jeweils die letzte Farbänderung, Füllung oder den letzten Pinselstrich zurück. Pinselstriche und Füllungen können getrennt zurückgesetzt werden. Beide werden in ihrer Reihenfolge auf Vorschau und PNG-Export angewendet. Bildregler und Methodenwechsel setzen alle manuellen Korrekturen zurück. Esc beendet den Pinsel und verwirft einen noch nicht abgeschlossenen Strich. Maximal 100 Füllungen und Striche mit insgesamt 20.000 Pinselpunkten (maximal 2.000 pro Strich).

## Bildzoom

Plus und Minus ändern die Ansicht zwischen 25 % und 800 %. „Zurücksetzen“ passt das Motiv wieder in die Bildansicht ein (100 %). Vergrößerte Motive lassen sich über die Scrollleisten oder das Touchpad verschieben. Original, Ergebnis, Vergleich und Farbmarkierungen werden gemeinsam vergrößert. Füllwerkzeug und Pipette beziehen ihre Bildposition aus der vergrößerten Ansicht. Beim Öffnen eines anderen Motivs wird der Zoom zurückgesetzt. Der Zoom verändert weder die Zielgröße noch die PNG-Datei.

## Prüfstand

Beim vorherigen Stand bestanden 41 Python-Tests und fünf JavaScript-Tests. Die anschließenden Erweiterungen der Füllfarbauswahl, des Bildzooms , der optionalen OKLab-Farbreduktion und des Korrekturpinsels sowie die Füllvorschau und Farbanzeige wurden noch nicht getestet. Geprüft sind Bildverarbeitung, Kennwortschutz, Upload, Vorschau, PNG-Export und Bereichsfüllungen, der Oberflächenstart ohne KI-Aufrufe und das Beibehalten der Serverkonfiguration beim Update. Ehemalige KI-Routen liefern nach Anmeldung HTTP 404. Ein echter Docker-Build auf dem Ubuntu-Host, der Creator-Import und ein Probestick müssen mit euren Motiven geprüft werden.

## Lokaler Git-Export

Dieser Quellordner ist ein eigenständiges Git-Repository mit Branch `main`. Der Projektstand wird im privaten [GitHub-Repository](https://github.com/maggemaknsen/Stickatelier) geführt. Kennwortdatei, Projektbilder, Python-Caches und lokale Umgebungsdateien sind durch `.gitignore` ausgeschlossen.

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
