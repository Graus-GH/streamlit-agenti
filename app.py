import io
import re
from typing import List, Tuple

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
    r = requests.get(url)
    r.raise_for_status()
    df_raw = pd.read_csv(io.BytesIO(r.content))

    df = pd.DataFrame({name: df_raw.iloc[:, idx] for name, idx in COL_MAP.items()})

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
        s = re.sub("[^0-9]", "", str(x))  # solo cifre
        s = s.lstrip("0") or "0"          # aspetto numerico
        return s

    df["codice"] = df["codice"].astype(str).apply(normalize_code)

    # Drop righe senza codice o prodotto
    df = df[(df["codice"] != "") & (df["prodotto"] != "")]
    df = df.sort_values(["prodotto", "codice"], kind="stable").reset_index(drop=True)
    return df


def tokenize_query(q: str) -> List[str]:
    return [t for t in re.split(r"\s+", q.strip()) if t]


def row_matches(row: pd.Series, tokens: List[str], fields: List[str]) -> bool:
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


def adaptive_price_bounds(df: pd.DataFrame) -> Tuple[float, float]:
    if df["prezzo"].notna().any():
        mn = float(np.nanmin(df["prezzo"]))
        mx = float(np.nanmax(df["prezzo"]))
        if mn == mx:
            mx = mn + 0.01
        return max(0.0, round(mn, 2)), max(0.01, round(mx, 2))
    return 0.0, 0.01


