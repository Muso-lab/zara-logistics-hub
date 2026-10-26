import sqlite3
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
from src.config import DB_PATH, ANAGRAFICA_FILE


def get_connection(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA journal_mode = DELETE;")
    except Exception:
        pass
    return conn


def init_db(db_path=DB_PATH):
    """Initializes the database schema."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Stores Master Data
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            store_id TEXT PRIMARY KEY,
            store_name TEXT NOT NULL,
            punto_vendita TEXT,
            brand TEXT,
            giro TEXT,
            cod_sga INTEGER,
            cc TEXT,
            attivo TEXT DEFAULT 'SI',
            barra TEXT DEFAULT 'BARRA 0',
            stender TEXT DEFAULT 'NO',
            formula TEXT,
            ff TEXT,
            lavorazione TEXT DEFAULT 'NO',
            sdoppiamento_b9 TEXT DEFAULT 'NO'
        );
        """)

        # Migration check for existing databases
        cursor.execute("PRAGMA table_info(stores)")
        existing_cols = [c[1] for c in cursor.fetchall()]
        if "lavorazione" not in existing_cols:
            cursor.execute("ALTER TABLE stores ADD COLUMN lavorazione TEXT DEFAULT 'NO'")
        if "sdoppiamento_b9" not in existing_cols:
            cursor.execute("ALTER TABLE stores ADD COLUMN sdoppiamento_b9 TEXT DEFAULT 'NO'")
        for col_name, col_type in [
            ("autista", "TEXT"),
            ("cell_autista", "TEXT"),
            ("tipo_mezzo", "TEXT"),
            ("vettore", "TEXT DEFAULT 'LACCHI SPA'"),
            ("indirizzo", "TEXT"),
            ("provincia", "TEXT"),
            ("autista_doppia", "TEXT DEFAULT ''"),
            ("tipo_mezzo_doppia", "TEXT DEFAULT ''"),
            ("scorporo_profumi", "TEXT DEFAULT 'NO'"),
            ("pezzi_profumi", "INTEGER DEFAULT 0"),
        ]:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE stores ADD COLUMN {col_name} {col_type}")

        # Ensure default special stores setup
        cursor.execute("UPDATE stores SET lavorazione = 'SI TESSILE' WHERE store_id IN ('3680', '9226', '3591') AND (lavorazione IS NULL OR lavorazione = 'NO')")
        cursor.execute("UPDATE stores SET lavorazione = 'SI HOME' WHERE store_id IN ('1984', '1971') AND (lavorazione IS NULL OR lavorazione = 'NO')")
        cursor.execute("UPDATE stores SET sdoppiamento_b9 = 'SI' WHERE store_id IN ('14010', '14825', '16723', '1984', '3503', '3680', '5349', '5367', '6525', '8428', '14010B', '14825B', '16723B', '1984B', '3503B', '3680B', '5349B', '5367B', '6525B', '8428B') AND (sdoppiamento_b9 IS NULL OR sdoppiamento_b9 = 'NO')")
        cursor.execute("UPDATE stores SET scorporo_profumi = 'SI' WHERE store_id IN ('3680', '9226', '3591') AND (scorporo_profumi IS NULL OR scorporo_profumi = 'NO')")
        cursor.execute("UPDATE stores SET pezzi_profumi = 0 WHERE pezzi_profumi IS NULL OR pezzi_profumi > 0")

        # Execution Runs / Batches (Weekly / Cycle runs)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            cycle_type TEXT NOT NULL, -- 'LUN-MER' or 'GIOV-DOM'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'COMPLETED',
            notes TEXT,
            total_bultos REAL DEFAULT 0,
            total_volume REAL DEFAULT 0,
            total_weight REAL DEFAULT 0,
            total_pedane INTEGER DEFAULT 0
        );
        """)

        # Raw Forecast Items (TOTAL, SHOES, TEXILE, ECOM)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS forecast_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            file_category TEXT NOT NULL, -- 'TOTAL', 'SHOES', 'TEXILE', 'ECOM'
            store_code TEXT NOT NULL,
            raw_tienda TEXT,
            p_colgada REAL DEFAULT 0,
            paqueteria REAL DEFAULT 0,
            peso REAL DEFAULT 0,
            volumen REAL DEFAULT 0,
            bultos REAL DEFAULT 0,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """)

        # Raw Other Items (from OTHER/*.xls)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS other_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            file_name TEXT,
            raw_tienda TEXT,
            store_code TEXT NOT NULL,
            confirm TEXT,
            bultos REAL DEFAULT 0,
            otros_bultos_enviado REAL DEFAULT 0,
            otros_bultos_entrega REAL DEFAULT 0,
            otros_bultos_diferen REAL DEFAULT 0,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """)

        # Actual Received Deliveries (from esportazione.xlsx / Access)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS actual_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            store_code TEXT NOT NULL,
            tipo_cons TEXT DEFAULT 'STD', -- 'STD' or 'DOPPIA'
            tot_abbigl REAL DEFAULT 0,
            tot_calzat REAL DEFAULT 0,
            tot_ecom REAL DEFAULT 0,
            tot_others REAL DEFAULT 0,
            tot_vario REAL DEFAULT 0,
            tot_cont REAL DEFAULT 0,
            colli_mat_vario REAL DEFAULT 0,
            stringa TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """)

        # Calculated Planning Summary
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS planning_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            store_code TEXT NOT NULL,
            brand TEXT,
            store_name TEXT,
            giro TEXT,
            planned_textile REAL DEFAULT 0,
            received_textile REAL DEFAULT 0,
            planned_others REAL DEFAULT 0,
            received_others REAL DEFAULT 0,
            vol_textile REAL DEFAULT 0,
            weight_textile REAL DEFAULT 0,
            planned_shoes REAL DEFAULT 0,
            received_shoes REAL DEFAULT 0,
            vol_shoes REAL DEFAULT 0,
            weight_shoes REAL DEFAULT 0,
            planned_ecom REAL DEFAULT 0,
            received_ecom REAL DEFAULT 0,
            vol_ecom REAL DEFAULT 0,
            weight_ecom REAL DEFAULT 0,
            total_vol REAL DEFAULT 0,
            total_weight REAL DEFAULT 0,
            total_planned_crts REAL DEFAULT 0,
            total_received_crts REAL DEFAULT 0,
            intershops TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """)

        # Spunta Arrivi Output Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS spunta_arrivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            row_idx INTEGER NOT NULL,
            store_code TEXT,
            store_name TEXT,
            punto_vendita TEXT,
            brand TEXT,
            mc REAL DEFAULT 0,
            textile_attesi REAL DEFAULT 0,
            other_attesi REAL DEFAULT 0,
            shoes_attesi REAL DEFAULT 0,
            ecom_attesi REAL DEFAULT 0,
            pedane INTEGER DEFAULT 0,
            totale_pedane REAL DEFAULT 0,
            vettore_autista TEXT,
            tipo_mezzo TEXT,
            targa TEXT,
            cod_mezzo TEXT,
            supporto TEXT,
            giro TEXT,
            is_barra9 INTEGER DEFAULT 0,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """)

        # Generated SGA Flows (Barra 0 and Barra 9)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sga_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            barra INTEGER NOT NULL, -- 0 or 9
            flusso_tipo TEXT NOT NULL, -- 'ANDATA' or 'RITORNO'
            giro TEXT,
            data_carico TEXT,
            cod_mittente INTEGER,
            magazzino_carico TEXT,
            data_scarico TEXT,
            cod_destinatario INTEGER,
            magazzino_scarico TEXT,
            peso REAL DEFAULT 0,
            volume REAL DEFAULT 0,
            colli REAL DEFAULT 0,
            store_code TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        """)

        # Native Bolle & Delivery Profiles Tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bolle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            access_id INTEGER UNIQUE,
            data TEXT NOT NULL,
            data_consegna TEXT,
            id_store TEXT NOT NULL,
            punto_vendita TEXT,
            store_name TEXT,
            tipo_cons TEXT DEFAULT 'STD',
            vettore TEXT,
            cell_autista TEXT,
            autista TEXT,
            tipo_mezzo TEXT,
            indirizzo_destino TEXT,
            colli_abbigl REAL DEFAULT 0,
            colli_calzat REAL DEFAULT 0,
            colli_ecom REAL DEFAULT 0,
            colli_others REAL DEFAULT 0,
            colli_vario REAL DEFAULT 0,
            colli_cont REAL DEFAULT 0,
            colli_mat_vario REAL DEFAULT 0,
            colli_dann REAL DEFAULT 0,
            colli_non_conf REAL DEFAULT 0,
            anomalie_scarico TEXT,
            intershops_json TEXT,
            stringa TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bolle_data ON bolle(data);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bolle_datac ON bolle(data_consegna);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bolle_store ON bolle(id_store);")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS store_delivery_profiles (
            id_store TEXT NOT NULL,
            tipo_cons TEXT NOT NULL DEFAULT 'STD',
            punto_vendita TEXT,
            store_name TEXT,
            provincia TEXT,
            tipo_mezzo TEXT,
            autista TEXT,
            indirizzo TEXT,
            PRIMARY KEY (id_store, tipo_cons)
        );
        """)


        # Fleet Registry (Anagrafica Mezzi & Capienze)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            cod_mezzo TEXT PRIMARY KEY,
            tipo_mezzo TEXT NOT NULL,
            descrizione TEXT,
            capienza_pedane INTEGER NOT NULL DEFAULT 18,
            attivo TEXT DEFAULT 'SI',
            note TEXT
        );
        """)

        # Application Key-Value Settings (Email, System configs)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Blacklist of deleted stores to prevent automatic recreation on new commitments
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS deleted_stores (
            store_id TEXT PRIMARY KEY,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("SELECT COUNT(*) FROM vehicles")
        if cursor.fetchone()[0] == 0:
            default_vehicles = [
                ("FURGONE 8", "FURGONE", "Furgone Passo Lungo (8 Pedane)", 8, "SI", "Urbano agile"),
                ("EUROCARGO 75", "EUROCARGO", "Iveco Eurocargo 75 (14 Pedane)", 14, "SI", "Medio raggio"),
                ("MOTRICE 14", "MOTRICE", "Motrice Media 14 Pedane", 14, "SI", "Standard 14 plt"),
                ("MOTRICE 18 PLT", "MOTRICE", "Motrice Pesante 18 Pedane", 18, "SI", "Flotta principale Roma"),
                ("MOTRICE 14x3", "MOTRICE", "Tris Motrici 14 (3x14 = 42 Pedane)", 42, "SI", "Servizio multiplo"),
                ("BILICO 33", "BILICO", "Bilico Standard 13.60m (33 Pedane)", 33, "SI", "Lunga percorrenza e grande carico"),
                ("BILICO x 3", "BILICO", "Tris Bilici Standard (3x33 = 99 Pedane)", 99, "SI", "Navetta polo"),
            ]
            cursor.executemany("""
            INSERT INTO vehicles (cod_mezzo, tipo_mezzo, descrizione, capienza_pedane, attivo, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """, default_vehicles)

        conn.commit()


def seed_anagrafica_if_empty(db_path=DB_PATH, anagrafica_file=ANAGRAFICA_FILE):
    """Loads anagrafica_negozi.xlsx into the database if stores table is empty."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stores")
        count = cursor.fetchone()[0]
        if count == 0 and anagrafica_file.exists():
            df = pd.read_excel(anagrafica_file)
            for _, r in df.iterrows():
                sid = str(r["STORE_ID"]).strip()
                # Determine lavorazione
                if sid in ["3680", "9226", "3591"]:
                    lav = "SI TESSILE"
                elif sid in ["1984", "1971"]:
                    lav = "SI HOME"
                else:
                    lav = "NO"
                # Determine sdoppiamento_b9
                if sid in ["14010", "14825", "16723", "1984", "3503", "3680", "5349", "5367", "6525", "8428"] or sid.endswith("B"):
                    sdop = "SI"
                else:
                    sdop = "NO"

                cursor.execute("""
                INSERT OR REPLACE INTO stores (
                    store_id, store_name, punto_vendita, brand, giro, cod_sga, cc, attivo, barra, stender, formula, ff, lavorazione, sdoppiamento_b9
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sid,
                    str(r.get("STORE", "")),
                    str(r.get("PUNTO_VENDITA", "")),
                    str(r.get("PUNTO_VENDITA", "")),
                    str(r.get("RAGG", "")),
                    int(r.get("codSGA", 0)) if pd.notna(r.get("codSGA")) else None,
                    str(r.get("CC", "")),
                    str(r.get("ATTIVO", "SI")),
                    str(r.get("BARRA", "BARRA 0")),
                    str(r.get("STENDER", "NO")),
                    str(r.get("FORMULA", "")),
                    str(r.get("ff", "")),
                    lav,
                    sdop
                ))
            conn.commit()
        sync_double_service_stores(db_path)


B9_STORES_DEFAULTS = {
    "3503B": {"base": "3503", "giro": "ZA17", "tipo_mezzo": "MOTRICE 14", "vettore": "CONSORZIO ORIENTA"},
    "3680B": {"base": "3680", "giro": "ZA15", "tipo_mezzo": "BILICO 33", "vettore": "LA CELESSICA"},
    "5349B": {"base": "5349", "giro": "ZA16", "tipo_mezzo": "FURGONE 8", "vettore": "LACCHI SPA"},
    "5367B": {"base": "5367", "giro": "ZA15", "tipo_mezzo": "BILICO 33", "vettore": "LA CELESSICA"},
    "6525B": {"base": "6525", "giro": "ZA18", "tipo_mezzo": "EUROCARGO 75", "vettore": "LACCHI SPA"},
    "8428B": {"base": "8428", "giro": "ZA16", "tipo_mezzo": "FURGONE 8", "vettore": "LACCHI SPA"},
    "14010B": {"base": "14010", "giro": "ZA19", "tipo_mezzo": "FURGONE 8", "vettore": "CONSORZIO ORIENTA"},
    "14825B": {"base": "14825", "giro": "ZA15", "tipo_mezzo": "BILICO 33", "vettore": "LA CELESSICA"},
    "16723B": {"base": "16723", "giro": "ZA18", "tipo_mezzo": "EUROCARGO 75", "vettore": "LACCHI SPA"},
    "1984B": {"base": "1984", "giro": "ZA19", "tipo_mezzo": "FURGONE 8", "vettore": "CONSORZIO ORIENTA"},
}


def sync_double_service_stores(db_path=DB_PATH):
    """
    Ensures that for every store with sdoppiamento_b9 == 'SI',
    a corresponding distinct 'B' record (e.g. 3503B) exists in the stores table
    with its own independent Giro, Vettore, and Tipo Mezzo for the Day B (/9) delivery.
    """
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stores WHERE sdoppiamento_b9 = 'SI' AND NOT store_id LIKE '%B'")
            cols = [col[0] for col in cursor.description]
            base_stores = [dict(zip(cols, row)) for row in cursor.fetchall()]

            for base in base_stores:
                base_id = str(base["store_id"]).strip()
                b_id = f"{base_id}B"
                defaults = B9_STORES_DEFAULTS.get(b_id, {})

                cursor.execute("SELECT COUNT(*) FROM stores WHERE store_id = ?", (b_id,))
                exists = cursor.fetchone()[0] > 0

                if not exists:
                    b_name = f"{base.get('store_name', '')} (DOPPIA /9)"
                    b_giro = defaults.get("giro") or f"{base.get('giro', 'ZA1')}B"
                    b_vett = defaults.get("vettore") or base.get("vettore") or "LACCHI SPA"
                    b_mezzo = defaults.get("tipo_mezzo") or base.get("tipo_mezzo_doppia") or "FURGONE 8"

                    cursor.execute("""
                    INSERT INTO stores (
                        store_id, store_name, punto_vendita, brand, giro, cod_sga, cc,
                        attivo, barra, stender, formula, lavorazione, sdoppiamento_b9,
                        tipo_mezzo, vettore, indirizzo, provincia
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        b_id,
                        b_name,
                        base.get("punto_vendita", ""),
                        base.get("brand", ""),
                        b_giro,
                        base.get("cod_sga"),
                        base.get("cc", ""),
                        base.get("attivo", "SI"),
                        "BARRA 9",
                        "NO",  # stender lavorazione is handled on Day A (/0)
                        base.get("formula", "MC/1,9"),
                        "NO",  # lavorazione is handled on Day A (/0)
                        "SI",
                        b_mezzo,
                        b_vett,
                        base.get("indirizzo", ""),
                        base.get("provincia", "")
                    ))
            conn.commit()
    except Exception:
        pass


