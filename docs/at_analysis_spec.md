# AT — specyfikacja logiki analizy

## Zakres wykrywania
- **Linie**: wykrywane z wektora PDF (`pdf_vector`), fallback rastrowy (`raster_detected`) tylko gdy brak użytecznej geometrii wektorowej.
- **Osie konstrukcyjne**: wykrywane **tylko na stronach typu `Rzut`** (nie na opisach, przekrojach, elewacjach, legendach, zestawieniach, detalach, schematach).
- **Skala**: najpierw kandydaci z tekstu/tabelki, potem inferencja z wymiarów.
- **Branże**: klasyfikacja po słowach kluczowych + metadanych + sygnałach per-strona.
- **Typ strony**: klasyfikowany per-strona (a nie globalnie).
- **Projekt**: ekstrakcja nazwy/adresu/działki + matching do projektu.

## Reguły wykrywania osi
Wykrywanie osi działa heurystycznie i scoringowo (wielosygnałowo), nie po pojedynczym warunku.

### Sygnały dodatnie
- bardzo długa linia względem strony,
- linia pozioma/pionowa (z tolerancją kąta),
- przynależność do grupy linii równoległych,
- obecność linii w kierunku prostopadłym (siatka),
- scalenie z wielu segmentów współliniowych,
- cienki profil linii,
- obecność etykiet osiopodobnych w tekście (`A`, `1`, `A1`, `K-1`).

### Sygnały osłabiające
- zbyt krótka linia,
- małe pokrycie strony,
- brak grupy równoległej,
- grubość mogąca wskazywać ścianę,
- brak spójności układu siatki.

## Budowanie osi z segmentów
- segmenty współliniowe są łączone w jedną oś,
- dopuszczane są małe przerwy między segmentami,
- wynik osi przechowuje `segmentsJson` i flagę `builtFromSegments`.

## Explainability
Dla każdej osi zapisywane są:
- `supportingSignals`,
- `weakeningSignals`,
- `scoreBreakdown`,
- `detectionSource` (`pdf_vector`, `raster_detected`, `merged_segments`),
- `hasEndpointLabel`, `labelCandidates`,
- `isUserConfirmed`, `userStatus`, `userOverrideLabel`.

## API osi
- `POST /api/at/documents/<id>/pages/<page>/detect-axes`
- `POST /api/at/documents/<id>/pages/<page>/detect-axes/retry`
- `GET /api/at/documents/<id>/pages/<page>/axes`
- `PATCH /api/at/documents/<id>/pages/<page>/axes/<axisId>`

## Ograniczenia
- Obecnie brak dedykowanego OCR-pozycyjnego dla bąbli osi (etykiety wiązane ostrożnie heurystycznie).
- Dla rzutów instalacyjnych wykrywanie działa, ale confidence może być niższy przy dużej liczbie linii technicznych.
- W przypadku słabych sygnałów system może zwracać pustą listę osi (brak wymuszania detekcji).
