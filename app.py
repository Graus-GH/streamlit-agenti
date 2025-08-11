import io
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
SEARCH_FIELDS = ["codice", "prodotto", "categoria", "tipologia", "provenienza"]

# =========================
# UTILS
# =========================
@st.cache_data(ttl=600)
def load_data(url: str) -> pd.DataFrame:
    """Carica CSV pubblico da Google Sheets e restituisce DataFrame normalizzato."""
    r = requests.get(url)
    r.raise_for_status()
    df_raw = pd.read_csv(io.BytesIO(r.content))

    max_idx_needed = max(COL_MAP.values())
    if df_raw.shape[1] <= max_idx_needed:
        raise ValueError(
            f"Il foglio ha solo {df_raw.shape[1]} colonne, ma ne servono almeno {max_idx_needed+1}."
        )

    df = pd.DataFrame()
    for name, idx in COL_MAP.items():
        df[name] = df_raw.iloc[:, idx]

    # Stringhe
    for c in ["prodotto", "categoria", "tipologia", "provenienza"]:
        df[c] = df[c].astype(str).fillna("").str.strip()

    # Prezzo -> float (gestisce 1.234,56 e 1234,56)
    def to_float(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip().replace("€", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return np.nan

    df["prezzo"] = df["prezzo"].apply(to_float)

    # Codice numerico senza separatori/decimali
    def normalize_code(x: str) -> str:
        s = re.sub(r"\D", "", str(x))  # solo cifre
        s = s.lstrip("0") or "0"       # aspetto numerico (niente zeri iniziali)
        return s

    df["codice"] = df.iloc[:, COL_MAP["codice"]].astype(str).apply(normalize_code)

    # Drop righe senza codice o prodotto
    df = df[(df["codice"] != "") & (df["prodotto"] != "")]
    df = df.sort_values(["prodotto", "codice"], kind="stable").reset_index(drop=True)
    return df

def tokenize_query(q: str) -> List[str]:
    return [t for t in re.split(r"\s+", q.strip()) if t]

def row_matches(row: pd.Series, tokens: List[str], fields: List[str]) -> bool:
    """True se TUTTI i token (AND) compaiono (case-insensitive) in almeno uno dei campi."""
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
    headers = DISPLAY_COLUMNS
    col_widths = [35, 120, 40, 40, 40, 25]
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, h.upper(), border=1)
    pdf.ln(8)

    pdf.set_font("Helvetica", size=9)
    for _, r in df.iterrows():
        cells = [
            str(r.get("codice", "")),
            str(r.get("prodotto", ""))[:200],
            str(r.get("categoria", "")),
            str(r.get("tipologia", "")),
            str(r.get("provenienza", "")),
            ("" if pd.isna(r.get("prezzo")) else f"{r.get('prezzo'):.2f}"),
        ]
        for c, w in zip(cells, col_widths):
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

# =========================
# DATA
# =========================
try:
    with st.spinner("Caricamento dati…"):
        df_all = load_data(CSV_URL)
except Exception as e:
    st.error(
        "Errore nel caricamento dati. Assicurati che il Google Sheet sia pubblico in sola lettura (File → Condividi → Chiunque con il link).\n"
        f"Dettagli: {e}"
    )
    st.stop()

df_all = df_all[DISPLAY_COLUMNS].copy()

st.title("🔎 Ricerca articoli & 🧺 Prodotti selezionati")
search_tab, basket_tab = st.tabs(["Ricerca", "Prodotti selezionati"])

# =========================
# TAB: RICERCA – griglia migliorata
# =========================
with search_tab:
    q = st.text_input(
        "Cerca (multi-parola) su: codice, prodotto, categoria, tipologia, provenienza",
        placeholder="Es. 'riesling alto adige 0,75'",
    )

    max_price = float(np.nanmax(df_all["prezzo"])) if df_all["prezzo"].notna().any() else 0.0
    price_range = st.slider(
        "Filtra per prezzo",
        min_value=0.0,
        max_value=max(0.0, round(max_price + 0.5, 2)),
        value=(0.0, max(0.0, round(max_price, 2))),
        step=0.1,
    )

    filt = df_all["prezzo"].fillna(0.0).between(price_range[0], price_range[1])
    tokens = tokenize_query(q) if q else []
    if tokens:
        mask = df_all.apply(lambda r: row_matches(r, tokens, SEARCH_FIELDS), axis=1)
        filt &= mask

    df_res = df_all.loc[filt].reset_index(drop=True)
    st.caption(f"Risultati: {len(df_res)}")

    # Colonna di selezione per la griglia
    df_res_display = df_res.copy()
    df_res_display.insert(0, "sel", False)

    edited_res = st.data_editor(
        df_res_display,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "sel": st.column_config.CheckboxColumn(label="Seleziona", help="Seleziona riga"),
            "codice": st.column_config.TextColumn(width="small"),
            "prodotto": st.column_config.TextColumn(width="medium"),
            "categoria": st.column_config.TextColumn(width="small"),
            "tipologia": st.column_config.TextColumn(width="small"),
            "provenienza": st.column_config.TextColumn(width="small"),
            "prezzo": st.column_config.NumberColumn(format="€ %.2f", width="small"),
        },
        disabled=["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"],
    )

    st.divider()
    c_add, c_clear = st.columns([1, 1])
    add_btn = c_add.button("➕ Aggiungi selezionati al paniere", type="primary")
    clear_sel = c_clear.button("Deseleziona tutti i risultati")

    if clear_sel:
        edited_res["sel"] = False

    if add_btn:
        selected_codes = set(df_res.loc[edited_res["sel"].fillna(False), "codice"].tolist())
        if selected_codes:
            df_to_add = df_res[df_res["codice"].isin(selected_codes)]
            basket = st.session_state.basket
            combined = pd.concat([basket, df_to_add], ignore_index=True)
            combined = combined.drop_duplicates(subset=["codice"]).reset_index(drop=True)
            st.session_state.basket = combined
            st.success(f"Aggiunti {len(df_to_add)} articoli al paniere.")
        else:
            st.info("Seleziona almeno un articolo dalla griglia.")

