"""
TMS XML Exporter - Standard TrasportoEntrataOrdini_1_00
Genera file XML conformi allo standard BeOne / Nova Systems per flussi di consegna e ritiro.
Ogni negozio servito genera 2 file XML:
  1. Consegna: Dati reali di merce (KG, CL, MC), Carico = Lacchi, Scarico = Negozio.
  2. Ritiro: Dati merce a 0, Carico = Negozio, Scarico = Lacchi, suffisso 'R' su ID e riferimenti.
"""

from datetime import datetime, date
import io
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union
import zipfile
import pandas as pd

from src.config import DB_PATH, OUTPUT_DIR

# Anagrafica Fissa Hub Lacchi
LACCHI_HUB = {
    "codice": 1,
    "ragione_sociale": "LACCHI SPA - MONTEROTONDO",
    "indirizzo": "VIA ERCOLE RAMARINI 11",
    "cap": "00015",
    "localita": "MONTEROTONDO",
    "provincia": "RM",
    "nazione": "IT",
}

# Tabella Province Italiane (mappatura nome -> sigla 2 caratteri)
PROVINCIE_ITALIANE = {
    "ROMA": "RM", "CHIETI": "CH", "TERAMO": "TE", "PERUGIA": "PG",
    "LATINA": "LT", "PESCARA": "PE", "ASCOLI PICENO": "AP",
    "CIVITANOVA MARCHE": "MC", "MACERATA": "MC", "FROSINONE": "FR",
    "RIETI": "RI", "VITERBO": "VT", "L'AQUILA": "AQ", "L AQUILA": "AQ",
    "AQUILA": "AQ", "ANCONA": "AN", "FERMO": "FM", "PESARO": "PU",
    "PESARO E URBINO": "PU", "TERNI": "TR", "CAMPOBASSO": "CB",
    "ISERNIA": "IS", "NAPOLI": "NA", "CASERTA": "CE", "SALERNO": "SA",
    "AVELLINO": "AV", "BENEVENTO": "BN", "BARI": "BA", "FOGGIA": "FG",
    "TARANTO": "TA", "BRINDISI": "BR", "LECCE": "LE", "POTENZA": "PZ",
    "MATERA": "MT", "COSENZA": "CS", "CATANZARO": "CZ", "REGGIO CALABRIA": "RC",
    "FIRENZE": "FI", "AREZZO": "AR", "SIENA": "SI", "GROSSETO": "GR",
    "LIVORNO": "LI", "PISA": "PI", "LUCCA": "LU", "PISTOIA": "PT",
    "PRATO": "PO", "MASSA-CARRARA": "MS", "BOLOGNA": "BO", "MODENA": "MO",
    "REGGIO EMILIA": "RE", "PARMA": "PR", "PIACENZA": "PC", "FERRARA": "FE",
    "RAVENNA": "RA", "FORLI-CESENA": "FC", "RIMINI": "RN", "MILANO": "MI",
    "MONZA E BRIANZA": "MB", "BRESCIA": "BS", "BERGAMO": "BG", "COMO": "CO",
    "VARESE": "VA", "PAVIA": "PV", "CREMONA": "CR", "MANTOVA": "MN",
    "LECCO": "LC", "LODI": "LO", "SONDRIO": "SO", "TORINO": "TO",
    "GENOVA": "GE", "VERONA": "VR", "PADOVA": "PD", "VICENZA": "VI",
    "TREVISO": "TV", "VENEZIA": "VE", "UDINE": "UD", "TRIESTE": "TS",
    "TRENTO": "TN", "BOLZANO": "BZ", "AOSTA": "AO", "PALERMO": "PA",
    "CATANIA": "CT", "MESSINA": "ME", "CAGLIARI": "CA", "SASSARI": "SS",
}


_last_id_flusso_val: int = 0


