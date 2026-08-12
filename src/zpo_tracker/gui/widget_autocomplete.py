"""
Pole tekstowe z podpowiedziami: dropdown pod polem + nawigacja klawiaturą.
Logika dopasowania jest w podpowiedzi.py (testowana, bez GUI) - ten widget
tylko wyświetla wyniki i obsługuje klawiaturę. Wpięty do
zakladka_wprowadzanie.py (kurier/nadawca/adres), zweryfikowany zarówno
zrzutem ekranu jak i test_widget_autocomplete.py.

Ghost text (nakładka z podpowiedzią przed kursorem) świadomie NIE
zaimplementowany - to najbardziej wrażliwy na pozycjonowanie element,
zdecydowanie wymaga wizualnej pętli sprzężenia.

Klawiatura:
  Tab / Return  -> zatwierdź podświetloną podpowiedź; przejdź do
                   następnego pola przez on_dalej, jeśli podany, inaczej
                   domyślnym mechanizmem Tk (<<NextWindow>>)
  Down / Up     -> przesuń podświetlenie na liście, NIE zatwierdza
  Escape        -> schowaj listę, zostaw wpisany tekst bez zmian
  inne znaki    -> przelicz podpowiedzi na nowo
"""
import tkinter as tk
from tkinter import ttk

from zpo_tracker.podpowiedzi import podpowiedz


