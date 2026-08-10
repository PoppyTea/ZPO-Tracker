"""
Logika przygotowania bloków formularza wprowadzania do zapisu - czysta,
bez widżetów. Widget w zakladka_wprowadzanie.py tylko zbiera surowe
wartości z pól i przekazuje tutaj; błędy walidacji (pydantic) wyświetla,
nie decyduje o nich.
"""
from zpo_tracker.models import BlankietBlok, WierszBlankietu


def _wiersz_pusty(surowy):
    """Pusty wiersz-placeholder (np. niewypełniony dodatkowy wiersz w bloku)."""
    return not (surowy.get("nadawca") or "").strip() and not (surowy.get("adres") or "").strip()


def zbuduj_bloki(kurier, wykonawca, dane_blokow):
    """
    dane_blokow: lista dictów {"rejon", "data", "komentarz", "wiersze": [...]},
    gdzie każdy wiersz to dict pasujący do WierszBlankietu.
    Zwraca listę BlankietBlok gotowych do repo.zapisz_blok (może rzucić
    pydantic.ValidationError - to jedyne źródło komunikatów o błędach).
    Bloki bez ani jednego niepustego wiersza są pomijane (np. dodany
    przyciskiem "dodaj rejon", ale nigdy nieuzupełniony).
    """
    bloki = []
    for surowy_blok in dane_blokow:
        wiersze_surowe = [w for w in surowy_blok["wiersze"] if not _wiersz_pusty(w)]
        if not wiersze_surowe:
            continue
        wiersze = [WierszBlankietu(**w) for w in wiersze_surowe]
        bloki.append(BlankietBlok(
            kurier=kurier,
            data=surowy_blok["data"],
            rejon=surowy_blok.get("rejon"),
            wykonawca=wykonawca,
            komentarz=surowy_blok.get("komentarz"),
            wiersze=wiersze,
        ))
    return bloki