def get_stores_df(db_path=DB_PATH) -> pd.DataFrame:
    sync_double_service_stores(db_path)
    try:
        with get_connection(db_path) as conn:
            return pd.read_sql_query("SELECT * FROM stores ORDER BY giro ASC, store_id ASC", conn)
    except Exception:
        try:
            init_db(db_path)
            seed_anagrafica_if_empty(db_path)
            with get_connection(db_path) as conn:
                return pd.read_sql_query("SELECT * FROM stores ORDER BY giro ASC, store_id ASC", conn)
        except Exception:
            try:
                if ANAGRAFICA_FILE.exists():
                    df = pd.read_excel(ANAGRAFICA_FILE)
                    df = df.rename(columns={
                        "STORE_ID": "store_id",
                        "STORE": "store_name",
                        "PUNTO_VENDITA": "punto_vendita",
                        "RAGG": "giro",
                        "codSGA": "cod_sga",
                        "CC": "cc",
                        "ATTIVO": "attivo",
                        "BARRA": "barra",
                        "STENDER": "stender",
                        "FORMULA": "formula",
                        "ff": "ff"
                    })
                    if "brand" not in df.columns and "punto_vendita" in df.columns:
                        df["brand"] = df["punto_vendita"]
                    if "lavorazione" not in df.columns:
                        df["lavorazione"] = "NO"
                    if "sdoppiamento_b9" not in df.columns:
                        df["sdoppiamento_b9"] = "NO"
                    return df
            except Exception:
                pass
            return pd.DataFrame()


