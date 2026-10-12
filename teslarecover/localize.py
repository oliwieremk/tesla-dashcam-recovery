"""Polish user-facing phases; technical details remain available for troubleshooting."""
import re

PHASES = {
    'Starting': 'Rozpoczynam pracę', 'Reading folders': 'Przeglądam foldery',
    'Reading existing clips': 'Sprawdzam istniejące nagrania',
    'Searching free space for deleted clips': 'Szukam usuniętych nagrań w wolnym miejscu',
    'Copied': 'Kopiowanie zakończone', 'Getting keys from Tesla': 'Pobieram klucze z Tesli',
    'Decrypting': 'Odszyfrowuję nagrania', 'Reading clip details': 'Sprawdzam i nazywam nagrania',
    'Done': 'Zakończono', 'Saved': 'Zapis zakończony',
    'Opening the Tesla sign-in window': 'Otwieram okno logowania Tesla',
    'Waiting for you to sign in in the Tesla window': 'Zaloguj się w otwartym oknie Tesla',
    'Reading your Tesla sign-in': 'Kończę logowanie do Tesli', 'Signed in': 'Zalogowano',
    'Opened one of your clips on dashcam.tesla.com to finish signing in': 'Kończę logowanie na stronie Tesla z użyciem skopiowanego klipu',
    'Almost done: open any encrypted clip on the dashcam.tesla.com page': 'Otwórz zaszyfrowany klip na stronie dashcam.tesla.com, aby zakończyć logowanie',
    'Downloading the sign-in browser (one time)': 'Pobieram przeglądarkę do logowania (jednorazowo)',
}


def phase_pl(text):
    if text in PHASES:
        return PHASES[text]
    for prefix, label in (('Copying ', 'Kopiuję '), ('Saving ', 'Zapisuję '),
                          ('Repairing ', 'Naprawiam ')):
        if text.startswith(prefix):
            return label + text[len(prefix):].replace('deleted clip ', 'usunięty klip ')
    if text.startswith('Downloading the sign-in browser'):
        return PHASES['Downloading the sign-in browser (one time)'] + text.split('(one time)', 1)[-1]
    return text


def error_pl(text):
    errors = (
        (r'not an exFAT or FAT32|allocation bitmap|unpack|index out of range',
         'Nie można odczytać partycji FAT32/exFAT. Wybierz obraz samej partycji, bez tablicy GPT/MBR, lub sprawdź stan nośnika.'),
        (r'denied|permission|operation not permitted',
         'macOS odmówił dostępu do nośnika. Włącz pełny dostęp do dysku dla aplikacji uruchamiającej odzyskiwanie i spróbuj ponownie.'),
        (r'No space left', 'Brakuje miejsca na dysku docelowym. Wybierz inny folder lub mniejszy zakres nagrań.'),
        (r'expired|refused.*sign|sign.in expired', 'Logowanie Tesla wygasło lub zostało odrzucone. Zaloguj się ponownie.'),
        (r'Sign-in took too long', 'Upłynął czas logowania. Spróbuj ponownie.'),
        (r'closed.*signing|tab was closed', 'Okno Tesla zamknięto przed zakończeniem logowania.'),
        (r'Downloading.*failed', 'Nie udało się pobrać przeglądarki. Sprawdź połączenie z internetem i spróbuj ponownie.'),
        (r'No such file|FileNotFound', 'Plik lub nośnik nie jest dostępny. Sprawdź połączenie i wybierz źródło ponownie.'),
        (r'Input/output error|Device not configured', 'Utracono połączenie z nośnikiem albo wystąpił błąd odczytu. Sprawdź kabel i podłączenie USB.'),
    )
    for pattern, result in errors:
        if re.search(pattern, text, re.I):
            return result
    if re.search(r'[ąćęłńóśźż]', text, re.I) or text.startswith(('Nie ', 'Brak ', 'Wybierz ', 'Najpierw ')):
        return text
    return 'Nie udało się ukończyć operacji. Rozwiń szczegóły błędu, aby sprawdzić przyczynę.'


