"""
Modele pydantic v2 - walidacja na granicach (wiersz importu .xlsx, blok
z formularza wprowadzania). Świadomie NIE odwzorowują tabel SQL 1:1 -
warstwa SQL zostaje na czystym sqlite3 (docs/tech-decisions.md).
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from zpo_tracker.importer import parse_quantity
from zpo_tracker.normalizacja import klucz_bialych_znakow

_POLA_ILOSCI = (
    "ilosc_total",
    "ilosc_zpo",
    "ilosc_vinted",
    "ilosc_automaty",
    "ilosc_kurier48",
    "ilosc_niezrealizowane",
)


class WierszImportu(BaseModel):
    """Wiersz z pliku .xlsx po walidacji, przed zapisem do bazy."""

    data: date
    nadawca: str
    adres: str
    kurier: str
    rejon: Optional[str] = None
    wykonawca: Optional[str] = None
    pni_zpo: Optional[str] = None
    ilosc_total: int = Field(ge=0)
    ilosc_zpo: Optional[int] = Field(default=None, ge=0)
    ilosc_vinted: Optional[int] = Field(default=None, ge=0)
    ilosc_automaty: Optional[int] = Field(default=None, ge=0)
    ilosc_kurier48: Optional[int] = Field(default=None, ge=0)
    ilosc_niezrealizowane: Optional[int] = Field(default=None, ge=0)

    @field_validator("data", mode="before")
    @classmethod
    def _konwertuj_date(cls, v):
        # xlsx (openpyxl) daje datetime.datetime, nie datetime.date
        if hasattr(v, "date") and not isinstance(v, str):
            return v.date()
        return v

    @field_validator(*_POLA_ILOSCI, mode="before")
    @classmethod
    def _parsuj_ilosc(cls, v):
        return parse_quantity(v)

    @field_validator("pni_zpo", "rejon", "wykonawca", mode="before")
    @classmethod
    def _pusty_string_na_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("kurier", "nadawca", "adres", mode="before")
    @classmethod
    def _normalizuj_biale_znaki(cls, v):
        # bezpieczne, automatyczne scalanie (tier 1 normalizacji, patrz
        # normalizacja.py) - musi się dziać na wejściu, nie tylko przy
        # wykrywaniu literówek, inaczej "Michalak Maciej " zostaje osobnym
        # kurierem w bazie
        if isinstance(v, str):
            return klucz_bialych_znakow(v)
        return v


class WierszBlankietu(BaseModel):
    """
    Pojedynczy wiersz formularza wprowadzania: punkt + rejon + ilość.
    Rejon per wiersz od 0.1-alpha.3.1 (dedukowany z adresu, patrz
    dedukcja.py) - `transakcje.rejon_id` był per wiersz w bazie/imporcie/
    eksporcie od zawsze, formularz (bloki REJON+DATA) tylko dogonił.
    """

    nadawca: str = Field(min_length=1)
    adres: str = Field(min_length=1)
    pni_zpo: Optional[str] = None
    rejon: Optional[str] = None
    ilosc_total: int = Field(ge=0)
    ilosc_zpo: Optional[int] = Field(default=None, ge=0)

    @field_validator("nadawca", "adres", mode="before")
    @classmethod
    def _normalizuj_biale_znaki(cls, v):
        if isinstance(v, str):
            return klucz_bialych_znakow(v)
        return v

    @field_validator("pni_zpo", "rejon", mode="before")
    @classmethod
    def _pusty_string_na_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class Blankiet(BaseModel):
    """
    Jeden papierowy blankiet = jeden kurier na jeden dzień (0.1-alpha.3.1 -
    bloki REJON+DATA zniknęły, rejon jest teraz per wiersz, patrz
    WierszBlankietu; komentarz per blok zniknął z formularza, kolumna w
    bazie zostaje dla danych historycznych). `wykonawca` dedukowany na
    poziomie nagłówka (dedukcja.dedukuj_naglowek - jeden kurier, jeden
    wykonawca na dzień, nie osobno per punkt), ale to wciąż atrybut wiersza
    w bazie - ta sama wartość aplikowana do każdego wiersza przy zapisie.
    """

    kurier: str = Field(min_length=1)
    data: date
    wykonawca: Optional[str] = None
    wiersze: list[WierszBlankietu]

    @field_validator("kurier", mode="before")
    @classmethod
    def _normalizuj_kuriera(cls, v):
        if isinstance(v, str):
            return klucz_bialych_znakow(v)
        return v

    @field_validator("wykonawca", mode="before")
    @classmethod
    def _pusty_string_na_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @model_validator(mode="after")
    def _wymaga_co_najmniej_jednego_wiersza(self):
        if not self.wiersze:
            raise ValueError("blankiet musi mieć co najmniej jeden wiersz punkt+ilość")
        return self