def update_store_formula(store_id: str, formula: str, db_path=DB_PATH):
    """Updates the pedane calculation formula for a specific store."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE stores
        SET formula = ?
        WHERE store_id = ?
        """, (formula.strip(), store_id.strip()))
        conn.commit()


def update_store_record(store_id: str, updates: Dict[str, Any], db_path=DB_PATH):
    """Updates multiple fields of a store in the anagrafica and synchronizes delivery profiles."""
    allowed_cols = [
        "store_name", "punto_vendita", "brand", "giro", "autista", "cell_autista",
        "tipo_mezzo", "vettore", "indirizzo", "provincia", "cod_sga", "cc",
        "attivo", "barra", "stender", "formula", "lavorazione", "sdoppiamento_b9",
        "autista_doppia", "tipo_mezzo_doppia", "scorporo_profumi", "pezzi_profumi"
    ]
    set_clauses = []
    values = []
    for k, v in updates.items():
        if k in allowed_cols:
            set_clauses.append(f"{k} = ?")
            values.append(v)
    if not set_clauses:
        return
    values.append(store_id.strip())
    query = f"UPDATE stores SET {', '.join(set_clauses)} WHERE store_id = ?"
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))

        # Sync to store_delivery_profiles if delivery fields updated
        if any(f in updates for f in ["autista", "cell_autista", "tipo_mezzo", "indirizzo", "provincia", "store_name", "punto_vendita"]):
            cursor.execute("SELECT store_name, punto_vendita, provincia, tipo_mezzo, autista, cell_autista, indirizzo FROM stores WHERE store_id = ?", (store_id.strip(),))
            s_row = cursor.fetchone()
            if s_row:
                s_name, s_pv, s_prov, s_tm, s_aut, s_cell, s_ind = s_row
                aut_display = f"{s_aut} ({s_cell})" if s_cell and str(s_cell).strip() else (s_aut or "")
                cursor.execute("""
                INSERT OR REPLACE INTO store_delivery_profiles 
                (id_store, tipo_cons, punto_vendita, store_name, provincia, tipo_mezzo, autista, indirizzo)
                VALUES (?, 'STD', ?, ?, ?, ?, ?, ?)
                """, (store_id.strip(), s_pv, s_name, s_prov, s_tm, aut_display, s_ind))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])


