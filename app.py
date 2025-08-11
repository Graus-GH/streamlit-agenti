import io
import math
import re
from typing import List

import numpy as np
import pandas as pd
import requests
import streamlit as st
from fpdf import FPDF

st.set_page_config(page_title="Ricerca articoli • Prodotti selezionati", layout="wide")

# =========================
# CONFIG – ORIGINE DATI
# =========================
SHEET_ID = "10BFJQTV1yL69cotE779zuR8vtG5NqKWOVH0Uv1AnGaw"
GID = "707323537"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Mappatura colonne: posizioni nello sheet (0-based)
COL_MAP = {
    "codice": 0,       # A
    "prodotto": 2,     # C
    "categoria": 5,    # F
    "tipologia": 6,    # G
    "provenienza": 7,  # H
    "prezzo": 8,       # I
}

DISPLAY_COLUMNS = ["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"]

# =========================
# UTILS
# =========================
@st.cache_data(ttl=600)
def load_data(url: str) -> pd.DataFrame:
    """Carica CSV pubblico da Google Sheets e restituisce DataFrame normalizzato."""
    r = requests.get(url)
    r.raise_for_status()
    df_raw = pd.read_csv(io.BytesIO(r.content))

    # Normalizza colonne secondo COL_MAP (in base a indice, a prescindere dai nomi nel foglio)
    # Se il foglio ha meno colonne del previsto, solleva errore chiaro.
    max_idx_needed = max(COL_MAP.values())
    if df_raw.shape[1] <= max_idx_needed:
        raise ValueError(
            f"Il foglio ha solo {df_raw.shape[1]} colonne, ma ne servono almeno {max_idx_needed+1}."
        )

    df = pd.DataFrame()
    for name, idx in COL_MAP.items():
        df[name] = df_raw.iloc[:, idx]

    # Pulizia prezzo: accetta formati con virgola o punto, rimuove simboli
    def to_float(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip()
        s = s.replace("€", "").replace(" ", "")
        # Se ha sia punto che virgola, prova a gestire 1.234,56
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return np.nan

    df["prezzo"] = df["prezzo"].apply(to_float)

    # Stringhe
    for c in ["codice", "prodotto", "categoria", "tipologia", "provenienza"]:
        df[c] = df[c].astype(str).fillna("").str.strip()

    # Drop righe senza codice o prodotto
    df = df[(df["codice"] != "") & (df["prodotto"] != "")].copy()

    return df


def tokenize_query(q: str) -> List[str]:
    tokens = re.split(r"\s+", q.strip())
    return [t for t in tokens if t]


def row_matches(row: pd.Series, tokens: List[str], fields: List[str]) -> bool:
    """True se TUTTI i token sono presenti (AND) in almeno uno dei campi indicati (ricerca case-insensitive)."""
    haystack = " ".join(str(row[f]) for f in fields).lower()
    return all(t.lower() in haystack for t in tokens)


def make_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prodotti selezionati")
    buf.seek(0)
    return buf.read()


def make_pdf(df: pd.DataFrame) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Prodotti selezionati", ln=1)

    # Header
    pdf.set_font("Helvetica", "B", 10)
    headers = ["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"]
    col_widths = [35, 120, 40, 40, 40, 25]

    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h.upper(), border=1)
    pdf.ln(8)

    pdf.set_font("Helvetica", size=9)
    # Rows
    for _, r in df.iterrows():
        cells = [
            str(r.get("codice", "")),
            str(r.get("prodotto", ""))[:200],
            str(r.get("categoria", "")),
            str(r.get("tipologia", "")),
            str(r.get("provenienza", "")),
            f"{r.get('prezzo', np.nan):.2f}" if not pd.isna(r.get("prezzo")) else "",
        ]
        for c, w in zip(cells, col_widths):
            # Multi-cell semplificata: taglio stringhe lunghe per evitare overflow
            txt = c.replace("\n", " ")
            if len(txt) > 80:
                txt = txt[:77] + "..."
            pdf.cell(w, 6, txt, border=1)
        pdf.ln(6)

    return bytes(pdf.output(dest="S").encode("latin1"))


# =========================
# STATE
# =========================
if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
if "checked_rows" not in st.session_state:
    st.session_state.checked_rows = set()  # codici selezionati in risultati
if "checked_basket" not in st.session_state:
    st.session_state.checked_basket = set()  # codici selezionati in paniere

# =========================
# DATA
# =========================
with st.spinner("Caricamento dati..."):
    df_all = load_data(CSV_URL)

# Per sicurezza, tieni solo le colonne previste (nell'ordine richiesto)
df_all = df_all[DISPLAY_COLUMNS].copy()

st.title("🔎 Ricerca articoli & 🧺 Prodotti selezionati")

search_tab, basket_tab = st.tabs(["Ricerca", "Prodotti selezionati"])

