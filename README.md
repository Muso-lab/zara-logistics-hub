# 🚚 Zara Logistics Automation Platform - Monterotondo Hub

Soluzione avanzata e strutturata in Python per la gestione, pianificazione, generazione flussi SGA e archiviazione storica delle spedizioni Zara / Inditex.

Sostituisce completamente il vecchio file Excel con macro VBA (`Planning ZARA.xlsm`), garantendo:
1. **Piena storicità dei dati**: ogni elaborazione settimanale (con previsioni, colli, volumi, pesi, flussi e spunte) viene salvata in modo permanente in un database SQLite (`data/zara_history.db`). Nulla viene sovrascritto o perso.
2. **Eliminazione degli errori e blocchi di Excel**: niente più macro lente, crash di Excel, tabelle pivot da aggiornare manualmente o copia-incolla fragili.
3. **Interfaccia Web moderna (Streamlit)**: dashboard interattiva fruibile da browser con KPI, tabelle filtrabili, anteprime e download in 1 click dei file generati.
4. **Linea di comando (CLI)** per esecuzioni batch o schedulate automatiche (`--from-extranet`).
5. **Automazione Web Extranet Inditex (Completata al 100%)**: bot Playwright integrato che accede all'Extranet Inditex, cerca le spedizioni per intervallo di date, scarica automaticamente `TOTAL.xls`, `SHOES.xls`, `ECOM.xls`, `TEXILE.xls` e scansiona tutte le consegne scaricando i pacchetti `OTHER/*.xls` con altri bultos!

---

## 📁 Struttura del Progetto

```
delightful-goodall/
├── app.py                         # Web Dashboard interattiva (Streamlit)
├── cli.py                         # Interfaccia a riga di comando per elaborazioni rapide
├── data/
│   ├── zara_history.db            # Database SQLite con storico completo
│   ├── anagrafica_negozi.xlsx     # Anagrafica negozi, giri (ZA1..ZA20), codSGA, Barra 0/9
│   ├── spunta_template.json       # Layout ordinato e parametri di Spunta Arrivi
│   ├── planner_template.json      # Struttura righe per Planning Roma
│   └── templates/
│       └── Planning ITX_RM.xlsx   # Modello ufficiale Excel per Planner Roma
├── src/
│   ├── config.py                  # Configurazione percorsi e parametri logistici
│   ├── db.py                      # Gestione database SQLite e storico
│   ├── parsers.py                 # Parser per file TOTAL, SHOES, TEXILE, ECOM, OTHER, esportazione
│   ├── engine.py                  # Motore di calcolo: Analisi, Spunta Arrivi, SGA Barra 0/9, Planner Roma
│   ├── exporters.py               # Generatore file Excel conformi (ZARA.xlsx, barrazero_Sga, etc.)
│   └── pipeline.py                # Coordinatore del flusso end-to-end
├── output/                        # Cartella con le cartelle storiche per ogni run
└── tests/
    └── test_engine.py             # Test automatici con pytest (100% superati)
```

---

## ⚙️ Logica di Business e Flusso dei File

Il sistema replica ed ottimizza il flusso operativo precedentemente eseguito dalle macro VBA:

### 1. Ingestion File di Input
- **`TOTAL.xls`**: Previsión grupo de envío complessivo.
- **`SHOES.xls`**: Previsione calzature (Elche).
- **`TEXILE.xls`**: Previsione tessile (escluso Elche ed ECOM).
- **`ECOM.xls`**: Previsione colli e-commerce.
- **`OTHER/*.xls`**: Dettaglio spedizioni con "Otros Bultos" (profumi, decorazioni, accessori speciali).
- **`esportazione.xlsx`**: Dati consuntivi registrati da Access (`tbl_dati`), con colli abbigliamento, calzature, ecom, others e gestione consegne `STD` e `DOPPIA`.

### 2. Motore di Calcolo (`src/engine.py`)
- **Tessile Atteso**: `crts_textile_total - planned_others` (sottrae gli "altri colli" aggregati dai file in `OTHER`).
- **Altri Colli Attesi**: Somma di `Otros Bultos -> Enviado` estratti dai file `OTHER`.
- **Calzature ed Ecom Attesi**: Mappati direttamente da `SHOES` ed `ECOM`.
- **Volumi e Pesi**: Somma pesata per categoria merceologica.
- **Spunta Arrivi & Suddivisione Barra 0 / Barra 9**:
  - I negozi con flusso misto (`BARRA 0 / BARRA 9`) vengono suddivisi secondo le regole logistiche operative (70% volume su Barra 0, 30% su Barra 9).
  - Calcolo Pedane automatico: $\lceil \text{Volume} / 1.9 \rceil$.
  - Totale pedane raggruppate per Giro (`ZA1`..`ZA20`).