def update_giro_driver(
    giro: str,
    autista: str = "",
    cell_autista: str = "",
    tipo_mezzo: str = "",
    tipo_mezzo_doppia: str = "",
    vettore: str = "LACCHI SPA",
    db_path=DB_PATH
) -> int:
    """Updates vehicle types (standard and doppia/b9) and carrier for all stores belonging to a specific giro."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        updates = ["vettore = ?"]
        params = [vettore.strip() if vettore else "LACCHI SPA"]
        
        if autista or cell_autista:
            updates.extend(["autista = ?", "cell_autista = ?"])
            params.extend([autista.strip(), cell_autista.strip()])
        if tipo_mezzo:
            updates.append("tipo_mezzo = ?")
            params.append(tipo_mezzo.strip())
        if tipo_mezzo_doppia:
            updates.append("tipo_mezzo_doppia = ?")
            params.append(tipo_mezzo_doppia.strip())

        params.append(giro.strip())
        sql = f"UPDATE stores SET {', '.join(updates)} WHERE giro = ?"
        cursor.execute(sql, params)
        n_updated = cursor.rowcount

        # Sync to store_delivery_profiles for all stores in this giro
        if tipo_mezzo:
            cursor.execute("""
            UPDATE store_delivery_profiles
            SET tipo_mezzo = ?
            WHERE id_store IN (SELECT store_id FROM stores WHERE giro = ?) AND tipo_cons = 'STD'
            """, (tipo_mezzo.strip(), giro.strip()))
        if tipo_mezzo_doppia:
            cursor.execute("""
            UPDATE store_delivery_profiles
            SET tipo_mezzo = ?
            WHERE id_store IN (SELECT store_id FROM stores WHERE giro = ?) AND tipo_cons = 'DOPPIA'
            """, (tipo_mezzo_doppia.strip(), giro.strip()))

        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])
    return n_updated


def get_giro_summary(db_path=DB_PATH) -> pd.DataFrame:
    """Returns aggregated summary of all delivery routes (Giri) with their assigned carriers, standard vehicle, and double-route vehicle."""
    with get_connection(db_path) as conn:
        query = """
        SELECT 
            giro,
            COUNT(*) as n_stores,
            MAX(COALESCE(NULLIF(autista, ''), 'Non Assegnato')) as autista,
            MAX(COALESCE(cell_autista, '')) as cell_autista,
            MAX(COALESCE(NULLIF(tipo_mezzo, ''), 'MOTRICE 18 PLT')) as tipo_mezzo,
            MAX(COALESCE(NULLIF(tipo_mezzo_doppia, ''), 'FURGONE 8')) as tipo_mezzo_doppia,
            MAX(COALESCE(NULLIF(vettore, ''), 'LACCHI SPA')) as vettore,
            GROUP_CONCAT(store_id || ' (' || store_name || ')') as elenco_negozi
        FROM stores
        GROUP BY giro
        ORDER BY giro ASC
        """
        return pd.read_sql_query(query, conn)


def add_store_record(store_data: Dict[str, Any], db_path=DB_PATH):
    """Inserts a new store or replaces an existing one in anagrafica."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO stores (
            store_id, store_name, punto_vendita, brand, giro, autista, cell_autista, tipo_mezzo, vettore, indirizzo, provincia, cod_sga, cc,
            attivo, barra, stender, formula, lavorazione, sdoppiamento_b9, autista_doppia, tipo_mezzo_doppia, scorporo_profumi, pezzi_profumi
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(store_data["store_id"]).strip(),
            str(store_data.get("store_name", "")).strip(),
            str(store_data.get("punto_vendita", "")).strip(),
            str(store_data.get("brand", "")).strip(),
            str(store_data.get("giro", "")).strip(),
            str(store_data.get("autista", "")).strip(),
            str(store_data.get("cell_autista", "")).strip(),
            str(store_data.get("tipo_mezzo", "")).strip(),
            str(store_data.get("vettore", "LACCHI SPA")).strip(),
            str(store_data.get("indirizzo", "")).strip(),
            str(store_data.get("provincia", "")).strip(),
            int(store_data.get("cod_sga", 0)) if store_data.get("cod_sga") is not None and str(store_data.get("cod_sga")).isdigit() else None,
            str(store_data.get("cc", "")).strip(),
            str(store_data.get("attivo", "SI")).strip().upper(),
            str(store_data.get("barra", "BARRA 0")).strip(),
            str(store_data.get("stender", "NO")).strip().upper(),
            str(store_data.get("formula", "MC/1,9")).strip(),
            str(store_data.get("lavorazione", "NO")).strip().upper(),
            str(store_data.get("sdoppiamento_b9", "NO")).strip().upper(),
            str(store_data.get("autista_doppia", "")).strip(),
            str(store_data.get("tipo_mezzo_doppia", "")).strip(),
            str(store_data.get("scorporo_profumi", "NO")).strip().upper(),
            int(float(store_data.get("pezzi_profumi", 0) or 0)),
        ))
        # Remove from deleted_stores if explicitly re-added
        try:
            cursor.execute("DELETE FROM deleted_stores WHERE store_id = ?", (str(store_data.get("store_id", "")).strip(),))
        except Exception:
            pass
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])