# =========================
# TAB: RICERCA
# =========================
with search_tab:
    with st.container():
        q = st.text_input(
            "Cerca (multi-parola) su: codice, prodotto, categoria, tipologia, provenienza",
            placeholder="Es. 'riesling alto adige 0,75'",
        )

        # Range prezzo: calcolato dinamicamente su df_all
        min_price = float(np.nanmin(df_all["prezzo"])) if df_all["prezzo"].notna().any() else 0.0
        max_price = float(np.nanmax(df_all["prezzo"])) if df_all["prezzo"].notna().any() else 0.0
        price_range = st.slider(
            "Filtra per prezzo",
            min_value=0.0,
            max_value=max(0.0, round(max_price + 0.5, 2)),
            value=(0.0, max(0.0, round(max_price + 0.0, 2))),
            step=0.1,
        )

        # Applica filtri
        filt = (df_all["prezzo"].fillna(0.0).between(price_range[0], price_range[1]))
        tokens = tokenize_query(q) if q else []
        if tokens:
            mask = df_all.apply(
                lambda r: row_matches(r, tokens, ["codice", "prodotto", "categoria", "tipologia", "provenienza"]),
                axis=1,
            )
            filt &= mask
        df_res = df_all.loc[filt].reset_index(drop=True)

        st.caption(f"Risultati: {len(df_res)}")

        # Tabella con checkbox per selezione
        st.write("**Seleziona articoli da aggiungere al paniere:**")
        # Costruzione griglia con checkbox per ogni riga
        results_checks = []
        header_cols = st.columns([0.8, 1.5, 3, 1.6, 1.6, 1.6, 1])
        header_cols[0].markdown("**sel.**")
        for i, colname in enumerate(["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"]):
            header_cols[i + 1].markdown(f"**{colname}**")

        for i, row in df_res.iterrows():
            cols = st.columns([0.8, 1.5, 3, 1.6, 1.6, 1.6, 1])
            code = row["codice"]
            checked = cols[0].checkbox("", key=f"res_{i}_{code}", value=(code in st.session_state.checked_rows))
            if checked:
                st.session_state.checked_rows.add(code)
            else:
                st.session_state.checked_rows.discard(code)

            cols[1].write(row["codice"])
            cols[2].write(row["prodotto"])
            cols[3].write(row["categoria"])
            cols[4].write(row["tipologia"])
            cols[5].write(row["provenienza"])
            cols[6].write("" if pd.isna(row["prezzo"]) else f"€ {row['prezzo']:.2f}")

        st.divider()
        left, right = st.columns([1, 3])
        with left:
            add_btn = st.button("➕ Aggiungi selezionati al paniere", type="primary")
        with right:
            clear_sel = st.button("Deseleziona tutti i risultati")

        if clear_sel:
            st.session_state.checked_rows.clear()

        if add_btn:
            if st.session_state.checked_rows:
                df_to_add = df_res[df_res["codice"].isin(st.session_state.checked_rows)]
                # Unisci al paniere evitando duplicati sul codice
                basket = st.session_state.basket
                combined = pd.concat([basket, df_to_add], ignore_index=True)
                combined = combined.drop_duplicates(subset=["codice"])  # no doppioni
                st.session_state.basket = combined.reset_index(drop=True)
                st.success(f"Aggiunti {len(df_to_add)} articoli al paniere.")
            else:
                st.info("Seleziona almeno un articolo dai risultati.")

# =========================
# TAB: PANIERE
# =========================
with basket_tab:
    st.subheader("🧺 Prodotti selezionati")

    basket = st.session_state.basket.copy()
    st.caption(f"Nel paniere: {len(basket)} articoli")

    # Tabella con checkbox per rimozione
    if len(basket) > 0:
        header_cols = st.columns([0.8, 1.5, 3, 1.6, 1.6, 1.6, 1])
        header_cols[0].markdown("**rm.**")
        for i, colname in enumerate(["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"]):
            header_cols[i + 1].markdown(f"**{colname}**")

        for i, row in basket.iterrows():
            cols = st.columns([0.8, 1.5, 3, 1.6, 1.6, 1.6, 1])
            code = row["codice"]
            checked = cols[0].checkbox("", key=f"basket_{i}_{code}", value=(code in st.session_state.checked_basket))
            if checked:
                st.session_state.checked_basket.add(code)
            else:
                st.session_state.checked_basket.discard(code)

            cols[1].write(row["codice"])
            cols[2].write(row["prodotto"])
            cols[3].write(row["categoria"])
            cols[4].write(row["tipologia"])
            cols[5].write(row["provenienza"])
            cols[6].write("" if pd.isna(row["prezzo"]) else f"€ {row['prezzo']:.2f}")

        st.divider()
        c1, c2, c3, c4 = st.columns([1,1,1,3])
        remove_btn = c1.button("🗑️ Rimuovi selezionati")
        clear_btn = c2.button("♻️ Svuota paniere")
        xlsx_btn = c3.button("⬇️ Esporta Excel")
        pdf_btn = c4.button("⬇️ Crea PDF")

        if remove_btn:
            if st.session_state.checked_basket:
                st.session_state.basket = basket[~basket["codice"].isin(st.session_state.checked_basket)].reset_index(drop=True)
                st.session_state.checked_basket.clear()
                st.success("Rimossi articoli selezionati.")
            else:
                st.info("Seleziona almeno un articolo da rimuovere.")

        if clear_btn:
            if st.confirm("Confermi di voler svuotare completamente il paniere? Questa operazione non è reversibile."):
                st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
                st.session_state.checked_basket.clear()
                st.success("Paniere svuotato.")

        if xlsx_btn:
            xbuf = make_excel(basket)
            st.download_button("Scarica Excel", data=xbuf, file_name="prodotti_selezionati.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if pdf_btn:
            pbuf = make_pdf(basket)
            st.download_button("Scarica PDF", data=pbuf, file_name="prodotti_selezionati.pdf", mime="application/pdf")

    else:
        st.info("Il paniere è vuoto. Aggiungi articoli dalla scheda 'Ricerca'.")
