import streamlit as st
import pandas as pd
from io import BytesIO
import xlsxwriter
from fpdf import FPDF
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Ricerca articoli - Agenti", layout="wide")

# --- CARICA DATI DA GOOGLE SHEET ---
@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/10BFJQTV1yL69cotE779zuR8vtG5NqKWOVH0Uv1AnGaw/export?format=csv&gid=707323537"
    
    # Carica tutto senza header
    raw_df = pd.read_csv(url, header=None)
    
    # Trova la riga che contiene l’intestazione (dove c'è "CODICE")
    header_row_index = raw_df[raw_df.iloc[:, 1] == "CODICE"].index[0]
    
    # Rileggi i dati veri con intestazione corretta
    df = pd.read_csv(url, skiprows=header_row_index + 1)

    # Rinomina colonne
    df = df.rename(columns={
        'Codice Articolo': 'codice',
        'Nuova descrizione': 'prodotto',
        'Reparto': 'categoria',
        'SottoReparto': 'tipologia',
        'Altro Reparto': 'provenienza',
        'Prezzo': 'prezzo'
    })

    df = df[['codice', 'prodotto', 'categoria', 'tipologia', 'provenienza', 'prezzo']]
    df['codice'] = pd.to_numeric(df['codice'], errors='coerce').fillna(0).astype(int)
    df['prezzo'] = pd.to_numeric(df['prezzo'], errors='coerce').fillna(0)

    return df

df = load_data()

# --- SESSION STATE ---
if "paniere" not in st.session_state:
    st.session_state["paniere"] = []

# --- RICERCA MULTI-PAROLA ---
def search_filter(df, query):
    if not query or query.strip() == "":
        return pd.DataFrame(columns=df.columns)

    keywords = query.lower().split()

    def row_matches(row):
        text = ' '.join(str(row[col]).lower() for col in ['codice', 'prodotto', 'categoria', 'tipologia', 'provenienza'])
        return all(keyword in text for keyword in keywords)

    mask = df.apply(row_matches, axis=1)
    filtered = df[mask]

    st.write(f"🔍 Risultati dopo filtro testuale: {len(filtered)} articoli trovati")
    return filtered

# --- SIDEBAR: FILTRO PREZZO ---
st.sidebar.header("Filtri")
min_price = float(df['prezzo'].min())
max_price = float(df['prezzo'].max())
price_range = st.sidebar.slider("Filtra per prezzo (€)", min_value=min_price, max_value=max_price, value=(min_price, max_price))

# --- LAYOUT ---
col1, col2 = st.columns([2, 1])

# ===========================
# COLONNA SINISTRA: RICERCA
# ===========================
with col1:
    st.header("🔍 Ricerca articoli")
    query = st.text_input("Cerca prodotto, codice, categoria, tipologia, provenienza:")
    results = search_filter(df, query)
    results = results[(results['prezzo'] >= price_range[0]) & (results['prezzo'] <= price_range[1])]

    if query and not results.empty:
        st.write(f"**{len(results)} articoli trovati nel range di prezzo selezionato**")

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
        if isinstance(selected_rows, pd.DataFrame):
            selected_rows = selected_rows.to_dict(orient="records")

        if st.button("➕ Aggiungi selezionati al paniere"):
            if selected_rows and len(selected_rows) > 0:
                for prodotto in selected_rows:
                    if prodotto not in st.session_state["paniere"]:
                        st.session_state["paniere"].append(prodotto)
                st.success(f"{len(selected_rows)} prodotti aggiunti al paniere.")
                st.experimental_rerun()
            else:
                st.warning("Nessun prodotto selezionato.")
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
            pdf.multi_cell(0, 10, f"{row['codice']} - {row['prodotto']} ({row['prezzo']} €)")
        return pdf.output(dest='S').encode('latin1')

    if not paniere_df.empty:
        xlsx_data = create_excel(paniere_df)
        st.download_button("⬇️ Scarica Excel", xlsx_data, "paniere.xlsx")

        pdf_data = create_pdf(paniere_df)
        st.download_button("⬇️ Scarica PDF", pdf_data, "paniere.pdf")
