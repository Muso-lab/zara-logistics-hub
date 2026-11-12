"""
Bolle Manager: Native management of delivery notes (bolle) in SQLite.
Completely replaces Microsoft Access (BOLLE INDITEX_rev.6.mdb).
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
import pandas as pd

from src.config import DB_PATH, DATA_DIR


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if pd.isna(val) or val is None or str(val).strip() == "":
            return default
        return float(val)
    except:
        return default


def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    except Exception:
        pass
    return conn


def init_bolle_tables(db_path: Path = DB_PATH):
    """Ensures bolle and store_delivery_profiles tables exist."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bolle_data ON bolle(data);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bolle_datac ON bolle(data_consegna);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bolle_store ON bolle(id_store);")

    # Migration: add note and prev_* columns if missing
    cur.execute("PRAGMA table_info(bolle);")
    existing_b_cols = [r[1] for r in cur.fetchall()]
    new_cols_defs = [
        ("note", "TEXT"),
        ("sigillo", "TEXT"),
        ("prev_abbigl", "REAL DEFAULT 0"),
        ("prev_calzat", "REAL DEFAULT 0"),
        ("prev_ecom", "REAL DEFAULT 0"),
        ("prev_others", "REAL DEFAULT 0"),
        ("prev_totale", "REAL DEFAULT 0"),
        ("spuntato", "INTEGER DEFAULT 0"),
    ]
    for col_n, col_d in new_cols_defs:
        if col_n not in existing_b_cols:
            try:
                cur.execute(f"ALTER TABLE bolle ADD COLUMN {col_n} {col_d};")
            except Exception:
                pass


    cur.execute("""
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
    conn.close()
    heal_shifted_bolle_dates(db_path=db_path)


def heal_shifted_bolle_dates(db_path: Path = DB_PATH) -> int:
    """
    Corregge automaticamente eventuali date traslate di -1 giorno a causa della
    serializzazione ISO UTC di Google Sheets (es. 2026-11-06T23:00:00.000Z -> Venerdì 06/11
    invece di Sabato 07/11 per /0 STD, e Sabato 07/11 invece di Domenica 08/11 per /9 DOPPIA),
    rimuove i duplicati traslati e ripulisce eventuali stringhe 'nan'.
    """
    from src.utils import parse_date_obj
    fixed_count = 0
    try:
        conn = get_db_connection(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS deleted_bolle (bolla_id INTEGER PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

        # 1. Ripulisce stringhe 'nan' / 'None' nei campi testuali
        for col_txt in ["note", "sigillo", "stringa", "anomalie_scarico", "autista", "cell_autista", "indirizzo_destino"]:
            try:
                cur.execute(f"UPDATE bolle SET {col_txt} = '' WHERE LOWER(TRIM(COALESCE({col_txt}, ''))) IN ('nan', 'none', 'null', 'nat')")
            except Exception:
                pass

        # 2. Normalizza eventuali timestamp ISO UTC (con 'T') in bolle e runs
        cur.execute("SELECT id, data, data_consegna FROM bolle WHERE data LIKE '%T%' OR data_consegna LIKE '%T%'")
        for bid, d_val, dc_val in cur.fetchall():
            new_d = parse_date_obj(d_val).strftime("%Y-%m-%d") if d_val else d_val
            new_dc = parse_date_obj(dc_val).strftime("%Y-%m-%d") if dc_val else new_d
            cur.execute("UPDATE bolle SET data = ?, data_consegna = ? WHERE id = ?", (new_d, new_dc, bid))
            fixed_count += 1

        try:
            cur.execute("SELECT id, run_date FROM runs WHERE run_date LIKE '%T%'")
            for rid, r_dt in cur.fetchall():
                new_rd = parse_date_obj(r_dt).strftime("%Y-%m-%d") if r_dt else r_dt
                cur.execute("UPDATE runs SET run_date = ? WHERE id = ?", (new_rd, rid))
        except Exception:
            pass

        # 3. Elimina record di test noti
        cur.execute(
            "SELECT id FROM bolle WHERE data LIKE '%2098%' OR data LIKE '%2099%' OR data LIKE '%2100%' "
            "OR data_consegna LIKE '%2098%' OR data_consegna LIKE '%2099%' OR data_consegna LIKE '%2100%' "
            "OR id_store = '9999' "
            "OR (data_consegna = '2026-11-01' AND tipo_cons = 'STD') "
            "OR (data_consegna = '2026-11-02' AND tipo_cons = 'DOPPIA') "
            "OR data_consegna = '2026-10-23' "
            "OR (data_consegna = '2026-10-24' AND tipo_cons = 'DOPPIA') "
            "OR (data_consegna = '2026-10-22' AND tipo_cons = 'STD')"
        )
        bad_ids = [int(r[0]) for r in cur.fetchall()]
        if bad_ids:
            for b_id in bad_ids:
                cur.execute("INSERT OR REPLACE INTO deleted_bolle (bolla_id) VALUES (?)", (b_id,))
            ph = ",".join("?" for _ in bad_ids)
            cur.execute(f"DELETE FROM bolle WHERE id IN ({ph})", bad_ids)
            fixed_count += len(bad_ids)

        # 4. Riallinea le bolle traslate di -1/-2/-3 giorni a causa della conversione UTC di Google Sheets:
        #    - W46 LUN-MER: Martedì 10/11 STD -> Mercoledì 11/11 STD; Mercoledì 11/11 DOPPIA -> Giovedì 12/11 DOPPIA
        #    - W45 GIOV-DOM: Venerdì 06/11 (o 05/11, 03/11) STD -> Sabato 07/11 STD;
        #                    Sabato 07/11 (o 06/11, 04/11) DOPPIA -> Domenica 08/11 DOPPIA
        #    - W44 GIOV-DOM: Venerdì 30/10 STD -> Sabato 31/10 STD; Sabato 31/10 DOPPIA -> Domenica 01/11 DOPPIA
        shift_pairs = [
            ("2026-11-11", "DOPPIA", "2026-11-12", "2026-11-09"),
            ("2026-11-10", "STD", "2026-11-11", "2026-11-09"),
            ("2026-11-07", "DOPPIA", "2026-11-08", "2026-11-05"),
            ("2026-11-06", "DOPPIA", "2026-11-08", "2026-11-05"),
            ("2026-11-04", "DOPPIA", "2026-11-08", "2026-11-05"),
            ("2026-11-06", "STD", "2026-11-07", "2026-11-05"),
            ("2026-11-05", "STD", "2026-11-07", "2026-11-05"),
            ("2026-11-03", "STD", "2026-11-07", "2026-11-05"),
            ("2026-10-31", "DOPPIA", "2026-11-01", "2026-10-29"),
            ("2026-10-30", "STD", "2026-10-31", "2026-10-29"),
        ]
        for wrong_dc, t_cons, right_dc, right_data in shift_pairs:
            cur.execute(
                "SELECT id, id_store, spuntato, colli_abbigl, colli_calzat, colli_ecom, colli_others, colli_vario, note, intershops_json, stringa "
                "FROM bolle WHERE data_consegna = ? AND UPPER(tipo_cons) = ?",
                (wrong_dc, t_cons),
            )
            wrong_rows = cur.fetchall()
            for w_row in wrong_rows:
                w_id, w_sid, w_sp, w_abb, w_cal, w_eco, w_oth, w_var, w_note, w_ij, w_str = w_row
                cur.execute(
                    "SELECT id, spuntato FROM bolle WHERE data_consegna = ? AND id_store = ? AND UPPER(tipo_cons) = ?",
                    (right_dc, w_sid, t_cons),
                )
                existing_right = cur.fetchone()
                if existing_right:
                    r_id, r_sp = existing_right
                    if int(w_sp or 0) == 1 and int(r_sp or 0) == 0:
                        cur.execute(
                            "UPDATE bolle SET spuntato = 1, colli_abbigl = ?, colli_calzat = ?, colli_ecom = ?, "
                            "colli_others = ?, colli_vario = ?, note = COALESCE(NULLIF(?, ''), note), "
                            "intershops_json = COALESCE(NULLIF(?, ''), intershops_json), "
                            "stringa = COALESCE(NULLIF(?, ''), stringa) WHERE id = ?",
                            (w_abb, w_cal, w_eco, w_oth, w_var, w_note, w_ij, w_str, r_id),
                        )
                    cur.execute("INSERT OR REPLACE INTO deleted_bolle (bolla_id) VALUES (?)", (w_id,))
                    cur.execute("DELETE FROM bolle WHERE id = ?", (w_id,))
                else:
                    cur.execute(
                        "UPDATE bolle SET data_consegna = ?, data = ? WHERE id = ?",
                        (right_dc, right_data, w_id),
                    )
                fixed_count += 1

        conn.commit()
        conn.close()
    except Exception:
        pass
    return fixed_count


def get_bolle_dates(limit: int = 100, db_path: Path = DB_PATH) -> List[str]:
    """Returns sorted unique delivery dates available in bolle."""
    from src.utils import parse_date_obj
    heal_shifted_bolle_dates(db_path=db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT COALESCE(NULLIF(data_consegna, ''), data) as dt 
        FROM bolle 
        WHERE dt IS NOT NULL AND dt != ''
          AND dt NOT LIKE '%2098%' AND dt NOT LIKE '%2099%' AND dt NOT LIKE '%2100%'
        ORDER BY dt DESC 
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    cleaned = []
    for r in rows:
        val = str(r[0]).strip() if r[0] else ""
        if not val or "2098" in val or "2099" in val or "2100" in val:
            continue
        try:
            d_iso = parse_date_obj(val).strftime("%Y-%m-%d")
            cleaned.append(d_iso)
        except Exception:
            if len(val) >= 10 and val[4] == '-' and val[7] == '-':
                cleaned.append(val[:10])
    return list(dict.fromkeys(cleaned))


def get_all_drivers(db_path: Path = DB_PATH) -> List[str]:
    """Returns unique autisti from bolle and store profiles."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT autista FROM store_delivery_profiles WHERE autista IS NOT NULL AND autista != ''
        UNION
        SELECT DISTINCT autista FROM bolle WHERE autista IS NOT NULL AND autista != ''
        ORDER BY 1 ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def get_all_carriers(db_path: Path = DB_PATH) -> List[str]:
    """Returns unique vettori."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT vettore FROM bolle WHERE vettore IS NOT NULL AND vettore != ''
        ORDER BY 1 ASC
    """)
    rows = cur.fetchall()
    conn.close()
    res = [r[0] for r in rows if r[0]]
    if not res:
        res = ["LACCHI SPA", "TRANSMEC"]
    return res


