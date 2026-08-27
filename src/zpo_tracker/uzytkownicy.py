"""
Tożsamość osoby wprowadzającej dane - kto zmienił który wiersz.

Sedno: `users.id` to **UUIDv5 wyliczone deterministycznie z
`domena\\login`**, a NIE losowy UUID nadawany przy pierwszym zetknięciu
z nieznanym loginem. Losowy rozjechałby się między stacjami: każda nadałaby
temu samemu człowiekowi inny identyfikator, a po ich zsynchronizowaniu ta
sama osoba istniałaby wielokrotnie i atrybucja przestałaby cokolwiek
znaczyć. UUIDv5 liczy się identycznie na każdej stacji, bez koordynacji
i bez wyścigu przy pierwszym uruchomieniu.

**Nr kadrowy to atrybut biznesowy OBOK UUID, nie zamiast.** Kusi, żeby
zrobić z niego klucz główny ("to przecież firmowy identyfikator"), ale
wpisuje go człowiek, a 5 znaków bez sumy kontrolnej znaczy, że literówka
jest niewykrywalna i rozniosłaby się po synchronizacji. UUID nie jest
nigdy wpisywany, więc nie może zostać przekręcony. Trzymanie obu daje
kontrolę krzyżową za darmo - patrz `ostrzezenia_tozsamosci`.

Numery kadrowe KURIERÓW to zupełnie inny byt: inny format i relacja
1 kurier : N numerów (patrz docs/roadmap.md). Nie mylić.
"""
import os
import re
import uuid
from datetime import datetime

# Stała przestrzeń nazw - NIE zmieniać. Zmiana unieważniłaby wszystkie
# dotychczasowe identyfikatory i rozdwoiła każdą osobę w bazie.
NAMESPACE_ZPO = uuid.UUID("c8d99132-35c0-5978-b932-1c21a5d1edb7")

_WZORZEC_NR_KADROWEGO = re.compile(r"^[a-zA-Z0-9]{5}$")


def uuid_uzytkownika(login):
    """
    Deterministyczny identyfikator osoby. Login jest sprowadzany do małych
    liter, bo Windows nie rozróżnia wielkości liter w nazwach kont -
    "JKowalski" i "jkowalski" to ta sama osoba.
    """
    return str(uuid.uuid5(NAMESPACE_ZPO, login.strip().lower()))


def biezacy_login(srodowisko=None):
    """
    Login zalogowanego użytkownika w formie "DOMENA\\konto". Domena jest
    częścią tożsamości: sam login bywa powtarzalny między domenami.
    """
    srodowisko = srodowisko if srodowisko is not None else os.environ
    konto = (srodowisko.get("USERNAME") or srodowisko.get("USER") or "").strip()
    domena = (srodowisko.get("USERDOMAIN") or "").strip()
    if not konto:
        return ""
    return f"{domena}\\{konto}" if domena else konto


def poprawny_nr_kadrowy(nr):
    """Dokładnie 5 znaków [a-zA-Z0-9]. Case sensitive (wymóg organizacji)."""
    if not isinstance(nr, str):
        return False
    return bool(_WZORZEC_NR_KADROWEGO.match(nr))


def zapewnij_uzytkownika(conn, login, alias=None, nr_kadrowy=None, teraz=None):
    """
    Zwraca `users.id` dla podanego loginu, tworząc wpis, jeśli go nie ma.
    Idempotentne. `alias`/`nr_kadrowy` są aktualizowane, gdy podane -
    zmiana aliasu NIE zmienia tożsamości (to tylko etykieta wyświetlana).
    """
    uid = uuid_uzytkownika(login)
    teraz = teraz or datetime.now().isoformat(timespec="seconds")

    istnieje = conn.execute(
        "SELECT id FROM users WHERE id = ?", (uid,)).fetchone()
    if istnieje is None:
        conn.execute(
            "INSERT INTO users(id, login, alias, nr_kadrowy, utworzono)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid, login, alias, nr_kadrowy, teraz),
        )
        return uid

    if alias is not None:
        conn.execute("UPDATE users SET alias = ? WHERE id = ?", (alias, uid))
    if nr_kadrowy is not None:
        conn.execute(
            "UPDATE users SET nr_kadrowy = ? WHERE id = ?", (nr_kadrowy, uid))
    return uid


def pobierz_uzytkownika(conn, login):
    return conn.execute(
        "SELECT id, login, alias, nr_kadrowy FROM users WHERE id = ?",
        (uuid_uzytkownika(login),),
    ).fetchone()


def wymaga_uzupelnienia(conn, login):
    """
    Czy pokazać popup "podaj imię i nazwisko" przy starcie. True także
    wtedy, gdy użytkownika w ogóle jeszcze nie ma.

    0.1-alpha.3.2: nr kadrowy PRZESTAŁ być tu sprawdzany - w momencie
    wdrożenia pracownicy jeszcze go nie mają, więc nie może blokować
    pierwszego uruchomienia. Pole zostaje w dialogu jako opcjonalne,
    przywracalne do wymaganego później bez zmiany UI.
    """
    wiersz = pobierz_uzytkownika(conn, login)
    if wiersz is None:
        return True
    return not wiersz["alias"]