def delete_store_record(store_id: str, blacklist: bool = False, db_path=DB_PATH):
    """Deletes a store from anagrafica. Also deletes its B clone if present. If blacklist=True, adds to deleted_stores to prevent re-onboarding."""
    sid = str(store_id).strip()
    sid_b = f"{sid}B" if not sid.endswith("B") else sid
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stores WHERE store_id IN (?, ?)", (sid, sid_b))
        cursor.execute("DELETE FROM store_delivery_profiles WHERE id_store IN (?, ?)", (sid, sid_b))
        if blacklist:
            try:
                cursor.execute("CREATE TABLE IF NOT EXISTS deleted_stores (store_id TEXT PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                cursor.execute("INSERT OR REPLACE INTO deleted_stores (store_id) VALUES (?)", (sid,))
                if sid != sid_b:
                    cursor.execute("INSERT OR REPLACE INTO deleted_stores (store_id) VALUES (?)", (sid_b,))
            except Exception:
                pass
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    tables = ["stores", "store_delivery_profiles"]
    if blacklist:
        tables.append("deleted_stores")
    auto_sync_tables(tables)


def get_deleted_store_ids(db_path=DB_PATH) -> set:
    """Returns set of store IDs explicitly deleted by user to prevent automatic re-creation from Inditex files."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT store_id FROM deleted_stores")
            return {str(r[0]).strip() for r in cursor.fetchall() if r[0]}
        except Exception:
            return set()


def bulk_update_stores(df_updated: pd.DataFrame, db_path=DB_PATH):
    """Bulk updates stores table from a modified DataFrame, dynamically updating only columns present."""
    if df_updated.empty or "store_id" not in df_updated.columns:
        return 0

    allowed_cols = [
        "store_name", "punto_vendita", "brand", "giro", "autista", "cell_autista",
        "tipo_mezzo", "vettore", "indirizzo", "provincia", "cod_sga", "cc",
        "attivo", "barra", "stender", "formula", "lavorazione", "sdoppiamento_b9",
        "autista_doppia", "tipo_mezzo_doppia", "scorporo_profumi", "pezzi_profumi"
    ]
    cols_to_update = [c for c in df_updated.columns if c in allowed_cols]
    if not cols_to_update:
        return 0

    set_sql = ", ".join(f"{c} = ?" for c in cols_to_update)
    query = f"UPDATE stores SET {set_sql} WHERE store_id = ?"

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for _, r in df_updated.iterrows():
            sid = str(r["store_id"]).strip()
            vals = []
            for c in cols_to_update:
                val = r[c]
                if pd.isna(val):
                    vals.append(None)
                elif c == "cod_sga":
                    try:
                        vals.append(int(val) if str(val).isdigit() else None)
                    except:
                        vals.append(None)
                elif c in ["attivo", "lavorazione", "scorporo_profumi", "sdoppiamento_b9"]:
                    vals.append(str(val).strip().upper())
                else:
                    vals.append(str(val).strip())
            vals.append(sid)
            cursor.execute(query, tuple(vals))

            # Delivery profile sync if driver/vehicle/name changed
            if any(f in cols_to_update for f in ["autista", "cell_autista", "tipo_mezzo", "indirizzo", "provincia", "store_name"]):
                cursor.execute("SELECT store_name, punto_vendita, provincia, tipo_mezzo, autista, cell_autista, indirizzo FROM stores WHERE store_id = ?", (sid,))
                s_row = cursor.fetchone()
                if s_row:
                    s_name, s_pv, s_prov, s_tm, s_aut, s_cell, s_ind = s_row
                    aut_display = f"{s_aut} ({s_cell})" if s_cell and str(s_cell).strip() else (s_aut or "")
                    cursor.execute("""
                    INSERT OR REPLACE INTO store_delivery_profiles 
                    (id_store, tipo_cons, punto_vendita, store_name, provincia, tipo_mezzo, autista, indirizzo)
                    VALUES (?, 'STD', ?, ?, ?, ?, ?, ?)
                    """, (sid, s_pv, s_name, s_prov, s_tm, aut_display, s_ind))

        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])
    return len(df_updated)




def get_vehicles_df(db_path=DB_PATH) -> pd.DataFrame:
    """Returns all vehicles sorted by capacity ascending."""
    with get_connection(db_path) as conn:
        try:
            return pd.read_sql_query(
                "SELECT cod_mezzo, tipo_mezzo, descrizione, capienza_pedane, attivo, note FROM vehicles ORDER BY capienza_pedane ASC, cod_mezzo ASC",
                conn
            )
        except Exception:
            return pd.DataFrame()


def add_vehicle_record(data: Dict[str, Any], db_path=DB_PATH):
    """Adds a new vehicle to the registry."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO vehicles (cod_mezzo, tipo_mezzo, descrizione, capienza_pedane, attivo, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(data.get("cod_mezzo", "")).strip().upper(),
            str(data.get("tipo_mezzo", "MOTRICE")).strip().upper(),
            str(data.get("descrizione", "")).strip(),
            int(data.get("capienza_pedane", 18)),
            str(data.get("attivo", "SI")).strip().upper(),
            str(data.get("note", "")).strip(),
        ))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["vehicles"])


def update_vehicle_record(old_cod_mezzo: str, updates: Dict[str, Any], db_path=DB_PATH):
    """Updates a vehicle record, allowing code rename, capacity change, description, active status, etc."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        old_cod = str(old_cod_mezzo).strip().upper()
        new_cod = str(updates.get("cod_mezzo", old_cod)).strip().upper()
        tipo_m = str(updates.get("tipo_mezzo", "MOTRICE")).strip().upper()
        desc = str(updates.get("descrizione", "")).strip()
        cap = int(float(updates.get("capienza_pedane", 18) or 18))
        att = str(updates.get("attivo", "SI")).strip().upper()
        note = str(updates.get("note", "")).strip()

        cursor.execute("""
        UPDATE vehicles
        SET cod_mezzo = ?, tipo_mezzo = ?, descrizione = ?, capienza_pedane = ?, attivo = ?, note = ?
        WHERE UPPER(TRIM(cod_mezzo)) = ?
        """, (new_cod, tipo_m, desc, cap, att, note, old_cod))

        # If vehicle code changed, sync to stores that referenced old vehicle code
        if new_cod != old_cod:
            cursor.execute("UPDATE stores SET tipo_mezzo = ? WHERE tipo_mezzo = ?", (new_cod, old_cod))
            cursor.execute("UPDATE stores SET tipo_mezzo_doppia = ? WHERE tipo_mezzo_doppia = ?", (new_cod, old_cod))

        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["vehicles", "stores"])


def delete_vehicle_record(cod_mezzo: str, db_path=DB_PATH):
    """Deletes a vehicle from the registry."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        c_m = str(cod_mezzo).strip().upper()
        cursor.execute("DELETE FROM vehicles WHERE UPPER(TRIM(cod_mezzo)) = ?", (c_m,))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["vehicles"])