def get_store_delivery_profile(store_id: str, tipo_cons: str = "STD", db_path: Path = DB_PATH) -> Dict[str, Any]:
    """Returns delivery profile for a store directly from the unified master stores table."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    sid = str(store_id).strip()

    is_explicit_b = sid.endswith("B")
    effective_tipo = "DOPPIA" if is_explicit_b else str(tipo_cons).strip().upper()

    s_row = None
    if effective_tipo == "DOPPIA" and not is_explicit_b:
        cur.execute("SELECT * FROM stores WHERE store_id = ?", (f"{sid}B",))
        s_row = cur.fetchone()

    if not s_row:
        cur.execute("SELECT * FROM stores WHERE store_id = ?", (sid,))
        s_row = cur.fetchone()

    conn.close()

    res = {
        "id_store": sid,
        "tipo_cons": effective_tipo,
        "punto_vendita": "",
        "store_name": "",
        "provincia": "",
        "tipo_mezzo": "",
        "autista": "",
        "cell_autista": "",
        "vettore": "LACCHI SPA",
        "indirizzo": ""
    }

    if s_row:
        s_dict = dict(s_row)
        res["punto_vendita"] = s_dict.get("brand") or s_dict.get("punto_vendita", "")
        res["store_name"] = s_dict.get("store_name", "")
        res["provincia"] = s_dict.get("provincia", "")
        res["vettore"] = s_dict.get("vettore") or "LACCHI SPA"
        res["indirizzo"] = s_dict.get("indirizzo", "")
        res["cell_autista"] = s_dict.get("cell_autista", "")

        if res["tipo_cons"] == "DOPPIA":
            res["autista"] = s_dict.get("autista_doppia") or s_dict.get("autista", "")
            res["tipo_mezzo"] = s_dict.get("tipo_mezzo") or s_dict.get("tipo_mezzo_doppia") or "FURGONE 8"
        else:
            res["autista"] = s_dict.get("autista", "")
            res["tipo_mezzo"] = s_dict.get("tipo_mezzo", "MOTRICE 18 PLT")

    return res


def list_store_delivery_profiles(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Returns active delivery profiles constructed directly from stores table."""
    conn = get_db_connection(db_path)
    df_s = pd.read_sql("SELECT * FROM stores WHERE attivo = 'SI' ORDER BY giro, store_id", conn)
    conn.close()
    
    rows = []
    for _, r in df_s.iterrows():
        sid = str(r["store_id"]).strip()
        sname = str(r.get("store_name", "")).strip()
        pv = str(r.get("brand") or r.get("punto_vendita", "")).strip()
        prov = str(r.get("provincia", "")).strip()
        vet = str(r.get("vettore", "LACCHI SPA")).strip()
        ind = str(r.get("indirizzo", "")).strip()
        aut = str(r.get("autista", "")).strip()
        cell = str(r.get("cell_autista", "")).strip()
        aut_str = f"{aut} ({cell})" if cell else aut
        tm = str(r.get("tipo_mezzo", "")).strip() or "MOTRICE 18 PLT"
        
        # Standard delivery row
        rows.append({
            "id_store": sid,
            "tipo_cons": "STD",
            "punto_vendita": pv,
            "store_name": sname,
            "provincia": prov,
            "tipo_mezzo": tm,
            "autista": aut_str,
            "indirizzo": ind
        })
        
        # If store has /9 split (DOPPIA)
        if str(r.get("sdoppiamento_b9", "NO")).upper() == "SI":
            aut_d = str(r.get("autista_doppia", "")).strip() or aut
            aut_d_str = f"{aut_d} ({cell})" if cell and aut_d == aut else aut_d
            tm_d = str(r.get("tipo_mezzo_doppia", "")).strip() or "FURGONE"
            rows.append({
                "id_store": sid,
                "tipo_cons": "DOPPIA",
                "punto_vendita": pv,
                "store_name": sname,
                "provincia": prov,
                "tipo_mezzo": tm_d,
                "autista": aut_d_str,
                "indirizzo": ind
            })
            
    return pd.DataFrame(rows)


def save_store_delivery_profile(profile: Dict[str, Any], db_path: Path = DB_PATH):
    """Saves profile updates directly into stores table, creating store if not yet in database."""
    sid = str(profile.get("id_store", "")).strip()
    tipo_cons = str(profile.get("tipo_cons", "STD")).strip().upper()
    if not sid:
        return
    from src.db import update_store_record, add_store_record, get_stores_df
    df_s = get_stores_df(db_path=db_path)
    if df_s.empty or sid not in df_s["store_id"].values:
        add_store_record({
            "store_id": sid,
            "store_name": profile.get("store_name", sid),
            "punto_vendita": profile.get("punto_vendita", "ZARA"),
            "brand": profile.get("punto_vendita", "ZARA"),
            "autista": profile.get("autista", "") if tipo_cons != "DOPPIA" else "",
            "autista_doppia": profile.get("autista", "") if tipo_cons == "DOPPIA" else "",
            "tipo_mezzo": profile.get("tipo_mezzo", "MOTRICE 18 PLT") if tipo_cons != "DOPPIA" else "MOTRICE 18 PLT",
            "tipo_mezzo_doppia": profile.get("tipo_mezzo", "FURGONE") if tipo_cons == "DOPPIA" else "",
            "indirizzo": profile.get("indirizzo", ""),
            "provincia": profile.get("provincia", "RM"),
            "attivo": "SI"
        }, db_path=db_path)
    else:
        if tipo_cons == "DOPPIA":
            updates = {
                "autista_doppia": profile.get("autista", ""),
                "tipo_mezzo_doppia": profile.get("tipo_mezzo", "")
            }
        else:
            updates = {
                "store_name": profile.get("store_name", ""),
                "punto_vendita": profile.get("punto_vendita", ""),
                "provincia": profile.get("provincia", ""),
                "autista": profile.get("autista", ""),
                "tipo_mezzo": profile.get("tipo_mezzo", ""),
                "indirizzo": profile.get("indirizzo", "")
            }
        update_store_record(sid, updates, db_path=db_path)