def generate_unique_id_flusso() -> str:
    """
    Genera un IdFlusso numerico sempre diverso (formato AAAAMMGGOOMMSS, es. dataminutisecondi).
    Se chiamato più volte nello stesso secondo, garantisce l'unicità incrementando progressivamente il valore numerico.
    """
    global _last_id_flusso_val
    now_int = int(datetime.now().strftime("%Y%m%d%H%M%S"))
    if now_int <= _last_id_flusso_val:
        now_int = _last_id_flusso_val + 1
    _last_id_flusso_val = now_int
    return str(now_int)


def parse_store_address(raw_addr: Any, raw_prov: Any) -> Dict[str, str]:
    """
    Estrae Indirizzo, CAP, Localita e Provincia partendo dai campi liberi presenti nel database stores.
    Esempio input: "LOCALITA S. FILOMENA -  66100 - Chieti - MEGALO'", "CHIETI"
    Output: {
        "indirizzo": "Località S. Filomena",
        "cap": "66100",
        "localita": "Chieti Megalò",
        "provincia": "CH",
        "nazione": "IT"
    }
    """
    prov_str = str(raw_prov).strip().upper() if raw_prov and not pd.isna(raw_prov) else ""
    prov_code = PROVINCIE_ITALIANE.get(prov_str, prov_str[:2] if len(prov_str) >= 2 else "RM")

    if not raw_addr or pd.isna(raw_addr):
        return {
            "indirizzo": "",
            "cap": "",
            "localita": "",
            "provincia": prov_code,
            "nazione": "IT",
        }

    s = str(raw_addr).strip()
    match = re.search(r"\b(\d{5})\b", s)
    if match:
        cap = match.group(1)
        before = s[:match.start()].strip(" -,\t")
        after = s[match.end():].strip(" -,\t")
        
        # Pulizia indirizzo (prima del CAP)
        addr = before.strip(" -,\t")
        # Se indirizzo è in maiuscolo, rendilo più leggibile ma preserva sigle come S. o C.C.
        if addr.isupper():
            addr = addr.title().replace("Loc.", "Località").replace("Loc ", "Località ")
        
        # Pulizia localita (dopo il CAP)
        loc_tokens = [t.strip() for t in re.split(r"[-–]", after) if t.strip()]
        loc = " ".join(loc_tokens).strip()
        if loc.isupper():
            loc = loc.title()
    else:
        cap = ""
        addr = s.title() if s.isupper() else s
        loc = ""

    return {
        "indirizzo": addr,
        "cap": cap,
        "localita": loc,
        "provincia": prov_code,
        "nazione": "IT",
    }


def format_store_ragione_sociale(brand: Any, store_name: Any, store_id: Any) -> str:
    """
    Formatta la Ragione Sociale del negozio secondo lo standard BeOne:
    Esempio: 'Stradivarius Megalo - 16647'
    """
    b_str = str(brand).strip().title() if brand and not pd.isna(brand) else ""
    s_raw = str(store_name).strip() if store_name and not pd.isna(store_name) else ""
    sid = str(store_id).strip()

    # Rimuovi prefissi geografici ridondanti (ROM-, PER-, TER-, CHIETI-, etc.)
    s_clean = re.sub(r"^(ROM|PER|TER|CHIETI|PES|ASC|LATI|CITT|MAC|FIUM)-", "", s_raw, flags=re.IGNORECASE)
    s_clean = s_clean.replace("-", " ").strip()
    if s_clean.isupper():
        s_clean = s_clean.title()

    if b_str and s_clean:
        # Evita duplicati tipo "Zara Zara Home"
        if s_clean.lower().startswith(b_str.lower()):
            nome_completo = s_clean
        else:
            nome_completo = f"{b_str} {s_clean}"
    elif b_str:
        nome_completo = b_str
    elif s_clean:
        nome_completo = s_clean
    else:
        nome_completo = f"Negozio {sid}"

    return f"{nome_completo} - {sid}"


