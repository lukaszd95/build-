# Generator projektów architektonicznych

To jest aplikacja webowa (SaaS), która na podstawie danych wejściowych generuje projekt architektoniczny.

Użytkownik podaje parametry działki, typ budynku i ograniczenia, a aplikacja tworzy propozycję układu architektonicznego.

---

## Jak uruchomić aplikację lokalnie

## Auth + projekty (logowanie/rejestracja z DB)

1. Skopiuj zmienne środowiskowe:
```bash
cp .env.example .env
```

2. Skonfiguruj bazę (SQLite – bez Dockera):
```bash
mkdir -p data
```

3. Wykonaj migracje:
```bash
alembic upgrade head
```

4. Uruchom aplikację:
```bash
python app.py
```

### PyCharm (Windows): 500 na `/api/auth/login` lub `/api/auth/register`


### PyCharm: „jedno kliknięcie” przed pierwszym uruchomieniem

Jeśli chcesz zrobić wszystko automatycznie (instalacja + konfiguracja + migracje), użyj skryptu bootstrap:

1. Otwórz plik `scripts/pycharm_bootstrap.py` w PyCharm.
2. Kliknij zielony przycisk **Run** (▶).
3. Skrypt wykona automatycznie:
   - utworzenie katalogu `data/`,
   - utworzenie `.env` z `.env.example` (jeśli brak),
   - instalację zależności (`requirements.txt` + `python-dotenv`),
   - migracje `alembic upgrade head`.
4. Po zakończeniu uruchom `app.py` w PyCharm.

Alternatywnie z terminala:
```bash
python scripts/pycharm_bootstrap.py
```

Jeśli w PyCharm masz błąd:

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte ... (psycopg2)
```

najczęściej oznacza to problem z niepoprawnym `DATABASE_URL` (np. hasło z polskimi znakami lub `@` bez kodowania URL) albo uszkodzonym plikiem `.env`.

Aktualna wersja aplikacji automatycznie normalizuje URL połączenia do PostgreSQL (koduje login/hasło), więc ten błąd nie powinien już blokować logowania/rejestracji.

#### Szybka konfiguracja krok po kroku (PowerShell + PyCharm)

1. W katalogu projektu przygotuj `.env`:
```powershell
copy .env.example .env
```

2. W `.env` ustaw poprawny adres bazy (na start najlepiej bez znaków specjalnych):
```env
DATABASE_URL=sqlite:///data/app.db
```

3. SQLite nie wymaga uruchamiania kontenera Dockera.

4. W terminalu PyCharm doinstaluj obsługę `.env` i zależności:
```powershell
pip install -r requirements.txt
pip install python-dotenv
```

5. Wykonaj migracje:
```powershell
alembic upgrade head
```

6. Uruchom aplikację ponownie:
```powershell
python app.py
```

#### Ważne dla `DATABASE_URL`

- Dla SQLite używaj ścieżki w formacie: `sqlite:///data/app.db`.
- Zapisz plik `.env` jako **UTF-8** (PyCharm: *File -> File Encoding -> UTF-8*).
- Komunikat Flaska `Tip: There are .env files present...` znika po instalacji `python-dotenv`.

5. Flow aplikacji:
- `/login` i `/register` obsługują autoryzację przez cookie httpOnly,
- po poprawnym logowaniu następuje przekierowanie do `/projects`,
- `/projects` to chroniony skrót do istniejącego panelu projektów (`/app?open=projects`),
- `/app` jest chroniony (brak sesji => redirect na `/login`),
- w górnym prawym menu panelu wyświetlane są dane zalogowanego użytkownika (`/api/auth/me`) oraz przycisk wylogowania (`/api/auth/logout`).


1. Upewnij się, że masz zainstalowanego Pythona 3.

2. Zainstaluj wymagane biblioteki:
```bash
pip install -r requirements.txt
```

3. (Opcjonalnie) OCR dla skanów PDF/JPG/PNG:
   - Zainstaluj Tesseract OCR w systemie (np. `tesseract-ocr`).
   - Jeżeli używasz języka polskiego, doinstaluj paczkę językową (np. `tesseract-ocr-pol`).
   - (Opcjonalnie) ustaw `OCR_LANG`, np. `OCR_LANG=pol+eng`.

## Import mapy CAD (DXF/DWG) — instrukcja manualna (MVP)

1. Zainstaluj zależności CAD:
```bash
pip install -r requirements.txt
```