# =========================
# TAB: PANIERE – griglia migliorata
# =========================
with basket_tab:
    st.subheader("🧺 Prodotti selezionati")
    basket = st.session_state.basket.copy()
    st.caption(f"Nel paniere: {len(basket)} articoli")

    if len(basket) > 0:
        basket_display = basket.copy()
        basket_display.insert(0, "rm", False)

        edited_basket = st.data_editor(
            basket_display,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "rm": st.column_config.CheckboxColumn(label="Rimuovi", help="Seleziona per rimuovere"),
                "codice": st.column_config.TextColumn(width="small"),
                "prodotto": st.column_config.TextColumn(width="medium"),
                "categoria": st.column_config.TextColumn(width="small"),
                "tipologia": st.column_config.TextColumn(width="small"),
                "provenienza": st.column_config.TextColumn(width="small"),
                "prezzo": st.column_config.NumberColumn(format="€ %.2f", width="small"),
            },
            disabled=["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"],
        )

        st.divider()
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        remove_btn = c1.button("🗑️ Rimuovi selezionati", type="primary")
        clear_btn = c2.button("♻️ Svuota paniere")
        xlsx_btn = c3.button("⬇️ Esporta Excel")
        pdf_btn = c4.button("⬇️ Crea PDF")

        if remove_btn:
            to_remove = set(basket.loc[edited_basket["rm"].fillna(False), "codice"].tolist())
            if to_remove:
                st.session_state.basket = basket[~basket["codice"].isin(to_remove)].reset_index(drop=True)
                st.success("Rimossi articoli selezionati.")
            else:
                st.info("Seleziona almeno un articolo da rimuovere.")

        if clear_btn:
            with st.expander("Conferma svuotamento paniere", expanded=True):
                confirm = st.checkbox("Confermo di voler svuotare completamente il paniere.")
                do_clear = st.button("Svuota ora", type="primary", disabled=not confirm)
                if do_clear:
                    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
                    st.success("Paniere svuotato.")

        if xlsx_btn:
            xbuf = make_excel(basket)
            st.download_button(
                "Scarica Excel",
                data=xbuf,
                file_name="prodotti_selezionati.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if pdf_btn:
            pbuf = make_pdf(basket)
            st.download_button(
                "Scarica PDF",
                data=pbuf,
                file_name="prodotti_selezionati.pdf",
                mime="application/pdf",
            )

    else:
        st.info("Il paniere è vuoto. Aggiungi articoli dalla scheda 'Ricerca'.")