def build_tms_order_xml(
    delivery_date: Union[str, date, datetime],
    store_info: Dict[str, Any],
    giro: str,
    stop_sequence: int = 1,
    peso_kg: float = 0.0,
    colli: int = 0,
    volume_mc: float = 0.0,
    is_ritiro: bool = False,
    id_flusso: Optional[str] = None,
    elemento_id: Optional[str] = None,
) -> str:
    """
    Costruisce la stringa XML completa conforme a TrasportoEntrataOrdini_1_00.
    """
    if isinstance(delivery_date, (datetime, date)):
        deliv_dt_str = delivery_date.strftime("%Y-%m-%d")
        dt_compact = delivery_date.strftime("%Y%m%d")
        anno = str(delivery_date.year)
    else:
        deliv_dt_str = str(delivery_date)[:10]
        dt_compact = deliv_dt_str.replace("-", "")
        anno = deliv_dt_str[:4]

    if not id_flusso:
        id_flusso = generate_unique_id_flusso()

    giro_clean = str(giro).strip().upper()
    ref_base = f"{giro_clean}-{stop_sequence}"
    order_ref = f"{ref_base}R" if is_ritiro else ref_base

    cod_sga = int(store_info.get("cod_sga", 0))

    if not elemento_id:
        if is_ritiro:
            elemento_id = f"{id_flusso}R"
        else:
            elemento_id = str(id_flusso)

    # Dati merce
    if is_ritiro:
        val_kg = "0.000"
        val_cl = "0"
        val_mc = "0.000"
    else:
        val_kg = f"{float(peso_kg):.3f}"
        val_cl = f"{int(round(colli))}"
        val_mc = f"{float(volume_mc):.3f}"

    store_rs = store_info.get("ragione_sociale", "")
    store_addr = store_info.get("indirizzo", "")
    store_cap = store_info.get("cap", "")
    store_loc = store_info.get("localita", "")
    store_prv = store_info.get("provincia", "RM")
    store_naz = store_info.get("nazione", "IT")

    # Inversione Mittente / Destinatario:
    # CONSEGNA: Carico = Lacchi, Scarico = Negozio
    # RITIRO: Carico = Negozio, Scarico = Lacchi
    if not is_ritiro:
        mittente_cod = str(LACCHI_HUB["codice"])
        mittente_rs = LACCHI_HUB["ragione_sociale"]
        mittente_addr = LACCHI_HUB["indirizzo"]
        mittente_cap = LACCHI_HUB["cap"]
        mittente_loc = LACCHI_HUB["localita"]
        mittente_prv = LACCHI_HUB["provincia"]
        mittente_naz = LACCHI_HUB["nazione"]

        dest_cod = str(cod_sga)
        dest_rs = store_rs
        dest_addr = store_addr
        dest_cap = store_cap
        dest_loc = store_loc
        dest_prv = store_prv
        dest_naz = store_naz
    else:
        mittente_cod = str(cod_sga)
        mittente_rs = store_rs
        mittente_addr = store_addr
        mittente_cap = store_cap
        mittente_loc = store_loc
        mittente_prv = store_prv
        mittente_naz = store_naz

        dest_cod = str(LACCHI_HUB["codice"])
        dest_rs = LACCHI_HUB["ragione_sociale"]
        dest_addr = LACCHI_HUB["indirizzo"]
        dest_cap = LACCHI_HUB["cap"]
        dest_loc = LACCHI_HUB["localita"]
        dest_prv = LACCHI_HUB["provincia"]
        dest_naz = LACCHI_HUB["nazione"]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<TrasportoEntrataOrdini_1_00>',
        f'  <IdFlusso>{id_flusso}</IdFlusso>',
        '  <Ordini>',
        '    <Ordine>',
        f'      <Anno>{anno}</Anno>',
        '      <Filiale>SE</Filiale>',
        f'      <ElementoId>{elemento_id}</ElementoId>',
        '      <Azione>Insert</Azione>',
        '      <Raggruppamento>',
        f'        <Id>{elemento_id}</Id>',
        f'        <Data>{deliv_dt_str}</Data>',
        '      </Raggruppamento>',
        '      <Cliente>1</Cliente>',
        f'      <OrdineRiferimento>{order_ref}</OrdineRiferimento>',
        f'      <RiferimentoInterno>{order_ref}</RiferimentoInterno>',
        '      <Descrizione/>',
        '      <TipoServizio>DI</TipoServizio>',
        '      <TipoSpecifica/>',
        '      <TipoMotriceTrattore/>',
        '      <TipoRimorchioSemirimorchio/>',
        '      <Priorita/>',
        '      <Classificazione/>',
        '      <Linea/>',
        '      <Resa/>',
        '      <NoteDisponente/>',
        '      <NoteConfermaCarico/>',
        '      <NoteFattura/>',
        '      <Caratteristiche/>',
        '      <Proprieta/>',
        '      <CarichiScarichi>',
        '        <CaricoScarico>',
        f'          <CaricoData>{deliv_dt_str}</CaricoData>',
        '          <CaricoDataFine/>',
        '          <CaricoTipoOra>N</CaricoTipoOra>',
        '          <CaricoOreMinuti/>',
        '          <CaricoOreMinutiFine/>',
        '          <CaricoTassativo>N</CaricoTassativo>',
        '          <CaricoDati>C</CaricoDati>',
        f'          <CaricoMittenteCodice>{mittente_cod}</CaricoMittenteCodice>',
        '          <CaricoMittenteInformazioniAnagrafiche>',
        f'            <RagioneSociale>{mittente_rs}</RagioneSociale>',
        f'            <Indirizzo>{mittente_addr}</Indirizzo>',
        f'            <Cap>{mittente_cap}</Cap>',
        f'            <Localita>{mittente_loc}</Localita>',
        f'            <Provincia>{mittente_prv}</Provincia>',
        f'            <Nazione>{mittente_naz}</Nazione>',
        '          </CaricoMittenteInformazioniAnagrafiche>',
        '          <CaricoProvenienzaInformazioniAnagrafiche>',
        '            <RagioneSociale/>',
        '            <Indirizzo/>',
        '            <Cap/>',
        '            <Localita/>',
        '            <Provincia/>',
        '            <Nazione/>',
        '          </CaricoProvenienzaInformazioniAnagrafiche>',
        '          <CaricoMagazzino/>',
        '          <CaricoTerminal/>',
        '          <CaricoSequenza/>',
        '          <CaricoNote/>',
        '          <CaricoPreavviso>N</CaricoPreavviso>',
        f'          <ScaricoData>{deliv_dt_str}</ScaricoData>',
        '          <ScaricoDataFine/>',
        '          <ScaricoTipoOra>N</ScaricoTipoOra>',
        '          <ScaricoOreMinuti/>',
        '          <ScaricoOreMinutiFine/>',
        '          <ScaricoDati>C</ScaricoDati>',
        f'          <ScaricoDestinatarioCodice>{dest_cod}</ScaricoDestinatarioCodice>',
        '          <ScaricoDestinatarioInformazioniAnagrafiche>',
        f'            <RagioneSociale>{dest_rs}</RagioneSociale>',
        f'            <Indirizzo>{dest_addr}</Indirizzo>',
        f'            <Cap>{dest_cap}</Cap>',
        f'            <Localita>{dest_loc}</Localita>',
        f'            <Provincia>{dest_prv}</Provincia>',
        f'            <Nazione>{dest_naz}</Nazione>',
        '          </ScaricoDestinatarioInformazioniAnagrafiche>',
        '          <ScaricoDestinazioneInformazioniAnagrafiche>',
        f'            <RagioneSociale>{dest_rs}</RagioneSociale>',
        f'            <Indirizzo>{dest_addr}</Indirizzo>',
        f'            <Cap>{dest_cap}</Cap>',
        f'            <Localita>{dest_loc}</Localita>',
        f'            <Provincia>{dest_prv}</Provincia>',
        f'            <Nazione>{dest_naz}</Nazione>',
        '          </ScaricoDestinazioneInformazioniAnagrafiche>',
        '          <ScaricoMagazzino/>',
        '          <ScaricoTerminal/>',
        '          <ScaricoIncompleti/>',
        '          <ScaricoSequenza/>',
        '          <DeterminazioneInstradamentoDaRegole>N</DeterminazioneInstradamentoDaRegole>',
        '          <ScaricoNote/>',
        '          <ScaricoPreavviso>N</ScaricoPreavviso>',
        '          <NoteFattura/>',
        '          <Merci>',
        '            <Merce>',
        '              <Codice>VAR</Codice>',
        '              <Descrizione>MATERIALE VARIO</Descrizione>',
        '              <Um1Codice>KG</Um1Codice>',
        f'              <Um1Valore>{val_kg}</Um1Valore>',
        '              <Um2Codice>CL</Um2Codice>',
        f'              <Um2Valore>{val_cl}</Um2Valore>',
        '              <Um3Codice>MC</Um3Codice>',
        f'              <Um3Valore>{val_mc}</Um3Valore>',
        '              <Riferimento/>',
        '              <UmDimensioni/>',
        '            </Merce>',
        '          </Merci>',
        '          <Documenti/>',
        '          <Caratteristiche/>',
        '          <SegnaColli/>',
        '          <Riferimenti/>',
        '          <Proprieta/>',
        '        </CaricoScarico>',
        '      </CarichiScarichi>',
        '    </Ordine>',
        '  </Ordini>',
        '</TrasportoEntrataOrdini_1_00>',
    ]
    return "\n".join(xml_lines)


