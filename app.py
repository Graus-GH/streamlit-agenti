import io
import re
from typing import List, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from fpdf import FPDF

st.set_page_config(page_title="✨GRAUS Proposta Clienti", layout="wide")

# =========================
# CSS – checkbox arancione quando attivo + primary button
# =========================
st.markdown("""
<style>
/* Checkbox a tutta larghezza */
div[data-testid="stForm"] div[data-testid="stCheckbox"] > label {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  box-sizing: border-box;
}
/* Sfondo arancione solo se spuntato */
div[data-testid="stForm"] div[data-testid="stCheckbox"] > label:has(input:checked) {
  background: #ffedd5;
  color: #7c2d12;
  border-color: #fdba74;
}
/* Checkbox un filo più grande */
div[data-testid="stForm"] div[data-testid="stCheckbox"] input[type="checkbox"] {
  transform: scale(1.15);
}
/* Primary button brand */
.stButton > button[kind="primary"] {
  background-color: #005caa;
  border-color: #005caa;
  color: #fff;
}
</style>
""", unsafe_allow_html=True)

# =========================
# CONFIG – ORIGINE DATI
# =========================
SHEET_ID = "10BFJQTV1yL69cotE779zuR8vtG5NqKWOVH0Uv1AnGaw"
GID = "707323537"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Fine Wines (inclusi solo se checkbox attivo)
FW_SHEET_ID = "1D4-zgwpAGiWDCpPwDVipAD7Nlpi4aesFwRRpud2W-rk"
FW_GID = "1549810072"
FW_CSV_URL = f"https://docs.google.com/spreadsheets/d/{FW_SHEET_ID}/export?format=csv&gid={FW_GID}"

COL_MAP = {
    "codice": 0,
    "prodotto": 2,
    "categoria": 5,
    "tipologia": 6,
    "provenienza": 7,
    "prezzo": 8,
}
DISPLAY_COLUMNS = ["codice", "prodotto", "prezzo", "categoria", "tipologia", "provenienza"]
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

    # Codice numerico senza “00” finali
    def normalize_code(x: str) -> str:
        s = re.sub("[^0-9]", "", str(x))
        s = s.lstrip("0") or "0"
        if len(s) > 2 and s.endswith("00"):
            s = s[:-2] or "0"
        return s
    df["codice"] = df["codice"].astype(str).apply(normalize_code)

    df = df[(df["codice"] != "") & (df["prodotto"] != "")]
    df = df.sort_values(["prodotto", "codice"], kind="stable").reset_index(drop=True)
    return df


def tokenize_query(q: str) -> List[str]:
    return [t for t in re.split(r"\s+", q.strip()) if t]


def row_matches(row: pd.Series, tokens: List[str], fields: List[str]) -> bool:
    haystack = " ".join(str(row[f]) for f in fields).lower()
    return all(t.lower() in haystack for t in tokens)


def adaptive_price_bounds(df: pd.DataFrame) -> Tuple[float, float]:
    if df["prezzo"].notna().any():
        mn = float(np.nanmin(df["prezzo"]))
        mx = float(np.nanmax(df["prezzo"]))
        if mn == mx:
            mx = mn + 0.01
        return max(0.0, round(mn, 2)), max(0.01, round(mx, 2))
    return 0.0, 0.01


def with_fw_prefix(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "is_fw" in d.columns:
        d["prodotto"] = np.where(d["is_fw"], "⏳ " + d["prodotto"].astype(str), d["prodotto"])
    return d


# =========================
# EXPORT (Excel/PDF)
# =========================
def make_excel(df: pd.DataFrame) -> bytes:
    import openpyxl
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prodotti selezionati"

    # Intestazioni
    for col_idx, col_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name.upper())
        cell.font = Font(name="Corbel", size=12, bold=True)
        cell.alignment = Alignment(horizontal="right" if col_name.lower()=="prezzo" else "left")

    # Dati
    for r_idx, row in enumerate(df.itertuples(index=False), start=2):
        for c_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.font = Font(name="Corbel", size=12)
            cell.alignment = Alignment(horizontal="right" if df.columns[c_idx-1].lower()=="prezzo" else "left")

    # Larghezze
    for col_idx, col_cells in enumerate(ws.columns, start=1):
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col_cells)
        ws.column_dimensions[get_column_letter(col_idx)].width = max_len + 2

    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def make_pdf(df: pd.DataFrame) -> bytes:
    def pdf_safe(s: str) -> str:
        if s is None:
            return ""
        s = str(s).replace("⏳", "[FW]")
        return s.encode("latin-1", "ignore").decode("latin-1")

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, pdf_safe("Prodotti selezionati"), ln=1)

    pdf.set_font("Helvetica", "B", 10)
    headers = DISPLAY_COLUMNS
    col_widths = [35, 120, 30, 40, 40, 40]
    for h, w in zip(headers, col_widths):
        pdf.cell(w, 8, pdf_safe(h.upper()), border=1)
    pdf.ln(8)

    pdf.set_font("Helvetica", size=9)
    for _, r in df.iterrows():
        cells = [
            str(r.get("codice", "")),
            str(r.get("prodotto", ""))[:200],
            ("" if pd.isna(r.get("prezzo")) else f"{r.get('prezzo'):.2f}"),
            str(r.get("categoria", "")),
            str(r.get("tipologia", "")),
            str(r.get("provenienza", "")),
        ]
        for c, w in zip(cells, col_widths):
            txt = pdf_safe(c.replace("\n", " "))
            if len(txt) > 80:
                txt = txt[:77] + "..."
            pdf.cell(w, 6, txt, border=1)
        pdf.ln(6)

    out = pdf.output(dest="S")
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1", "ignore")