2. Zainstaluj konwerter DWG → DXF (wybierz jedną opcję):
   - **dwg2dxf (LibreDWG)** — najszybsza instalacja:
     ```bash
     ./scripts/install_dwg_converter.sh
     ```
     Jeśli `dwg2dxf` nie trafi do `PATH`, ustaw `DWG2DXF_PATH`.
   - **ODAFileConverter** (darmowy) — pobierz z ODA i ustaw
     `ODA_FILE_CONVERTER_PATH` (np. `/opt/ODAFileConverter/ODAFileConverter`).

3. Uruchom aplikację lokalnie:
```bash
python app.py
```

4. W aplikacji:
   - Kliknij przycisk **Mapa DWG/DXF** w lewym menu.
   - Wgraj plik `.dxf` (lub `.dwg`, jeśli masz skonfigurowany konwerter).
   - Kliknij **Wgraj i wczytaj**.
   - Sprawdź status importu (jednostki, liczba warstw, bbox).
   - Włącz/wyłącz warstwy i ustawiaj przezroczystość.

---

## Wgrywanie > Działka (granice działek z DXF/DWG)

### Konfiguracja
1. Zainstaluj zależności:
```bash
pip install -r requirements.txt
```
2. (Opcjonalnie) skonfiguruj konwerter DWG:
   - **ODA File Converter**: ustaw `ODA_FILE_CONVERTER_PATH`.
   - **dwg2dxf**: ustaw `DWG2DXF_PATH`.

### Endpointy API
#### Upload działki
`POST /api/plots/upload` (multipart/form-data, pole `file`)

**Przykład odpowiedzi:**
```json
{
  "importJobId": 12,
  "status": "COMPLETED",
  "confidence": 0.92,
  "units": "m",
  "unitScale": 1.0,
  "bounds": { "minX": 0, "minY": 0, "maxX": 120.5, "maxY": 80.2 }
}
```

#### Pobranie granic (overlay na PZT)
`GET /api/plots/{importJobId}/boundaries`

**Przykład odpowiedzi (skrót):**
```json
{
  "importJob": { "id": 12, "status": "NEEDS_REVIEW", "confidence": 0.63 },
  "selectedBoundary": null,
  "candidates": [
    {
      "id": 88,
      "geometry": { "type": "Polygon", "coordinates": [[[0,0],[10,0],[10,10],[0,10],[0,0]]] },
      "metadata": { "layer": "DZIALKA", "area": 100, "vertexCount": 5 }
    }
  ],
  "transform": { "scale": 1.0, "translate": { "x": 0, "y": 0 } },
  "bbox": { "minX": 0, "minY": 0, "maxX": 120.5, "maxY": 80.2 }
}
```

#### Wybór właściwej granicy
`POST /api/plots/{importJobId}/select-boundary`
```json
{ "candidate_id": 88 }
```

**Przykład odpowiedzi:**
```json
{
  "selectedBoundary": {
    "id": 88,
    "geometry": { "type": "Polygon", "coordinates": [[[0,0],[10,0],[10,10],[0,10],[0,0]]] },
    "metadata": { "layer": "DZIALKA", "area": 100 }
  }
}
```

---

## Moduł „Wgrywanie” (Upload Center)

Panel **Wgrywanie** obsługuje sekcje „Wypis z MPZP” i „Wyrys z MPZP” jako generyczne karty dokumentów.
Każda karta umożliwia:
- upload plików PDF/JPG/PNG z walidacją rozmiaru i typu,
- stały podgląd dokumentu po lewej stronie,
- statusy i metadane pliku,
- OCR dla skanów (jeśli Tesseract jest dostępny w systemie).
- wersjonowanie (lista 3 ostatnich wersji),
- uruchomienie OCR (stub, gotowy do podmiany),
- zapis danych MPZP ręcznie lub po OCR.

### API (skrót)
- `POST /api/documents` – upload nowego dokumentu (parametry: `file`, `type`).
- `GET /api/documents?type=MPZP_WYPIS` – lista wersji dla typu.
- `GET /api/documents/:id` – metadane + zapisane pola.
- `GET /api/documents/:id/file` – podgląd/pobranie pliku.
- `POST /api/documents/:id/data` – zapis pól formularza (opcjonalnie `parcelId`, `projectId`).
- `POST /api/documents/:id/ocr` – uruchom OCR (stub, opcjonalnie `parcelId`).
- `DELETE /api/documents/:id` – miękkie usunięcie wersji.

### Jak dodać nowy typ dokumentu
1. Dodaj nowy wpis do tablicy `DOCUMENT_TYPES` w `static/js/upload/uploadUI.js`
   (type, label, hint, akceptowane rozszerzenia).
