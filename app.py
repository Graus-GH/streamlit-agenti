import io
import re
from typing import List, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from fpdf import FPDF

st.set_page_config(page_title="📦✨GRAUS Proposta+", layout="wide")

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

    # Codice numerico: solo cifre, rimuovi eventuali "decimali" '00' finali
    def normalize_code(x: str) -> str:
        s = re.sub("[^0-9]", "", str(x))      # solo cifre
        s = s.lstrip("0") or "0"              # aspetto numerico
        if len(s) > 2 and s.endswith("00"):   # es. '123400' -> '1234'
            s = s[:-2] or "0"
        return s

    df["codice"] = df["codice"].astype(str).apply(normalize_code)

    # Drop righe senza codice o prodotto
    df = df[(df["codice"] != "") & (df["prodotto"] != "")]
    df = df.sort_values(["prodotto", "codice"], kind="stable").reset_index(drop=True)
    return df

def sorted_for_export(df: pd.DataFrame) -> pd.DataFrame:
    # Ordina per Categoria, Tipologia, Provenienza, Prodotto
    return df.sort_values(
        by=["categoria", "tipologia", "provenienza", "prodotto"],
        kind="stable",
        na_position="last"
    ).reset_index(drop=True)

def tokenize_query(q: str) -> List[str]:
    return [t for t in re.split(r"\s+", q.strip()) if t]

def row_matches(row: pd.Series, tokens: List[str], fields: List[str]) -> bool:
    haystack = " ".join(str(row[f]) for f in fields).lower()
    return all(t.lower() in haystack for t in tokens)

def make_excel(df: pd.DataFrame) -> bytes:
    df = sorted_for_export(df)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prodotti selezionati")
    buf.seek(0)
    return buf.read()

# ---------- PDF “stile listino” ----------
class ListinoPDF(FPDF):
    def header(self):
        # Titolo in alto
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "Prodotti selezionati", ln=1)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 8, f"Pag. {self.page_no()}", align="R")

def enc(txt: str) -> str:
    # Gestione accenti su fpdf classico (latin-1)
    return str(txt).encode("latin-1", "replace").decode("latin-1")

def table_header(pdf: ListinoPDF, widths):
    pdf.set_fill_color(235, 235, 235)
    pdf.set_font("Helvetica", "B", 9)
    headers = ["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"]
    for h, w in zip(headers, widths):
        pdf.cell(w, 7, enc(h.upper()), border=1, ln=0, align="L", fill=True)
    pdf.ln(7)

def new_page_with_header(pdf: ListinoPDF, widths):
    pdf.add_page(orientation="L")
    table_header(pdf, widths)

def make_pdf(df: pd.DataFrame) -> bytes:
    df = sorted_for_export(df)

    pdf = ListinoPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)  # gestiamo noi i break
    widths = [32, 138, 38, 38, 38, 27]   # tot ≈ 311mm area utile in L
    row_h = 6

    new_page_with_header(pdf, widths)

    # Gruppi: Categoria -> Tipologia -> Provenienza
    grouped = df.groupby(["categoria", "tipologia", "provenienza"], dropna=False)

    pdf.set_font("Helvetica", "", 9)
    for (cat, tip, prov), g in grouped:
        # Sezione come nei listini: fascia grigia con il “breadcrumb” della sezione
        if pdf.get_y() > 190:  # spazio residuo, circa
            new_page_with_header(pdf, widths)
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font("Helvetica", "B", 10)
        section = " / ".join([x for x in [cat, tip, prov] if str(x)])
        pdf.cell(sum(widths), 7, enc(section), border=1, ln=1, fill=True)
        pdf.set_font("Helvetica", "", 9)

        # Righe prodotti
        for _, r in g.iterrows():
            if pdf.get_y() > 190:
                new_page_with_header(pdf, widths)
                # ripeti anche la banda di sezione quando spezza pagina
                pdf.set_fill_color(220, 220, 220)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(sum(widths), 7, enc(section), border=1, ln=1, fill=True)
                pdf.set_font("Helvetica", "", 9)

            cells = [
                enc(str(r.get("codice", ""))),
                enc(str(r.get("prodotto", ""))[:200]),
                enc(str(r.get("categoria", ""))),
                enc(str(r.get("tipologia", ""))),
                enc(str(r.get("provenienza", ""))),
                ("" if pd.isna(r.get("prezzo")) else f"{r.get('prezzo'):.2f}")
            ]

            # stampa riga
            for c, w in zip(cells, widths):
                # trunc soft per celle troppo lunghe
                txt = c.replace("\n", " ")
                if len(txt) > 90:
                    txt = txt[:87] + "..."
                pdf.cell(w, row_h, txt, border=1)
            pdf.ln(row_h)

    out = pdf.output(dest="S")
    return out if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")

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
if "flash" not in st.session_state:
    st.session_state.flash = None  # notifica one-shot

