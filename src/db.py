import sqlite3
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
from src.config import DB_PATH, ANAGRAFICA_FILE


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
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
        cursor.execute("UPDATE stores SET pezzi_profumi = 1085 WHERE store_id = '3680' AND (pezzi_profumi IS NULL OR pezzi_profumi = 0)")
        cursor.execute("UPDATE stores SET pezzi_profumi = 1791 WHERE store_id = '9226' AND (pezzi_profumi IS NULL OR pezzi_profumi = 0)")
        cursor.execute("UPDATE stores SET pezzi_profumi = 1030 WHERE store_id = '3591' AND (pezzi_profumi IS NULL OR pezzi_profumi = 0)")

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


def get_stores_df(db_path=DB_PATH) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM stores ORDER BY giro ASC, store_id ASC", conn)


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


def update_giro_driver(giro: str, autista: str, cell_autista: str = "", tipo_mezzo: str = "", vettore: str = "LACCHI SPA", db_path=DB_PATH) -> int:
    """Updates driver, vehicle, and carrier for all stores belonging to a specific giro."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE stores 
        SET autista = ?, cell_autista = ?, tipo_mezzo = ?, vettore = ?
        WHERE giro = ?
        """, (autista.strip(), cell_autista.strip(), tipo_mezzo.strip(), vettore.strip(), giro.strip()))
        n_updated = cursor.rowcount

        # Sync to store_delivery_profiles for all stores in this giro
        aut_display = f"{autista.strip()} ({cell_autista.strip()})" if cell_autista.strip() else autista.strip()
        cursor.execute("""
        UPDATE store_delivery_profiles
        SET autista = ?, tipo_mezzo = ?
        WHERE id_store IN (SELECT store_id FROM stores WHERE giro = ?)
        """, (aut_display, tipo_mezzo.strip(), giro.strip()))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])
    return n_updated


def get_giro_summary(db_path=DB_PATH) -> pd.DataFrame:
    """Returns aggregated summary of all delivery routes (Giri) with their assigned drivers and stores."""
    with get_connection(db_path) as conn:
        query = """
        SELECT 
            giro,
            COUNT(*) as n_stores,
            MAX(COALESCE(NULLIF(autista, ''), 'Non Assegnato')) as autista,
            MAX(COALESCE(cell_autista, '')) as cell_autista,
            MAX(COALESCE(NULLIF(tipo_mezzo, ''), 'MOTRICE')) as tipo_mezzo,
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
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])


def delete_store_record(store_id: str, db_path=DB_PATH):
    """Deletes a store from anagrafica."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stores WHERE store_id = ?", (str(store_id).strip(),))
        cursor.execute("DELETE FROM store_delivery_profiles WHERE id_store = ?", (str(store_id).strip(),))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])


