# Tesla Recovery — macOS (PL / EN)

Port projektu [Arquiteto](https://github.com/Arquiteto/tesla-dashcam-recovery), licencja MIT.
To nieoficjalna aplikacja do odzyskiwania własnych nagrań Tesli.

**[Pobierz ZIP z Releases](https://github.com/oliwieremk/tesla-dashcam-recovery/releases/tag/macos-v0.3.0)** · [English instructions](README-MAC-EN.md)

## Uruchomienie z Findera

1. Rozpakuj `tesla-recovery-macos-pl-en.zip` na dysku Maca.
2. Przenieś **Tesla Recovery.app** do folderu Aplikacje lub pozostaw w rozpakowanym folderze.
3. Otwórz aplikację dwukrotnym kliknięciem. Przy pierwszym starcie pokaże się okno przygotowania:
   pobrane zostaną uv, Python 3.14 i potrzebne składniki. Wymagany jest internet.
4. Podłącz pendrive Tesli. W oknie wybierz jego kartę, sprawdź nazwę i pojemność, a następnie kliknij **Skanuj wybrane źródło**.
5. macOS poprosi o hasło administratora do odczytu tego USB. Wpisz je wyłącznie w oknie systemowym.
6. Wybierz zakres na osi czasu lub kliknij sesję. Wskaż pusty folder na Macu i skopiuj pliki.
7. Dla zaszyfrowanych nagrań zaloguj się do Tesli, następnie wybierz **Przygotuj nagrania**.
   Nagrania niezaszyfrowane pomijają etap logowania.
8. Otwórz odtwarzacz. Kliknięcie kamery ją powiększa; klawisze 1–6 wybierają kamerę, 0 wraca do siatki.

Launcher `.app` jest uniwersalny (Apple Silicon i Intel), wymaga macOS 13 lub nowszego.
Sprawdzono uruchomienie na Apple Silicon; działania na fizycznym Macu Intel jeszcze nie zweryfikowano.
Paczka ma lokalny podpis ad hoc, bez certyfikatu Developer ID i notaryzacji Apple.
Jeśli macOS zablokuje uruchomienie, użyj opcji Otwórz w menu kontekstowym lub ustawieniach Prywatność i ochrona.

## Język i ikona

Przyciski **PL / EN** w nagłówku zmieniają język interfejsu. Wybór jest zapamiętywany na kolejne uruchomienie.
Zmiana języka nie przerywa operacji ani nie zeruje zakresu, zaznaczonych minut czy pozycji odtwarzania.
Tłumaczone są również komunikaty postępu, opisy jakości i menu aplikacji.

Aplikacja ma własną ikonę kamery i odzyskiwania w Finderze, Docku oraz nagłówku.
Podczas pierwszego przygotowania widoczna jest ikona launchera; po uruchomieniu okna launcher
usuwa swój dodatkowy wpis z Docka. Jeśli w Docku pozostał skrót do starej wersji `Tesla Recovery PL.app`,
usuń ten skrót i przypnij nową `Tesla Recovery.app`.

Przyciski mają jawne kolory aktywne, po najechaniu i nieaktywne. Fokus klawiatury jest oznaczony
jasną obwódką. Nieaktywne przyciski nie znikają przez obniżenie przezroczystości.

## Odczyt USB i uprawnienia

Aplikacja i przeglądarka działają jako zwykły użytkownik. Krótko działający pomocnik
z uprawnieniami administratora odmontowuje wyłącznie wybraną zewnętrzną partycję FAT32/exFAT
i przekazuje aplikacji dostęp tylko do odczytu. Nie zmienia uprawnień plików urządzenia.
Hasło nie trafia do serwera aplikacji ani do Tesli.

Na czas odzyskiwania USB znika z Findera. Po zamknięciu okna lub użyciu przycisku **Zakończ odczyt USB**
zostaje ponownie zamontowane. Przy zmianie USB poprzedni nośnik również zostanie zwolniony.
Nie odłączaj go podczas skanowania/kopiowania. Po wymuszonym zakończeniu użyj Narzędzia dyskowego,
aby ponownie zamontować nośnik.

W razie odmowy dostępu: Ustawienia systemowe → Prywatność i ochrona → Pełny dostęp do dysku.
Dla skryptu `.command` włącz dostęp dla Terminala. Przy `.app` zgoda może być potrzebna dla
aplikacji/procesu, który uruchamia odczyt. Komunikat błędu ma dodatkowe szczegóły pomagające ustalić przyczynę.

## Oś czasu i statusy

- Filtr dnia ogranicza widoczne sesje i zaznacza ich zakres.
- Powiększenie zwiększa szerokość osi czasu; można przewijać ją poziomo.
- Przeciągnięcie wybiera zakres, a pola Od/do pozwalają wpisać dokładny czas w strefie czasowej Maca.
- Długie przerwy między sesjami są skrócone i oznaczone odstępami na osi.
- **Wybierz wszystko** usuwa filtr i zaznacza także klipy z nieustalonym czasem.

Status **Do weryfikacji** oznacza odnalezione dane, nie gwarancję działającego filmu.
**Częściowo odzyskane** oznacza wykryte braki albo przerwy w danych. **Naprawione** oznacza
odbudowaną strukturę pliku; jeśli dostępna, pokazana jest długość zachowanego nagrania.
**Gotowe do odtwarzania** oznacza odczytaną strukturę pliku, nie pewność, że przetrwała cała treść.
Kompletność potwierdź podczas oglądania. **Nieodtwarzalne** oznacza, że przygotowanie pliku się nie powiodło.

W odtwarzaczu ⌘ / Ctrl + klik zaznacza minuty, Shift + klik rozszerza zaznaczenie.
Przycisk **Zapisz wybór** kopiuje je do innego folderu. Spacja steruje odtwarzaniem,
a strzałki w lewo/prawo przewijają o 5 sekund. Telemetria pojawia się, jeśli jest obecna w nagraniu.

## Obrazy partycji i istniejące biblioteki

Przycisk **Otwórz obraz partycji** przyjmuje nieskompresowane obrazy `.img`, `.raw` i `.dd`.
Plik musi zaczynać się sektorem rozruchowym partycji FAT32/exFAT. Całe dyski z GPT/MBR i skompresowane DMG
nie są obsługiwane. Praca na obrazie nie wymaga hasła administratora.
**Otwórz bibliotekę** otwiera wcześniej odzyskane nagrania.

Skrypt `Tesla Recover.command` i kod źródłowy są także w `Tesla Recovery.app/Contents/Resources/app`.
Można uruchomić go z Terminala, np.:

```bash
./"Tesla Recover.command" --image "/ścieżka/do/tesla-partition.img"
./"Tesla Recover.command" --library "/ścieżka/do/odzyskanych"
```

## Pliki aplikacji

Składniki, profil przeglądarki i ustawienia: `~/Library/Application Support/TeslaRecover`.
Dziennik startu `.app`: `~/Library/Application Support/TeslaRecover/startup.log`.
Nagrania zapisują się tylko w wybranym folderze docelowym. Token dostępu jest przechowywany w pamięci, bez zapisywania w ustawieniach. Osobny profil przeglądarki może zachować sesję logowania Tesli.

## Sprawdzone i niesprawdzone

Testy obejmują syntetyczny obraz exFAT, odnajdywanie klipów w wolnych klastrach, dokładne kopiowanie
fragmentowanego istniejącego pliku, niezmienność źródła, przekazywanie dostępu tylko do odczytu,
odrzucanie dysków wewnętrznych, anulowanie zgody macOS, walidację obrazów i oznaczenia jakości.
Sprawdzono także obie wersje językowe w natywnym oknie, zapamiętywanie języka, start launchera `.app`, odtwarzanie wygenerowanego MP4 i kontrast przycisków. Testy multimediów obejmują przygotowanie i dekodowanie MP4, odbudowę brakującego indeksu oraz lokalne odszyfrowanie syntetycznych stron AES. To nie jest test kluczy pobieranych z Tesli.

Nie sprawdzono pełnego odzyskiwania z fizycznego pendrive’a Tesli, odszyfrowania prawdziwych
zaszyfrowanych nagrań ani całego procesu autoryzacji fizycznego USB. Logowanie Tesla i istniejący
silnik odszyfrowywania zachowują mechanizm projektu bazowego; działanie na rzeczywistych danych
wymaga osobnego testu. Paczka nie zawiera nagrań ani danych konta.