def bulk_update_vehicles(df_updated: pd.DataFrame, db_path=DB_PATH):
    """Bulk updates vehicle records from data_editor."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for _, r in df_updated.iterrows():
            c_m = str(r.get("cod_mezzo", "")).strip().upper()
            if not c_m:
                continue
            cursor.execute("""
            UPDATE vehicles
            SET tipo_mezzo = ?, descrizione = ?, capienza_pedane = ?, attivo = ?, note = ?
            WHERE UPPER(TRIM(cod_mezzo)) = ?
            """, (
                str(r.get("tipo_mezzo", "")).strip().upper(),
                str(r.get("descrizione", "")).strip(),
                int(float(r.get("capienza_pedane", 18) or 18)),
                str(r.get("attivo", "SI")).strip().upper(),
                str(r.get("note", "")).strip(),
                c_m
            ))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["vehicles"])


def create_run(run_date: str, cycle_type: str, notes: str = "", db_path=DB_PATH) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO runs (run_date, cycle_type, notes)
        VALUES (?, ?, ?)
        """, (run_date, cycle_type, notes))
        conn.commit()
        return cursor.lastrowid


def update_run_totals(run_id: int, total_bultos: float, total_volume: float, total_weight: float, total_pedane: int, db_path=DB_PATH):
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE runs
        SET total_bultos = ?, total_volume = ?, total_weight = ?, total_pedane = ?
        WHERE id = ?
        """, (total_bultos, total_volume, total_weight, total_pedane, run_id))
        conn.commit()


def get_all_runs(db_path=DB_PATH) -> pd.DataFrame:
    try:
        with get_connection(db_path) as conn:
            return pd.read_sql_query(
                "SELECT id, id AS run_id, run_date, cycle_type, total_bultos, total_bultos AS total_planned_crts, total_volume, total_weight, total_pedane, notes, created_at FROM runs ORDER BY id DESC",
                conn
            )
    except Exception:
        try:
            init_db(db_path)
            with get_connection(db_path) as conn:
                return pd.read_sql_query(
                    "SELECT id, id AS run_id, run_date, cycle_type, total_bultos, total_bultos AS total_planned_crts, total_volume, total_weight, total_pedane, notes, created_at FROM runs ORDER BY id DESC",
                    conn
                )
        except Exception:
            return pd.DataFrame()


def get_run_details(run_id: int, db_path=DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        def _safe_query(sql: str, params=None) -> pd.DataFrame:
            try:
                if params is not None:
                    return pd.read_sql_query(sql, conn, params=params)
                return pd.read_sql_query(sql, conn)
            except Exception:
                return pd.DataFrame()

        run_df = _safe_query("SELECT * FROM runs WHERE id = ?", params=(int(run_id),))
        run_dict = run_df.iloc[0].to_dict() if not run_df.empty else None
        planning = _safe_query("SELECT * FROM planning_results WHERE run_id = ?", params=(int(run_id),))
        spunta = _safe_query("SELECT * FROM spunta_arrivi WHERE run_id = ? ORDER BY row_idx", params=(int(run_id),))
        if not spunta.empty and "is_store" not in spunta.columns:
            spunta["is_store"] = ~spunta["store_code"].astype(str).str.strip().str.upper().isin(["", "NEGOZIO", "STORE ID", "EXTRA", "NONE"])
        sga0 = _safe_query("SELECT * FROM sga_flows WHERE run_id = ? AND barra = 0 ORDER BY id", params=(int(run_id),))
        sga9 = _safe_query("SELECT * FROM sga_flows WHERE run_id = ? AND barra = 9 ORDER BY id", params=(int(run_id),))
        sga_all = _safe_query("SELECT * FROM sga_flows WHERE run_id = ? ORDER BY id", params=(int(run_id),))
        actuals = _safe_query("SELECT * FROM actual_deliveries WHERE run_id = ?", params=(int(run_id),))

        # Reconstruct special_breakdowns from forecast_raw
        df_tot = _safe_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'TOTAL'",
            params=(int(run_id),)
        )
        df_sho = _safe_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'SHOES'",
            params=(int(run_id),)
        )
        df_tex = _safe_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'TEXILE'",
            params=(int(run_id),)
        )
        df_eco = _safe_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'ECOM'",
            params=(int(run_id),)
        )
        df_stores = _safe_query("SELECT * FROM stores ORDER BY giro ASC, store_id ASC")

        from src.engine import compute_special_breakdowns
        special_breakdowns = compute_special_breakdowns(spunta, df_tot, df_sho, df_texile=df_tex, df_ecom=df_eco, df_stores=df_stores)

        return {
            "run": run_dict,
            "run_info": run_df,
            "planning": planning,
            "planning_results": planning,
            "spunta": spunta,
            "spunta_arrivi": spunta,
            "sga0": sga0,
            "sga9": sga9,
            "sga_flows": sga_all,
            "actuals": actuals,
            "special_breakdowns": special_breakdowns
        }


def load_run_data(run_id: int, db_path=DB_PATH) -> Optional[Dict[str, Any]]:
    """
    Loads full run data either from the fast run_cache.pkl or by reconstructing
    from SQLite database tables (spunta_arrivi, sga_flows, planning_results, forecast_raw).
    """
    import pickle
    from src.config import OUTPUT_DIR

    # 1. Search for run_cache.pkl in OUTPUT_DIR
    for p_cache in OUTPUT_DIR.glob(f"run_{run_id}_*/run_cache.pkl"):
        try:
            with open(p_cache, "rb") as f_c:
                data = pickle.load(f_c)
                if data and isinstance(data, dict):
                    return data
        except Exception:
            pass

    # 2. Reconstruct from DB
    det = get_run_details(run_id, db_path=db_path)
    if not det or not det.get("run"):
        return None

    r_info = det["run"]
    r_date = str(r_info.get("run_date", ""))
    out_dir = OUTPUT_DIR / f"run_{run_id}_{r_date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    spunta_df = det.get("spunta", pd.DataFrame())
    sga0_df = det.get("sga0", pd.DataFrame())
    sga9_df = det.get("sga9", pd.DataFrame())
    planning_df = det.get("planning", pd.DataFrame())
    special_breakdowns = det.get("special_breakdowns", {})

    path_sintesi = out_dir / "Sintesi_Operativa.xlsx"
    path_sga0 = out_dir / "barrazero_Sga.xlsx"
    path_sga9 = out_dir / "barranove_Sga.xlsx"
    path_zip = out_dir / f"File_Operativa_{run_id}_{r_date}.zip"

    exported_files = {
        "sintesi": path_sintesi,
        "sga0": path_sga0,
        "sga9": path_sga9,
        "sga0_csv": path_sga0.with_suffix(".csv"),
        "sga9_csv": path_sga9.with_suffix(".csv"),
        "operativa_zip": path_zip,
        "zara": out_dir / "ZARA.xlsx",
        "planner": out_dir / f"PLANNER ROMA _{r_date}.xlsx",
    }

    return {
        "run_id": run_id,
        "run_date": r_date,
        "cycle_type": r_info.get("cycle_type", ""),
        "totals": {
            "total_bultos": float(r_info.get("total_bultos", 0) or 0),
            "total_volume": float(r_info.get("total_volume", 0) or 0),
            "total_weight": float(r_info.get("total_weight", 0) or 0),
            "total_pedane": float(r_info.get("total_pedane", 0) or 0),
        },
        "df_analisi": planning_df,
        "df_spunta": spunta_df,
        "df_sga0": sga0_df,
        "df_sga9": sga9_df,
        "df_planner": planning_df,
        "special_breakdowns": special_breakdowns,
        "exported_files": exported_files,
        "new_stores_alert": []
    }


def delete_run(run_id: int, db_path=DB_PATH):
    """
    Deletes a run and all its associated child records (forecast_raw, other_items,
    actual_deliveries, planning_results, spunta_arrivi, sga_flows) from the database.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM runs WHERE id = ?", (int(run_id),))
        cursor.execute("DELETE FROM forecast_raw WHERE run_id = ?", (int(run_id),))
        cursor.execute("DELETE FROM other_items WHERE run_id = ?", (int(run_id),))
        cursor.execute("DELETE FROM actual_deliveries WHERE run_id = ?", (int(run_id),))
        cursor.execute("DELETE FROM planning_results WHERE run_id = ?", (int(run_id),))
        cursor.execute("DELETE FROM spunta_arrivi WHERE run_id = ?", (int(run_id),))
        cursor.execute("DELETE FROM sga_flows WHERE run_id = ?", (int(run_id),))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["runs", "planning_results", "spunta_arrivi"])


