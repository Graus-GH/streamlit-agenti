import streamlit as st
import pandas as pd
from io import BytesIO
import xlsxwriter
from fpdf import FPDF
from rapidfuzz import fuzz
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Ricerca articoli - Agenti", layout="wide")

# --- DEDUPLICA COLONNE ---
def make_unique_columns(columns):
    seen = {}
    new_cols = []
    for col in columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    return new_cols

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
    df['codice'] = pd.to_numeric(df['codice'], errors='coerce').fillna(0).astype(int)
    df.columns = make_unique_columns(df.columns)
    return df

df = load_data()

# --- SESSION STATE ---
if "paniere" not in st.session_state:
    st.session_state["paniere"] = []

# --- RICERCA FUZZY ---
def fuzzy_filter(df, query, threshold=50):
    if not query or query.strip() == "":
        return pd.DataFrame(columns=df.columns)  # restituisce vuoto se non c'è query
    mask = df.apply(lambda row: any(
        fuzz.partial_ratio(str(value).lower(), query.lower()) >= threshold
        for value in row[['codice', 'prodotto', 'categoria', 'tipologia', 'provenienza']]
    ), axis=1)
    return df[mask]

# --- LAYOUT ---
col1, col2 = st.columns([2, 1])

# ===========================
# COLONNA SINISTRA: RICERCA
# ===========================
with col1:
    st.header("🔍 Ricerca articoli")
    query = st.text_input("Cerca prodotto, codice, categoria, tipologia, provenienza:")
    results = fuzzy_filter(df, query)

    if query and not results.empty:
        st.write(f"**{len(results)} articoli trovati**")

        # --- TABELLA INTERATTIVA ---
        gb = GridOptionsBuilder.from_dataframe(results[['codice', 'prodotto', 'categoria', 'tipologia', 'provenienza', 'prezzo']])
        gb.configure_selection('multiple', use_checkbox=True)
        gb.configure_pagination(paginationAutoPageSize=True)
        grid_options = gb.build()

        grid_response = AgGrid(
            results,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            theme="balham",
            fit_columns_on_grid_load=True,
            use_container_width=True
        )
        selected_rows = grid_response['selected_rows']

        if st.button("➕ Aggiungi selezionati al paniere") and selected_rows:
            for prodotto in selected_rows:
                if prodotto not in st.session_state["paniere"]:
                    st.session_state["paniere"].append(prodotto)
            st.success(f"{len(selected_rows)} prodotti aggiunti al paniere.")
    elif query:
        st.warning("Nessun articolo trovato.")
    else:
        st.info("Digita un testo per cercare articoli.")

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
