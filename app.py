import io
import re
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
DISPLAY_COLUMNS = list(COL_MAP.keys())

# ---------- Utils ----------
def normalize_code(x: str) -> str:
    """
    Mantieni il codice 'com'è' se NON ha decimali.
    Se il codice contiene decimali ('.' o ','), restituisci la parte intera (senza decimali).
      Esempi:
        '00123.00' -> '123'
        '00123,45' -> '123'
        '00123'    -> '00123'  (immutato)
    """
    s = str(x).strip()
    # Se contiene separatore decimale, prendi il primo numero con decimali e tronca a intero
    if "." in s or "," in s:
        # prendi la prima sequenza numerica (con eventuali decimali)
        m = re.search(r"\d+(?:[.,]\d+)?", s)
        if m:
            whole = m.group(0).replace(",", ".")
            try:
                return str(int(float(whole)))  # rimuove i decimali e zeri finali
            except Exception:
                pass
        # fallback: solo cifre
        digits = re.sub(r"\D", "", s)
        return str(int(digits)) if digits else "0"
    else:
        # nessun decimale: restituisci solo le cifre ma SENZA toccare eventuali zeri iniziali nel mezzo del testo
        # (se il codice è alfanumerico, estraiamo la prima sequenza di cifre)
        m = re.search(r"\d+", s)
        return m.group(0) if m else "0"

def make_pdf(df: pd.DataFrame) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Prodotti selezionati", ln=1)
    pdf.set_font("Helvetica", "B", 10)
    for col in DISPLAY_COLUMNS:
        pdf.cell(40, 8, col.upper(), border=1)
    pdf.ln(8)
    pdf.set_font("Helvetica", size=9)
    for _, r in df.iterrows():
        for col in DISPLAY_COLUMNS:
            pdf.cell(40, 6, str(r[col]), border=1)
        pdf.ln(6)
    return bytes(pdf.output(dest="S").encode("latin1"))

def make_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Prodotti selezionati")
    buf.seek(0)
    return buf.read()

@st.cache_data(ttl=600)
def load_data():
    r = requests.get(CSV_URL)
    r.raise_for_status()
    df_raw = pd.read_csv(io.BytesIO(r.content))
    df = pd.DataFrame({name: df_raw.iloc[:, idx] for name, idx in COL_MAP.items()})
    for c in ["prodotto", "categoria", "tipologia", "provenienza"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
    # prezzo numerico robusto
    df["prezzo"] = pd.to_numeric(
        df["prezzo"].astype(str).str.replace("€", "").str.replace(",", "."),
        errors="coerce"
    )
    # codice normalizzato come richiesto
    df["codice"] = df["codice"].apply(normalize_code)
    # solo righe con prodotto
    return df.dropna(subset=["prodotto"])

# ---------- State ----------
if "basket" not in st.session_state:
    st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
# selezioni risultati
if "res_selected_codes" not in st.session_state:
    st.session_state.res_selected_codes = set()
if "res_editor_version" not in st.session_state:
    st.session_state.res_editor_version = 0
# messaggio persistente dopo aggiunta
if "last_add_count" not in st.session_state:
    st.session_state.last_add_count = 0

# ---------- Data ----------
df_all = load_data()

st.title("🔎 Ricerca articoli & 🧺 Prodotti selezionati")

# Ricerca testuale semplice su tutte le colonne
q = st.text_input("Cerca articoli", placeholder="Parole multiple consentite")
if q:
    tokens = [t for t in q.split() if t]
    def _row_ok(r):
        hay = " ".join(str(r[f]) for f in DISPLAY_COLUMNS).lower()
        return all(t.lower() in hay for t in tokens)
    filtered = df_all[df_all.apply(_row_ok, axis=1)].reset_index(drop=True)
else:
    filtered = df_all.reset_index(drop=True)

st.caption(f"Risultati: {len(filtered)}")

# --- Seleziona / Deseleziona tutti: sempre coerenti con la tabella corrente ---
c1, c2, _ = st.columns([1.2, 1.8, 6])
if c1.button("Seleziona tutti"):
    st.session_state.res_selected_codes = set(filtered["codice"])
    st.session_state.res_editor_version += 1
if c2.button("Deseleziona tutti"):
    st.session_state.res_selected_codes.clear()
    st.session_state.res_editor_version += 1

# Griglia con colonna di selezione derivata dallo stato
df_display = filtered.copy()
df_display.insert(0, "sel", filtered["codice"].isin(st.session_state.res_selected_codes))

edited = st.data_editor(
    df_display,
    hide_index=True,
    key=f"res_editor_{st.session_state.res_editor_version}",
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "sel": st.column_config.CheckboxColumn(label="", help="Seleziona riga"),
        "codice": st.column_config.TextColumn(width="small"),
        "prodotto": st.column_config.TextColumn(width="medium"),
        "categoria": st.column_config.TextColumn(width="small"),
        "tipologia": st.column_config.TextColumn(width="small"),
        "provenienza": st.column_config.TextColumn(width="small"),
        "prezzo": st.column_config.NumberColumn(format="€ %.2f", width="small"),
    },
    disabled=["codice", "prodotto", "categoria", "tipologia", "provenienza", "prezzo"],
)

# Aggiorna lo stato in base alle checkbox correnti (funziona anche se ne hai selezionate solo alcune)
st.session_state.res_selected_codes = set(edited.loc[edited["sel"].fillna(False), "codice"].tolist())

# Bottone aggiunta con messaggio persistente
if st.button("Aggiungi selezionati al paniere", type="primary"):
    if st.session_state.res_selected_codes:
        to_add = filtered[filtered["codice"].isin(st.session_state.res_selected_codes)]
        st.session_state.basket = (
            pd.concat([st.session_state.basket, to_add], ignore_index=True)
              .drop_duplicates(subset=["codice"])
        )
        # deseleziona tutto e forza refresh della tabella (senza st.rerun, così il messaggio resta)
        st.session_state.res_selected_codes.clear()
        st.session_state.res_editor_version += 1
        st.session_state.last_add_count = len(to_add)
    else:
        st.info("Seleziona almeno un articolo.")

# Messaggio che resta finché non fai un’altra azione (es. nuova ricerca o nuova aggiunta)
if st.session_state.last_add_count:
    st.success(f"Aggiunti {st.session_state.last_add_count} articoli al paniere.", icon="✅")

# --- Paniere ---
st.subheader("🧺 Prodotti selezionati")
if not st.session_state.basket.empty:
    st.dataframe(st.session_state.basket, use_container_width=True)
    col1, col2, col3 = st.columns(3)
    if col1.button("Svuota paniere"):
        st.session_state.basket = pd.DataFrame(columns=DISPLAY_COLUMNS)
        st.session_state.last_add_count = 0
    with col2:
        xbuf = make_excel_bytes(st.session_state.basket)
        st.download_button("Scarica Excel", data=xbuf,
                           file_name="prodotti.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with col3:
        pbuf = make_pdf(st.session_state.basket)
        st.download_button("Scarica PDF", data=pbuf,
                           file_name="prodotti.pdf",
                           mime="application/pdf")
else:
    st.info("Paniere vuoto")