def get_stores_lookup(db_path: Union[str, Path] = DB_PATH) -> Dict[str, Dict[str, Any]]:
    """
    Carica i dati anagrafici dei negozi dal database SQLite e restituisce
    un dizionario indicizzato per store_id con dati parsed.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT store_id, brand, store_name, cod_sga, giro, indirizzo, provincia FROM stores")
    rows = cur.fetchall()
    conn.close()

    lookup = {}
    for r in rows:
        sid = str(r["store_id"]).strip()
        parsed_addr = parse_store_address(r["indirizzo"], r["provincia"])
        rs = format_store_ragione_sociale(r["brand"], r["store_name"], sid)

        cod_sga = r["cod_sga"]
        if pd.isna(cod_sga) or cod_sga is None:
            base_sid = sid[:-1] if sid.endswith("B") else sid
            cod_sga = int(base_sid) if base_sid.isdigit() else 0
        else:
            cod_sga = int(cod_sga)

        lookup[sid] = {
            "store_id": sid,
            "brand": r["brand"],
            "store_name": r["store_name"],
            "cod_sga": cod_sga,
            "giro": r["giro"],
            "ragione_sociale": rs,
            "indirizzo": parsed_addr["indirizzo"],
            "cap": parsed_addr["cap"],
            "localita": parsed_addr["localita"],
            "provincia": parsed_addr["provincia"],
            "nazione": parsed_addr["nazione"],
        }
    return lookup


def generate_tms_xml_files(
    records: List[Dict[str, Any]],
    output_dir: Optional[Union[str, Path]] = None,
    zip_filename: Optional[str] = None,
    db_path: Union[str, Path] = DB_PATH,
) -> Tuple[List[Path], Path]:
    """
    Genera i 2 file XML (consegna e ritiro) per ciascun record specificato.
    Ciascun record in `records` deve contenere:
      - store_id: str
      - giro: str
      - delivery_date: str (YYYY-MM-DD o DD/MM/YYYY)
      - colli: float/int
      - volume_mc: float
      - peso_kg: float
      - (opzionale) stop_sequence: int
    Salva i file XML nella cartella `output_dir` e crea un archivio ZIP contenente tutti i file.
    Restituisce (lista_file_xml, percorso_zip).
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / f"tms_xml_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stores_lookup = get_stores_lookup(db_path)

    # Raggruppa o ordina per giro per calcolare la corretta sequenza di fermata
    # Manteniamo un contatore di stop per ciascun (giro, delivery_date)
    giro_stop_counters: Dict[Tuple[str, str], int] = {}
    
    generated_xml_files: List[Path] = []

    for rec in records:
        sid = str(rec.get("store_id") or rec.get("store_code") or "").strip()
        giro = str(rec.get("giro") or "").strip().upper()
        if not sid or not giro or giro in ("DA ASSEGNARE", "NON ASSEGNATO", "NONE", "NAN", "-"):
            continue

        deliv_date_raw = rec.get("delivery_date") or rec.get("data_consegna") or rec.get("data_scarico") or datetime.now().strftime("%Y-%m-%d")
        deliv_date_str = str(deliv_date_raw).strip()
        # Gestione data in formato DD/MM/YYYY -> YYYY-MM-DD
        if "/" in deliv_date_str:
            parts = deliv_date_str.split("/")
            if len(parts) == 3 and len(parts[2]) == 4:
                deliv_date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
        deliv_date_str = deliv_date_str[:10]
        dt_compact = deliv_date_str.replace("-", "")

        giro_key = (giro, deliv_date_str)
        if "stop_sequence" in rec and rec["stop_sequence"]:
            stop_seq = int(rec["stop_sequence"])
        else:
            current_count = giro_stop_counters.get(giro_key, 0) + 1
            giro_stop_counters[giro_key] = current_count
            stop_seq = current_count

        # Anagrafica store
        st_info = stores_lookup.get(sid)
        if not st_info:
            # Fallback se non censito in stores
            base_sid = sid[:-1] if sid.endswith("B") else sid
            cod_sga_fb = int(base_sid) if base_sid.isdigit() else 0
            st_info = {
                "store_id": sid,
                "brand": "INDITEX",
                "store_name": f"NEGOZIO {sid}",
                "cod_sga": cod_sga_fb,
                "giro": giro,
                "ragione_sociale": f"Inditex Store - {sid}",
                "indirizzo": "",
                "cap": "00015",
                "localita": "Roma",
                "provincia": "RM",
                "nazione": "IT",
            }

        colli = int(round(float(rec.get("colli") or 0)))
        mc = float(rec.get("volume_mc") or rec.get("volume") or rec.get("mc") or 0.0)
        peso = float(rec.get("peso_kg") or rec.get("peso") or 0.0)
        if peso <= 0 and colli > 0:
            peso = colli * 15.0  # Fallback peso collo medio

        # 1. FILE CONSEGNA
        id_flusso_c = generate_unique_id_flusso()
        xml_consegna = build_tms_order_xml(
            delivery_date=deliv_date_str,
            store_info=st_info,
            giro=giro,
            stop_sequence=stop_seq,
            peso_kg=peso,
            colli=colli,
            volume_mc=mc,
            is_ritiro=False,
            id_flusso=id_flusso_c,
            elemento_id=id_flusso_c,
        )
        fn_consegna = f"{deliv_date_str}_{giro}_{sid}_CONSEGNA.xml"
        path_consegna = output_dir / fn_consegna
        if path_consegna.exists():
            fn_consegna = f"{deliv_date_str}_{giro}_{sid}_{stop_seq}_CONSEGNA.xml"
            path_consegna = output_dir / fn_consegna
        path_consegna.write_text(xml_consegna, encoding="utf-8")
        generated_xml_files.append(path_consegna)

        # 2. FILE RITIRO
        id_flusso_r = generate_unique_id_flusso()
        xml_ritiro = build_tms_order_xml(
            delivery_date=deliv_date_str,
            store_info=st_info,
            giro=giro,
            stop_sequence=stop_seq,
            peso_kg=0.0,
            colli=0,
            volume_mc=0.0,
            is_ritiro=True,
            id_flusso=id_flusso_r,
            elemento_id=f"{id_flusso_r}R",
        )
        fn_ritiro = f"{deliv_date_str}_{giro}_{sid}_RITIRO.xml"
        path_ritiro = output_dir / fn_ritiro
        if path_ritiro.exists():
            fn_ritiro = f"{deliv_date_str}_{giro}_{sid}_{stop_seq}_RITIRO.xml"
            path_ritiro = output_dir / fn_ritiro
        path_ritiro.write_text(xml_ritiro, encoding="utf-8")
        generated_xml_files.append(path_ritiro)

    # Creazione Archivio ZIP
    if not zip_filename:
        first_dt = records[0].get("delivery_date", datetime.now().strftime("%Y-%m-%d")) if records else datetime.now().strftime("%Y-%m-%d")
        clean_dt = re.sub(r"[^0-9]", "", str(first_dt)[:10])
        zip_filename = f"TMS_XML_Ordini_{clean_dt}.zip"

    zip_path = output_dir / zip_filename
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in generated_xml_files:
            zf.write(f, arcname=f.name)

    return generated_xml_files, zip_path


