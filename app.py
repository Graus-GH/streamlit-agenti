import streamlit as st
import pandas as pd
from io import BytesIO
import xlsxwriter
from fpdf import FPDF
from rapidfuzz import fuzz

# --- CONFIGURAZIONE ---
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

    # Converte il codice in numerico senza decimali
    df['codice'] = pd.to_numeric(df['codice'], errors='coerce').fillna(0).astype(int)

    return df

df = load_data()

# --- INIZIALIZZA SESSION STATE ---
if "paniere" not in st.session_state:
    st.session_state["paniere"] = []
if "selected_rows" not in st.session_state:
    st.session_state["selected_rows"] = set()
if "active_filters" not in st.session_state:
    st.session_state["active_filters"] = {"categoria": set(), "tipologia": set(), "provenienza": set()}

# --- FUNZIONE DI RICERCA FUZZY ---
def fuzzy_filter(df, query, threshold=50):
    if not query:
        return df
    mask = df.apply(lambda row: any(
        fuzz.partial_ratio(str(value).lower(), query.lower()) >= threshold
        for value in row[['codice', 'prodotto', 'categoria', 'tipologia', 'provenienza']]
    ), axis=1)
    return df[mask]

# --- FILTRO SU TAG ATTIVI ---
def apply_tag_filters(df):
    for field, excluded in st.session_state["active_filters"].items():
        if excluded:
            df = df[~df[field].isin(excluded)]
    return df

# --- LAYOUT A DUE COLONNE ---
col1, col2 = st.columns([2, 1])

# ===========================
# COLONNA SINISTRA: RICERCA
# ===========================
with col1:
    st.header("🔍 Ricerca articoli")
    query = st.text_input("Cerca prodotto, codice, categoria, tipologia, provenienza:")
    results = fuzzy_filter(df, query)
    results = apply_tag_filters(results)

    st.write(f"**{len(results)} articoli trovati**")

    # --- MOSTRA TAG DI FILTRO ---
    for field in ['categoria', 'tipologia', 'provenienza']:
        st.write(f"**Filtra {field}:**")
        unique_values = sorted(results[field].dropna().unique())
        for val in unique_values:
            if st.button(f"❌ {val}", key=f"filter_{field}_{val}"):
                st.session_state["active_filters"][field].add(val)
        if st.session_state["active_filters"][field]:
            st.write("Filtri esclusi: ", ", ".join(st.session_state["active_filters"][field]))

    # --- TABELLA RISULTATI ---
    if not results.empty:
        st.dataframe(results, use_container_width=True)
    else:
        st.warning("Nessun articolo trovato.")

    # --- CHECKBOX PER SELEZIONE ---
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