- **Flussi SGA per TMS**:
  - **Barra 0 (`barrazero_Sga.xlsx`)**: Genera per ogni negozio attivo la coppia di righe:
    - **ANDATA**: Da `MAMONT` (1) a `codSGA` con Peso, Volume e Colli calcolati.
    - **RITORNO**: Dal negozio a `MAMONT` con Peso/Volume/Colli azzerati.
  - **Barra 9 (`barranove_Sga.xlsx`)**: Calcola i colli equivalenti ($\text{Volume} / 0.092$) e peso ($\text{Colli} \times 15$) generando le coppie Andata/Ritorno per i flussi Barra 9.
- **Planning Roma (`PLANNER ROMA _<data>.xlsx`)**: Confronta puntualmente Previsto vs Consegnato (Abbigliamento, Calzature, Altri, Ecom, Intershops).
- **Correzioni Speciali**: Calcolo automatico Sviluppo Stander e Bancali per i negozi 3680, 9226, 3591 (correzione profumi) e split 50/50 Zara Home (1984, 1971).

### 3. File Prodotti in Output
1. `ZARA.xlsx`: Foglio *SPUNTA ARRIVI* pronto all'uso.
2. `barrazero_Sga.xlsx`: Tracciato SGA per i carichi di Barra 0.
3. `barranove_Sga.xlsx`: Tracciato SGA per i carichi di Barra 9.
4. `PLANNER ROMA _<dd-mm-yyyy>.xlsx`: Modello compilato per la distribuzione.

---

## 🚀 Come Utilizzare il Tool

### Modalità 1: Dashboard Web Interattiva (Consigliata)
Avvia la dashboard dal terminale con:
```powershell
streamlit run app.py
```
Si aprirà automaticamente il browser su `http://localhost:8501`. Dalla dashboard puoi:
- Scegliere la data e il ciclo (`GIOV-DOM` o `LUN-MER`).
- Selezionare i dati in 3 modi:
  - **Cartella di rete con 1 click**: legge direttamente da `X:\ZARA - NON TOCCARE\Analisi_ZARA`.
  - **Upload manuale**: carica i file `.xls` o `.xlsx`.
  - **Incolla testo**: incolla direttamente tabelle o testo CSV.
- Cliccare **"ELABORA ORA"** per visualizzare tabelle interattive, grafici e scaricare i 4 file Excel generati.
- Consultare la pagina **"Storico & Trend"** per visualizzare qualsiasi elaborazione passata e scaricare i file storici.

### Modalità 2: Da Riga di Comando (CLI)
Per elaborazioni batch o script automatici:
```powershell
# Esecuzione standard con lettura dalla cartella di rete
python cli.py --run-date 2026-10-22 --cycle GIOV-DOM --input-dir "X:\ZARA - NON TOCCARE\Analisi_ZARA" --save-to-network

# Esecuzione specificando una cartella locale
python cli.py --run-date 2026-10-22 --cycle GIOV-DOM --input-dir ".\reference_data"
```

---

## 🧪 Esecuzione dei Test
Tutti i componenti sono coperti da test automatici:
```powershell
python -m pytest tests/test_engine.py -v
```

---

## 🌐 Automazione Web Extranet Inditex (Fase 2 Completata al 100%)
Il modulo `src/scraper.py` implementa il bot Playwright che automatizza l'intera procedura manuale:
1. Accede ad Extranet Inditex (`https://extranet.inditex.com`) con credenziali sicure.
2. Naviga nel Buzón Plataforma e filtra le spedizioni per intervallo di date.
3. Scarica in automatico:
   - **`TOTAL.xls`** (Tutte le spedizioni)
   - **`SHOES.xls`** (Filtro Centro = Elche)
   - **`ECOM.xls`** (Filtro Cod. spedizione contiene ECOM)
   - **`TEXILE.xls`** (Spedizioni comparto tessile escluso Elche ed Ecom)
   - **`OTHER/*.xls`** (Scansiona ciascuna spedizione tessile aprendo *Entrega*; se rileva *Otros bultos* > 0, scarica il file numerato).
4. Sia dalla dashboard Streamlit (opzione *"🌐 Prelievo Diretto da Extranet Inditex"* o pagina dedicata *"🌐 Automazione Extranet Inditex"*), sia da riga di comando con `python cli.py --from-extranet --desde 2026-10-19 --hasta 2026-10-21`, l'estrazione e i calcoli avvengono con 1 solo click in circa 1 minuto!