def bulk_update_stores(df_updated: pd.DataFrame, db_path=DB_PATH):
    """Bulk updates stores table from a modified DataFrame."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for _, r in df_updated.iterrows():
            sid = str(r["store_id"]).strip()
            cod_val = r.get("cod_sga")
            try:
                cod_sga_int = int(cod_val) if pd.notna(cod_val) and str(cod_val).isdigit() else None
            except:
                cod_sga_int = None

            aut_val = str(r.get("autista", "") or "").strip()
            cell_val = str(r.get("cell_autista", "") or "").strip()
            tm_val = str(r.get("tipo_mezzo", "") or "").strip()
            ind_val = str(r.get("indirizzo", "") or "").strip()
            prov_val = str(r.get("provincia", "") or "").strip()
            vet_val = str(r.get("vettore", "LACCHI SPA") or "LACCHI SPA").strip()
            aut_d_val = str(r.get("autista_doppia", "") or "").strip()
            tm_d_val = str(r.get("tipo_mezzo_doppia", "") or "").strip()
            scorp_val = str(r.get("scorporo_profumi", "NO") or "NO").strip().upper()
            try:
                pz_prof_val = int(float(r.get("pezzi_profumi", 0) or 0))
            except Exception:
                pz_prof_val = 0

            cursor.execute("""
            UPDATE stores
            SET store_name = ?, punto_vendita = ?, brand = ?, giro = ?,
                autista = ?, cell_autista = ?, tipo_mezzo = ?, vettore = ?, indirizzo = ?, provincia = ?,
                cod_sga = ?, cc = ?, attivo = ?, barra = ?, stender = ?, formula = ?,
                lavorazione = ?, sdoppiamento_b9 = ?, autista_doppia = ?, tipo_mezzo_doppia = ?,
                scorporo_profumi = ?, pezzi_profumi = ?
            WHERE store_id = ?
            """, (
                str(r.get("store_name", "")).strip(),
                str(r.get("punto_vendita", "")).strip(),
                str(r.get("brand", "")).strip(),
                str(r.get("giro", "")).strip(),
                aut_val,
                cell_val,
                tm_val,
                vet_val,
                ind_val,
                prov_val,
                cod_sga_int,
                str(r.get("cc", "")).strip(),
                str(r.get("attivo", "SI")).strip().upper(),
                str(r.get("barra", "BARRA 0")).strip(),
                str(r.get("stender", "NO")).strip().upper(),
                str(r.get("formula", "MC/1,9")).strip(),
                str(r.get("lavorazione", "NO")).strip().upper(),
                str(r.get("sdoppiamento_b9", "NO")).strip().upper(),
                aut_d_val,
                tm_d_val,
                scorp_val,
                pz_prof_val,
                sid
            ))

            aut_disp = f"{aut_val} ({cell_val})" if cell_val else aut_val
            cursor.execute("""
            INSERT OR REPLACE INTO store_delivery_profiles
            (id_store, tipo_cons, punto_vendita, store_name, provincia, tipo_mezzo, autista, indirizzo)
            VALUES (?, 'STD', ?, ?, ?, ?, ?, ?)
            """, (
                sid,
                str(r.get("punto_vendita", "")).strip(),
                str(r.get("store_name", "")).strip(),
                prov_val,
                tm_val,
                aut_disp,
                ind_val
            ))
        conn.commit()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["stores", "store_delivery_profiles"])


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
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            "SELECT id, id AS run_id, run_date, cycle_type, total_bultos, total_bultos AS total_planned_crts, total_volume, total_weight, total_pedane, notes, created_at FROM runs ORDER BY id DESC",
            conn
        )


def get_run_details(run_id: int, db_path=DB_PATH) -> Dict[str, Any]:
    with get_connection(db_path) as conn:
        run_df = pd.read_sql_query("SELECT * FROM runs WHERE id = ?", conn, params=(run_id,))
        run_dict = run_df.iloc[0].to_dict() if not run_df.empty else None
        planning = pd.read_sql_query("SELECT * FROM planning_results WHERE run_id = ?", conn, params=(run_id,))
        spunta = pd.read_sql_query("SELECT * FROM spunta_arrivi WHERE run_id = ? ORDER BY row_idx", conn, params=(run_id,))
        if not spunta.empty and "is_store" not in spunta.columns:
            spunta["is_store"] = ~spunta["store_code"].astype(str).str.strip().str.upper().isin(["", "NEGOZIO", "STORE ID", "EXTRA", "NONE"])
        sga0 = pd.read_sql_query("SELECT * FROM sga_flows WHERE run_id = ? AND barra = 0 ORDER BY id", conn, params=(run_id,))
        sga9 = pd.read_sql_query("SELECT * FROM sga_flows WHERE run_id = ? AND barra = 9 ORDER BY id", conn, params=(run_id,))
        sga_all = pd.read_sql_query("SELECT * FROM sga_flows WHERE run_id = ? ORDER BY id", conn, params=(run_id,))
        actuals = pd.read_sql_query("SELECT * FROM actual_deliveries WHERE run_id = ?", conn, params=(run_id,))

        # Reconstruct special_breakdowns from forecast_raw
        df_tot = pd.read_sql_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'TOTAL'",
            conn, params=(run_id,)
        )
        df_sho = pd.read_sql_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'SHOES'",
            conn, params=(run_id,)
        )
        df_tex = pd.read_sql_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'TEXILE'",
            conn, params=(run_id,)
        )
        df_eco = pd.read_sql_query(
            "SELECT store_code AS store_id, p_colgada, paqueteria, peso, volumen, bultos FROM forecast_raw WHERE run_id = ? AND file_category = 'ECOM'",
            conn, params=(run_id,)
        )
        df_stores = pd.read_sql_query("SELECT * FROM stores ORDER BY giro ASC, store_id ASC", conn)

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
