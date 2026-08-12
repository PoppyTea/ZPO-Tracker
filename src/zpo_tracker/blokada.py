"""
Blokada jednej instancji na katalog danych (`app.main`, patrz `0.1-alpha.3`
w roadmap.md) - blokada pliku na poziomie systemu operacyjnego, NIE zapis
PID-u do pliku i sprawdzanie go później: PID martwego procesu bywa
ponownie przydzielony innemu, żywemu procesowi (typowe po restarcie
systemu), więc sama obecność pliku z PID-em niczego by nie gwarantowała.
System operacyjny zwalnia blokadę pliku automatycznie nawet przy awarii
procesu (kill -9, crash) - nie trzeba jej ręcznie sprzątać.

Windows: `msvcrt.locking`. POSIX (maszyna deweloperska): `fcntl.flock`.
Ścieżka Windows nie jest tu odpalana w testach (maszyna dev to Linux) -
zweryfikowana przeglądem kodu, patrz `docs/environment.md`.
"""
import sys
from pathlib import Path

NAZWA_PLIKU = "zpo_tracker.lock"


class Blokada:
    def __init__(self, katalog_danych):
        self._sciezka = Path(katalog_danych) / NAZWA_PLIKU
        self._plik = None

    def zdobadz(self):
        self._sciezka.parent.mkdir(parents=True, exist_ok=True)
        plik = open(self._sciezka, "a+")
        try:
            _zablokuj(plik)
        except OSError:
            plik.close()
            return False
        self._plik = plik
        return True

    def zwolnij(self):
        if self._plik is None:
            return
        _odblokuj(self._plik)
        self._plik.close()
        self._plik = None

    def __enter__(self):
        return self.zdobadz()

    def __exit__(self, *_wyjatek):
        self.zwolnij()


def _zablokuj(plik):
    if sys.platform == "win32":
        import msvcrt
        plik.seek(0)
        msvcrt.locking(plik.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(plik.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _odblokuj(plik):
    if sys.platform == "win32":
        import msvcrt
        plik.seek(0)
        msvcrt.locking(plik.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(plik.fileno(), fcntl.LOCK_UN)