2. Dodaj obsługę typu w backendzie (wystarczy nowy `type` w `POST /api/documents` – schemat jest generyczny).
3. (Opcjonalnie) rozszerz formularz pól w `MPZP_FIELDS` i mapowanie OCR w `utils/ocr.py`.
4. Jeśli dane mają być przypisane do działki, ustawiaj `parcelId` przy zapisie/ocr.

### OCR
OCR jest stubem w `utils/ocr.py` – zwraca przykładowe dane z confidence.
Podmień funkcję `run_document_ocr` na integrację z wybraną usługą OCR.



### Projekt demo (domyślny)
Przy inicjalizacji bazy tworzony jest automatycznie projekt `DEMO` z domyślną działką `_global`.

- Endpoint `GET /api/projects/demo` zwraca dane projektu demo i jego działek/parametrów.
- Endpoint `PATCH /api/projects/demo` pozwala edytować podstawowe dane (`name`, `description`, `status`, `investorName`).
- Zapis formularza MPZP (`POST /api/documents/:id/data`) bez `projectId` domyślnie zapisuje zmiany do projektu `DEMO`.
- Dodanie działki przez `POST /api/parcels` zapisuje także granice (`geometry`) do działki projektu demo (`project_plots.geometryJson`).

#### Synchronizacja MPZP do modelu projektu
Jeśli przy zapisie `POST /api/documents/:id/data` podasz jednocześnie:
- `parcelId`
- `projectId`

...to wszystkie pola z karty MPZP (`fields`) są dodatkowo zapisywane do `project_plot_parameters`
dla działki projektu (`project_plots`) jako klucze w formacie `mpzp.<field_key>`.

Dzięki temu parametry MPZP są dostępne zarówno w warstwie dokumentowej (`document_extracted_data`),
jak i bezpośrednio w modelu projektu (do kosztorysu/warunków/walidacji).

---

## Moduł MAP (automatyczne PZT)

Dodano moduł `MAP` z API oraz widokiem mapy opartym o MapLibre.

### Co robi
- Przyjmuje: nr działki, obręb, miejscowość.
- Endpoint `POST /api/map/parcel/resolve` rozwiązuje działkę, liczy bufor 30 m i buduje sesję mapy.
- Endpoint `GET /api/map/tiles/{z}/{x}/{y}.mvt?sessionId=...` serwuje warstwy wektorowe jako MVT.
- Endpoint `GET /api/map/export?sessionId=...&format=geojson` eksportuje dane sesji do GeoJSON.

### Konfiguracja providerów
Plik: `config/map.config.json`.

Najważniejsze sekcje:
- `parcels` – provider działek (wymagany), mapping pól geometrii i numeru działki.
- `context` – budynki/drogi (BDOT + OSM fallback).
- `utilities` – media wektorowo (WFS) lub podkład orientacyjny (WMS).

#### Konfiguracja środowiskowa Geoportal WFS

Aplikacja pozwala nadpisać konfigurację WFS zmiennymi środowiskowymi:

- `GEO_WFS_URL` – URL usługi WFS (domyślnie: `https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza`).
- `GEO_WFS_TYPENAME` – nazwa warstwy (domyślnie: `dzialki`).
- `GEO_WFS_TIMEOUT_MS` – timeout w milisekundach (np. `25000`).
- `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` – standardowe ustawienia proxy.

Proxy jest używane tylko wtedy, gdy zmienne proxy są ustawione w środowisku runtime.

#### Diagnostyka integracji z Geoportalem

Techniczny endpoint healthcheck (bez wpływu na endpointy biznesowe):

- `GET /api/geoportal/health`

Endpoint wykonuje `GetCapabilities` i zwraca kod diagnostyczny (`code`), m.in.:

- `DNS_OK` (połączenie i parsowanie odpowiedzi działają),
- `PROXY_CONNECT_403`,
- `NETWORK_UNREACHABLE`,
- `TCP_TIMEOUT`,
- `TLS_ERROR`,
- `WFS_HTTP_ERROR`.

Jeśli pojawia się `PROXY_CONNECT_403` lub `NETWORK_UNREACHABLE`, problem jest poza aplikacją i wymaga zmian w infrastrukturze sieciowej (proxy/firewall/egress).

### Checklista stabilności wyszukiwania działek (cel: >= 90% skuteczności)

Poniższa lista jest praktyczną checklistą diagnostyczną dla środowiska produkcyjnego/staging.

