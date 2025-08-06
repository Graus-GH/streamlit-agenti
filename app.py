import streamlit as st
import pandas as pd
from io import BytesIO
import xlsxwriter
from fpdf import FPDF
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(page_title="Ricerca articoli - Agenti", layout="wide")

# --- DEDUPLICA NOMI COLONNE ---
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
    df.columns = make_unique_columns(df.columns)  # <-- colonne uniche

    # Individua la prima colonna che contiene questi campi
    def find_col(name):
        for col in df.columns:
            if col.startswith(name):
                return col
        return None

    col_codice = find_col('codice articolo') or find_col('codice')
    col_prodotto = find_col('nuova descrizione') or find_col('prodotto')
    col_categoria = find_col('reparto') or find_col('categoria')
    col_tipologia = find_col('sottoreparto') or find_col('tipologia')
    col_provenienza = find_col('altro reparto') or find_col('provenienza')
    col_prezzo = find_col('prezzo')

    # Prendi solo le colonne trovate
    cols = [c for c in [col_codice, col_prodotto, col_categoria, col_tipologia, col_provenienza, col_prezzo] if c]
    df = df[cols]
    df.columns = ['codice', 'prodotto', 'categoria', 'tipologia', 'provenienza', 'prezzo'][:len(df.columns)]

    # Conversione numerica
    if 'codice' in df.columns:
        df['codice'] = pd.to_numeric(df['codice'], errors='coerce').fillna(0).astype(int)
    if 'prezzo' in df.columns:
        df['prezzo'] = pd.to_numeric(df['prezzo'], errors='coerce').fillna(0)
    return df

df = load_data()

if "paniere" not in st.session_state:
    st.session_state["paniere"] = []

# --- RICERCA ---
def search_filter(df, query):
    if not query or query.strip() == "":
        return df
    query = query.lower()
    mask = df.apply(lambda row: any(query in str(value).lower() for value in row if pd.notna(value)), axis=1)
    return df[mask]

# --- SIDEBAR: FILTRO PREZZO (DINAMICO) ---
st.sidebar.header("Filtri")
query = st.sidebar.text_input("Cerca prodotto, codice, categoria, tipologia, provenienza:")
results = search_filter(df, query)

if not results.empty and 'prezzo' in results.columns:
    min_price = float(results['prezzo'].min())
    max_price = float(results['prezzo'].max())
else:
    min_price = 0
    max_price = 0

price_range = st.sidebar.slider("Filtra per prezzo (€)", min_value=min_price, max_value=max_price, value=(min_price, max_price))
results = results[(results['prezzo'] >= price_range[0]) & (results['prezzo'] <= price_range[1])]

# --- LAYOUT ---
col1, col2 = st.columns([2.5, 1])

# ===========================
# COLONNA SINISTRA: RICERCA
# ===========================
with col1:
    st.header("🔍 Risultati ricerca")
    if not results.empty:
        st.write(f"**{len(results)} articoli trovati**")

        gb = GridOptionsBuilder.from_dataframe(results)
        gb.configure_selection('multiple', use_checkbox=True)
        gb.configure_pagination(enabled=False)
        gb.configure_column("prodotto", width=400)
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
        gb_p = GridOptionsBuilder.from_dataframe(paniere_df[['codice', 'prodotto', 'prezzo']])
        gb_p.configure_selection('multiple', use_checkbox=True)
        grid_options_paniere = gb_p.build()

        grid_response_paniere = AgGrid(
            paniere_df[['codice', 'prodotto', 'prezzo']],
            gridOptions=grid_options_paniere,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            theme="balham",
            fit_columns_on_grid_load=True,
            use_container_width=True
        )

        selected_remove = grid_response_paniere['selected_rows']
        if st.button("🗑️ Rimuovi selezionati") and selected_remove:
            st.session_state["paniere"] = [p for p in st.session_state["paniere"] if p not in selected_remove]
            st.success("Prodotti rimossi.")

        # Totale paniere
        st.markdown(f"**Totale: {paniere_df['prezzo'].sum():.2f} €**")
    else:
        st.info("Il paniere è vuoto.")
