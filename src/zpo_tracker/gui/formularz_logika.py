"""
Logika przygotowania blankietu formularza wprowadzania do zapisu - czysta,
bez widżetów. Widget w zakladka_wprowadzanie.py tylko zbiera surowe
wartości z pól i przekazuje tutaj; błędy walidacji (pydantic) wyświetla,
nie decyduje o nich.
"""
from zpo_tracker.models import Blankiet, WierszBlankietu


def wiersz_pusty(surowy):
    """Pusty wiersz-placeholder (np. niewypełniony dodatkowy wiersz)."""
    return not (surowy.get("nadawca") or "").strip() and not (surowy.get("adres") or "").strip()


def zbuduj_blankiet(kurier, data, wykonawca, dane_wierszy):
    """
    dane_wierszy: lista dictów pasujących do WierszBlankietu (w tym
    "rejon" per wiersz, 0.1-alpha.3.1). Zwraca gotowy do zapisu Blankiet,
    albo None, jeśli żaden wiersz nie został wypełniony (może rzucić
    pydantic.ValidationError - to jedyne źródło komunikatów o błędach).
    """
    wiersze_surowe = [w for w in dane_wierszy if not wiersz_pusty(w)]
    if not wiersze_surowe:
        return None
    wiersze = [WierszBlankietu(**w) for w in wiersze_surowe]
    return Blankiet(kurier=kurier, data=data, wykonawca=wykonawca, wiersze=wiersze)
