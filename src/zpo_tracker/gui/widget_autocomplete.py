"""
Pole tekstowe z podpowiedziami: dropdown pod polem + nawigacja klawiaturą.
Logika dopasowania jest w podpowiedzi.py (testowana, bez GUI) - ten widget
tylko wyświetla wyniki i obsługuje klawiaturę.

NIEZWERYFIKOWANE WIZUALNIE. Awaria środowiska X11 w tej sesji (patrz plan
MVP, sekcja "Aktualizacja w trakcie realizacji") uniemożliwiła nawet
stworzenie zwykłego tk.Entry, więc ten plik nie został odpalony ani razu -
tylko sprawdzony pod względem składni/importu. Celowo NIE wpięty do
zakladka_wprowadzanie.py, żeby nie ryzykować już działającego formularza
niesprawdzonym kodem. Do zweryfikowania i wpięcia jako pierwszy krok, gdy
środowisko graficzne wróci do działania.

Ghost text (nakładka z podpowiedzią przed kursorem) świadomie NIE
zaimplementowany - to najbardziej wrażliwy na pozycjonowanie element,
zdecydowanie wymaga wizualnej pętli sprzężenia, której nie miałem.

Klawiatura (docelowa, patrz plan MVP):
  Tab / Return  -> zatwierdź podświetloną podpowiedź, przejdź do następnego pola
  Down / Up     -> przesuń podświetlenie na liście, NIE zatwierdza
  Escape        -> schowaj listę, zostaw wpisany tekst bez zmian
  inne znaki    -> przelicz podpowiedzi na nowo
"""
import tkinter as tk
from tkinter import ttk

from zpo_tracker.podpowiedzi import podpowiedz


class EntryZPodpowiedzia(ttk.Frame):
    def __init__(self, parent, pobierz_kandydatow, textvariable=None, **kwargs_entry):
        """
        pobierz_kandydatow: funkcja bezargumentowa zwracająca AKTUALNĄ listę
        kandydatów (wymienne źródło danych - docs/ux-ui.md wymaga, żeby
        dało się później dołożyć dane referencyjne bez przeprojektowania).
        """
        super().__init__(parent)
        self.pobierz_kandydatow = pobierz_kandydatow
        self.var = textvariable or tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, **kwargs_entry)
        self.entry.pack(fill="both", expand=True)

        self._lista_toplevel = None
        self._lista = None
        self._podswietlony = -1
        self._aktywne_podpowiedzi = []

        self.entry.bind("<KeyRelease>", self._na_klawisz_release)
        self.entry.bind("<Tab>", self._zatwierdz_i_dalej)
        self.entry.bind("<Return>", self._zatwierdz_i_dalej)
        self.entry.bind("<Down>", self._przesun(1))
        self.entry.bind("<Up>", self._przesun(-1))
        self.entry.bind("<Escape>", self._schowaj)
        self.entry.bind("<FocusOut>", self._na_focus_out)

    def get(self):
        return self.var.get()

    def set(self, wartosc):
        self.var.set(wartosc)

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
        return None  # brak "break": Tab/Return mają normalnie przejść do następnego pola

    def _klik_na_liste(self, _event):
        wybor = self._lista.curselection()
        if wybor:
            self.var.set(self._aktywne_podpowiedzi[wybor[0]])
        self._schowaj()

    def _na_focus_out(self, _event):
        self.after(150, self._schowaj)