def quality(entry):
    """Absence of recovery warnings is never a guarantee that all footage survived."""
    status = entry.get('status')
    if status == 'unplayable':
        return {'code': 'unplayable', 'label': 'Nieodtwarzalne', 'note': 'Nie udało się przygotować pliku do odtwarzania.'}
    if status == 'key_error':
        return {'code': 'encrypted', 'label': 'Brak klucza', 'note': 'Tesla nie zwróciła klucza do tego nagrania.'}
    if entry.get('truncated') or entry.get('gap'):
        return {'code': 'partial', 'label': 'Częściowo odzyskane', 'note': 'Wykryto brakujące lub rozdzielone dane. Nagranie może być krótsze.'}
    if entry.get('repaired'):
        duration = entry.get('repaired_seconds')
        return {'code': 'repaired', 'label': 'Naprawione',
                'note': f'Odbudowano plik; zachowano {duration} s nagrania.' if duration else 'Odbudowano strukturę pliku. Część nagrania mogła nie przetrwać.'}
    if status == 'ok':
        return {'code': 'ready', 'label': 'Gotowe do odtwarzania', 'note': 'Struktura pliku odczytana. Kompletność treści potwierdź podczas oglądania.'}
    if status in ('encrypted', 'raw', 'plain'):
        return {'code': 'encrypted' if status == 'encrypted' else 'unverified',
                'label': 'Zaszyfrowane' if status == 'encrypted' else 'Do weryfikacji',
                'note': 'Plik skopiowany; czeka na przygotowanie do odtwarzania.'}
    return {'code': 'unverified', 'label': 'Do weryfikacji', 'note': 'Odnaleziono dane. Odtwarzalność i kompletność nie są jeszcze potwierdzone.'}

# One shared catalog is used by the GUI and the HTTP API.
import json
from pathlib import Path
CATALOG = json.loads((Path(__file__).parent / 'static' / 'i18n.json').read_text(encoding='utf-8'))


def translate(text, language='pl', values=()):
    result = CATALOG.get(text, text) if language == 'en' else text
    return re.sub(r'\{(\d+)\}', lambda match: str(values[int(match[1])]) if int(match[1]) < len(values) else match[0], result)


def phase(text, language='pl'):
    if language == 'pl':
        return phase_pl(text)
    if text in PHASES:
        return text
    reverse = {value: key for key, value in PHASES.items()}
    if text in reverse:
        return reverse[text]
    for source, english in (('Copying ', 'Copying '), ('Kopiuję ', 'Copying '),
                            ('Saving ', 'Saving '), ('Zapisuję ', 'Saving '),
                            ('Repairing ', 'Repairing '), ('Naprawiam ', 'Repairing ')):
        if text.startswith(source):
            return english + text[len(source):].replace('usunięty klip ', 'deleted clip ')
    if text.startswith('Downloading the sign-in browser'):
        return text
    return translate(text, language)


def localized_error(text, language='pl'):
    return translate(error_pl(text), language)


def native_strings(language):
    pairs = {
        'global.quitConfirmation': ('Czy na pewno zakończyć?', 'Do you really want to quit?'),
        'global.ok': ('OK', 'OK'), 'global.quit': ('Zakończ', 'Quit'), 'global.cancel': ('Anuluj', 'Cancel'),
        'global.saveFile': ('Zapisz plik', 'Save file'),
        'cocoa.menu.about': ('O aplikacji', 'About'), 'cocoa.menu.services': ('Usługi', 'Services'),
        'cocoa.menu.view': ('Widok', 'View'), 'cocoa.menu.edit': ('Edycja', 'Edit'),
        'cocoa.menu.hide': ('Ukryj', 'Hide'), 'cocoa.menu.hideOthers': ('Ukryj pozostałe', 'Hide Others'),
        'cocoa.menu.showAll': ('Pokaż wszystko', 'Show All'), 'cocoa.menu.quit': ('Zakończ', 'Quit'),
        'cocoa.menu.fullscreen': ('Pełny ekran', 'Enter Fullscreen'), 'cocoa.menu.cut': ('Wytnij', 'Cut'),
        'cocoa.menu.copy': ('Kopiuj', 'Copy'), 'cocoa.menu.paste': ('Wklej', 'Paste'),
        'cocoa.menu.selectAll': ('Zaznacz wszystko', 'Select All'),
        'windows.fileFilter.allFiles': ('Wszystkie pliki', 'All files'),
        'windows.fileFilter.otherFiles': ('Inne typy plików', 'Other file types'),
        'linux.openFile': ('Otwórz plik', 'Open file'), 'linux.openFiles': ('Otwórz pliki', 'Open files'),
        'linux.openFolder': ('Otwórz folder', 'Open folder'),
    }
    return {key: value[language == 'en'] for key, value in pairs.items()}


def localize_quality(entry, language='pl'):
    value = quality(entry)
    value['label'] = translate(value['label'], language)
    if entry.get('repaired') and value['code'] == 'repaired' and entry.get('repaired_seconds'):
        value['note'] = translate('Odbudowano plik; zachowano {0} s nagrania.', language, [entry['repaired_seconds']])
    else:
        value['note'] = translate(value['note'], language)
    return value