1. **Sprawdź health endpoint aplikacji**
   - `GET /api/geoportal/health`
   - Oczekiwane: `ok=true`, `code=DNS_OK`.
   - Jeśli `PROXY_CONNECT_403` -> proxy blokuje tunel CONNECT.
   - Jeśli `NETWORK_UNREACHABLE` / `TCP_TIMEOUT` -> problem egress/firewall.

2. **Zweryfikuj routing przez proxy vs direct**
   - Sprawdź aktywne zmienne: `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`.
   - Dla hosta `mapy.geoportal.gov.pl` rozważ wpis do `NO_PROXY` (jeśli direct działa stabilniej).
   - Potwierdź z zespołem sieciowym, czy proxy dopuszcza CONNECT do portu 443 dla Geoportalu.

3. **Przetestuj 100 prób z proxy i bez proxy**
   - Z proxy: `curl ... GetFeature` x100 i policz sukcesy.
   - Bez proxy: `curl --noproxy '*' ... GetFeature` x100 i policz sukcesy.
   - Różnica wyników wskaże, czy winny jest proxy czy ogólny brak egress.

4. **Ustaw timeout i retry adekwatnie do środowiska**
   - `GEO_WFS_TIMEOUT_MS` ustaw na minimum `15000-25000` ms przy wolniejszym łączu.
   - Upewnij się, że retry nie są wycinane przez upstream timeout (np. ingress/proxy/app gateway).

5. **Skontroluj DNS i TLS na węźle runtime**
   - DNS: host `mapy.geoportal.gov.pl` musi się rozwiązywać stabilnie.
   - TLS: brak MITM/certyfikatów firmowych, które zrywają handshake do hosta zewnętrznego.

6. **Sprawdź limity i ochrona anty-DDoS po stronie infrastruktury**
   - Jeśli ruch idzie przez wspólny egress IP, możliwe okresowe ograniczenia.
   - Rozważ rate limiting po stronie aplikacji i kontrolowane kolejki zapytań.

7. **Włącz monitoring kodów błędów i skuteczności**
   - Monitoruj procent sukcesów endpointu wyszukiwania działek (SLI).
   - Monitoruj liczniki błędów: `PROXY_CONNECT_403`, `NETWORK_UNREACHABLE`, `TCP_TIMEOUT`, `WFS_HTTP_ERROR`.
   - Ustal alert np. gdy skuteczność z 15 minut spada < 90%.

8. **Zweryfikuj cache fallback w scenariuszu awarii**
   - Dla często wyszukiwanych działek potwierdź, że aplikacja zwraca wynik z cache przy chwilowym braku WFS.
   - Ustal akceptowalny TTL cache (`cacheTtlSeconds`) względem wymagań biznesowych.

9. **Procedura awaryjna (runbook)**
   - Jeśli awaria trwa > X min: przełącz ruch na direct/no-proxy lub zapasowy egress (jeśli dostępne).
   - Jeśli oba kanały niedostępne: komunikat degradacji + eskalacja do zespołu sieciowego.

10. **Kryterium odbioru poprawki stabilności**
   - W 3 niezależnych oknach testowych (np. rano/popołudnie/wieczór) wykonaj po 100 prób.
   - Każde okno: skuteczność >= 90%.
   - Brak dominującego błędu infrastrukturalnego (>20% pojedynczego typu).

Jeśli `parcels.provider` nie jest ustawiony, API zwraca `503 PARCEL_PROVIDER_NOT_CONFIGURED`.

### Mapowanie pól
Przykładowy mapping zawiera:
- `geomField`,
- `parcelNumber` (`singleField` albo `mainSubFields`),
- `obreb`,
- `miejscowosc` (opcjonalne),
- pola administracyjne,
- `idField`.

### Ograniczenia prawne i jakościowe
- Nie ma wektoryzacji rastrowych map ewidencyjnych.
- Raster WMS jest używany tylko jako overlay poglądowy.
- Dokładność i licencja zależą od źródła danych providera.
- Fallback OSM ma charakter pomocniczy/orientacyjny.

### Warstwa mapowa
Warstwa mapowa działa teraz na SQLite (tabele `map_sessions`, `map_features`) inicjalizowane przez aplikację w `utils/db.py`, bez zależności od Dockera.


## Model danych projektu (projekty + działki + wymagania + kosztorys)

Dodano relacyjny model danych dla „pełnego projektu”, żeby każdy projekt był niezależną jednostką z własnymi:
- działkami,
- plikami i dokumentami,
- wymaganiami,
- kosztorysem,
- wersjami projektu architektonicznego.