# =========================
# DATA
# =========================
with st.spinner("Caricamento dati…"):
    df_all = load_data(CSV_URL)
df_all = df_all[DISPLAY_COLUMNS].copy()

st.title("📦✨GRAUS Proposta+")

# Conteggio paniere -> etichetta scheda dinamica
basket_len = len(st.session_state.basket)
tab_search, tab_basket = st.tabs(["Ricerca", f"Prodotti selezionati ({basket_len})"])

# =========================
# TAB: RICERCA
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

    # Toggle: Seleziona/Deseleziona tutti i risultati
    c_toggle, _ = st.columns([3, 7])
    all_on = st.session_state.res_select_all_toggle and not st.session_state.reset_res_selection
    if c_toggle.button("Deseleziona tutti i risultati" if all_on else "Seleziona tutti i risultati"):
        st.session_state.res_select_all_toggle = not all_on
        st.session_state.reset_res_selection = not st.session_state.res_select_all_toggle
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

    # Notifica SOTTO il bottone
    if st.session_state.flash:
        f = st.session_state.flash
        {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}.get(
            f.get("type", "success"), st.success
        )(f.get("msg", ""))
        if not f.get("shown", False):
            st.session_state.flash["shown"] = True
        else:
            st.session_state.flash = None

    if add_btn:
        selected_mask = edited_res["sel"].fillna(False)
        selected_codes = set(edited_res.loc[selected_mask, "codice"].tolist())
        if selected_codes:
            df_to_add = df_res[df_res["codice"].isin(selected_codes)]
            basket = st.session_state.basket
            combined = pd.concat([basket, df_to_add], ignore_index=True)
            combined = combined.drop_duplicates(subset=["codice"]).reset_index(drop=True)
            st.session_state.basket = combined
            st.session_state.res_select_all_toggle = False
            st.session_state.reset_res_selection = True
            st.session_state.flash = {
                "type": "success",
                "msg": f"Aggiunti {len(df_to_add)} articoli al paniere.",
                "shown": False
            }
            st.rerun()
        else:
            st.info("Seleziona almeno un articolo dalla griglia.")

# =========================
# TAB: PANIERE
# =========================
with tab_basket:
    basket = st.session_state.basket.copy()

    # Toggle selezione completo paniere
    c_toggle_b, _ = st.columns([3, 7])
    all_on_b = st.session_state.basket_select_all_toggle and not st.session_state.reset_basket_selection
    if c_toggle_b.button("Deseleziona tutto il paniere" if all_on_b else "Seleziona tutto il paniere"):
        st.session_state.basket_select_all_toggle = not all_on_b
        st.session_state.reset_basket_selection = not st.session_state.basket_select_all_toggle
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
    # Azioni (senza "Svuota paniere")
    c1, c2, c3 = st.columns([1, 1, 1])
    remove_btn = c1.button("🗑️ Rimuovi selezionati", type="primary")

    # Download diretto (ordinati dentro ai generatori)
    xbuf = make_excel(basket)
    c2.download_button(
        "⬇️ Esporta Excel",
        data=xbuf,
        file_name="prodotti_selezionati.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    pbuf = make_pdf(basket)
    c3.download_button(
        "⬇️ Crea PDF",
        data=pbuf,
        file_name="prodotti_selezionati.pdf",
        mime="application/pdf",
    )

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