# =========================
# THEME TWEAKS (pulsanti #005caa)
# =========================
st.markdown(
    """
<style>
.stButton > button[kind="primary"] {
  background-color: #005caa;
  border-color: #005caa;
  color: #fff;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# STATE
# =========================
if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
if "res_select_all_toggle" not in st.session_state:
    st.session_state.res_select_all_toggle = False
if "basket_select_all_toggle" not in st.session_state:
    st.session_state.basket_select_all_toggle = False
if "reset_res_selection" not in st.session_state:
    st.session_state.reset_res_selection = False
if "reset_basket_selection" not in st.session_state:
    st.session_state.reset_basket_selection = False

# =========================
# DATA
# =========================
with st.spinner("Caricamento dati…"):
    df_all = load_data(CSV_URL)

df_all = df_all[DISPLAY_COLUMNS].copy()

st.title("🔎 Ricerca articoli & 🧺 Prodotti selezionati")

tab_search, tab_basket = st.tabs(["Ricerca", "Prodotti selezionati"]) 

# =========================
# TAB: RICERCA – form, filtro prezzo dinamico, selezione massiva
# =========================
with tab_search:
    with st.form("search_form", clear_on_submit=False):
        q = st.text_input(
            "Cerca (multi-parola) su: codice, prodotto, categoria, tipologia, provenienza",
            placeholder="Es. 'riesling alto adige 0,75'",
        )
        tokens = tokenize_query(q) if q else []
        mask_text = (
            df_all.apply(lambda r: row_matches(r, tokens, SEARCH_FIELDS), axis=1)
            if tokens
            else pd.Series(True, index=df_all.index)
        )
        df_after_text = df_all.loc[mask_text]

        dyn_min, dyn_max = adaptive_price_bounds(df_after_text)
        c1, c2, c3 = st.columns([1, 1, 2])
        min_price_input = c1.number_input(
            "Prezzo min", min_value=0.0, value=float(dyn_min), step=0.1, format="%.2f"
        )
        max_price_input = c2.number_input(
            "Prezzo max", min_value=0.01, value=float(dyn_max), step=0.1, format="%.2f"
        )
        max_for_slider = max(min_price_input, max_price_input)
        price_range = c3.slider(
            "Slider prezzo (sincronizzato)",
            min_value=0.0,
            max_value=max(0.01, round(max_for_slider, 2)),
            value=(float(min_price_input), float(max_price_input)),
            step=0.1,
        )
        min_price = min(price_range[0], price_range[1])
        max_price = max(price_range[0], price_range[1])

        submitted = st.form_submit_button("Cerca")

    mask_price = df_after_text["prezzo"].fillna(0.0).between(min_price, max_price)
    df_res = df_after_text.loc[mask_price].reset_index(drop=True)

    st.caption(f"Risultati: {len(df_res)}")

    # Pulsanti selezione globale
    csel_all, cdesel_all, _ = st.columns([1.4, 1.8, 6])
    if csel_all.button("Seleziona tutti i risultati"):
        st.session_state.res_select_all_toggle = True
        st.session_state.reset_res_selection = False
        st.rerun()
    if cdesel_all.button("Deseleziona tutti i risultati"):
        st.session_state.res_select_all_toggle = False
        st.session_state.reset_res_selection = True
        st.rerun()

    # Griglia con checkbox
    default_sel = st.session_state.res_select_all_toggle and not st.session_state.reset_res_selection
    df_res_display = df_res.copy()
    df_res_display.insert(0, "sel", default_sel)

    edited_res = st.data_editor(
        df_res_display,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "sel": st.column_config.CheckboxColumn(label="", width=38, help="Seleziona riga"),
            "codice": st.column_config.TextColumn(label="codice", width=120),
            "prodotto": st.column_config.TextColumn(label="prodotto", width=420),
            "categoria": st.column_config.TextColumn(label="categoria", width=160),
            "tipologia": st.column_config.TextColumn(label="tipologia", width=160),
            "provenienza": st.column_config.TextColumn(label="provenienza", width=160),
            "prezzo": st.column_config.NumberColumn(label="prezzo", format="€ %.2f", width=120),
        },
        disabled=["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"],
        key="res_editor",
    )

    st.divider()
    add_btn = st.button("➕ Aggiungi selezionati al paniere", type="primary")

    if add_btn:
        selected_mask = edited_res["sel"].fillna(False)
        selected_codes = set(edited_res.loc[selected_mask, "codice"].tolist())
        if selected_codes:
            df_to_add = df_res[df_res["codice"].isin(selected_codes)]
            basket = st.session_state.basket
            combined = pd.concat([basket, df_to_add], ignore_index=True)
            combined = combined.drop_duplicates(subset=["codice"]).reset_index(drop=True)
            st.session_state.basket = combined
            # reset selezioni dopo aggiunta
            st.session_state.res_select_all_toggle = False
            st.session_state.reset_res_selection = True
            st.success(f"Aggiunti {len(df_to_add)} articoli al paniere.")
            st.rerun()
        else:
            st.info("Seleziona almeno un articolo dalla griglia.")

# =========================
# TAB: PANIERE – selezione massiva, export
# =========================
with tab_basket:
    st.subheader("🧺 Prodotti selezionati")
    basket = st.session_state.basket.copy()
    st.caption(f"Nel paniere: {len(basket)} articoli")

    if len(basket) > 0:
        csel_all_b, cdesel_all_b, _ = st.columns([1.6, 2.0, 6])
        if csel_all_b.button("Seleziona tutto il paniere"):
            st.session_state.basket_select_all_toggle = True
            st.session_state.reset_basket_selection = False
            st.rerun()
        if cdesel_all_b.button("Deseleziona tutto il paniere"):
            st.session_state.basket_select_all_toggle = False
            st.session_state.reset_basket_selection = True
            st.rerun()

        default_sel_b = st.session_state.basket_select_all_toggle and not st.session_state.reset_basket_selection
        basket_display = basket.copy()
        basket_display.insert(0, "rm", default_sel_b)

        edited_basket = st.data_editor(
            basket_display,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "rm": st.column_config.CheckboxColumn(label="", width=38, help="Seleziona per rimuovere"),
                "codice": st.column_config.TextColumn(width=120),
                "prodotto": st.column_config.TextColumn(width=420),
                "categoria": st.column_config.TextColumn(width=160),
                "tipologia": st.column_config.TextColumn(width=160),
                "provenienza": st.column_config.TextColumn(width=160),
                "prezzo": st.column_config.NumberColumn(format="€ %.2f", width=120),
            },
            disabled=["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"],
            key="basket_editor",
        )

        st.divider()
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        remove_btn = c1.button("🗑️ Rimuovi selezionati", type="primary")
        clear_btn = c2.button("♻️ Svuota paniere")
        xlsx_btn = c3.button("⬇️ Esporta Excel")
        pdf_btn = c4.button("⬇️ Crea PDF")

        if remove_btn:
            to_remove = set(edited_basket.loc[edited_basket["rm"].fillna(False), "codice"].tolist())
            if to_remove:
                st.session_state.basket = basket[~basket["codice"].isin(to_remove)].reset_index(drop=True)
                st.session_state.basket_select_all_toggle = False
                st.session_state.reset_basket_selection = True
                st.success("Rimossi articoli selezionati.")
                st.rerun()
            else:
                st.info("Seleziona almeno un articolo da rimuovere.")

        if clear_btn:
            with st.expander("Conferma svuotamento paniere", expanded=True):
                confirm = st.checkbox("Confermo di voler svuotare completamente il paniere.")
                do_clear = st.button("Svuota ora", type="primary", disabled=not confirm)
                if do_clear:
                    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
                    st.session_state.basket_select_all_toggle = False
                    st.session_state.reset_basket_selection = True
                    st.success("Paniere svuotato.")
                    st.rerun()

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
