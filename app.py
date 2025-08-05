import streamlit as st
import pandas as pd
from io import BytesIO
import xlsxwriter
from fpdf import FPDF

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Ricerca articoli - Agenti", layout="wide")

# --- CARICA DATI ---
@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/10BFJQTV1yL69cotE779zuR8vtG5NqKWOVH0Uv1AnGaw/export?format=csv&gid=707323537"
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower()
    mapping = {
        'codice articolo': 'codice',
        'nuova descrizione': 'prodotto',
        'reparto': 'categoria',
        'sottoreparto': 'tipologia',
        'altro reparto': 'provenienza',
        'prezzo': 'prezzo'
    }
    df = df.rename(columns=mapping)
    df = df[list(mapping.values())]
    return df

df = load_data()

# --- INIZIALIZZA SESSION STATE ---
if "paniere" not in st.session_state:
    st.session_state["paniere"] = []
if "selected_rows" not in st.session_state:
    st.session_state["selected_rows"] = set()

# --- LAYOUT A DUE COLONNE ---
col1, col2 = st.columns([2, 1])

# ===========================
# COLONNA SINISTRA: RICERCA
# ===========================
with col1:
    st.header("🔍 Ricerca articoli")
    query = st.text_input("Cerca prodotto, codice, categoria, tipologia, provenienza:")

    if query:
        mask = df.apply(lambda row: query.lower() in row.astype(str).str.lower().to_string(), axis=1)
        results = df[mask]
    else:
        results = df.copy()

    st.write(f"**{len(results)} articoli trovati**")

    # Tabella con checkbox
    st.write("**Seleziona prodotti:**")
    all_indices = results.index.tolist()
    select_all = st.checkbox("Seleziona tutti", value=False, key="select_all")

    if select_all:
        st.session_state["selected_rows"] = set(all_indices)
    else:
        st.session_state["selected_rows"].intersection_update(all_indices)

    for i, row in results.iterrows():
        checked = st.checkbox(
            f"{row['codice']} - {row['prodotto']} ({row['prezzo']})",
            value=i in st.session_state["selected_rows"],
            key=f"check_{i}"
        )
        if checked:
            st.session_state["selected_rows"].add(i)
        else:
            st.session_state["selected_rows"].discard(i)

    if st.button("➕ Aggiungi selezionati al paniere"):
        for i in st.session_state["selected_rows"]:
            prodotto = results.loc[i].to_dict()
            if prodotto not in st.session_state["paniere"]:
                st.session_state["paniere"].append(prodotto)
        st.session_state["selected_rows"].clear()
        st.success("Prodotti aggiunti al paniere.")

# ===========================
# COLONNA DESTRA: PANIERE
# ===========================
with col2:
    st.header("🛒 Paniere")
    paniere_df = pd.DataFrame(st.session_state["paniere"])
    if not paniere_df.empty:
        st.dataframe(paniere_df, use_container_width=True)
        to_remove = st.multiselect("Seleziona prodotti da rimuovere", paniere_df.index)
        if st.button("🗑️ Rimuovi selezionati"):
            for i in sorted(to_remove, reverse=True):
                del st.session_state["paniere"][i]
            st.success("Prodotti rimossi.")
    else:
        st.info("Il paniere è vuoto.")

    # --- ESPORTA ---
    def create_excel(data):
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            data.to_excel(writer, index=False, sheet_name="Paniere")
        return output.getvalue()

    def create_pdf(data):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, "Paniere Prodotti", ln=True, align='C')
        pdf.ln(10)
        for _, row in data.iterrows():
            pdf.multi_cell(0, 10, f"{row['codice']} - {row['prodotto']} ({row['prezzo']})")
        return pdf.output(dest='S').encode('latin1')

    if not paniere_df.empty:
        xlsx_data = create_excel(paniere_df)
        st.download_button("⬇️ Scarica Excel", xlsx_data, "paniere.xlsx")

        pdf_data = create_pdf(paniere_df)
        st.download_button("⬇️ Scarica PDF", pdf_data, "paniere.pdf")
