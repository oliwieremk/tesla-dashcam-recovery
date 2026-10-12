# Weryfikacja Tesla Recovery 0.3.0 — 12 października 2026

Wykonano testy na macOS Apple Silicon. **18 testów automatycznych przeszło, bez pominięć.**
Sprawdzono też gotową paczkę `.app` w natywnym oknie i ikonę w Finderze.

## Sprawdzone działanie

- Skanowanie syntetycznych obrazów exFAT: istniejące pliki i dane po usunięciu.
- Kopiowanie fragmentowanego istniejącego pliku — wynik identyczny bajt po bajcie; źródło bez zmian.
- Skanowanie, eksport i przygotowanie wygenerowanego MP4, następnie dekodowanie filmu przez FFmpeg.
- Naprawa MP4 po usunięciu indeksu `moov`: zachowano 90 klatek, a odbudowany film daje się dekodować.
- Lokalne odszyfrowanie stron AES-CBC w formacie eCryptfs z syntetycznym kluczem; wynik identyczny z filmem wejściowym.
- Odrzucenie uciętej strony szyfrogramu zamiast uznania niepełnego wyniku za sukces.
- Dostęp do urządzenia przekazywany tylko do odczytu; próba zapisu przez przekazany uchwyt jest odrzucana.
- Odrzucanie dysków wewnętrznych, anulowanie zgody macOS i blokada przygotowania/zapisu na nośniku źródłowym Tesli.
- Języki PL/EN, pokrycie statycznych etykiet, parametry tłumaczeń, opisy jakości i komunikaty postępu.
- Zapis języka na kolejne uruchomienie, bez utraty ustawionego folderu ani stanu skanowania/zadania.
- Odtwarzanie wygenerowanego filmu w natywnym odtwarzaczu; skróty spacji i strzałek.
- W gotowej paczce EN → PL zachowało zaznaczoną minutę i pozycję odtwarzania na 5. sekundzie.
- Finder pokazuje własną ikonę i wersję 0.3.0 oraz rozpoznaje launcher jako aplikację uniwersalną.
- Podpis lokalny `codesign --verify --deep --strict` jest poprawny.
- Po starcie `.app` w paczce nie powstaje cache Pythona; składniki i dane aplikacji trafiają poza pakiet.

## Kontrast

Współczynniki obliczono z końcowych kolorów tekstu i tła. Dotyczą tych par kolorów, a nie pełnego audytu dostępności całej aplikacji.

| Element | Tekst / tło | Kontrast |
|---|---|---:|
| Główny przycisk | `#102039` / `#78afff` | 7,28:1 |
| Główny przycisk po najechaniu | `#102039` / `#97c3ff` | 8,98:1 |
| Główny przycisk wciśnięty | `#102039` / `#69a4fa` | 6,44:1 |
| Zwykły przycisk | `#f4f7fb` / `#202e44` | 12,73:1 |
| Zwykły przycisk po najechaniu | `#ffffff` / `#2a3f5c` | 10,69:1 |
| Przycisk nieaktywny | `#b4c0d2` / `#293448` | 6,80:1 |
| Aktywny etap / aktywny język | `#102039` / `#78afff` | 7,28:1 |
| Wybrana minuta | `#ffffff` / `#274f84` | 8,27:1 |
| Obramowanie kontrolki / jej tło | `#798ca9` / `#202e44` | 4,00:1 |
| Obwódka fokusu / otoczenie | `#ffd080` / `#10141c` | 12,81:1 |

## Granice weryfikacji

**Nie potwierdzono jeszcze pełnego procesu na fizycznym pendrivie Tesli**, w tym rzeczywistej zgody macOS na surowy odczyt USB i ewentualnych wymagań pełnego dostępu do dysku.
Nie wykonano testu prawdziwego konta Tesli, pobierania rzeczywistych kluczy ani odszyfrowania materiału z samochodu.
Test lokalnego AES potwierdza obsługę syntetycznych stron, nie integrację konta z serwisem Tesla.
Nie testowano działania na fizycznym Macu Intel; launcher zawiera oba warianty architektury.
Nie sprawdzono synchronizacji sześciu rzeczywistych kamer ani telemetrii z prawdziwego nagrania Tesli.

Aplikacja ma podpis ad hoc; nie ma certyfikatu Developer ID ani notaryzacji Apple.
Status „gotowe do odtwarzania” nie stanowi gwarancji kompletności odzyskanego nagrania.