### Główne tabele
- `projects` – nagłówek projektu (`code`, `name`, status, inwestor, daty).
- `project_plots` – działki przypisane do projektu (wspiera 1..N działek na projekt).
- `project_plot_parameters` – parametry działki jako klucz/wartość (np. powierzchnia, linia zabudowy, MPZP, intensywność).
- `project_files` – pliki projektu; opcjonalnie przypięte do konkretnej działki (`projectPlotId`).
- `project_requirements` – wymagania projektu (kategoria, priorytet, status, termin, źródło).
- `cost_estimates` + `cost_estimate_items` – wersjonowany kosztorys projektu z pozycjami.
- `project_designs` – wersje koncepcji/projektu budowlanego/wykonawczego wraz z założeniami i opcjonalnym plikiem.

### Dlaczego taki podział
- **Skalowanie na wiele działek**: jeden projekt może mieć kilka działek i osobne parametry każdej działki.
- **Wymagania zmienne między projektami**: tabela `project_requirements` pozwala trzymać dowolną liczbę wymagań o różnej randze i statusie.
- **Kosztorys wersjonowany**: `version` w `cost_estimates` umożliwia porównanie wariantów budżetu w czasie.
- **Separacja plików od logiki**: `project_files` umożliwia spójne podpinanie załączników do projektu i/lub działki.
- **Wersje projektu architektonicznego**: `project_designs` oddziela etapy i rewizje projektu.

### Co można rozszerzyć w kolejnym kroku
- słowniki/statusy jako osobne tabele (`project_statuses`, `requirement_categories`),
- śledzenie zmian (audit log),
- użytkownicy i role przypisane do projektu,
- workflow akceptacji wymagań i kosztorysu.

---

## Backend v2 (SQLite + SQLAlchemy + Alembic + JWT)

Dodano nową warstwę API opartą o SQLite dla encji wieloużytkownikowych (`users`, `projects_v2`, `mpzp_conditions`, `cost_estimates_v2`, `cost_items`, `design_assets`). Dane są separowane po `user_id` i sprawdzane middleware JWT.

### Uruchomienie od zera

1. Skopiuj env:
```bash
cp .env.example .env
```
2. Przygotuj katalog danych SQLite:
```bash
mkdir -p data
```
3. Zainstaluj zależności:
```bash
pip install -r requirements.txt
```
4. Wykonaj migracje:
```bash
alembic upgrade head
```
5. Seed (opcjonalny):
```bash
python scripts/seed_v2.py
```
6. Uruchom backend:
```bash
python app.py
```

### Diagram relacji (tekstowy)

- `users (1) -> (N) projects_v2`
- `projects_v2 (1) -> (1) mpzp_conditions`
- `projects_v2 (1) -> (1) cost_estimates_v2`
- `cost_estimates_v2 (1) -> (N) cost_items`
- `projects_v2 (1) -> (N) design_assets`

Dodatkowo:
- soft delete: `projects_v2.deleted_at`, `design_assets.deleted_at`
- timestamps: `created_at`, `updated_at` we wszystkich tabelach v2
- wersjonowanie assetów: `design_assets.version`, `design_assets.status`, `design_assets.is_current`

### Główne endpointy

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/users/me`
- `GET/POST/PATCH/DELETE /api/projects`
- `GET/POST/PATCH/DELETE /api/projects/{id}/mpzp`
- `GET /api/projects/{id}/cost-estimate`
- `POST/PATCH/DELETE /api/projects/{id}/cost-estimate/items`
- `GET/POST/DELETE /api/projects/{id}/design-assets`

### Przykładowe curl

Rejestracja:
```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"tajne123","full_name":"Jan Kowalski"}'
```

Logowanie:
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"tajne123"}'
```

Tworzenie projektu:
```bash
curl -X POST http://localhost:5000/api/projects \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Osiedle Lipowa","description":"Wariant A"}'
```

Zapis MPZP:
```bash
curl -X PATCH http://localhost:5000/api/projects/1/mpzp \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"max_height":12.5,"biologically_active_area":40,"extra_data":{"strefa":"MN/U"}}'
```

Dodanie pozycji kosztorysu:
```bash
curl -X POST http://localhost:5000/api/projects/1/cost-estimate/items \
  -H 'Authorization: Bearer <TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Fundamenty","category":"Roboty ziemne","unit":"m2","quantity":100,"unit_price":350}'
```

Dodanie assetu 2D/3D:
```bash
curl -X POST http://localhost:5000/api/projects/1/design-assets \
  -H 'Authorization: Bearer <TOKEN>' \
  -F 'dimension=3D' -F 'kind=concept' -F 'version=1' -F 'status=draft' \
  -F 'file=@./example.glb'
```
