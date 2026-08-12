"""
Silnik dedukcji pól formularza wprowadzania z bazy - czysta logika, bez
display (`src/CLAUDE.md`: jeśli widget zaczyna decydować/szeregować, kod
należy do modułu logiki, nie do widoku).

Zasada jednolita (Papaver, 2026-08-12): jednoznaczne -> wypełniamy;
niejednoznaczne -> NIE wypełniamy, aktywujemy pole, sprzeczne warianty
dajemy jako kandydatów podpowiedzi. Rejon dedukowany z adresu (docelowo ma
zniknąć na rzecz integracji z rejonarzem - patrz roadmap.md), wykonawca
z kuriera.

Kolejność ma znaczenie - najpierw rozstrzygamy PUNKT (z adresu, opcjonalnie
zawężony podanym ręcznie nadawcą), dopiero z rozstrzygniętego punktu
wyprowadzamy nadawcę/PNI/rejon. PNI NIGDY nie jest dedukowane niezależnie
od nadawcy: przy adresie z dwoma nadawcami (np. Gemartis i Żabka pod tym
samym numerem) jednoznaczne PNI jednego z nich mogłoby po cichu podpiąć
transakcję pod zły punkt, mimo że pole nadawca poprawnie zostało puste jako
niejednoznaczne (`importer.get_or_create_punkt` kluczuje po PNI, nie po
adresie). Złapane przy planowaniu - 9,4% wierszy realnej próbki jest pod
adresami z więcej niż jednym nadawcą.

Ilość/"w tym ZPO" (poprawka Papavera, 2026-08-12) NIGDY nie są źródłem ani
bramą dedukcji innych pól - dedukcja rusza z kuriera/adresu niezależnie od
tego, czy Ilość jest jeszcze wypełniona. Jedyna rola Ilości to jednokierunkowe
autouzupełnienie "w tym ZPO", gdy nadawca ma PNI - i to dopiero PO tym, jak
nadawca jest już znany.
"""
from dataclasses import dataclass, field

from zpo_tracker import repo

STANY = ("szary", "zielony", "pomaranczowy", "czerwony")


@dataclass(frozen=True)
class StanPola:
    wartosc: object = None
    stan: str = "szary"
    aktywne: bool = False
    w_nawigacji: bool = False
    kandydaci: tuple = None
    powod: str = None


@dataclass(frozen=True)
class WynikWiersza:
    punkt_id: object = None
    kandydaci_punktow: tuple = ()
    pola: dict = field(default_factory=dict)


def _rozstrzygnij_punkt(conn, adres, nadawca):
    if not adres or not adres.strip():
        return [], None
    kandydaci = repo.znajdz_punkty_po_adresie(conn, adres)
    if len(kandydaci) > 1 and nadawca:
        zaweznone = [k for k in kandydaci if k["nadawca"] == nadawca]
        if len(zaweznone) == 1:
            kandydaci = zaweznone
    punkt_id = kandydaci[0]["id"] if len(kandydaci) == 1 else None
    return kandydaci, punkt_id


