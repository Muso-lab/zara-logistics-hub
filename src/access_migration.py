import os
import sqlite3
import time
from pathlib import Path
from datetime import datetime
import pandas as pd

from src.config import DB_PATH
from src.access_reader import DEFAULT_ACCESS_PATH, get_oledb_connection


def init_bolle_table(db_path=DB_PATH):
    """Creates the bolle table and indexes in SQLite."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bolle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        access_id INTEGER UNIQUE,
        data TEXT NOT NULL, -- YYYY-MM-DD
        data_consegna TEXT,
        id_store TEXT NOT NULL,
        punto_vendita TEXT,
        store_name TEXT,
        tipo_cons TEXT DEFAULT 'STD', -- STD or DOPPIA
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bolle_store ON bolle(id_store);")
    conn.commit()
    conn.close()


def migrate_access_to_sqlite(mdb_path=DEFAULT_ACCESS_PATH, db_path=DB_PATH, progress_callback=None) -> int:
    """
    Migrates all records from TBL_DATI and DETTAGLIATO in Access into SQLite.
    Returns the total number of records imported.
    """
    p = Path(mdb_path)
    if not p.exists():
        raise FileNotFoundError(f"File Access non trovato: {p}")

    init_bolle_table(db_path)

    # 1. Load DETTAGLIATO mapping from Access
    conn_acc = get_oledb_connection(p)
    import win32com.client

    rs_det = win32com.client.Dispatch("ADODB.Recordset")
    rs_det.Open("SELECT * FROM [DETTAGLIATO]", conn_acc, 1, 1)
    dettagliato_map = {}
    while not rs_det.EOF:
        sid_raw = str(rs_det.Fields("Store ID").Value or "").strip()
        t_cons = str(rs_det.Fields("TIPO CONS").Value or "STD").strip().upper()
        if sid_raw:
            sid = sid_raw[:-2] if sid_raw.endswith(".0") else sid_raw
            key = (sid, t_cons)
            dettagliato_map[key] = {
                "punto_vendita": str(rs_det.Fields("PUNTO VENDITA").Value or "").strip(),
                "store_name": str(rs_det.Fields("Store").Value or "").strip(),
                "provincia": str(rs_det.Fields("Provincia").Value or "").strip(),
                "tipo_mezzo": str(rs_det.Fields("TIPOLOGIA AUTOMEZZO").Value or "").strip(),
                "autista": str(rs_det.Fields("AUTISTA").Value or "").strip(),
                "indirizzo": str(rs_det.Fields("INDIRIZZO").Value or "").strip()
            }
        rs_det.MoveNext()
    rs_det.Close()

    # 2. Read TBL_DATI from Access
    rs = win32com.client.Dispatch("ADODB.Recordset")
    rs.Open("SELECT * FROM [TBL_DATI] ORDER BY id ASC", conn_acc, 1, 1)

    cols = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    rows_to_insert = []
    batch_size = 2000
    total_inserted = 0

    conn_sqlite = sqlite3.connect(db_path)
    cur_sqlite = conn_sqlite.cursor()

    while not rs.EOF:
        v_id = rs.Fields("id").Value
        v_data = rs.Fields("DATA").Value
        if v_data is not None and hasattr(v_data, "strftime"):
            data_str = str(v_data)[:10]
        else:
            data_str = str(v_data)[:10] if v_data else ""

        v_datac = rs.Fields("DATA_CONSEGNA").Value
        if v_datac is not None and hasattr(v_datac, "strftime"):
            datac_str = str(v_datac)[:10]
        else:
            datac_str = str(v_datac)[:10] if v_datac else data_str

        sid_raw = str(rs.Fields("ID_STORE").Value or "").strip()
        if sid_raw.endswith(".0"):
            sid = sid_raw[:-2]
        else:
            sid = sid_raw.split("-")[0].strip()

        tipo_cons = str(rs.Fields("TIPO_CONS").Value or "STD").strip().upper()
        if not tipo_cons or tipo_cons == "NONE":
            tipo_cons = "STD"

        det = dettagliato_map.get((sid, tipo_cons), dettagliato_map.get((sid, "STD"), {}))
        pv = det.get("punto_vendita", "")
        sname = det.get("store_name", "")
        autista = det.get("autista", "")
        tipo_mezzo = det.get("tipo_mezzo", "")
        indirizzo = str(rs.Fields("INDIRIZZO_DESTINO").Value or det.get("indirizzo", "")).strip()

        vettore = str(rs.Fields("VETTORE").Value or "").strip()
        cell = str(rs.Fields("CELL_AUTISTA").Value or "").strip()

        def get_f(fld):
            val = rs.Fields(fld).Value
            try:
                return float(val) if val is not None and str(val).strip() != "" else 0.0
            except:
                return 0.0

        c_abb = get_f("COLLI_ABBIGL")
        c_calz = get_f("COLLI_CALZAT")
        c_eco = get_f("COLLI_ECOM")
        c_oth = get_f("COLLI_OTHERS")
        c_var = get_f("COLLI_VARIO")
        c_cont = get_f("COLLI_CONT")
        c_mat = get_f("COLLI_MAT_VARIO")
        c_dann = get_f("COLLI_DANN")
        c_nonconf = get_f("COLLI_NON_CONF")
        anomalie = str(rs.Fields("ANOMALIE_SCARICO").Value or "").strip()

        # Intershops
        inter_parts = []
        for i in range(1, 11):
            m = rs.Fields(f"MITTENTE{i}").Value
            c = rs.Fields(f"COLLI{i}").Value
            t = rs.Fields(f"TIPO_MERCE{i}").Value
            try:
                c_val = float(c) if c is not None and str(c).strip() else 0.0
            except:
                c_val = 0.0

            if c_val > 0:
                p_desc = f"{int(c_val)}C"
                if t and str(t).strip() and str(t).strip().upper() != "NONE":
                    p_desc += f" {str(t).strip()}"
                if m and str(m).strip() and str(m).strip().upper() != "NONE":
                    m_str = str(m).strip()
                    if m_str.endswith(".0"):
                        m_str = m_str[:-2]
                    p_desc += f" da {m_str}"
                inter_parts.append(p_desc)

        stringa_val = " ".join(inter_parts)

        rows_to_insert.append((
            int(v_id), data_str, datac_str, sid, pv, sname, tipo_cons,
            vettore, cell, autista, tipo_mezzo, indirizzo,
            c_abb, c_calz, c_eco, c_oth, c_var, c_cont, c_mat,
            c_dann, c_nonconf, anomalie, "", stringa_val
        ))

        if len(rows_to_insert) >= batch_size:
            cur_sqlite.executemany("""
            INSERT OR REPLACE INTO bolle (
                access_id, data, data_consegna, id_store, punto_vendita, store_name, tipo_cons,
                vettore, cell_autista, autista, tipo_mezzo, indirizzo_destino,
                colli_abbigl, colli_calzat, colli_ecom, colli_others, colli_vario, colli_cont,
                colli_mat_vario, colli_dann, colli_non_conf, anomalie_scarico, intershops_json, stringa
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows_to_insert)
            conn_sqlite.commit()
            total_inserted += len(rows_to_insert)
            rows_to_insert = []
            if progress_callback:
                progress_callback(total_inserted)

        rs.MoveNext()

    if rows_to_insert:
        cur_sqlite.executemany("""
        INSERT OR REPLACE INTO bolle (
            access_id, data, data_consegna, id_store, punto_vendita, store_name, tipo_cons,
            vettore, cell_autista, autista, tipo_mezzo, indirizzo_destino,
            colli_abbigl, colli_calzat, colli_ecom, colli_others, colli_vario, colli_cont,
            colli_mat_vario, colli_dann, colli_non_conf, anomalie_scarico, intershops_json, stringa
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows_to_insert)
        conn_sqlite.commit()
        total_inserted += len(rows_to_insert)

    rs.Close()
    conn_acc.Close()
    conn_sqlite.close()

    return total_inserted


if __name__ == "__main__":
    t0 = time.time()
    print("Starting Access migration to SQLite...")
    n = migrate_access_to_sqlite()
    print(f"Migration completed in {time.time() - t0:.2f}s! Total records migrated: {n}")