def create_tms_xml_zip_bytes(records: List[Dict[str, Any]], db_path: Union[str, Path] = DB_PATH) -> bytes:
    """
    Genera tutti i file XML di consegna e ritiro direttamente in memoria e restituisce
    il contenuto dell'archivio ZIP in formato bytes, ideale per Streamlit download button.
    """
    stores_lookup = get_stores_lookup(db_path)
    giro_stop_counters: Dict[Tuple[str, str], int] = {}
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for rec in records:
            sid = str(rec.get("store_id") or rec.get("store_code") or "").strip()
            giro = str(rec.get("giro") or "").strip().upper()
            if not sid or not giro or giro in ("DA ASSEGNARE", "NON ASSEGNATO", "NONE", "NAN", "-"):
                continue

            deliv_date_raw = rec.get("delivery_date") or rec.get("data_consegna") or rec.get("data_scarico") or datetime.now().strftime("%Y-%m-%d")
            deliv_date_str = str(deliv_date_raw).strip()
            if "/" in deliv_date_str:
                parts = deliv_date_str.split("/")
                if len(parts) == 3 and len(parts[2]) == 4:
                    deliv_date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
            deliv_date_str = deliv_date_str[:10]

            giro_key = (giro, deliv_date_str)
            if "stop_sequence" in rec and rec["stop_sequence"]:
                stop_seq = int(rec["stop_sequence"])
            else:
                current_count = giro_stop_counters.get(giro_key, 0) + 1
                giro_stop_counters[giro_key] = current_count
                stop_seq = current_count

            st_info = stores_lookup.get(sid)
            if not st_info:
                base_sid = sid[:-1] if sid.endswith("B") else sid
                cod_sga_fb = int(base_sid) if base_sid.isdigit() else 0
                st_info = {
                    "store_id": sid,
                    "brand": "INDITEX",
                    "store_name": f"NEGOZIO {sid}",
                    "cod_sga": cod_sga_fb,
                    "giro": giro,
                    "ragione_sociale": f"Inditex Store - {sid}",
                    "indirizzo": "",
                    "cap": "00015",
                    "localita": "Roma",
                    "provincia": "RM",
                    "nazione": "IT",
                }

            colli = int(round(float(rec.get("colli") or 0)))
            mc = float(rec.get("volume_mc") or rec.get("volume") or rec.get("mc") or 0.0)
            peso = float(rec.get("peso_kg") or rec.get("peso") or 0.0)
            if peso <= 0 and colli > 0:
                peso = colli * 15.0

            # Consegna
            id_flusso_c = generate_unique_id_flusso()
            xml_consegna = build_tms_order_xml(
                delivery_date=deliv_date_str,
                store_info=st_info,
                giro=giro,
                stop_sequence=stop_seq,
                peso_kg=peso,
                colli=colli,
                volume_mc=mc,
                is_ritiro=False,
                id_flusso=id_flusso_c,
                elemento_id=id_flusso_c,
            )
            arc_c = f"{deliv_date_str}_{giro}_{sid}_CONSEGNA.xml"
            if arc_c in zf.namelist():
                arc_c = f"{deliv_date_str}_{giro}_{sid}_{stop_seq}_CONSEGNA.xml"
            zf.writestr(arc_c, xml_consegna.encode("utf-8"))

            # Ritiro
            id_flusso_r = generate_unique_id_flusso()
            xml_ritiro = build_tms_order_xml(
                delivery_date=deliv_date_str,
                store_info=st_info,
                giro=giro,
                stop_sequence=stop_seq,
                peso_kg=0.0,
                colli=0,
                volume_mc=0.0,
                is_ritiro=True,
                id_flusso=id_flusso_r,
                elemento_id=f"{id_flusso_r}R",
            )
            arc_r = f"{deliv_date_str}_{giro}_{sid}_RITIRO.xml"
            if arc_r in zf.namelist():
                arc_r = f"{deliv_date_str}_{giro}_{sid}_{stop_seq}_RITIRO.xml"
            zf.writestr(arc_r, xml_ritiro.encode("utf-8"))

    return zip_buffer.getvalue()


