import io
import re
from typing import List, Tuple
import numpy as np
import pandas as pd
import requests
import streamlit as st
from fpdf import FPDF

st.set_page_config(page_title="Ricerca articoli • Prodotti selezionati", layout="wide")

SHEET_ID = "10BFJQTV1yL69cotE779zuR8vtG5NqKWOVH0Uv1AnGaw"
GID = "707323537"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

COL_MAP = {
    "codice": 0,
    "prodotto": 2,
    "categoria": 5,
    "tipologia": 6,
    "provenienza": 7,
    "prezzo": 8,
}

DISPLAY_COLUMNS = ["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"]
SEARCH_FIELDS = ["codice", "prodotto", "categoria", "tipologia", "provenienza"]

@st.cache_data(ttl=600)
def load_data(url: str) -> pd.DataFrame:
    r = requests.get(url)
    r.raise_for_status()
    df_raw = pd.read_csv(io.BytesIO(r.content))
    df = pd.DataFrame({name: df_raw.iloc[:, idx] for name, idx in COL_MAP.items()})
    for c in ["prodotto", "categoria", "tipologia", "provenienza"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
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
    def normalize_code(x: str) -> str:
        s = re.sub(r"\D", "", str(x))
        s = s.lstrip("0") or "0"
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

st.markdown("""
<style>
.stButton > button[kind="primary"] {
  background-color: #005caa;
  border-color: #005caa;
  color: #fff;
}
</style>
""", unsafe_allow_html=True)

if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)

with st.spinner("Caricamento dati…"):
    df_all = load_data(CSV_URL)

df_all = df_all[DISPLAY_COLUMNS].copy()

st.title("🔎 Ricerca articoli & 🧺 Prodotti selezionati")

# --- Ricerca ---
q = st.text_input("Cerca articoli", placeholder="Es. 'riesling alto adige 0,75'")
tokens = tokenize_query(q) if q else []
mask_text = df_all.apply(lambda r: row_matches(r, tokens, SEARCH_FIELDS), axis=1) if tokens else pd.Series(True, index=df_all.index)
df_after_text = df_all.loc[mask_text]

mn, mx = adaptive_price_bounds(df_after_text)
min_price = st.number_input("Prezzo min", min_value=0.0, value=float(mn), step=0.1, format="%.2f")
max_price = st.number_input("Prezzo max", min_value=0.01, value=float(mx), step=0.1, format="%.2f")
mask_price = df_after_text["prezzo"].fillna(0.0).between(min_price, max_price)
df_res = df_after_text.loc[mask_price].reset_index(drop=True)

selected_rows = st.multiselect("Seleziona prodotti", options=df_res.index, format_func=lambda x: df_res.loc[x, "prodotto"])
if st.button("Aggiungi selezionati al paniere", type="primary"):
    if selected_rows:
        st.session_state.basket = pd.concat([st.session_state.basket, df_res.loc[selected_rows]], ignore_index=True).drop_duplicates(subset=["codice"])
        st.success(f"Aggiunti {len(selected_rows)} prodotti al paniere.")
    else:
        st.info("Seleziona almeno un prodotto.")

# --- Paniere ---
st.subheader("🧺 Prodotti selezionati")
if not st.session_state.basket.empty:
    st.dataframe(st.session_state.basket)
    if st.button("Svuota paniere"):
        st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
        st.success("Paniere svuotato.")
    if st.button("Esporta Excel"):
        st.download_button("Scarica Excel", data=make_excel(st.session_state.basket), file_name="prodotti_selezionati.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if st.button("Crea PDF"):
        st.download_button("Scarica PDF", data=make_pdf(st.session_state.basket), file_name="prodotti_selezionati.pdf", mime="application/pdf")
else:
    st.info("Il paniere è vuoto.")