def dedukuj_wiersz(conn, *, kurier, adres, nadawca=None, ilosc_total=None, ilosc_zpo=None):
    """
    Dedukuje nadawcę/PNI/rejon z adresu (przez rozstrzygnięty punkt) i
    aktywność/wartość "w tym ZPO" z Ilości. `kurier` przyjmowany dla
    symetrii sygnatury i przyszłego użycia (wykonawca jest dziś dedukowany
    WYŁĄCZNIE na poziomie nagłówka blankietu, patrz `dedukuj_naglowek` -
    jeden blankiet = jeden kurier = jeden wykonawca, nie osobno per wiersz).
    """
    kandydaci_punktow, punkt_id = _rozstrzygnij_punkt(conn, adres, nadawca)
    pola = {}

    if not adres or not adres.strip():
        pola["nadawca"] = StanPola(stan="szary", aktywne=False)
    elif punkt_id is not None:
        pola["nadawca"] = StanPola(
            wartosc=kandydaci_punktow[0]["nadawca"], stan="zielony", aktywne=False)
    elif len(kandydaci_punktow) > 1:
        warianty = tuple(sorted({k["nadawca"] for k in kandydaci_punktow}))
        pola["nadawca"] = StanPola(
            stan="pomaranczowy", aktywne=True, w_nawigacji=True, kandydaci=warianty,
            powod="Kilku nadawców pod tym adresem - wybierz właściwego.")
    else:  # adres podany, zero trafień - nowy punkt
        pola["nadawca"] = StanPola(
            stan="czerwony", aktywne=True, w_nawigacji=True,
            powod="Nowy adres - wpisz nadawcę ręcznie.")

    nadawca_efektywny = nadawca or (
        pola["nadawca"].wartosc if pola["nadawca"].stan == "zielony" else None)

    # PNI: WYŁĄCZNIE z rozstrzygniętego punktu, nigdy niezależnie - patrz
    # docstring modułu
    if punkt_id is not None:
        pni = kandydaci_punktow[0]["pni_zpo"]
        if pni:
            pola["pni_zpo"] = StanPola(wartosc=pni, stan="zielony", aktywne=False)
        elif nadawca_efektywny and repo.czy_nadawca_ma_pni(conn, nadawca_efektywny):
            pola["pni_zpo"] = StanPola(
                stan="pomaranczowy", aktywne=True,
                powod="Ten nadawca ma PNI w innych lokalizacjach - "
                      "sprawdź, czy tu też nie powinno być.")
        else:
            pola["pni_zpo"] = StanPola(stan="zielony", aktywne=False)
    else:
        pola["pni_zpo"] = StanPola(stan="szary", aktywne=False)

    if punkt_id is not None:
        historia = repo.historia_rejonow_punktu(conn, punkt_id)
        kody = {h["kod"] for h in historia}
        if len(kody) == 1:
            pola["rejon"] = StanPola(wartosc=next(iter(kody)), stan="zielony", aktywne=False)
        elif len(kody) > 1:
            pola["rejon"] = StanPola(
                stan="pomaranczowy", aktywne=True, w_nawigacji=True,
                kandydaci=tuple(h["kod"] for h in historia),
                powod="Ten punkt bywał w różnych rejonach - wybierz właściwy.")
        else:
            pola["rejon"] = StanPola(
                stan="pomaranczowy", aktywne=True, w_nawigacji=True,
                powod="Brak historii rejonu dla tego punktu.")
    else:
        pola["rejon"] = StanPola(stan="szary", aktywne=False)

    # ilosc_zpo: aktywność <- WYŁĄCZNIE czy_nadawca_ma_pni, nigdy nie
    # bramowana przez ilosc_total (patrz docstring modułu) - ilosc_total
    # rządzi tylko WARTOŚCIĄ autouzupełnienia, nie aktywnością
    if nadawca_efektywny and repo.czy_nadawca_ma_pni(conn, nadawca_efektywny):
        wartosc = ilosc_zpo if ilosc_zpo is not None else ilosc_total
        pola["ilosc_zpo"] = StanPola(
            wartosc=wartosc, stan="zielony" if wartosc is not None else "pomaranczowy",
            aktywne=True)
    else:
        pola["ilosc_zpo"] = StanPola(stan="szary", aktywne=False)

    return WynikWiersza(
        punkt_id=punkt_id,
        kandydaci_punktow=tuple(k["id"] for k in kandydaci_punktow),
        pola=pola,
    )


def dedukuj_naglowek(conn, *, kurier, data):
    """Wykonawca z historii kuriera - patrz docstring modułu, dlaczego to
    poziom nagłówka, nie wiersza."""
    pola = {}
    if kurier and kurier.strip():
        historia = repo.historia_wykonawcow_kuriera(conn, kurier)
        nazwy = {h["nazwa"] for h in historia}
        if len(nazwy) == 1:
            pola["wykonawca"] = StanPola(
                wartosc=next(iter(nazwy)), stan="zielony", aktywne=False)
        elif len(nazwy) > 1:
            pola["wykonawca"] = StanPola(
                stan="pomaranczowy", aktywne=True, w_nawigacji=True,
                kandydaci=tuple(h["nazwa"] for h in historia),  # posortowane po świeżości
                powod="Ten kurier jeździł dla różnych wykonawców - wybierz aktualnego.")
        else:
            pola["wykonawca"] = StanPola(
                stan="pomaranczowy", aktywne=True, w_nawigacji=True,
                powod="Brak historii wykonawcy dla tego kuriera.")
    else:
        pola["wykonawca"] = StanPola(stan="szary", aktywne=False)
    return pola