def generate_tms_xml_from_bolle(
    delivery_date: str,
    output_dir: Optional[Union[str, Path]] = None,
    db_path: Union[str, Path] = DB_PATH,
) -> Tuple[List[Path], Path]:
    """
    Estrae le bolle registrate per una specifica data di consegna (o per entrambe le date di un ciclo)
    e genera tutti i file XML Consegna + Ritiro e relativo archivio ZIP.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, b.data_consegna, b.data, b.id_store, b.tipo_cons,
               b.colli_abbigl, b.colli_calzat, b.colli_ecom, b.colli_others, b.colli_vario, b.colli_cont, b.colli_mat_vario,
               b.prev_totale,
               s.giro, s.cod_sga, s.brand, s.store_name
        FROM bolle b
        LEFT JOIN stores s ON b.id_store = s.store_id
        WHERE b.data_consegna = ? OR b.data = ?
        ORDER BY s.giro ASC, b.id_store ASC
    """, (delivery_date, delivery_date))
    rows = cur.fetchall()
    conn.close()

    records = []
    for r in rows:
        tot_c = (
            (r["colli_abbigl"] or 0) + (r["colli_calzat"] or 0) + (r["colli_ecom"] or 0) +
            (r["colli_others"] or 0) + (r["colli_vario"] or 0) + (r["colli_cont"] or 0) +
            (r["colli_mat_vario"] or 0)
        )
        if tot_c <= 0:
            tot_c = int(round(float(r["prev_totale"] or 0)))

        # Volume e Peso
        mc = tot_c * 0.105 if tot_c > 0 else 0.0
        peso = tot_c * 15.0 if tot_c > 0 else 0.0

        records.append({
            "store_id": str(r["id_store"]),
            "giro": str(r["giro"] or "ZA1"),
            "delivery_date": str(r["data_consegna"] or r["data"] or delivery_date)[:10],
            "colli": tot_c,
            "volume_mc": mc,
            "peso_kg": peso,
        })

    return generate_tms_xml_files(records, output_dir=output_dir, db_path=db_path)


def generate_tms_xml_from_run(
    run_id: str,
    output_dir: Optional[Union[str, Path]] = None,
    db_path: Union[str, Path] = DB_PATH,
) -> Tuple[List[Path], Path]:
    """
    Estrae i flussi dell'operativa (da sga_flows o spunta_arrivi) per il run_id indicato
    e genera i file XML Consegna + Ritiro per tutti i negozi.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Prendi i flussi di ANDATA da sga_flows
    cur.execute("""
        SELECT store_code, giro, data_scarico, peso, volume, colli
        FROM sga_flows
        WHERE run_id = ? AND UPPER(flusso_tipo) = 'ANDATA'
        ORDER BY giro ASC, store_code ASC
    """, (run_id,))
    rows = cur.fetchall()
    conn.close()

    records = []
    for r in rows:
        records.append({
            "store_id": str(r["store_code"]),
            "giro": str(r["giro"]),
            "delivery_date": str(r["data_scarico"]),
            "colli": int(round(float(r["colli"] or 0))),
            "volume_mc": float(r["volume"] or 0.0),
            "peso_kg": float(r["peso"] or 0.0),
        })

    return generate_tms_xml_files(records, output_dir=output_dir, db_path=db_path)