def get_bolle(
    data: Optional[str] = None,
    data_consegna: Optional[str] = None,
    id_store: Optional[str] = None,
    tipo_cons: Optional[str] = None,
    autista: Optional[str] = None,
    vettore: Optional[str] = None,
    search: Optional[str] = None,
    db_path: Path = DB_PATH
) -> pd.DataFrame:
    """Filters bolle and returns a DataFrame."""
    conn = get_db_connection(db_path)
    query = ["SELECT * FROM bolle WHERE 1=1"]
    params = []

    if not (data and ("2098" in str(data) or "2099" in str(data))):
        query.append("AND data NOT LIKE '%2098%' AND data NOT LIKE '%2099%'")
        query.append("AND (data_consegna IS NULL OR (data_consegna NOT LIKE '%2098%' AND data_consegna NOT LIKE '%2099%'))")

    if data:
        query.append("AND (data = ? OR data_consegna = ?)")
        params.extend([data, data])
    if data_consegna:
        query.append("AND data_consegna = ?")
        params.append(data_consegna)
    if id_store:
        query.append("AND id_store = ?")
        params.append(str(id_store).strip())
    if tipo_cons and tipo_cons != "TUTTI":
        query.append("AND tipo_cons = ?")
        params.append(tipo_cons.strip().upper())
    if autista and autista != "TUTTI":
        query.append("AND autista LIKE ?")
        params.append(f"%{autista.strip()}%")
    if vettore and vettore != "TUTTI":
        query.append("AND vettore LIKE ?")
        params.append(f"%{vettore.strip()}%")
    if search:
        query.append("AND (id_store LIKE ? OR store_name LIKE ? OR punto_vendita LIKE ? OR indirizzo_destino LIKE ? OR stringa LIKE ?)")
        s = f"%{search.strip()}%"
        params.extend([s, s, s, s, s])

    query.append("ORDER BY data_consegna DESC, id_store ASC, tipo_cons ASC")
    df = pd.read_sql(" ".join(query), conn, params=params)
    conn.close()
    if not df.empty:
        colli_cols = [c for c in ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario", "colli_cont", "colli_mat_vario"] if c in df.columns]
        df["TOT_COLLI"] = df[colli_cols].fillna(0).sum(axis=1) if colli_cols else 0.0
        if "prev_totale" not in df.columns:
            df["prev_totale"] = 0.0
        if "spuntato" not in df.columns:
            df["spuntato"] = 0
    else:
        df["TOT_COLLI"] = pd.Series(dtype=float)
        if "prev_totale" not in df.columns:
            df["prev_totale"] = pd.Series(dtype=float)
        if "spuntato" not in df.columns:
            df["spuntato"] = pd.Series(dtype=int)
    return df


def get_bolle_by_date(delivery_date: Any, db_path: Path = DB_PATH) -> pd.DataFrame:
    """Returns all bolle for a given delivery date (YYYY-MM-DD or date object)."""
    from src.utils import parse_date_obj
    if isinstance(delivery_date, (date, datetime)):
        d_str = delivery_date.strftime("%Y-%m-%d")
    else:
        try:
            d_str = parse_date_obj(delivery_date).strftime("%Y-%m-%d")
        except Exception:
            d_str = str(delivery_date).strip()[:10]
    return get_bolle(data_consegna=d_str, db_path=db_path)


def get_bolla_by_id(bolla_id: int, db_path: Path = DB_PATH) -> Optional[Dict[str, Any]]:
    """Returns single bolla dict by id."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM bolle WHERE id = ?", (bolla_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        colli_cols = ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario", "colli_cont", "colli_mat_vario"]
        d["TOT_COLLI"] = sum(float(d.get(c, 0) or 0) for c in colli_cols)
        return d
    return None


def format_intershops_string(intershops_list: List[Dict[str, Any]]) -> str:
    """
    Formats list of intershop items into string:
    e.g. [{"mittente": "3680", "colli": 6, "tipo": "MERCE", "descrizione": "Manichini"}] -> "6C MERCE (Manichini) da 3680"
    """
    parts = []
    for item in intershops_list:
        try:
            c = float(item.get("colli", 0))
        except:
            c = 0.0
        if c <= 0:
            continue
        p = f"{int(c)}C"
        t = str(item.get("tipo", "")).strip()
        d = str(item.get("descrizione", "") or "").strip()
        m = str(item.get("mittente", "")).strip()
        if t and t.upper() not in ("NONE", "NAN"):
            p += f" {t}"
        if d and d.upper() not in ("NONE", "NAN") and d.upper() != t.upper():
            p += f" ({d})"
        if m and m.upper() not in ("NONE", "NAN"):
            p += f" da {m}"
        parts.append(p)
    return " ".join(parts)


def parse_intershops_string(stringa: str) -> List[Dict[str, Any]]:
    """Parses a string like '6C MERCE da 3680 4C CESTE' back into structured records."""
    if not stringa or not stringa.strip():
        return []
    items = []
    # If JSON was saved, prefer it
    try:
        data = json.loads(stringa)
        if isinstance(data, list):
            return data
    except:
        pass
    # Basic textual fallback representation
    return [{"mittente": "", "colli": 0, "tipo": stringa}]


def save_or_update_bolla(data: Dict[str, Any], db_path: Path = DB_PATH, sync_cloud: bool = True) -> int:
    """Inserts or updates a delivery note in SQLite."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    b_id = data.get("id")

    # If intershops_list is present, compute stringa and json
    inter_list = data.get("intershops_list")
    if inter_list is not None and isinstance(inter_list, list):
        stringa_val = format_intershops_string(inter_list)
        inter_json = json.dumps(inter_list)
    else:
        stringa_val = data.get("stringa", "")
        inter_json = data.get("intershops_json", "")

    if b_id and int(b_id) > 0:
        cur.execute("""
        UPDATE bolle SET
            data = ?,
            data_consegna = ?,
            id_store = ?,
            punto_vendita = ?,
            store_name = ?,
            tipo_cons = ?,
            vettore = ?,
            cell_autista = ?,
            autista = ?,
            tipo_mezzo = ?,
            indirizzo_destino = ?,
            colli_abbigl = ?,
            colli_calzat = ?,
            colli_ecom = ?,
            colli_others = ?,
            colli_vario = ?,
            colli_cont = ?,
            colli_mat_vario = ?,
            colli_dann = ?,
            colli_non_conf = ?,
            anomalie_scarico = ?,
            intershops_json = ?,
            stringa = ?,
            note = COALESCE(?, note),
            sigillo = CASE WHEN ? IS NOT NULL THEN ? ELSE sigillo END,
            prev_abbigl = CASE WHEN ? IS NOT NULL THEN ? ELSE prev_abbigl END,
            prev_calzat = CASE WHEN ? IS NOT NULL THEN ? ELSE prev_calzat END,
            prev_ecom = CASE WHEN ? IS NOT NULL THEN ? ELSE prev_ecom END,
            prev_others = CASE WHEN ? IS NOT NULL THEN ? ELSE prev_others END,
            prev_totale = CASE WHEN ? IS NOT NULL THEN ? ELSE prev_totale END,
            spuntato = COALESCE(?, spuntato)
        WHERE id = ?
        """, (
            data.get("data", datetime.now().strftime("%Y-%m-%d")),
            data.get("data_consegna", data.get("data", datetime.now().strftime("%Y-%m-%d"))),
            str(data.get("id_store", "")).strip(),
            data.get("punto_vendita", ""),
            data.get("store_name", ""),
            str(data.get("tipo_cons", "STD")).strip().upper(),
            data.get("vettore", "LACCHI SPA"),
            data.get("cell_autista", ""),
            data.get("autista", ""),
            data.get("tipo_mezzo", ""),
            data.get("indirizzo_destino", ""),
            int(round(float(data.get("colli_abbigl", 0) or 0))),
            int(round(float(data.get("colli_calzat", 0) or 0))),
            int(round(float(data.get("colli_ecom", 0) or 0))),
            int(round(float(data.get("colli_others", 0) or 0))),
            int(round(float(data.get("colli_vario", 0) or 0))),
            int(round(float(data.get("colli_cont", 0) or 0))),
            int(round(float(data.get("colli_mat_vario", 0) or 0))),
            int(round(float(data.get("colli_dann", 0) or 0))),
            int(round(float(data.get("colli_non_conf", 0) or 0))),
            data.get("anomalie_scarico", ""),
            inter_json,
            stringa_val,
            data.get("note", None),
            data.get("sigillo", None), data.get("sigillo", None),
            data.get("prev_abbigl", None), data.get("prev_abbigl", None),
            data.get("prev_calzat", None), data.get("prev_calzat", None),
            data.get("prev_ecom", None), data.get("prev_ecom", None),
            data.get("prev_others", None), data.get("prev_others", None),
            data.get("prev_totale", None), data.get("prev_totale", None),
            data.get("spuntato", None),
            int(b_id)
        ))
        res_id = int(b_id)
    else:
        cur.execute("""
        INSERT INTO bolle (
            data, data_consegna, id_store, punto_vendita, store_name, tipo_cons,
            vettore, cell_autista, autista, tipo_mezzo, indirizzo_destino,
            colli_abbigl, colli_calzat, colli_ecom, colli_others, colli_vario,
            colli_cont, colli_mat_vario, colli_dann, colli_non_conf,
            anomalie_scarico, intershops_json, stringa,
            note, sigillo, prev_abbigl, prev_calzat, prev_ecom, prev_others, prev_totale, spuntato
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("data", datetime.now().strftime("%Y-%m-%d")),
            data.get("data_consegna", data.get("data", datetime.now().strftime("%Y-%m-%d"))),
            str(data.get("id_store", "")).strip(),
            data.get("punto_vendita", ""),
            data.get("store_name", ""),
            str(data.get("tipo_cons", "STD")).strip().upper(),
            data.get("vettore", "LACCHI SPA"),
            data.get("cell_autista", ""),
            data.get("autista", ""),
            data.get("tipo_mezzo", ""),
            data.get("indirizzo_destino", ""),
            int(round(float(data.get("colli_abbigl", 0) or 0))),
            int(round(float(data.get("colli_calzat", 0) or 0))),
            int(round(float(data.get("colli_ecom", 0) or 0))),
            int(round(float(data.get("colli_others", 0) or 0))),
            int(round(float(data.get("colli_vario", 0) or 0))),
            int(round(float(data.get("colli_cont", 0) or 0))),
            int(round(float(data.get("colli_mat_vario", 0) or 0))),
            int(round(float(data.get("colli_dann", 0) or 0))),
            int(round(float(data.get("colli_non_conf", 0) or 0))),
            data.get("anomalie_scarico", ""),
            inter_json,
            stringa_val,
            data.get("note", ""),
            data.get("sigillo", ""),
            float(data.get("prev_abbigl") or data.get("colli_abbigl") or 0.0),
            float(data.get("prev_calzat") or data.get("colli_calzat") or 0.0),
            float(data.get("prev_ecom") or data.get("colli_ecom") or 0.0),
            float(data.get("prev_others") or data.get("colli_others") or 0.0),
            float(data.get("prev_totale") or (float(data.get("colli_abbigl") or 0) + float(data.get("colli_calzat") or 0) + float(data.get("colli_ecom") or 0) + float(data.get("colli_others") or 0))),
            int(data.get("spuntato", 0))
        ))
        res_id = cur.lastrowid

    conn.commit()
    conn.close()
    if sync_cloud:
        from src.cloud_sync import auto_sync_tables
        auto_sync_tables(["bolle"])
    return res_id


def delete_bolla(bolla_id: int, db_path: Path = DB_PATH) -> bool:
    """Deletes a single bolla by id and blacklists it so cloud pull never revives it."""
    bid = int(bolla_id)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS deleted_bolle (bolla_id INTEGER PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cur.execute("INSERT OR REPLACE INTO deleted_bolle (bolla_id) VALUES (?)", (bid,))
    cur.execute("DELETE FROM bolle WHERE id = ?", (bid,))
    rows_affected = cur.rowcount
    conn.commit()
    conn.close()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["bolle", "deleted_bolle"])
    return rows_affected > 0


def delete_bolle_by_date(date_str: str, db_path: Path = DB_PATH) -> int:
    """
    Deletes all bolle for a specific delivery date.
    Robustly matches across all formats (YYYY-MM-DD, DD/MM/YYYY, ISO timestamps).
    Blacklists deleted IDs so cloud sync never restores them.
    """
    from src.utils import parse_date_obj
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS deleted_bolle (bolla_id INTEGER PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    d_obj = None
    try:
        d_obj = parse_date_obj(date_str)
    except Exception:
        pass

    patterns = [str(date_str).strip()]
    if d_obj:
        patterns.append(d_obj.strftime("%Y-%m-%d"))
        patterns.append(d_obj.strftime("%d/%m/%Y"))

    cur.execute("SELECT id, data, data_consegna FROM bolle")
    all_b = cur.fetchall()
    to_delete = []
    for b_id, b_data, b_data_cons in all_b:
        matched = False
        for p in patterns:
            if (b_data and p in str(b_data)) or (b_data_cons and p in str(b_data_cons)):
                matched = True
                break
        if not matched and d_obj:
            for cand in [b_data_cons, b_data]:
                if cand:
                    try:
                        if parse_date_obj(cand) == d_obj:
                            matched = True
                            break
                    except Exception:
                        pass
        if matched:
            to_delete.append(b_id)

    if to_delete:
        placeholders = ",".join("?" for _ in to_delete)
        for bid in to_delete:
            cur.execute("INSERT OR REPLACE INTO deleted_bolle (bolla_id) VALUES (?)", (bid,))
        cur.execute(f"DELETE FROM bolle WHERE id IN ({placeholders})", to_delete)
        n = len(to_delete)
    else:
        n = 0

    conn.commit()
    conn.close()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["bolle", "deleted_bolle"])
    return n


def compute_inditex_delivery_dates(dt_base: Any, cycle_type: str = "LUN-MER") -> Tuple[date, date]:
    """
    Calcola le date di consegna operative Inditex con rigorosa corrispondenza:
    - /0 (Standard / STD) e SEMPRE il Mercoledi e il Sabato:
        - Ciclo LUN-MER: Mercoledi (monday + 2 giorni)
        - Ciclo GIOV-DOM: Sabato (monday + 5 giorni)
    - /9 (DOPPIA / 2a Uscita) e SEMPRE il Giovedi e la Domenica:
        - Ciclo LUN-MER: Giovedi (monday + 3 giorni)
        - Ciclo GIOV-DOM: Domenica (monday + 6 giorni)
    Ritorna: (date_b9, date_b0)
    """
    from src.utils import parse_date_obj
    if isinstance(dt_base, str):
        try:
            dt_base = parse_date_obj(dt_base, default=date.today())
        except:
            dt_base = date.today()
    elif isinstance(dt_base, datetime):
        dt_base = dt_base.date()
    elif not isinstance(dt_base, date):
        dt_base = date.today()

    monday = dt_base - timedelta(days=dt_base.weekday())
    cyc_up = str(cycle_type or "").strip().upper()
    if "GIO" in cyc_up or "SAB" in cyc_up or "DOM" in cyc_up:
        is_midweek = False
    elif "LUN" in cyc_up or "MER" in cyc_up:
        is_midweek = True
    else:
        is_midweek = (dt_base.weekday() <= 2)

    # Se si lancia di Domenica un ciclo LUN-MER, il lunedì di riferimento è il giorno successivo
    if is_midweek and dt_base.weekday() == 6:
        monday = dt_base + timedelta(days=1)

    if is_midweek:
        # LUN-MER:
        # /0 (Standard / STD) = Mercoledi (monday + 2 giorni)
        # /9 (DOPPIA / 2a Uscita) = Giovedi (monday + 3 giorni)
        date_b0 = monday + timedelta(days=2)  # Mercoledi (/0 STD)
        date_b9 = monday + timedelta(days=3)  # Giovedi (/9 DOPPIA)
    else:
        # GIOV-DOM:
        # /0 (Standard / STD) = Sabato (monday + 5 giorni)
        # /9 (DOPPIA / 2a Uscita) = Domenica (monday + 6 giorni)
        date_b0 = monday + timedelta(days=5)  # Sabato (/0 STD)
        date_b9 = monday + timedelta(days=6)  # Domenica (/9 DOPPIA)

    return date_b9, date_b0


def generate_bolle_from_forecast(
    run_id: int,
    delivery_date: Optional[str] = None,
    overwrite: bool = False,
    db_path: Path = DB_PATH,
    delivery_date_std: Optional[str] = None,
    delivery_date_dop: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Generates bolle directly from the forecast analysis, spunta arrivi and planning of run_id.
    Pre-fills store addresses, carrier, and vehicle from master stores table.
    Creates STD and DOPPIA bolle as needed, preserving exact 100% total colli.
    """
    conn = get_db_connection(db_path)
    # 1. Fetch run info
    df_run = pd.read_sql("SELECT * FROM runs WHERE id = ?", conn, params=(run_id,))
    if df_run.empty:
        conn.close()
        raise ValueError(f"Run {run_id} non trovata.")

    from src.utils import parse_date_obj
    raw_run_date = df_run.iloc[0]["run_date"]
    cycle_type = str(df_run.iloc[0].get("cycle_type", "LUN-MER")).strip().upper()
    try:
        dt_base = parse_date_obj(raw_run_date, default=date.today())
    except:
        dt_base = date.today()
    run_date = dt_base.strftime("%Y-%m-%d")

    default_dop_dt, default_std_dt = compute_inditex_delivery_dates(dt_base, cycle_type)

    if delivery_date_std and delivery_date_dop:
        deliv_date_std = str(delivery_date_std)[:10]
        deliv_date_dop = str(delivery_date_dop)[:10]
    elif delivery_date:
        try:
            dt_given = datetime.strptime(str(delivery_date)[:10], "%Y-%m-%d").date()
            if dt_given.weekday() in (3, 6):
                # Data /9 (Giovedi 3 o Domenica 6): /0 STD e il giorno precedente (Mercoledi 2 o Sabato 5)
                deliv_date_dop = dt_given.strftime("%Y-%m-%d")
                deliv_date_std = (dt_given - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                # Data /0 (Mercoledi 2 o Sabato 5 o altro): /9 DOPPIA e il giorno successivo (Giovedi 3 o Domenica 6)
                deliv_date_std = dt_given.strftime("%Y-%m-%d")
                if dt_given.weekday() in (2, 5):
                    deliv_date_dop = (dt_given + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    deliv_date_dop = dt_given.strftime("%Y-%m-%d")
        except:
            deliv_date_std = str(delivery_date)[:10]
            deliv_date_dop = str(delivery_date)[:10]
    else:
        deliv_date_dop = default_dop_dt.strftime("%Y-%m-%d")
        deliv_date_std = default_std_dt.strftime("%Y-%m-%d")

    # 2. If overwrite, delete existing bolle for both delivery dates
    if overwrite:
        cur = conn.cursor()
        cur.execute("DELETE FROM bolle WHERE data_consegna IN (?, ?) OR data IN (?, ?)", (deliv_date_std, deliv_date_dop, deliv_date_std, deliv_date_dop))
        conn.commit()

    # 3. Check existing stores already having bolle for these dates
    cur = conn.cursor()
    cur.execute("SELECT id_store, tipo_cons FROM bolle WHERE data_consegna IN (?, ?)", (deliv_date_std, deliv_date_dop))
    existing_pairs = set((str(r[0]), str(r[1]).upper()) for r in cur.fetchall())

    # 4. Read spunta_arrivi, planning_results, and stores master
    df_spunta = pd.read_sql("SELECT * FROM spunta_arrivi WHERE run_id = ? AND store_code IS NOT NULL AND store_code != ''", conn, params=(run_id,))
    df_planning = pd.read_sql("SELECT * FROM planning_results WHERE run_id = ?", conn, params=(run_id,))
    df_stores = pd.read_sql("SELECT * FROM stores", conn)
    stores_meta = {str(r["store_id"]).strip(): r.to_dict() for _, r in df_stores.iterrows()}
    conn.close()

    # Determine which stores have dedicated SHOES rows in planner template
    stores_with_shoes = set()
    try:
        with open(DATA_DIR / "planner_template.json", "r", encoding="utf-8") as f:
            t_rows = json.load(f)
            stores_with_shoes = {
                str(r["store_code"]).strip()
                for r in t_rows
                if "SHOES" in str(r.get("brand", "")).upper()
            }
    except:
        pass

    # Aggregate total planned quantities cleanly per physical store ID
    store_planned = {}
    if not df_spunta.empty:
        # Preferred source: spunta_arrivi has the clean 100% total per physical store on is_barra9 == 0
        for _, sp in df_spunta.iterrows():
            raw_code = str(sp.get("store_code", "")).strip()
            if not raw_code or raw_code.upper() in ["NEGOZIO", "STORE ID", "EXTRA", "TOTAL", "TOTALE", "NONE", "DA ASSEGNARE"]:
                continue
            is_b9 = int(sp.get("is_barra9", 0)) == 1 or raw_code.endswith("B")
            if is_b9:
                continue
            base_sid = raw_code
            if base_sid not in store_planned:
                meta = stores_meta.get(base_sid, {})
                store_planned[base_sid] = {
                    "textile": 0.0,
                    "shoes": 0.0,
                    "others": 0.0,
                    "ecom": 0.0,
                    "punto_vendita": meta.get("brand") or sp.get("punto_vendita") or "ZARA",
                    "store_name": meta.get("store_name") or sp.get("store_name", "")
                }
            store_planned[base_sid]["textile"] += _safe_float(sp.get("textile_attesi", 0.0))
            store_planned[base_sid]["shoes"] += _safe_float(sp.get("shoes_attesi", 0.0))
            store_planned[base_sid]["others"] += _safe_float(sp.get("other_attesi", 0.0))
            store_planned[base_sid]["ecom"] += _safe_float(sp.get("ecom_attesi", 0.0))
    elif not df_planning.empty:
        seen_store_codes = set()
        for _, r in df_planning.iterrows():
            raw_code = str(r["store_code"]).strip()
            if not raw_code or raw_code.upper() in ["NEGOZIO", "STORE ID", "EXTRA", "TOTAL", "TOTALE", "NONE", "DA ASSEGNARE"]:
                continue
            base_sid = raw_code[:-1] if raw_code.endswith("B") else raw_code
            b_name = str(r.get("brand", "")).upper()
            is_shoes = "SHOES" in b_name
            # Prevent duplicate placeholder lines while allowing Barra 9 and shoes lines
            key_line = (raw_code, is_shoes)
            if key_line in seen_store_codes:
                continue
            seen_store_codes.add(key_line)

            if base_sid not in store_planned:
                meta = stores_meta.get(base_sid, {})
                store_planned[base_sid] = {
                    "textile": 0.0,
                    "shoes": 0.0,
                    "others": 0.0,
                    "ecom": 0.0,
                    "punto_vendita": meta.get("brand") or r.get("brand", "ZARA"),
                    "store_name": meta.get("store_name") or r.get("store_name", "")
                }
            if is_shoes:
                store_planned[base_sid]["shoes"] += _safe_float(r.get("planned_shoes", 0.0))
            else:
                store_planned[base_sid]["textile"] += _safe_float(r.get("planned_textile", 0.0))
                if base_sid not in stores_with_shoes or raw_code.endswith("B"):
                    store_planned[base_sid]["shoes"] += _safe_float(r.get("planned_shoes", 0.0))
                store_planned[base_sid]["others"] += _safe_float(r.get("planned_others", 0.0))
                store_planned[base_sid]["ecom"] += _safe_float(r.get("planned_ecom", 0.0))

    # Garantisce che TUTTI i negozi attivi dell'anagrafica (tabella stores) siano sempre presenti
    # anche se avevano 0 colli in previsione, così da pescare sempre dallo stesso DB completo
    for m_sid, m_row in stores_meta.items():
        if not m_sid or m_sid.endswith("B") or m_sid.upper() in ["NEGOZIO", "STORE ID", "EXTRA", "TOTAL", "TOTALE", "NONE", "DA ASSEGNARE"]:
            continue
        if str(m_row.get("attivo", "SI") or "SI").strip().upper() != "SI":
            continue
        if m_sid not in store_planned:
            store_planned[m_sid] = {
                "textile": 0.0,
                "shoes": 0.0,
                "others": 0.0,
                "ecom": 0.0,
                "punto_vendita": m_row.get("brand") or "ZARA",
                "store_name": m_row.get("store_name") or "",
            }

    created = 0
    skipped = 0

    for base_sid, pdata in store_planned.items():
        meta = stores_meta.get(base_sid, {})
        pv = meta.get("brand") or meta.get("punto_vendita") or pdata.get("punto_vendita", "ZARA")
        sname = meta.get("store_name") or pdata.get("store_name", "")
        vettore = meta.get("vettore") or "LACCHI SPA"
        indirizzo = meta.get("indirizzo") or ""
        cell_autista = meta.get("cell_autista") or ""

        sdoppia = str(meta.get("sdoppiamento_b9", "NO")).strip().upper() == "SI"

        tot_tex = int(round(pdata["textile"]))
        tot_sho = int(round(pdata["shoes"]))
        tot_oth = int(round(pdata["others"]))
        tot_eco = int(round(pdata["ecom"]))

        if sdoppia:
            d_tex = int(round(tot_tex * 0.3))
            d_sho = int(round(tot_sho * 0.3))
            d_eco = int(round(tot_eco * 0.3))
            d_oth = int(round(tot_oth * 0.3))

            # 1. STD (/0) Bolla (70%)
            if (base_sid, "STD") in existing_pairs:
                skipped += 1
            else:
                std_abb = int(tot_tex - d_tex)
                std_calz = int(tot_sho - d_sho)
                std_eco = int(tot_eco - d_eco)
                std_oth = int(tot_oth - d_oth)
                std_tot = std_abb + std_calz + std_eco + std_oth
                bolla_std = {
                    "data": run_date,
                    "data_consegna": deliv_date_std,
                    "id_store": base_sid,
                    "punto_vendita": pv,
                    "store_name": sname,
                    "tipo_cons": "STD",
                    "vettore": vettore,
                    "cell_autista": "",
                    "autista": "",
                    "tipo_mezzo": meta.get("tipo_mezzo", "MOTRICE 18 PLT"),
                    "indirizzo_destino": indirizzo,
                    "colli_abbigl": std_abb,
                    "colli_calzat": std_calz,
                    "colli_ecom": std_eco,
                    "colli_others": std_oth,
                    "prev_abbigl": std_abb,
                    "prev_calzat": std_calz,
                    "prev_ecom": std_eco,
                    "prev_others": std_oth,
                    "prev_totale": std_tot,
                    "colli_vario": 0,
                    "colli_cont": 0,
                    "colli_mat_vario": 0,
                    "colli_dann": 0,
                    "colli_non_conf": 0,
                    "anomalie_scarico": "",
                    "note": "",
                    "sigillo": "",
                    "stringa": "",
                    "spuntato": 0
                }
                save_or_update_bolla(bolla_std, db_path=db_path, sync_cloud=False)
                created += 1

            # 2. DOPPIA (/9) Bolla (30%)
            if (base_sid, "DOPPIA") in existing_pairs:
                skipped += 1
            else:
                meta_b = stores_meta.get(f"{base_sid}B", {})
                b_vett = meta_b.get("vettore") or vettore
                b_mezzo = meta_b.get("tipo_mezzo") or meta.get("tipo_mezzo_doppia") or "FURGONE 8"
                dop_tot = d_tex + d_sho + d_eco + d_oth
                bolla_d = {
                    "data": run_date,
                    "data_consegna": deliv_date_dop,
                    "id_store": base_sid,
                    "punto_vendita": pv,
                    "store_name": sname,
                    "tipo_cons": "DOPPIA",
                    "vettore": b_vett,
                    "cell_autista": "",
                    "autista": "",
                    "tipo_mezzo": b_mezzo,
                    "indirizzo_destino": indirizzo,
                    "colli_abbigl": d_tex,
                    "colli_calzat": d_sho,
                    "colli_ecom": d_eco,
                    "colli_others": d_oth,
                    "prev_abbigl": d_tex,
                    "prev_calzat": d_sho,
                    "prev_ecom": d_eco,
                    "prev_others": d_oth,
                    "prev_totale": dop_tot,
                    "colli_vario": 0,
                    "colli_cont": 0,
                    "colli_mat_vario": 0,
                    "colli_dann": 0,
                    "colli_non_conf": 0,
                    "anomalie_scarico": "",
                    "note": "",
                    "sigillo": "",
                    "stringa": "",
                    "spuntato": 0
                }
                save_or_update_bolla(bolla_d, db_path=db_path, sync_cloud=False)
                created += 1
        else:
            # Single STD Bolla (100%)
            if (base_sid, "STD") in existing_pairs:
                skipped += 1
            else:
                sng_tot = tot_tex + tot_sho + tot_eco + tot_oth
                bolla_single = {
                    "data": run_date,
                    "data_consegna": deliv_date_std,
                    "id_store": base_sid,
                    "punto_vendita": pv,
                    "store_name": sname,
                    "tipo_cons": "STD",
                    "vettore": vettore,
                    "cell_autista": "",
                    "autista": "",
                    "tipo_mezzo": meta.get("tipo_mezzo", "MOTRICE 18 PLT"),
                    "indirizzo_destino": indirizzo,
                    "colli_abbigl": tot_tex,
                    "colli_calzat": tot_sho,
                    "colli_ecom": tot_eco,
                    "colli_others": tot_oth,
                    "prev_abbigl": tot_tex,
                    "prev_calzat": tot_sho,
                    "prev_ecom": tot_eco,
                    "prev_others": tot_oth,
                    "prev_totale": sng_tot,
                    "colli_vario": 0,
                    "colli_cont": 0,
                    "colli_mat_vario": 0,
                    "colli_dann": 0,
                    "colli_non_conf": 0,
                    "anomalie_scarico": "",
                    "note": "",
                    "sigillo": "",
                    "stringa": "",
                    "spuntato": 0
                }
                save_or_update_bolla(bolla_single, db_path=db_path, sync_cloud=False)
                created += 1

    if created > 0 or overwrite:
        from src.cloud_sync import auto_sync_tables
        auto_sync_tables(["bolle"])

    return created, skipped


def get_actuals_for_planner(target_date: Union[str, List[str], Tuple[str, ...]], db_path: Path = DB_PATH) -> pd.DataFrame:
    """
    Extracts actual delivered totals and intershops directly from SQLite bolle
    for the specified delivery date(s), ready for compute_planning_roma().
    Supports a single date string or a list/tuple of dates (e.g. both /0 and /9 dates of an operative cycle).
    Returns DataFrame with columns: ID_STORE, tipo_cons, TOT_ABBIGL, TOT_CALZAT, TOT_ECOM, TOT_OTHERS, stringa.
    """
    conn = get_db_connection(db_path)
    if isinstance(target_date, (list, tuple, set)):
        date_list = [str(d)[:10] for d in target_date]
        placeholders = ",".join("?" for _ in date_list)
        query = f"""
        SELECT 
            id_store AS ID_STORE,
            tipo_cons,
            colli_abbigl AS TOT_ABBIGL,
            colli_calzat AS TOT_CALZAT,
            colli_ecom AS TOT_ECOM,
            colli_others AS TOT_OTHERS,
            colli_vario AS TOT_VARIO,
            stringa
        FROM bolle
        WHERE (data_consegna IN ({placeholders}) OR data IN ({placeholders}))
          AND id_store NOT IN ('NEGOZIO', 'Store ID', 'EXTRA', 'TOTAL', 'TOTALE', '')
        """
        params = tuple(date_list + date_list)
    else:
        t_dt = str(target_date)[:10]
        query = """
        SELECT 
            id_store AS ID_STORE,
            tipo_cons,
            colli_abbigl AS TOT_ABBIGL,
            colli_calzat AS TOT_CALZAT,
            colli_ecom AS TOT_ECOM,
            colli_others AS TOT_OTHERS,
            colli_vario AS TOT_VARIO,
            stringa
        FROM bolle
        WHERE (data_consegna = ? OR data = ?)
          AND id_store NOT IN ('NEGOZIO', 'Store ID', 'EXTRA', 'TOTAL', 'TOTALE', '')
        """
        params = (t_dt, t_dt)

    df = pd.read_sql(query, conn, params=params)
    conn.close()

    if df.empty:
        return pd.DataFrame(columns=["ID_STORE", "tipo_cons", "TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM", "TOT_OTHERS", "stringa"])

    return df


def export_bolle_excel(df_bolle: pd.DataFrame, delivery_date: str) -> bytes:
    """
    Exports delivery notes (bolle) to a styled Excel sheet with Italian formatting,
    carrier prominence, accurate column ordering, and totals row.
    """
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Riepilogo Bolle"
    ws.views.sheetView[0].showGridLines = True

    # Palette
    FILL_TITLE = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    FILL_HEADER = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
    FILL_ZEBRA = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
    FILL_TOTAL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

    FONT_TITLE = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    FONT_HEADER = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    FONT_DATA = Font(name="Calibri", size=10)
    FONT_DATA_BOLD = Font(name="Calibri", size=10, bold=True)
    FONT_TOTAL = Font(name="Calibri", size=10, bold=True, color="1F4E79")

    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    total_border = Border(
        top=Side(style='thin', color='1F4E79'),
        bottom=Side(style='double', color='1F4E79'),
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9')
    )

    # Format delivery date DD/MM/YYYY
    try:
        d_obj = datetime.strptime(str(delivery_date)[:10], "%Y-%m-%d")
        dt_fmt = d_obj.strftime("%d/%m/%Y")
    except:
        dt_fmt = str(delivery_date)

    # 1. Title Banner
    ws.merge_cells("A1:P1")
    title_cell = ws["A1"]
    title_cell.value = f"RIEPILOGO BOLLE DI CONSEGNA INDITEX - DATA CONSEGNA: {dt_fmt}"
    title_cell.font = FONT_TITLE
    title_cell.fill = FILL_TITLE
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # 2. Column Headers
    headers = [
        "Giro", "Store ID", "Insegna", "Punto Vendita", "Tipo Consegna",
        "Totale Colli", "Abbigliamento", "Calzature", "E-Commerce",
        "Altri Colli", "Mat. Vario Piattaforma", "Vettore", "Mezzo",
        "Indirizzo di Destinazione", "Note / Intershops", "Anomalie allo Scarico"
    ]
    ws.row_dimensions[2].height = 26
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        align = "center" if col_idx in [1, 2, 5] else ("right" if 6 <= col_idx <= 11 else "left")
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)

    # 3. Data Rows
    current_row = 3
    if df_bolle is not None and not df_bolle.empty:
        df_sorted = df_bolle.copy()
        if "tipo_cons" in df_sorted.columns:
            tipo_order = {"STD": 0, "DOPPIA": 1}
            df_sorted["_tipo_rank"] = df_sorted["tipo_cons"].map(lambda t: tipo_order.get(str(t).upper(), 2))
            sort_cols = [c for c in ["giro", "id_store", "_tipo_rank"] if c in df_sorted.columns]
            df_sorted = df_sorted.sort_values(by=sort_cols).drop(columns=["_tipo_rank"])
        else:
            sort_cols = [c for c in ["giro", "id_store"] if c in df_sorted.columns]
            if sort_cols:
                df_sorted = df_sorted.sort_values(by=sort_cols)

        for _, r in df_sorted.iterrows():
            c_abb = int(round(_safe_float(r.get("colli_abbigl", 0))))
            c_calz = int(round(_safe_float(r.get("colli_calzat", 0))))
            c_eco = int(round(_safe_float(r.get("colli_ecom", 0))))
            c_oth = int(round(_safe_float(r.get("colli_others", 0))))
            c_var = int(round(_safe_float(r.get("colli_vario", 0))))
            tot_c = c_abb + c_calz + c_eco + c_oth + c_var

            row_data = [
                str(r.get("giro", "") or ""),
                str(r.get("id_store", "") or ""),
                str(r.get("punto_vendita", "") or "ZARA"),
                str(r.get("store_name", "") or ""),
                str(r.get("tipo_cons", "STD") or "STD"),
                tot_c,
                c_abb,
                c_calz,
                c_eco,
                c_oth,
                c_var,
                str(r.get("vettore", "LACCHI SPA") or ""),
                str(r.get("tipo_mezzo", "") or ""),
                str(r.get("indirizzo_destino", "") or ""),
                str(r.get("stringa", "") or ""),
                str(r.get("anomalie_scarico", "") or "")
            ]

            ws.row_dimensions[current_row].height = 20
            is_even = (current_row % 2 == 0)

            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=current_row, column=col_idx, value=val)
                cell.border = thin_border
                if is_even:
                    cell.fill = FILL_ZEBRA

                if 6 <= col_idx <= 11:
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.font = FONT_DATA_BOLD if col_idx == 6 else FONT_DATA
                elif col_idx in [1, 2, 5]:
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.font = FONT_DATA_BOLD if col_idx == 2 else FONT_DATA
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                    cell.font = FONT_DATA

            current_row += 1

        # 4. Totals Row
        ws.row_dimensions[current_row].height = 22
        for col_idx in range(1, 17):
            c_tot = ws.cell(row=current_row, column=col_idx)
            c_tot.fill = FILL_TOTAL
            c_tot.border = total_border
            c_tot.font = FONT_TOTAL

        ws.cell(row=current_row, column=1, value="TOTALE").alignment = Alignment(horizontal="center", vertical="center")
        for num_col in range(6, 12):
            col_letter = get_column_letter(num_col)
            c_sum = ws.cell(row=current_row, column=num_col)
            c_sum.value = f"=SUM({col_letter}3:{col_letter}{current_row-1})"
            c_sum.number_format = "#,##0"
            c_sum.alignment = Alignment(horizontal="right", vertical="center")

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            if cell.row == 1:
                continue
            val_str = str(cell.value or "")
            if val_str.startswith("="):
                max_len = max(max_len, 10)
            else:
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SPLIT_CAT_KEYS = ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario"]


def compute_equal_split_parts(bolla: Dict[str, Any], n_parts: int = 2) -> List[Dict[str, int]]:
    """
    Calcola la ripartizione equa automatica di una bolla in `n_parts` (2, 3 o 4 furgoni).
    Ogni categoria viene divisa in parti intere distribuendo il resto sui primi furgoni,
    così la somma per ogni singola categoria e il totale complessivo coincidono sempre al 100%.
    """
    n = max(1, min(4, int(n_parts or 1)))
    orig = {k: max(0, int(round(float(bolla.get(k, 0) or 0)))) for k in SPLIT_CAT_KEYS}
    parts: List[Dict[str, int]] = [{k: 0 for k in SPLIT_CAT_KEYS} for _ in range(n)]
    for k in SPLIT_CAT_KEYS:
        base_q = orig[k] // n
        rem_q = orig[k] % n
        for i in range(n):
            parts[i][k] = base_q + (1 if i < rem_q else 0)
    for i in range(n):
        parts[i]["tot_colli"] = sum(parts[i][k] for k in SPLIT_CAT_KEYS)
    return parts


def _allocate_total_proportionally(remaining_cats: Dict[str, int], target_total: int) -> Dict[str, int]:
    """
    Spalma un totale colli desiderato (`target_total`) sulle categorie disponibili in `remaining_cats`
    in modo proporzionale, garantendo che nessuna categoria superi il residuo disponibile
    e che la somma finale sia esattamente `min(target_total, sum(remaining_cats))`.
    """
    rem_tot = sum(remaining_cats.get(k, 0) for k in SPLIT_CAT_KEYS)
    clamped_target = max(0, min(int(target_total or 0), rem_tot))
    if clamped_target == 0:
        return {k: 0 for k in SPLIT_CAT_KEYS}
    if clamped_target == rem_tot:
        return {k: int(remaining_cats.get(k, 0)) for k in SPLIT_CAT_KEYS}

    alloc: Dict[str, int] = {}
    fracs = []
    for k in SPLIT_CAT_KEYS:
        avail = int(remaining_cats.get(k, 0))
        exact = (avail * clamped_target) / float(rem_tot)
        fl = min(avail, int(exact))
        alloc[k] = fl
        fracs.append((exact - fl, avail - fl, k))

    diff = clamped_target - sum(alloc.values())
    fracs.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for _, _, k in fracs:
        if diff <= 0:
            break
        if alloc[k] < remaining_cats[k]:
            alloc[k] += 1
            diff -= 1

    # Fallback se restano unità da assegnare
    if diff > 0:
        for k in SPLIT_CAT_KEYS:
            while diff > 0 and alloc[k] < remaining_cats[k]:
                alloc[k] += 1
                diff -= 1

    return alloc


def split_bolla_for_printing(
    bolla: Dict[str, Any],
    n_parts: int = 2,
    custom_parts: Optional[List[Dict[str, Any]]] = None,
    intershops_part_idx: int = 1,
) -> List[Dict[str, Any]]:
    """
    Divide una bolla in `n_parts` (2, 3 o 4) sotto-bolle per la stampa su più furgoni.
    - Garantisce matematicamente che la somma dei colli delle `n_parts` sotto-bolle sia
      SEMPRE identica al 100% al totale della bolla originale (l'ultimo furgone assorbe
      sempre a saldo la differenza residua).
    - Non modifica il database: opera esclusivamente sui record destinati alla stampa.
    - Supporta l'assegnazione opzionale di Autista, Sigillo e Mezzo per ciascun furgone
      e l'assegnazione dei Trasferimenti (Intershops) a uno specifico furgone (default: Furgone 1).
    """
    n = max(1, min(4, int(n_parts or 1)))
    if n <= 1:
        return [dict(bolla)]

    orig_cats = {k: max(0, int(round(float(bolla.get(k, 0) or 0)))) for k in SPLIT_CAT_KEYS}
    orig_total = sum(orig_cats.values())
    rem_cats = dict(orig_cats)

    eq_parts = compute_equal_split_parts(bolla, n)
    computed_cats: List[Dict[str, int]] = []

    for idx in range(n):
        if idx == n - 1:
            # L'ultimo furgone (Furgone N) riceve SEMPRE il saldo esatto residuo!
            part_c = {k: max(0, rem_cats[k]) for k in SPLIT_CAT_KEYS}
        else:
            c_spec = custom_parts[idx] if (custom_parts and idx < len(custom_parts) and isinstance(custom_parts[idx], dict)) else None
            if c_spec is not None and any(k in c_spec for k in SPLIT_CAT_KEYS):
                part_c = {}
                for k in SPLIT_CAT_KEYS:
                    req_v = max(0, int(round(float(c_spec.get(k, 0) or 0))))
                    actual_v = min(req_v, rem_cats[k])
                    part_c[k] = actual_v
                    rem_cats[k] -= actual_v
            elif c_spec is not None and "target_total" in c_spec and c_spec["target_total"] is not None:
                part_c = _allocate_total_proportionally(rem_cats, int(c_spec["target_total"]))
                for k in SPLIT_CAT_KEYS:
                    rem_cats[k] -= part_c[k]
            else:
                part_c = {}
                for k in SPLIT_CAT_KEYS:
                    req_v = eq_parts[idx][k]
                    actual_v = min(req_v, rem_cats[k])
                    part_c[k] = actual_v
                    rem_cats[k] -= actual_v
        computed_cats.append(part_c)

    target_inter_idx = max(1, min(n, int(intershops_part_idx or 1)))
    has_inter = bool(
        (bolla.get("intershops_json") and str(bolla.get("intershops_json")).strip() not in ("", "[]"))
        or (bolla.get("stringa") and str(bolla.get("stringa")).strip())
    )

    out_records: List[Dict[str, Any]] = []
    base_note = str(bolla.get("note") or "").strip()
    if base_note.lower() in ("nan", "none"):
        base_note = ""

    for idx in range(n):
        part_num = idx + 1
        sub_b = dict(bolla)
        p_cats = computed_cats[idx]
        part_tot = sum(p_cats.values())

        for k in SPLIT_CAT_KEYS:
            sub_b[k] = p_cats[k]
        sub_b["TOT_COLLI"] = part_tot
        sub_b["split_index"] = part_num
        sub_b["split_total"] = n
        sub_b["split_parent_total_colli"] = orig_total
        sub_b["split_part_label"] = f"FURGONE {part_num}/{n}"

        # Personalizzazioni opzionali per singolo furgone (Autista, Sigillo, Mezzo)
        c_spec = custom_parts[idx] if (custom_parts and idx < len(custom_parts) and isinstance(custom_parts[idx], dict)) else {}
        custom_aut = str(c_spec.get("autista") or "").strip()
        custom_sig = str(c_spec.get("sigillo") or "").strip()
        custom_mez = str(c_spec.get("tipo_mezzo") or "").strip()
        if custom_aut:
            sub_b["autista"] = custom_aut
        if custom_sig:
            sub_b["sigillo"] = custom_sig
            sub_b["split_sigillo"] = custom_sig
        if custom_mez:
            sub_b["tipo_mezzo"] = custom_mez

        # Gestione Trasferimenti (Intershops): assegnati solo al furgone prescelto per non duplicarli
        if part_num != target_inter_idx:
            sub_b["intershops_json"] = "[]"
            sub_b["stringa"] = ""

        split_note = f"🚛 CONSEGNA DIVISA SU {n} FURGONI — QUOTA FURGONE {part_num}/{n}: {part_tot} colli (su {orig_total} colli totali negozio)"
        if has_inter and part_num != target_inter_idx:
            split_note += f" • [Trasferimenti caricati su Furgone {target_inter_idx}/{n}]"
        sub_b["note"] = f"{split_note} | {base_note}" if base_note else split_note
        out_records.append(sub_b)

    return out_records


def render_bolla_printable_html(
    bolla_records: List[Dict[str, Any]],
    title: str = "Bolla di Consegna Inditex",
    auto_print: bool = False,
    override_sigillo: Optional[str] = None,
) -> str:
    """
    Generates a clean, professional printable HTML page for one or multiple bolle.
    Includes page breaks between notes for batch printing without blank intermediate pages.
    Supports split bolle (2-3-4 vans per store) with clear part numbering and total verification.
    """
    html_pages = []

    for b in bolla_records:
        bid = b.get("id", "")
        access_id = b.get("access_id")
        base_doc_num = f"{access_id}" if access_id else f"{bid:05d}" if isinstance(bid, int) else (str(bid) if bid else "BOZZA")
        split_idx = int(b.get("split_index", 1) or 1)
        split_tot = int(b.get("split_total", 1) or 1)
        is_split = split_tot > 1
        doc_num = f"{base_doc_num}/{split_idx}" if is_split else base_doc_num

        data_cons = b.get("data_consegna") or b.get("data") or ""
        # Format DD/MM/YYYY
        try:
            d_obj = datetime.strptime(data_cons[:10], "%Y-%m-%d")
            data_cons_fmt = d_obj.strftime("%d/%m/%Y")
        except:
            data_cons_fmt = data_cons

        store_id = b.get("id_store", "")
        pv = b.get("punto_vendita", "")
        sname = b.get("store_name", "")
        tipo_cons = b.get("tipo_cons", "STD")
        vettore = b.get("vettore") or "LACCHI SPA - VIA ERCOLE RAMARINI, 11/13 - 00015 MONTEROTONDO"
        autista = str(b.get("autista") or "").strip()
        cell = str(b.get("cell_autista") or "").strip()
        mezzo = b.get("tipo_mezzo", "")
        indirizzo = b.get("indirizzo_destino", "")

        aut_line = f"<strong>Autista:</strong> {autista}<br>" if autista else ""
        if b.get("split_sigillo"):
            sigillo_val = str(b.get("split_sigillo")).strip()
        elif override_sigillo is not None:
            sigillo_val = str(override_sigillo).strip()
        else:
            sigillo_val = str(b.get("sigillo") or "").strip()
        sigillo_line = f"<br><strong>Sigillo:</strong> <span style='font-family:monospace; font-weight:bold;'>{sigillo_val}</span>" if sigillo_val else ""
        nota_consegna = str(b.get("note") or b.get("stringa") or "").strip()

        c_abb = int(round(float(b.get("colli_abbigl") or 0)))
        c_calz = int(round(float(b.get("colli_calzat") or 0)))
        c_eco = int(round(float(b.get("colli_ecom") or 0)))
        c_oth = int(round(float(b.get("colli_others") or 0)))
        c_var = int(round(float(b.get("colli_vario") or 0)))
        c_dann = int(round(float(b.get("colli_dann") or 0)))
        c_nonconf = int(round(float(b.get("colli_non_conf") or 0)))
        anomalie = b.get("anomalie_scarico", "")
        stringa = b.get("stringa", "")

        tot_operativa = c_abb + c_calz + c_eco + c_oth + c_var
        parent_tot_colli = int(b.get("split_parent_total_colli", tot_operativa) or tot_operativa)
        split_badge_html = (
            f" <span class='badge' style='background:#7c3aed; color:white; margin-left:6px;'>"
            f"🚛 FURGONE {split_idx} DI {split_tot} (Quota: {tot_operativa}/{parent_tot_colli} colli)</span>"
            if is_split
            else ""
        )
        total_row_label = (
            f"TOTALE COLLI SU QUESTO MEZZO (FURGONE {split_idx} DI {split_tot})"
            if is_split
            else "TOTALE COLLI OPERATIVA CONSEGNATI"
        )
        total_row_note = (
            f"Quota Furgone {split_idx}/{split_tot} (Totale Complessivo Negozio: {parent_tot_colli} colli)"
            if is_split
            else "-"
        )

        # Parse intershops if JSON or text
        inter_rows_html = ""
        inter_list = []
        try:
            if b.get("intershops_json"):
                inter_list = json.loads(b["intershops_json"])
        except:
            inter_list = []

        tot_inter_colli = 0
        if inter_list:
            for item in inter_list:
                m = item.get("mittente", "")
                c = float(item.get("colli", 0) or 0)
                t = str(item.get("tipo", "") or "").strip()
                d_mat = str(item.get("descrizione", "") or "").strip()
                if d_mat and d_mat.upper() not in ("NONE", "NAN") and d_mat.upper() != t.upper():
                    t_disp = f"{t} — {d_mat}" if t else d_mat
                else:
                    t_disp = t
                if c > 0:
                    tot_inter_colli += int(c)
                    inter_rows_html += f"<tr><td>{m}</td><td style='text-align:center;'>{int(c)}</td><td>{t_disp}</td></tr>"

        if not inter_rows_html and stringa:
            inter_rows_html = f"<tr><td colspan='3' style='font-style:italic;'>{stringa}</td></tr>"

        badge_tipo = f"<span class='badge badge-{tipo_cons.lower()}'>{tipo_cons}</span>"

        page = f"""
        <div class="bolla-sheet">
            <!-- HEADER -->
            <div class="header-box">
                <div class="header-col">
                    <strong>TRASPORTI INTERNAZIONALI TRANSMEC S.P.A.</strong><br>
                    Sede Legale: Via Ponte Alto, 32<br>
                    41011 Campogalliano (MO)<br>
                    Tel. (+39) 059 895811<br>
                    C.F. e P.IVA IT001179970363<br>
                    Cap. Soc. € 10.000.000,00 i.v.
                </div>
                <div class="header-col" style="border-left: 1px solid #ccc; border-right: 1px solid #ccc; padding: 0 10px;">
                    <strong>MITTENTE / CARICO:</strong><br>
                    <strong>LACCHI SPA</strong> - Filiale di Monterotondo<br>
                    Via E. Ramarini, 11 - 00015 Monterotondo (RM)<br>
                    P.IVA 0096768100
                </div>
                <div class="header-col" style="text-align: right;">
                    <strong>COMMITTENTE:</strong><br>
                    <strong>ITX ITALIA S.r.l.</strong><br>
                    Largo Corsia dei Servi, 3 - 20122 Milano (MI)<br>
                    C.F. e P.IVA 11209550158
                </div>
            </div>

            <!-- TITLE BAR -->
            <div class="title-bar">
                <div style="font-size: 18px; font-weight: bold;">
                    BOLLA DI CONSEGNA N° <span style="color:#d9534f;">{doc_num}</span> {badge_tipo}{split_badge_html}
                </div>
                <div style="font-size: 15px; font-weight: bold;">
                    DATA CONSEGNA: <span style="text-decoration: underline;">{data_cons_fmt}</span>
                </div>
            </div>

            <!-- VETTORE E DESTINATARIO -->
            <div class="info-grid">
                <div class="info-box">
                    <div class="info-title">VETTORE & TRASPORTO</div>
                    <div class="info-content">
                        <strong>Vettore:</strong> {vettore}<br>
                        {aut_line}
                        <strong>Mezzo:</strong> {mezzo or 'ND'}{sigillo_line}
                    </div>
                </div>
                <div class="info-box">
                    <div class="info-title">DESTINATARIO (PUNTO VENDITA)</div>
                    <div class="info-content">
                        <strong style="font-size: 15px;">{pv} - {sname}</strong> (Cod. Store: <strong>{store_id}</strong>)<br>
                        <strong>Indirizzo:</strong> {indirizzo or 'ND'}
                    </div>
                </div>
            </div>

            <div style="margin: 8px 0; font-size: 12px; font-weight: bold; color: #333;">
                CAUSALE TRASPORTO: CONTO VENDITA
            </div>

            <!-- TABELLA COLLI OPERATIVA -->
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="text-align:left;">TIPOLOGIA COLLI</th>
                        <th style="width: 140px; text-align: center;">QUANTITÀ COLLI</th>
                        <th style="text-align:left;">NOTE / DETTAGLI</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>COLLI ABBIGLIAMENTO + PROFUMI</strong></td>
                        <td class="num">{c_abb}</td>
                        <td>Previsione Piattaforma Roma</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI CALZATURE</strong></td>
                        <td class="num">{c_calz}</td>
                        <td>Calzature e Accessori</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI E-COMMERCE</strong></td>
                        <td class="num">{c_eco}</td>
                        <td>Consegne E-com negozio</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI OTHERS</strong></td>
                        <td class="num">{c_oth}</td>
                        <td>Altri Bultos / Arredo / Cancelleria</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI MAT. VARIO DA PIATTAFORMA</strong></td>
                        <td class="num">{c_var}</td>
                        <td>Stand / Ceste / Materiali</td>
                    </tr>
                    <tr class="total-row">
                        <td>{total_row_label}</td>
                        <td class="num" style="font-size: 15px;">{tot_operativa}</td>
                        <td>{total_row_note}</td>
                    </tr>
                </tbody>
            </table>

            <!-- SEZIONE TRASFERIMENTI / INTERSHOPS -->
            <div style="margin-top: 10px;">
                <div class="sub-header">TRASFERIMENTI IN ARRIVO DA ALTRI PDV (INTERSHOPS)</div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 25%; text-align:left;">NEGOZIO MITTENTE</th>
                            <th style="width: 20%; text-align:center;">NUMERO COLLI</th>
                            <th style="text-align:left;">TIPOLOGIA / DESCRIZIONE MATERIALE</th>
                        </tr>
                    </thead>
                    <tbody>
                        {inter_rows_html or "<tr><td colspan='3' style='text-align:center; color:#888;'>Nessun trasferimento inter-negozio registrato</td></tr>"}
                        {f'<tr class="total-row"><td colspan="2" style="text-align:right;">TOTALE COLLI TRASFERIMENTI:</td><td class="num">{tot_inter_colli}</td></tr>' if tot_inter_colli > 0 else ''}
                    </tbody>
                </table>
            </div>

            <!-- NOTE DI CONSEGNA -->
            <div style="margin-top: 8px;">
                <div class="border-box" style="min-height: 40px; padding: 6px 10px;">
                    <strong>NOTE DI CONSEGNA:</strong><br>
                    <span>{nota_consegna or 'Nessuna nota operativa segnalata.'}</span>
                </div>
            </div>

            <!-- FIRME E ORARI -->
            <div class="signature-grid">
                <div class="sig-box">
                    <strong>ORARI CONSEGNA</strong><br><br>
                    ARRIVO ORE: [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; : &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ]<br><br>
                    PARTENZA ORE: [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; : &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ]
                </div>
                <div class="sig-box">
                    <strong>FIRMA VETTORE</strong><br><br><br>
                    ____________________________________
                </div>
                <div class="sig-box">
                    <strong>FIRMA REFERENTE SCARICO (TIMBRO/NOME)</strong><br><br><br>
                    ____________________________________
                </div>
            </div>
        </div>
        """
        html_pages.append(page)

    auto_print_script = "<script>window.addEventListener('DOMContentLoaded', function() { setTimeout(function() { try { window.focus(); window.print(); } catch(e) {} }, 300); });</script>" if auto_print else ""
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            font-size: 11px;
            color: #111;
            margin: 0;
            padding: 10px;
            background: #f7f9fa;
        }}
        .print-btn-bar {{
            text-align: center;
            margin-bottom: 20px;
            padding: 10px;
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 6px;
        }}
        .btn-print {{
            background: #0284c7;
            color: white;
            font-weight: bold;
            padding: 10px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }}
        .btn-print:hover {{
            background: #0369a1;
        }}
        .bolla-sheet {{
            background: white;
            width: 210mm;
            margin: 0 auto 20px auto;
            padding: 10mm 14mm;
            box-sizing: border-box;
            border: 1px solid #ccc;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            page-break-inside: avoid;
            break-inside: avoid;
            page-break-after: always;
            break-after: page;
        }}
        .bolla-sheet:last-of-type {{
            page-break-after: auto;
            break-after: auto;
        }}
        .header-box {{
            display: flex;
            justify-content: space-between;
            font-size: 9.5px;
            line-height: 1.3;
            border: 1px solid #333;
            padding: 6px 8px;
            margin-bottom: 8px;
        }}
        .header-col {{
            flex: 1;
        }}
        .title-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #eee;
            border: 1.5px solid #222;
            padding: 6px 12px;
            margin-bottom: 8px;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: bold;
            border-radius: 3px;
        }}
        .badge-std {{
            background: #2563eb;
            color: white;
        }}
        .badge-doppia {{
            background: #ea580c;
            color: white;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 6px;
        }}
        .info-box {{
            border: 1px solid #333;
            border-radius: 3px;
        }}
        .info-title {{
            background: #f1f5f9;
            font-weight: bold;
            padding: 4px 8px;
            border-bottom: 1px solid #333;
            font-size: 10px;
        }}
        .info-content {{
            padding: 5px 8px;
            line-height: 1.35;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 3px;
            font-size: 10.5px;
        }}
        .data-table th, .data-table td {{
            border: 1px solid #444;
            padding: 4px 7px;
        }}
        .data-table th {{
            background: #f8fafc;
            font-weight: bold;
        }}
        .num {{
            text-align: right;
            font-weight: bold;
        }}
        .total-row {{
            background: #f1f5f9;
            font-weight: bold;
        }}
        .sub-header {{
            font-size: 10px;
            font-weight: bold;
            background: #e2e8f0;
            padding: 3px 8px;
            border: 1px solid #444;
            border-bottom: none;
        }}
        .border-box {{
            border: 1px solid #444;
            padding: 5px 8px;
            min-height: 32px;
            line-height: 1.35;
        }}
        .signature-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
            margin-top: 10px;
        }}
        .sig-box {{
            border: 1px solid #444;
            padding: 6px 8px;
            min-height: 62px;
            text-align: center;
            font-size: 9.5px;
        }}

        @page {{
            size: A4 portrait;
            margin: 8mm 10mm;
        }}

        @media print {{
            html, body {{
                background: white !important;
                padding: 0 !important;
                margin: 0 !important;
                width: 100% !important;
            }}
            .print-btn-bar {{
                display: none !important;
            }}
            .bolla-sheet {{
                width: 100% !important;
                min-height: 0 !important;
                height: auto !important;
                box-shadow: none !important;
                border: none !important;
                margin: 0 !important;
                padding: 2mm 4mm !important;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
                page-break-after: always !important;
                break-after: page !important;
            }}
            .bolla-sheet:last-of-type {{
                page-break-after: auto !important;
                break-after: auto !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="print-btn-bar">
        <button class="btn-print" onclick="window.print()">🖨️ Stampa Documento ({len(bolla_records)} Bolle)</button>
        <button class="btn-print" style="background:#475569; margin-left:8px;" onclick="try{{window.close();}}catch(e){{}}">❌ Chiudi Finestra</button>
        <span style="margin-left: 15px; color: #555;">Totale Bolle: <strong>{len(bolla_records)}</strong></span>
    </div>
    {"".join(html_pages)}
    {auto_print_script}
</body>
</html>
"""
    return full_html


def add_colli_to_bolla_spuntata(
    bolla_id: int,
    colli_to_add: int,
    category: str = "colli_abbigl",
    note_reason: str = "",
    mark_spuntato: bool = True,
    db_path: Path = DB_PATH
) -> Dict[str, Any]:
    """
    Funzione per la versione mobile: aggiunge colli extra a un negozio (sia già spuntato sia ancora da spuntare).
    Aggiorna la categoria specificata, imposta spuntato = 1 se mark_spuntato è True (o mantiene lo stato attuale)
    e registra una nota con orario.
    """
    if colli_to_add <= 0:
        return {"status": "error", "message": "Il numero di colli da aggiungere deve essere maggiore di 0."}

    bolla = get_bolla_by_id(bolla_id, db_path=db_path)
    if not bolla:
        return {"status": "error", "message": f"Bolla con ID {bolla_id} non trovata in archivio."}

    valid_cats = {
        "colli_abbigl": "Abbigliamento",
        "colli_calzat": "Calzature",
        "colli_ecom": "E-Commerce",
        "colli_others": "Altri Bultos",
        "colli_vario": "Materiale Vario"
    }
    cat_key = category if category in valid_cats else "colli_abbigl"
    cat_label = valid_cats[cat_key]

    old_val = int(round(float(bolla.get(cat_key, 0) or 0)))
    new_val = old_val + int(colli_to_add)
    bolla[cat_key] = new_val

    if mark_spuntato:
        bolla["spuntato"] = 1
    else:
        bolla["spuntato"] = int(bolla.get("spuntato", 0) or 0)

    # Registra nota con timestamp
    now_str = datetime.now().strftime("%H:%M")
    reason_str = f" ({note_reason.strip()})" if note_reason.strip() else ""
    log_entry = f"+{colli_to_add} {cat_label}{reason_str} [h {now_str}]"
    curr_note = str(bolla.get("note") or "").strip()
    if curr_note:
        bolla["note"] = f"{curr_note} | {log_entry}"
    else:
        bolla["note"] = log_entry

    save_or_update_bolla(bolla, db_path=db_path)

    tot_colli = sum(int(round(float(bolla.get(k, 0) or 0))) for k in valid_cats)

    return {
        "status": "ok",
        "bolla_id": bolla_id,
        "id_store": bolla.get("id_store"),
        "store_name": bolla.get("store_name"),
        "category": cat_key,
        "category_label": cat_label,
        "added_colli": colli_to_add,
        "new_category_total": new_val,
        "new_total_colli": tot_colli,
        "spuntato": bolla["spuntato"],
        "note": bolla["note"]
    }


def add_intershop_to_bolla(
    bolla_id: int,
    mittente: str,
    colli: int,
    tipo: str = "MERCE",
    descrizione: str = "",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """
    Aggiunge un trasferimento inter-negozio (Intershop) a una bolla direttamente da Mobile.
    Supporta anche la descrizione libera del materiale trasferito (es. manichini, grucce, ceste).
    Aggiorna intershops_json e ricalcola automaticamente il campo stringa.
    """
    if int(colli or 0) <= 0:
        return {"status": "error", "message": "Il numero di colli del trasferimento deve essere maggiore di 0."}

    bolla = get_bolla_by_id(bolla_id, db_path=db_path)
    if not bolla:
        return {"status": "error", "message": f"Bolla con ID {bolla_id} non trovata."}

    inter_list: List[Dict[str, Any]] = []
    try:
        if bolla.get("intershops_json"):
            parsed = json.loads(bolla["intershops_json"])
            if isinstance(parsed, list):
                inter_list = [x for x in parsed if isinstance(x, dict) and float(x.get("colli", 0) or 0) > 0]
    except Exception:
        inter_list = []

    clean_mitt = str(mittente or "").strip()
    clean_tipo = str(tipo or "MERCE").strip().upper() or "MERCE"
    clean_desc = str(descrizione or "").strip()
    if clean_desc.lower() in ("nan", "none", "null"):
        clean_desc = ""
    new_item: Dict[str, Any] = {
        "mittente": clean_mitt,
        "colli": int(colli),
        "tipo": clean_tipo,
    }
    if clean_desc:
        new_item["descrizione"] = clean_desc
    inter_list.append(new_item)

    bolla["intershops_list"] = inter_list
    bolla["intershops_json"] = json.dumps(inter_list)
    bolla["stringa"] = format_intershops_string(inter_list)
    save_or_update_bolla(bolla, db_path=db_path)

    return {
        "status": "ok",
        "bolla_id": bolla_id,
        "id_store": bolla.get("id_store"),
        "store_name": bolla.get("store_name"),
        "intershops_list": inter_list,
        "stringa": bolla["stringa"],
    }


def remove_intershop_from_bolla(
    bolla_id: int,
    index: int,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Rimuove un trasferimento inter-negozio (per indice) da una bolla e aggiorna stringa."""
    bolla = get_bolla_by_id(bolla_id, db_path=db_path)
    if not bolla:
        return {"status": "error", "message": f"Bolla con ID {bolla_id} non trovata."}

    inter_list: List[Dict[str, Any]] = []
    try:
        if bolla.get("intershops_json"):
            parsed = json.loads(bolla["intershops_json"])
            if isinstance(parsed, list):
                inter_list = [x for x in parsed if isinstance(x, dict) and float(x.get("colli", 0) or 0) > 0]
    except Exception:
        inter_list = []

    if 0 <= index < len(inter_list):
        inter_list.pop(index)

    bolla["intershops_list"] = inter_list
    bolla["intershops_json"] = json.dumps(inter_list)
    bolla["stringa"] = format_intershops_string(inter_list)
    save_or_update_bolla(bolla, db_path=db_path)

    return {
        "status": "ok",
        "bolla_id": bolla_id,
        "intershops_list": inter_list,
        "stringa": bolla["stringa"],
    }


def clear_sigilli_by_date(delivery_date: str, db_path: Path = DB_PATH) -> int:
    """Azzera il campo sigillo su tutte le bolle di una determinata data di consegna."""
    d_str = str(delivery_date).strip()[:10]
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE bolle SET sigillo = '' WHERE data_consegna = ? OR data = ?", (d_str, d_str))
    cnt = cur.rowcount
    conn.commit()
    conn.close()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["bolle"])
    return cnt


def confirm_bolla_spunta(
    bolla_id: int,
    use_expected: bool = False,
    colli_abbigl: Optional[int] = None,
    colli_calzat: Optional[int] = None,
    colli_ecom: Optional[int] = None,
    colli_others: Optional[int] = None,
    colli_vario: Optional[int] = None,
    note: Optional[str] = None,
    db_path: Path = DB_PATH
) -> Dict[str, Any]:
    """
    Conferma la spunta di una bolla (modalità 1-Tap Conforme al previsto oppure con quantità manuali).
    Imposta spuntato = 1 e salva su SQLite + Cloud Sync.
    """
    bolla = get_bolla_by_id(bolla_id, db_path=db_path)
    if not bolla:
        return {"status": "error", "message": f"Bolla con ID {bolla_id} non trovata in archivio."}

    if use_expected:
        bolla["colli_abbigl"] = int(round(float(bolla.get("prev_abbigl", bolla.get("colli_abbigl", 0)) or 0)))
        bolla["colli_calzat"] = int(round(float(bolla.get("prev_calzat", bolla.get("colli_calzat", 0)) or 0)))
        bolla["colli_ecom"] = int(round(float(bolla.get("prev_ecom", bolla.get("colli_ecom", 0)) or 0)))
        bolla["colli_others"] = int(round(float(bolla.get("prev_others", bolla.get("colli_others", 0)) or 0)))
        bolla["colli_vario"] = int(round(float(bolla.get("prev_vario", bolla.get("colli_vario", 0)) or 0)))
    else:
        if colli_abbigl is not None:
            bolla["colli_abbigl"] = max(0, int(colli_abbigl))
        if colli_calzat is not None:
            bolla["colli_calzat"] = max(0, int(colli_calzat))
        if colli_ecom is not None:
            bolla["colli_ecom"] = max(0, int(colli_ecom))
        if colli_others is not None:
            bolla["colli_others"] = max(0, int(colli_others))
        if colli_vario is not None:
            bolla["colli_vario"] = max(0, int(colli_vario))

    if note is not None:
        bolla["note"] = str(note).strip()

    bolla["spuntato"] = 1
    save_or_update_bolla(bolla, db_path=db_path)

    tot_colli = sum(
        int(round(float(bolla.get(k, 0) or 0)))
        for k in ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario"]
    )
    return {
        "status": "ok",
        "bolla_id": bolla_id,
        "id_store": bolla.get("id_store"),
        "store_name": bolla.get("store_name"),
        "total_colli": tot_colli,
        "spuntato": 1
    }