class EntryZPodpowiedzia(ttk.Frame):
    def __init__(self, parent, pobierz_kandydatow, textvariable=None,
                 on_dalej=None, rozwijaj_na_pusty_fokus=False, **kwargs_entry):
        """
        pobierz_kandydatow: funkcja bezargumentowa zwracająca AKTUALNĄ listę
        kandydatów (wymienne źródło danych - docs/ux-ui.md wymaga, żeby
        dało się później dołożyć dane referencyjne bez przeprojektowania).
        Podmienna w locie przez `ustaw_zrodlo_kandydatow` - pole
        dedukowane niejednoznacznie (dedukcja.StanPola.kandydaci) dostaje
        w ten sposób WŁASNĄ, zawężoną listę zamiast pełnego słownika.

        on_dalej: wywoływane po Tab/Return zamiast domyślnego przejścia
        Tk (patrz `_zatwierdz_i_dalej`) - potrzebne do wspólnej kolejności
        nawigacji z dedukcja.kolejnosc_pol (0.1-alpha.3.1).

        rozwijaj_na_pusty_fokus: pokaż `pobierz_kandydatow()` od razu po
        wejściu fokusem do PUSTEGO pola, bez czekania na pierwszy znak.
        Domyślnie wyłączone - dla pól z pełnym słownikiem (kurier/nadawca/
        adres) wyskakująca lista setek pozycji na każdy fokus byłaby
        regresją UX, nie pomocą. Włączane tylko tam, gdzie źródło jest już
        zawężone (pole pomarańczowe z konkretnymi kandydatami).
        """
        super().__init__(parent)
        self.pobierz_kandydatow = pobierz_kandydatow
        self.on_dalej = on_dalej
        self.rozwijaj_na_pusty_fokus = rozwijaj_na_pusty_fokus
        self.var = textvariable or tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, **kwargs_entry)
        self.entry.pack(fill="both", expand=True)

        self._lista_toplevel = None
        self._lista = None
        self._podswietlony = -1
        self._aktywne_podpowiedzi = []
        self._ukryj_po_id = None

        self.entry.bind("<KeyRelease>", self._na_klawisz_release)
        self.entry.bind("<Tab>", self._zatwierdz_i_dalej)
        self.entry.bind("<Return>", self._zatwierdz_i_dalej)
        self.entry.bind("<Down>", self._przesun(1))
        self.entry.bind("<Up>", self._przesun(-1))
        self.entry.bind("<Escape>", self._schowaj)
        self.entry.bind("<FocusIn>", self._na_focus_in)
        self.entry.bind("<FocusOut>", self._na_focus_out)

    def get(self):
        return self.var.get()

    def set(self, wartosc):
        self.var.set(wartosc)

    def ustaw_zrodlo_kandydatow(self, pobierz_kandydatow):
        """Podmienia źródło kandydatów w locie - patrz docstring `__init__`."""
        self.pobierz_kandydatow = pobierz_kandydatow

    def ustaw_stan_pola(self, stan, takefocus):
        """
        Proxy do wewnętrznego Entry - Frame-owy wrapper nie przepuszcza
        `configure(...)` automatycznie. `stan`: "normal"/"readonly".
        `takefocus`: 0/1 - dopiero RAZEM z readonly wypada z nawigacji Tab
        (zweryfikowane empirycznie: samo readonly nie wystarczy). Wołane
        przez widget_pole.PoleZeWskaznikiem.ustaw_aktywnosc.
        """
        self.entry.configure(state=stan, takefocus=takefocus)

    def _na_klawisz_release(self, event):
        if event.keysym in ("Tab", "Return", "Up", "Down", "Escape"):
            return
        self._przelicz()

    def _przelicz(self):
        tekst = self.var.get()
        self._aktywne_podpowiedzi = podpowiedz(tekst, self.pobierz_kandydatow()) if tekst else []
        self._podswietlony = 0 if self._aktywne_podpowiedzi else -1
        if self._aktywne_podpowiedzi:
            self._pokaz()
        else:
            self._schowaj()

    def _pokaz(self):
        if self._lista_toplevel is None:
            self._lista_toplevel = tk.Toplevel(self)
            self._lista_toplevel.overrideredirect(True)
            self._lista = tk.Listbox(self._lista_toplevel)
            self._lista.pack(fill="both", expand=True)
            self._lista.bind("<Button-1>", self._klik_na_liste)

        self._lista.configure(height=min(6, len(self._aktywne_podpowiedzi)))
        self._lista.delete(0, "end")
        for p in self._aktywne_podpowiedzi:
            self._lista.insert("end", p)
        if self._podswietlony >= 0:
            self._lista.selection_clear(0, "end")
            self._lista.selection_set(self._podswietlony)

        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        self._lista_toplevel.geometry(f"+{x}+{y}")
        self._lista_toplevel.deiconify()

    def _schowaj(self, _event=None):
        if self._lista_toplevel is not None:
            self._lista_toplevel.withdraw()
        self._aktywne_podpowiedzi = []
        self._podswietlony = -1
        return "break" if _event is not None else None

    def _przesun(self, kierunek):
        def handler(_event):
            if not self._aktywne_podpowiedzi:
                return "break"
            self._podswietlony = (self._podswietlony + kierunek) % len(self._aktywne_podpowiedzi)
            self._lista.selection_clear(0, "end")
            self._lista.selection_set(self._podswietlony)
            return "break"
        return handler

    def _zatwierdz_i_dalej(self, _event):
        if self._aktywne_podpowiedzi and self._podswietlony >= 0:
            self.var.set(self._aktywne_podpowiedzi[self._podswietlony])
        self._schowaj()
        if self.on_dalej is not None:
            self.on_dalej()
            return "break"
        return None  # brak on_dalej: Tab/Return mają normalnie przejść do następnego pola

    def _klik_na_liste(self, _event):
        wybor = self._lista.curselection()
        if wybor:
            self.var.set(self._aktywne_podpowiedzi[wybor[0]])
        self._schowaj()

    def _na_focus_in(self, _event=None):
        # wyścig zweryfikowany empirycznie: fokus bywa "z powrotem" w tym
        # samym polu w <150ms (typowe przy Enter=TAB z klawiatury) - bez
        # anulowania stary timer z _na_focus_out gasiłby świeżo pokazaną
        # listę. Niszczenie widgetu z zaplanowanym `after` jest bezpieczne,
        # więc nie trzeba tego odwoływać nigdzie indziej.
        if self._ukryj_po_id is not None:
            self.after_cancel(self._ukryj_po_id)
            self._ukryj_po_id = None
        if not self.rozwijaj_na_pusty_fokus or self.var.get():
            return
        kandydaci = self.pobierz_kandydatow()
        if not kandydaci:
            return
        self._aktywne_podpowiedzi = list(kandydaci)
        self._podswietlony = 0
        self._pokaz()

    def _na_focus_out(self, _event):
        self._ukryj_po_id = self.after(150, self._schowaj)