def delete_runs(run_ids: List[int], db_path=DB_PATH) -> int:
    """
    Deletes multiple runs and all their associated child records in a single transaction.
    Returns the number of runs deleted.
    """
    if not run_ids:
        return 0
    clean_ids = [int(rid) for rid in run_ids]
    placeholders = ",".join("?" for _ in clean_ids)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for tbl in ["forecast_raw", "other_items", "actual_deliveries", "planning_results", "spunta_arrivi", "sga_flows"]:
            cursor.execute(f"DELETE FROM {tbl} WHERE run_id IN ({placeholders})", clean_ids)
        cursor.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", clean_ids)
        n_deleted = cursor.rowcount
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["runs", "planning_results", "spunta_arrivi"])
    return n_deleted


def clear_all_runs(db_path=DB_PATH) -> int:
    """
    Clears all execution runs and associated history data from the database.
    Returns the number of runs deleted.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM runs")
        n_runs = cursor.fetchone()[0]
        for tbl in ["forecast_raw", "other_items", "actual_deliveries", "planning_results", "spunta_arrivi", "sga_flows"]:
            cursor.execute(f"DELETE FROM {tbl}")
        cursor.execute("DELETE FROM runs")
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["runs", "planning_results", "spunta_arrivi"])
    return n_runs


def get_store_latest_planned_data(store_id: str, db_path=DB_PATH) -> Dict[str, Any]:
    """
    Returns the latest forecast/planning metrics (colli previsti, volumi, pedane)
    for a given store from the most recent run.
    """
    with get_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(id) FROM runs")
        r = cur.fetchone()
        if not r or not r[0]:
            return {"has_data": False, "run_id": None, "run_date": "", "total_crts": 0.0}
        latest_run_id = r[0]

        cur.execute("SELECT run_date, cycle_type FROM runs WHERE id = ?", (latest_run_id,))
        run_meta = cur.fetchone()

        df_pl = pd.read_sql_query("SELECT * FROM planning_results WHERE run_id = ?", conn, params=(latest_run_id,))
        df_sp = pd.read_sql_query("SELECT * FROM spunta_arrivi WHERE run_id = ?", conn, params=(latest_run_id,))

    sid_str = str(store_id).strip()
    pl_rows = df_pl[df_pl["store_code"].astype(str).str.startswith(sid_str)] if not df_pl.empty else pd.DataFrame()
    sp_rows = df_sp[df_sp["store_code"].astype(str).str.startswith(sid_str)] if not df_sp.empty else pd.DataFrame()

    if pl_rows.empty and sp_rows.empty:
        return {
            "has_data": False,
            "run_id": latest_run_id,
            "run_date": str(run_meta[0])[:10] if run_meta else "",
            "cycle_type": run_meta[1] if run_meta else "",
            "total_crts": 0.0
        }

    from src.engine import _safe_float
    tot_text = _safe_float(pl_rows[~pl_rows["brand"].str.upper().str.contains("SHOES")]["planned_textile"].sum()) if not pl_rows.empty else 0.0
    tot_sho = _safe_float(pl_rows["planned_shoes"].sum()) if not pl_rows.empty else 0.0
    tot_oth = _safe_float(pl_rows["planned_others"].sum()) if not pl_rows.empty else 0.0
    tot_eco = _safe_float(pl_rows["planned_ecom"].sum()) if not pl_rows.empty else 0.0
    tot_vol = _safe_float(pl_rows["total_vol"].sum()) if not pl_rows.empty else 0.0
    tot_crts = _safe_float(pl_rows["total_planned_crts"].sum()) if not pl_rows.empty else 0.0

    tot_ped = int(sp_rows["pedane"].sum()) if not sp_rows.empty else int(tot_vol / 1.9)

    return {
        "has_data": True,
        "run_id": latest_run_id,
        "run_date": str(run_meta[0])[:10] if run_meta else "",
        "cycle_type": run_meta[1] if run_meta else "",
        "textile": tot_text,
        "shoes": tot_sho,
        "others": tot_oth,
        "ecom": tot_eco,
        "total_crts": tot_crts,
        "volume": tot_vol,
        "pedane": tot_ped
    }



# ==============================================================================
# SETTINGS & EMAIL CONFIGURATION
# ==============================================================================

def get_app_setting(key: str, default: str = "", db_path=None) -> str:
    """Reads a setting value from app_settings table."""
    try:
        with get_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,))
            row = c.fetchone()
            if row and row[0] is not None:
                return str(row[0])
    except Exception:
        pass
    return default


def set_app_setting(key: str, value: str, db_path=None):
    """Writes a setting value to app_settings table (UPSERT)."""
    with get_connection(db_path) as conn:
        c = conn.cursor()
        c.execute("""
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = CURRENT_TIMESTAMP
        """, (key, str(value)))
        conn.commit()


def get_email_config(db_path=None) -> Dict[str, Any]:
    """
    Retrieves full email and SMTP configuration, merging DB app_settings,
    email_config.json, cloud_config.json, Streamlit Secrets, and OS environment variables.
    """
    import json
    import os
    from src.config import DATA_DIR

    cfg = {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_security": "STARTTLS",
        "sender_name": "Logistica Zara Hub",
        "default_to": "operativa@trasporti.it, traffico@trasporti.it",
        "default_cc": "",
        "subject_template": "[ZARA LOGISTICS] File Operativa & Flussi SGA - Spedizione del {date}",
        "body_template": (
            "Gentili Colleghi,\n\n"
            "in allegato trasmettiamo i file operativi relativi alla spedizione del {date}:\n\n"
            "- Sintesi Operativa Giri & Lavorazioni (Sintesi_Operativa.xlsx)\n"
            "- Flusso Viaggi TMS Barra 0 (barrazero_Sga.xlsx / .csv)\n"
            "- Flusso Viaggi TMS Barra 9 Sdoppiati (barranove_Sga.xlsx / .csv)\n\n"
            "Riepilogo Totali Spedizione:\n"
            "- Totale Colli: {total_bultos}\n"
            "- Volume Complessivo: {total_volume} m³\n"
            "- Peso Complessivo: {total_weight} kg\n"
            "- Pedane Stimate: {total_pedane} PLT\n\n"
            "Restiamo a disposizione per qualsiasi chiarimento operativo.\n\n"
            "Cordiali saluti,\n"
            "Ufficio Logistica & Traffico Zara Hub"
        )
    }

    # 1. Check local email_config.json (persistent across git pulls if untracked)
    em_file = DATA_DIR / "email_config.json"
    if em_file.exists():
        try:
            em_data = json.loads(em_file.read_text(encoding="utf-8"))
            if isinstance(em_data, dict):
                cfg.update(em_data)
        except Exception:
            pass

    # 2. Check DB app_settings table
    raw_db = get_app_setting("email_config_json", "", db_path=db_path)
    if raw_db:
        try:
            loaded = json.loads(raw_db)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass

    # 3. Check cloud_config.json
    if db_path is None:
        c_file = DATA_DIR / "cloud_config.json"
        if c_file.exists():
            try:
                fdata = json.loads(c_file.read_text(encoding="utf-8"))
                if "email_config" in fdata and isinstance(fdata["email_config"], dict):
                    for k, v in fdata["email_config"].items():
                        if v and not cfg.get(k):
                            cfg[k] = v
            except Exception:
                pass

    # 4. Check Streamlit Secrets (permanent on Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if "smtp" in st.secrets:
                for k, v in st.secrets["smtp"].items():
                    if v:
                        cfg[k] = v
            for k in ["smtp_host", "smtp_user", "smtp_password", "smtp_port", "smtp_security", "default_to", "default_cc"]:
                if k in st.secrets and st.secrets[k]:
                    cfg[k] = st.secrets[k]
                upper_k = k.upper()
                if upper_k in st.secrets and st.secrets[upper_k]:
                    cfg[k] = st.secrets[upper_k]
    except Exception:
        pass

    # 5. OS Environment variables
    if not cfg["smtp_host"] and os.getenv("SMTP_HOST"):
        cfg["smtp_host"] = os.getenv("SMTP_HOST", "")
    if os.getenv("SMTP_PORT"):
        try:
            cfg["smtp_port"] = int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            pass
    if not cfg["smtp_user"] and os.getenv("SMTP_USER"):
        cfg["smtp_user"] = os.getenv("SMTP_USER", "")
    if not cfg["smtp_password"] and os.getenv("SMTP_PASSWORD"):
        cfg["smtp_password"] = os.getenv("SMTP_PASSWORD", "")

    return cfg


def save_email_config(cfg: Dict[str, Any], db_path=None):
    """
    Saves email and SMTP configuration into DB app_settings, mirrors to
    data/email_config.json and data/cloud_config.json, and pushes to Google Sheets.
    """
    import json
    from src.config import DATA_DIR

    raw_json = json.dumps(cfg, ensure_ascii=False, indent=2)
    set_app_setting("email_config_json", raw_json, db_path=db_path)

    # Save to local email_config.json
    try:
        em_file = DATA_DIR / "email_config.json"
        em_file.parent.mkdir(parents=True, exist_ok=True)
        em_file.write_text(raw_json, encoding="utf-8")
    except Exception:
        pass

    # Mirror to cloud_config.json
    if db_path is None:
        try:
            c_file = DATA_DIR / "cloud_config.json"
            c_file.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if c_file.exists():
                try:
                    data = json.loads(c_file.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["email_config"] = cfg
            c_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

        # Push to Google Sheets in background so it's backed up to Cloud
        try:
            from src.cloud_sync import auto_sync_tables
            auto_sync_tables(["app_settings"])
        except Exception:
            pass