def sprawdz_niezmienniki(pola, tryb):
    """
    Stany zakazane, wyłapywane testem, nie w produkcji: pomarańczowy/
    czerwony implikują aktywne; aktywne i nie-szare implikuje w_nawigacji
    (inaczej pole wymagające uwagi jest nieosiągalne z klawiatury - to był
    najgroźniejszy brak funkcjonalny poprzedniej wersji tego planu). Od
    0.1-alpha.3.2 w trybie manualnym dojdzie: stan != "szary".
    """
    for klucz, stan in pola.items():
        if stan.stan == "pomaranczowy":
            assert stan.aktywne, f"{klucz}: pomarańczowy musi być aktywne"
        if stan.stan == "czerwony":
            assert stan.aktywne, f"{klucz}: czerwony musi być aktywne"
        if stan.aktywne and stan.stan != "szary":
            assert stan.w_nawigacji, (
                f"{klucz}: aktywne pole wymagające uwagi musi być w kolejności nawigacji")
        if tryb == "manual":
            assert stan.stan != "szary", f"{klucz}: szary jest zakazany w trybie manualnym"


def kolejnosc_pol(tryb, wynik_naglowka, wyniki_wierszy):
    """
    Kolejność nawigacji TAB/Enter. Zwraca listę KLUCZY pól (krotki), NIE
    widgetów - mapowanie klucz->widget należy do GUI (`src/CLAUDE.md`:
    szeregowanie to logika, nie widok). Testowalne bez Tk i gotowe na
    polityki innych trybów w 0.1-alpha.3.2 (dziś istnieje tylko "auto").

    Pole pomarańczowe/czerwone (w_nawigacji=True) MUSI wejść do kolejności
    niezależnie od tego, że nie jest polem głównym - inaczej nie da się go
    wypełnić z klawiatury (np. nadawca nowego punktu).
    """
    if tryb != "auto":
        raise NotImplementedError(f"tryb {tryb!r} nie istnieje jeszcze - patrz 0.1-alpha.3.2")

    kolejnosc = [("naglowek", "kurier"), ("naglowek", "data")]
    for klucz, stan in wynik_naglowka.items():
        if stan.w_nawigacji:
            kolejnosc.append(("naglowek", klucz))

    for i, wynik in enumerate(wyniki_wierszy):
        kolejnosc.append(("wiersz", i, "adres"))
        for klucz, stan in wynik.pola.items():
            if klucz == "ilosc_zpo":
                continue  # idzie po ilosc_total, wizualnie sąsiaduje z nim
            if stan.w_nawigacji:
                kolejnosc.append(("wiersz", i, klucz))
        kolejnosc.append(("wiersz", i, "ilosc_total"))
        if wynik.pola.get("ilosc_zpo") and wynik.pola["ilosc_zpo"].aktywne:
            kolejnosc.append(("wiersz", i, "ilosc_zpo"))
    return kolejnosc


def przesun_w_kolejnosci(kolejnosc, biezace, kierunek):
    """
    Następny/poprzedni klucz pola dla Tab/Enter (kierunek=1) albo
    Shift-Tab/ISO_Left_Tab (kierunek=-1), z zawijaniem na końcach.
    `biezace` spoza `kolejnosc` (np. fokus trafił z zewnątrz w pole
    nieaktywne) startuje od początku/końca zamiast wybuchać. Pusta
    `kolejnosc` -> None (nie ma dokąd przejść).
    """
    if not kolejnosc:
        return None
    try:
        i = kolejnosc.index(biezace)
    except ValueError:
        return kolejnosc[0] if kierunek >= 0 else kolejnosc[-1]
    return kolejnosc[(i + kierunek) % len(kolejnosc)]
