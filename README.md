# Ricerca articoli & Paniere – Streamlit

Interfaccia per agenti con ricerca flessibile su articoli da Google Sheets, filtro prezzo, paniere, export Excel e PDF.

## ⚙️ Configurazione rapida
1) **Copia questo repo** su GitHub.
2) Verifica che il Google Sheet sia condiviso con visibilità "Chiunque con il link può visualizzare".
3) Aggiorna l'ID del foglio e il `gid` in `app.py` (se necessario).
4) Avvia in locale:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