# Proces logowania jest ŚWIADOMIE WSTRZYMANY. Powód: pracownicy nie mają
# jeszcze numerów kadrowych, a cała ścieżka tożsamości czeka na
# rozstrzygnięcie. Dopóki czeka, program nie wita użytkownika okienkiem,
# którego nie da się sensownie wypełnić.
#
# To NIE jest usunięcie funkcji: dialog zostaje osiągalny z menu
# („Zmień użytkownika…"), a `autor_id` i tak powstaje z loginu Windows,
# więc atrybucja wpisów działa bez pytania o cokolwiek. Wstrzymane jest
# wyłącznie zaczepianie człowieka przy starcie.
LOGOWANIE_WSTRZYMANE = True


def czy_pytac_o_dane(conn, login, dane_ustawien=None) -> bool:
    """
    Czy pokazać dialog uzupełnienia danych przy starcie.

    Rozdzielone od `wymaga_uzupelnienia` celowo. Tamto jest predykatem
    o STANIE DANYCH („alias jest pusty") i ma dalej odpowiadać zgodnie
    z prawdą — na nim stoją inne ścieżki. Wstrzymana jest DECYZJA
    o pokazaniu okna, a to dwie różne rzeczy i zlanie ich w jedną
    kazałoby kłamać predykatowi.

    Wznowienie nie wymaga nowego `.exe`: wystarczy wpis
    `zaawansowane.pytaj_o_dane_uzytkownika` w `settings.json`.
    """
    wznowione = bool(
        (dane_ustawien or {}).get("zaawansowane", {}).get("pytaj_o_dane_uzytkownika"))
    if LOGOWANIE_WSTRZYMANE and not wznowione:
        return False
    return wymaga_uzupelnienia(conn, login)


def ostrzezenia_tozsamosci(conn, login, nr_kadrowy):
    """
    Kontrola krzyżowa UUID <-> nr kadrowy. **Miękkie ostrzeżenia, nie
    blokady** (docs/ux-ui.md) - zapis ma się udać, człowiek ma się
    dowiedzieć, że coś nie gra.
    """
    ostrzezenia = []
    if not nr_kadrowy:
        return ostrzezenia
    uid = uuid_uzytkownika(login)

    wlasny = conn.execute(
        "SELECT nr_kadrowy FROM users WHERE id = ?", (uid,)).fetchone()
    if wlasny and wlasny["nr_kadrowy"] and wlasny["nr_kadrowy"] != nr_kadrowy:
        ostrzezenia.append(
            f"To konto miało dotąd numer kadrowy „{wlasny['nr_kadrowy']}”, "
            f"a podano „{nr_kadrowy}”. Sprawdź, czy to nie literówka."
        )

    obcy = conn.execute(
        "SELECT login FROM users WHERE nr_kadrowy = ? AND id <> ?",
        (nr_kadrowy, uid),
    ).fetchone()
    if obcy:
        ostrzezenia.append(
            f"Numer kadrowy „{nr_kadrowy}” jest już przypisany do konta "
            f"„{obcy['login']}”. To zwykle znaczy, że ta sama osoba pracuje "
            f"na dwóch kontach Windows."
        )
    return ostrzezenia


# --- 0.1-alpha.3.2: współdzielone konta Windows ---

def login_rozszerzony(login_bazowy, alias):
    """
    Login "rozszerzony" o alias: `DOMENA\\konto#Imię Nazwisko`. Pozwala
    kilku osobom pracującym na TYM SAMYM koncie Windows mieć osobną
    tożsamość w `users` bez wprowadzania nowego mechanizmu identyfikacji -
    to wciąż zwykły string wchodzący do `uuid_uzytkownika` (ta sama
    maszyneria UUIDv5), więc pozostaje deterministyczny między stacjami.
    """
    return f"{login_bazowy}#{alias}"


def znajdz_konta_dla_loginu(conn, login_bazowy):
    """
    Wszystkie konta "spod" tego loginu Windows: samo konto bazowe oraz
    wszystkie jego warianty rozszerzone (patrz `login_rozszerzony`) - lista
    do wyboru w oknie "kto teraz pracuje" (zmiana użytkownika/wyloguj).
    Alfabetycznie po aliasie.
    """
    # substr zamiast LIKE - login_bazowy może zawierać "_"/"%", które LIKE
    # potraktowałby jak wieloznaczniki i dopasował cudze konto
    prefiks = login_bazowy + "#"
    wiersze = conn.execute(
        "SELECT id, login, alias, nr_kadrowy FROM users"
        " WHERE login = ? OR substr(login, 1, ?) = ? ORDER BY alias",
        (login_bazowy, len(prefiks), prefiks),
    ).fetchall()
    return [dict(w) for w in wiersze]