# =========================
# STATE
# =========================
if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS + ["is_fw"])
if "res_select_all_toggle" not in st.session_state:
    st.session_state.res_select_all_toggle = False
if "basket_select_all_toggle" not in st.session_state:
    st.session_state.basket_select_all_toggle = False
if "reset_res_selection" not in st.session_state:
    st.session_state.reset_res_selection = False
if "reset_basket_selection" not in st.session_state:
    st.session_state.reset_basket_selection = False
if "flash" not in st.session_state:
    st.session_state.flash = None
if "include_fw" not in st.session_state:
    st.session_state.include_fw = False

# =========================
# DATA
# =========================
with st.spinner("Caricamento dati…"):
    df_base = load_data(CSV_URL)
df_base["is_fw"] = False

st.title("✨GRAUS Proposta Clienti")

basket_len = len(st.session_state.basket)
tab_search, tab_basket = st.tabs(["Ricerca", f"Prodotti selezionati ({basket_len})"])

# =========================
# TAB: RICERCA
# =========================
with tab_search:
    with st.form("search_form", clear_on_submit=False):
        # Layout responsive: ricerca a sinistra, filtri prezzo a destra
        col_search, col_price = st.columns([2, 1])

        # --- Colonna sinistra: Ricerca + FW ---
        with col_search:
            q = st.text_input(
                "Cerca (multi-parola) su: codice, prodotto, categoria, tipologia, provenienza",
                placeholder="Es. 'riesling alto adige 0,75'",
            )
            st.checkbox(
                "Includi FINE WINES (⏳ disponibilità salvo conferma e almeno 3 settimane per consegna)",
                value=st.session_state.include_fw,
                key="include_fw",
            )

        # Costruisci dataset PARZIALE per calcolare i bound dinamici dei prezzi
        df_all = df_base.copy()
        if st.session_state.include_fw:
            try:
                df_fw = load_data(FW_CSV_URL)
                df_fw["is_fw"] = True
                df_all = pd.concat([df_all, df_fw], ignore_index=True)
            except requests.exceptions.HTTPError as e:
                st.warning("⚠️ Impossibile caricare il foglio Fine Wines.")
                st.caption(f"Dettaglio: {e}")

        tokens = tokenize_query(q) if q else []
        mask_text = (
            df_all.apply(lambda r: row_matches(r, tokens, SEARCH_FIELDS), axis=1)
            if tokens else pd.Series(True, index=df_all.index)
        )
        df_after_text = df_all.loc[mask_text]

        dyn_min, dyn_max = adaptive_price_bounds(df_after_text)

        # --- Colonna destra: Box filtri prezzo ---
        with col_price:
            with st.container(border=True):
                st.markdown("**Filtri prezzo**")
                min_price_input = st.number_input(
                    "Prezzo min", min_value=0.0, value=float(dyn_min), step=0.1, format="%.2f"
                )
                max_price_input = st.number_input(
                    "Prezzo max", min_value=0.01, value=float(dyn_max), step=0.1, format="%.2f"
                )
                max_for_slider = max(min_price_input, max_price_input)
                price_range = st.slider(
                    "Range",
                    min_value=0.0,
                    max_value=max(0.01, round(max_for_slider, 2)),
                    value=(float(min_price_input), float(max_price_input)),
                    step=0.1,
                )

        # Valori finali selezionati
        min_price = min(price_range[0], price_range[1])
        max_price = max(price_range[0], price_range[1])

        submitted = st.form_submit_button("Cerca")

    # Applica anche il filtro prezzo
    mask_price = df_after_text["prezzo"].fillna(0.0).between(min_price, max_price)
    df_res = df_after_text.loc[mask_price].reset_index(drop=True)

    st.caption(f"Risultati: {len(df_res)}")

    # Toggle risultati
    c_toggle, _ = st.columns([3, 7])
    all_on = st.session_state.res_select_all_toggle and not st.session_state.reset_res_selection
    if c_toggle.button("Deseleziona tutti i risultati" if all_on else "Seleziona tutti i risultati"):
        st.session_state.res_select_all_toggle = not all_on
        st.session_state.reset_res_selection = not st.session_state.res_select_all_toggle
        st.rerun()

    # Griglia risultati con prefisso ⏳ per FW (solo display)
    default_sel = st.session_state.res_select_all_toggle and not st.session_state.reset_res_selection
    df_res_display = with_fw_prefix(df_res)[DISPLAY_COLUMNS].copy()
    df_res_display.insert(0, "sel", default_sel)

    edited_res = st.data_editor(
        df_res_display,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "sel": st.column_config.CheckboxColumn(label="", width=38, help="Seleziona riga"),
            "codice": st.column_config.TextColumn(width=50),
            "prodotto": st.column_config.TextColumn(width=380),
            "prezzo": st.column_config.NumberColumn(format="€ %.2f", width=75),
            "categoria": st.column_config.TextColumn(width=160),
            "tipologia": st.column_config.TextColumn(width=160),
            "provenienza": st.column_config.TextColumn(width=160),
        },
        disabled=["codice", "prodotto", "prezzo", "categoria", "tipologia", "provenienza"],
        key="res_editor",
    )

    st.divider()
    add_btn = st.button("➕ Aggiungi selezionati al paniere", type="primary")

    # Notifica sotto al bottone
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
            combined = pd.concat([st.session_state.basket, df_to_add], ignore_index=True)
            combined = combined.drop_duplicates(subset=["codice"]).reset_index(drop=True)
            st.session_state.basket = combined
            st.session_state.res_select_all_toggle = False
            st.session_state.reset_res_selection = True
            st.session_state.flash = {"type": "success", "msg": f"Aggiunti {len(df_to_add)} articoli al paniere.", "shown": False}
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

    # Prefisso ⏳ in display anche nel paniere
    basket_display = with_fw_prefix(basket)[DISPLAY_COLUMNS].copy()
    basket_display.insert(0, "rm", default_sel_b)

    edited_basket = st.data_editor(
        basket_display,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "rm": st.column_config.CheckboxColumn(label="", width=38, help="Seleziona per rimuovere"),
            "codice": st.column_config.TextColumn(width=120),
            "prodotto": st.column_config.TextColumn(width=380),
            "prezzo": st.column_config.NumberColumn(format="€ %.2f", width=100),
            "categoria": st.column_config.TextColumn(width=160),
            "tipologia": st.column_config.TextColumn(width=160),
            "provenienza": st.column_config.TextColumn(width=160),
        },
        disabled=["codice", "prodotto", "prezzo", "categoria", "tipologia", "provenienza"],
        key="basket_editor",
    )

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 1])
    remove_btn = c1.button("🗑️ Rimuovi selezionati", type="primary")

    # Ordina prima di esportare
    basket_sorted = st.session_state.basket.sort_values(
        ["categoria", "tipologia", "provenienza", "prodotto"], kind="stable"
    ).reset_index(drop=True)

    # Export con prefisso ⏳ per i FW (PDF-safe sostituisce ⏳ -> [FW])
    export_df = with_fw_prefix(basket_sorted)[DISPLAY_COLUMNS].copy()

    # Download diretto: Excel e PDF
    xbuf = make_excel(export_df)
    c2.download_button(
        "⬇️ Esporta Excel",
        data=xbuf,
        file_name="prodotti_selezionati.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    pbuf = make_pdf(export_df)
    c3.download_button(
        "⬇️ Crea PDF",
        data=pbuf,
        file_name="prodotti_selezionati.pdf",
        mime="application/pdf",
    )

    if remove_btn:
        to_remove = set(edited_basket.loc[edited_basket["rm"].fillna(False), "codice"].tolist())
        if to_remove:
            st.session_state.basket = st.session_state.basket[
                ~st.session_state.basket["codice"].isin(to_remove)
            ].reset_index(drop=True)
            st.session_state.basket_select_all_toggle = False
            st.session_state.reset_basket_selection = True
            st.success("Rimossi articoli selezionati.")
            st.rerun()
        else:
            st.info("Seleziona almeno un articolo da rimuovere.")
