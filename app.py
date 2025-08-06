import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(page_title="Ricerca articoli - Agenti", layout="wide")

# --- CARICA DATI ---
@st.cache_data
def load_data():
    url = "https://docs.google.com/spreadsheets/d/10BFJQTV1yL69cotE779zuR8vtG5NqKWOVH0Uv1AnGaw/export?format=csv&gid=707323537"
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()

    mapping = {
        'Codice Articolo': 'codice',
        'Nuova descrizione': 'prodotto',
        'Reparto': 'categoria',
        'SottoReparto': 'tipologia',
        'Altro Reparto': 'provenienza',
        'Prezzo': 'prezzo'
    }
    available = {k: v for k, v in mapping.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available)

    # Conversioni
    if 'codice' in df.columns:
        df['codice'] = pd.to_numeric(df['codice'], errors='coerce').fillna(0).astype(int)
    else:
        df['codice'] = 0
    if 'prezzo' in df.columns:
        df['prezzo'] = pd.to_numeric(df['prezzo'], errors='coerce').fillna(0)
    else:
        df['prezzo'] = 0.0

    return df

df = load_data()

if "paniere" not in st.session_state:
    st.session_state["paniere"] = []
if "grid_key" not in st.session_state:
    st.session_state["grid_key"] = 0

# --- RICERCA ---
def search_filter(df, query):
    if not query or query.strip() == "":
        return df
    query = query.lower()
    mask = df.apply(lambda row: any(query in str(value).lower() for value in row if pd.notna(value)), axis=1)
    return df[mask]

# --- FILTRI ---
st.sidebar.header("Filtri")
query = st.sidebar.text_input("Cerca prodotto, codice, categoria, tipologia, provenienza:")
results = search_filter(df, query)

if not results.empty:
    min_price = float(results['prezzo'].min())
    max_price = float(results['prezzo'].max())
    if min_price == max_price:  # evita errore slider
        max_price = min_price + 1
else:
    min_price = 0
    max_price = 1

price_range = st.sidebar.slider("Filtra per prezzo (€)", min_value=min_price, max_value=max_price, value=(min_price, max_price))
manual_min = st.sidebar.number_input("Prezzo minimo", min_value=min_price, max_value=max_price, value=price_range[0])
manual_max = st.sidebar.number_input("Prezzo massimo", min_value=min_price, max_value=max_price, value=price_range[1])
price_range = (manual_min, manual_max)
results = results[(results['prezzo'] >= price_range[0]) & (results['prezzo'] <= price_range[1])]

# --- LAYOUT ---
col1, col2 = st.columns([2.5, 1])

# ===========================
# RISULTATI RICERCA
# ===========================
with col1:
    st.header("🔍 Risultati ricerca")
    if not results.empty:
        st.write(f"**{len(results)} articoli trovati**")

        # Pulsante a destra sopra la tabella
        _, top_right = st.columns([4, 1])
        with top_right:
            if st.button("➕ Aggiungi selezionati"):
                selected_rows = st.session_state.get('last_selection', [])
                if isinstance(selected_rows, pd.DataFrame):
                    selected_rows = selected_rows.to_dict(orient="records")
                if selected_rows:
                    for prodotto in selected_rows:
                        if prodotto not in st.session_state["paniere"]:
                            st.session_state["paniere"].append(prodotto)
                    st.success(f"{len(selected_rows)} prodotti aggiunti.")
                    st.session_state['last_selection'] = []
                    st.session_state["grid_key"] += 1
                else:
                    st.warning("Nessun prodotto selezionato.")

        # Tabella
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
            use_container_width=True,
            key=st.session_state["grid_key"]
        )

        selected_rows = grid_response['selected_rows']
        if isinstance(selected_rows, pd.DataFrame):
            selected_rows = selected_rows.to_dict(orient="records")
        st.session_state['last_selection'] = selected_rows

    elif query:
        st.warning("Nessun articolo trovato.")
    else:
        st.info("Digita un testo per cercare articoli.")

# ===========================
# PANIERE
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

        st.markdown(f"**Totale: {paniere_df['prezzo'].sum():.2f} €** ({len(paniere_df)} articoli)")
    else:
        st.info("Il paniere è vuoto.")
