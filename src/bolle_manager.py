"""
Bolle Manager: Native management of delivery notes (bolle) in SQLite.
Completely replaces Microsoft Access (BOLLE INDITEX_rev.6.mdb).
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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


def get_bolle_dates(limit: int = 100) -> List[str]:
    """Returns sorted unique delivery dates available in bolle."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT COALESCE(NULLIF(data_consegna, ''), data) as dt 
        FROM bolle 
        WHERE dt IS NOT NULL AND dt != ''
        ORDER BY dt DESC 
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def get_all_drivers() -> List[str]:
    """Returns unique autisti from bolle and store profiles."""
    conn = get_db_connection()
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


def get_all_carriers() -> List[str]:
    """Returns unique vettori."""
    conn = get_db_connection()
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


def get_store_delivery_profile(store_id: str, tipo_cons: str = "STD") -> Dict[str, Any]:
    """Returns delivery profile for a store directly from the unified master stores table."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stores WHERE store_id = ?", (str(store_id).strip(),))
    s_row = cur.fetchone()
    conn.close()

    res = {
        "id_store": str(store_id).strip(),
        "tipo_cons": str(tipo_cons).strip().upper(),
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
            res["tipo_mezzo"] = s_dict.get("tipo_mezzo_doppia") or s_dict.get("tipo_mezzo", "FURGONE")
        else:
            res["autista"] = s_dict.get("autista", "")
            res["tipo_mezzo"] = s_dict.get("tipo_mezzo", "MOTRICE 18 PLT")

    return res


def list_store_delivery_profiles() -> pd.DataFrame:
    """Returns active delivery profiles constructed directly from stores table."""
    conn = get_db_connection()
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


def save_store_delivery_profile(profile: Dict[str, Any]):
    """Saves profile updates directly into stores table, creating store if not yet in database."""
    sid = str(profile.get("id_store", "")).strip()
    tipo_cons = str(profile.get("tipo_cons", "STD")).strip().upper()
    if not sid:
        return
    from src.db import update_store_record, add_store_record, get_stores_df
    df_s = get_stores_df()
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
        })
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
        update_store_record(sid, updates)


def get_bolle(
    data: Optional[str] = None,
    data_consegna: Optional[str] = None,
    id_store: Optional[str] = None,
    tipo_cons: Optional[str] = None,
    autista: Optional[str] = None,
    vettore: Optional[str] = None,
    search: Optional[str] = None
) -> pd.DataFrame:
    """Filters bolle and returns a DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    query = ["SELECT * FROM bolle WHERE 1=1"]
    params = []

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
    return df


def get_bolla_by_id(bolla_id: int) -> Optional[Dict[str, Any]]:
    """Returns single bolla dict by id."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bolle WHERE id = ?", (bolla_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def format_intershops_string(intershops_list: List[Dict[str, Any]]) -> str:
    """
    Formats list of intershop items into string:
    e.g. [{"mittente": "3680", "colli": 6, "tipo": "MERCE"}] -> "6C MERCE da 3680"
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
        m = str(item.get("mittente", "")).strip()
        if t and t.upper() != "NONE":
            p += f" {t}"
        if m and m.upper() != "NONE":
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


def save_or_update_bolla(data: Dict[str, Any]) -> int:
    """Inserts or updates a delivery note in SQLite."""
    conn = sqlite3.connect(DB_PATH)
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
            stringa = ?
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
            float(data.get("colli_abbigl", 0) or 0),
            float(data.get("colli_calzat", 0) or 0),
            float(data.get("colli_ecom", 0) or 0),
            float(data.get("colli_others", 0) or 0),
            float(data.get("colli_vario", 0) or 0),
            float(data.get("colli_cont", 0) or 0),
            float(data.get("colli_mat_vario", 0) or 0),
            float(data.get("colli_dann", 0) or 0),
            float(data.get("colli_non_conf", 0) or 0),
            data.get("anomalie_scarico", ""),
            inter_json,
            stringa_val,
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
            anomalie_scarico, intershops_json, stringa
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            float(data.get("colli_abbigl", 0) or 0),
            float(data.get("colli_calzat", 0) or 0),
            float(data.get("colli_ecom", 0) or 0),
            float(data.get("colli_others", 0) or 0),
            float(data.get("colli_vario", 0) or 0),
            float(data.get("colli_cont", 0) or 0),
            float(data.get("colli_mat_vario", 0) or 0),
            float(data.get("colli_dann", 0) or 0),
            float(data.get("colli_non_conf", 0) or 0),
            data.get("anomalie_scarico", ""),
            inter_json,
            stringa_val
        ))
        res_id = cur.lastrowid

    conn.commit()
    conn.close()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["bolle"])
    return res_id


def delete_bolla(bolla_id: int) -> bool:
    """Deletes a single bolla by id."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM bolle WHERE id = ?", (bolla_id,))
    rows_affected = cur.rowcount
    conn.commit()
    conn.close()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["bolle"])
    return rows_affected > 0


def delete_bolle_by_date(date_str: str) -> int:
    """Deletes all bolle for a specific delivery date."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM bolle WHERE data_consegna = ? OR data = ?", (date_str, date_str))
    n = cur.rowcount
    conn.commit()
    conn.close()
    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["bolle"])
    return n


def generate_bolle_from_forecast(run_id: int, delivery_date: Optional[str] = None, overwrite: bool = False) -> Tuple[int, int]:
    """
    Generates bolle directly from the forecast analysis, spunta arrivi and planning of run_id.
    Pre-fills store addresses, carrier, driver and vehicle from master stores table.
    Creates STD and DOPPIA bolle as needed.
    """
    conn = sqlite3.connect(DB_PATH)
    # 1. Fetch run info
    df_run = pd.read_sql("SELECT * FROM runs WHERE id = ?", conn, params=(run_id,))
    if df_run.empty:
        conn.close()
        raise ValueError(f"Run {run_id} non trovata.")

    run_date = str(df_run.iloc[0]["run_date"])[:10]
    if not delivery_date:
        try:
            dt = datetime.strptime(run_date, "%Y-%m-%d")
            delivery_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        except:
            delivery_date = run_date

    # 2. If overwrite, delete existing bolle for that delivery_date
    if overwrite:
        cur = conn.cursor()
        cur.execute("DELETE FROM bolle WHERE data_consegna = ? OR data = ?", (delivery_date, delivery_date))
        conn.commit()

    # 3. Check existing stores already having bolle for this date
    cur = conn.cursor()
    cur.execute("SELECT id_store, tipo_cons FROM bolle WHERE data_consegna = ? OR data = ?", (delivery_date, delivery_date))
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
    seen_store_brands = set()
    if not df_planning.empty:
        for _, r in df_planning.iterrows():
            raw_code = str(r["store_code"]).strip()
            if not raw_code or raw_code.upper() in ["NEGOZIO", "STORE ID", "EXTRA", "TOTAL", "TOTALE", "NONE"]:
                continue
            base_sid = raw_code[:-1] if raw_code.endswith("B") else raw_code
            b_name = str(r.get("brand", "")).upper()
            is_shoes = "SHOES" in b_name
            # If we already processed this store and brand category (textile vs shoes), skip duplicates
            if (base_sid, is_shoes) in seen_store_brands:
                continue
            seen_store_brands.add((base_sid, is_shoes))

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
                # Only take shoes from non-shoes line if store does NOT have a separate SHOES line
                if base_sid not in stores_with_shoes:
                    store_planned[base_sid]["shoes"] += _safe_float(r.get("planned_shoes", 0.0))
                store_planned[base_sid]["others"] += _safe_float(r.get("planned_others", 0.0))
                store_planned[base_sid]["ecom"] += _safe_float(r.get("planned_ecom", 0.0))
    elif not df_spunta.empty:
        for _, sp in df_spunta.iterrows():
            raw_code = str(sp["store_code"]).strip()
            if not raw_code or raw_code.upper() in ["NEGOZIO", "STORE ID", "EXTRA", "TOTAL", "TOTALE", "NONE"]:
                continue
            base_sid = raw_code[:-1] if raw_code.endswith("B") else raw_code
            # Skip Barra 9 rows in spunta to avoid double summing (since Barra 0 has base volume/colli)
            is_b9 = int(sp.get("is_barra9", 0)) == 1 or raw_code.endswith("B")
            if is_b9:
                continue
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
                bolla_std = {
                    "data": run_date,
                    "data_consegna": delivery_date,
                    "id_store": base_sid,
                    "punto_vendita": pv,
                    "store_name": sname,
                    "tipo_cons": "STD",
                    "vettore": vettore,
                    "cell_autista": cell_autista,
                    "autista": meta.get("autista", ""),
                    "tipo_mezzo": meta.get("tipo_mezzo", "MOTRICE 18 PLT"),
                    "indirizzo_destino": indirizzo,
                    "colli_abbigl": int(tot_tex - d_tex),
                    "colli_calzat": int(tot_sho - d_sho),
                    "colli_ecom": int(tot_eco - d_eco),
                    "colli_others": int(tot_oth - d_oth),
                    "colli_vario": 0,
                    "colli_cont": 0,
                    "colli_mat_vario": 0,
                    "colli_dann": 0,
                    "colli_non_conf": 0,
                    "anomalie_scarico": "",
                    "stringa": ""
                }
                save_or_update_bolla(bolla_std)
                created += 1

            # 2. DOPPIA (/9) Bolla (30%)
            if (base_sid, "DOPPIA") in existing_pairs:
                skipped += 1
            else:
                bolla_d = {
                    "data": run_date,
                    "data_consegna": delivery_date,
                    "id_store": base_sid,
                    "punto_vendita": pv,
                    "store_name": sname,
                    "tipo_cons": "DOPPIA",
                    "vettore": vettore,
                    "cell_autista": cell_autista,
                    "autista": meta.get("autista_doppia") or meta.get("autista", ""),
                    "tipo_mezzo": meta.get("tipo_mezzo_doppia") or "FURGONE",
                    "indirizzo_destino": indirizzo,
                    "colli_abbigl": d_tex,
                    "colli_calzat": d_sho,
                    "colli_ecom": d_eco,
                    "colli_others": d_oth,
                    "colli_vario": 0,
                    "colli_cont": 0,
                    "colli_mat_vario": 0,
                    "colli_dann": 0,
                    "colli_non_conf": 0,
                    "anomalie_scarico": "",
                    "stringa": ""
                }
                save_or_update_bolla(bolla_d)
                created += 1
        else:
            # Single STD Bolla (100%)
            if (base_sid, "STD") in existing_pairs:
                skipped += 1
            else:
                bolla_single = {
                    "data": run_date,
                    "data_consegna": delivery_date,
                    "id_store": base_sid,
                    "punto_vendita": pv,
                    "store_name": sname,
                    "tipo_cons": "STD",
                    "vettore": vettore,
                    "cell_autista": cell_autista,
                    "autista": meta.get("autista", ""),
                    "tipo_mezzo": meta.get("tipo_mezzo", "MOTRICE 18 PLT"),
                    "indirizzo_destino": indirizzo,
                    "colli_abbigl": round(tot_tex, 1),
                    "colli_calzat": round(tot_sho, 1),
                    "colli_ecom": round(tot_eco, 1),
                    "colli_others": round(tot_oth, 1),
                    "colli_vario": 0.0,
                    "colli_cont": 0.0,
                    "colli_mat_vario": 0.0,
                    "colli_dann": 0.0,
                    "colli_non_conf": 0.0,
                    "anomalie_scarico": "",
                    "stringa": ""
                }
                save_or_update_bolla(bolla_single)
                created += 1

    return created, skipped


def get_actuals_for_planner(target_date: str) -> pd.DataFrame:
    """
    Extracts actual delivered totals and intershops directly from SQLite bolle
    for the specified delivery date (or cargo date), ready for compute_planning_roma().
    Returns DataFrame with columns: ID_STORE, tipo_cons, TOT_ABBIGL, TOT_CALZAT, TOT_ECOM, TOT_OTHERS, stringa.
    """
    conn = sqlite3.connect(DB_PATH)
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
    df = pd.read_sql(query, conn, params=(target_date, target_date))
    conn.close()

    if df.empty:
        return pd.DataFrame(columns=["ID_STORE", "tipo_cons", "TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM", "TOT_OTHERS", "stringa"])

    return df


def render_bolla_printable_html(bolla_records: List[Dict[str, Any]], title: str = "Bolla di Consegna Inditex") -> str:
    """
    Generates a clean, professional printable HTML page for one or multiple bolle.
    Includes page breaks between notes for batch printing.
    """
    html_pages = []

    for b in bolla_records:
        bid = b.get("id", "")
        access_id = b.get("access_id")
        doc_num = f"{access_id}" if access_id else f"{bid:05d}" if bid else "BOZZA"

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
        autista = b.get("autista", "")
        cell = b.get("cell_autista", "")
        mezzo = b.get("tipo_mezzo", "")
        indirizzo = b.get("indirizzo_destino", "")

        c_abb = float(b.get("colli_abbigl") or 0)
        c_calz = float(b.get("colli_calzat") or 0)
        c_eco = float(b.get("colli_ecom") or 0)
        c_oth = float(b.get("colli_others") or 0)
        c_var = float(b.get("colli_vario") or 0)
        c_dann = float(b.get("colli_dann") or 0)
        c_nonconf = float(b.get("colli_non_conf") or 0)
        anomalie = b.get("anomalie_scarico", "")
        stringa = b.get("stringa", "")

        tot_operativa = c_abb + c_calz + c_eco + c_oth + c_var

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
                t = item.get("tipo", "")
                if c > 0:
                    tot_inter_colli += int(c)
                    inter_rows_html += f"<tr><td>{m}</td><td style='text-align:center;'>{int(c)}</td><td>{t}</td></tr>"

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
                    BOLLA DI CONSEGNA N° <span style="color:#d9534f;">{doc_num}</span> {badge_tipo}
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
                        <strong>Autista:</strong> {autista} &nbsp;|&nbsp; <strong>Cell:</strong> {cell}<br>
                        <strong>Mezzo:</strong> {mezzo}
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
                        <td class="num">{int(c_abb) if c_abb.is_integer() else c_abb}</td>
                        <td>Previsione Piattaforma Roma</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI CALZATURE</strong></td>
                        <td class="num">{int(c_calz) if c_calz.is_integer() else c_calz}</td>
                        <td>Calzature e Accessori</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI E-COMMERCE</strong></td>
                        <td class="num">{int(c_eco) if c_eco.is_integer() else c_eco}</td>
                        <td>Consegne E-com negozio</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI OTHERS</strong></td>
                        <td class="num">{int(c_oth) if c_oth.is_integer() else c_oth}</td>
                        <td>Altri Bultos / Arredo / Cancelleria</td>
                    </tr>
                    <tr>
                        <td><strong>COLLI MAT. VARIO DA PIATTAFORMA</strong></td>
                        <td class="num">{int(c_var) if c_var.is_integer() else c_var}</td>
                        <td>Stand / Ceste / Materiali</td>
                    </tr>
                    <tr class="total-row">
                        <td>TOTALE COLLI OPERATIVA CONSEGNATI</td>
                        <td class="num" style="font-size: 15px;">{int(tot_operativa) if tot_operativa.is_integer() else tot_operativa}</td>
                        <td>-</td>
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
                            <th style="text-align:left;">TIPOLOGIA MERCE</th>
                        </tr>
                    </thead>
                    <tbody>
                        {inter_rows_html or "<tr><td colspan='3' style='text-align:center; color:#888;'>Nessun trasferimento inter-negozio registrato</td></tr>"}
                        {f'<tr class="total-row"><td colspan="2" style="text-align:right;">TOTALE COLLI TRASFERIMENTI:</td><td class="num">{tot_inter_colli}</td></tr>' if tot_inter_colli > 0 else ''}
                    </tbody>
                </table>
            </div>

            <!-- ANOMALIE E SCARICO -->
            <div style="margin-top: 8px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                <div class="border-box">
                    <strong>COLLI DANNEGGIATI IN ORIGINE:</strong> {int(c_dann) if c_dann else '0'}<br>
                    <strong>COLLI NON CONFORMI:</strong> {int(c_nonconf) if c_nonconf else '0'}
                </div>
                <div class="border-box">
                    <strong>ANOMALIE RISCONTRATE ALLO SCARICO:</strong><br>
                    <span style="color:#d9534f; font-weight:bold;">{anomalie or 'Nessuna anomalia riscontrata'}</span>
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
                    <strong>FIRMA VETTORE / AUTISTA</strong><br><br><br>
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
            min-height: 285mm;
            margin: 0 auto 25px auto;
            padding: 12mm 15mm;
            box-sizing: border-box;
            border: 1px solid #ccc;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            page-break-after: always;
        }}
        .header-box {{
            display: flex;
            justify-content: space-between;
            font-size: 9.5px;
            line-height: 1.35;
            border: 1px solid #333;
            padding: 8px;
            margin-bottom: 10px;
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
            padding: 7px 12px;
            margin-bottom: 10px;
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
            gap: 10px;
            margin-bottom: 8px;
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
            padding: 6px 8px;
            line-height: 1.45;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 4px;
            font-size: 11px;
        }}
        .data-table th, .data-table td {{
            border: 1px solid #444;
            padding: 5px 8px;
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
            font-size: 10.5px;
            font-weight: bold;
            background: #e2e8f0;
            padding: 4px 8px;
            border: 1px solid #444;
            border-bottom: none;
        }}
        .border-box {{
            border: 1px solid #444;
            padding: 6px 8px;
            min-height: 40px;
            line-height: 1.4;
        }}
        .signature-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 8px;
            margin-top: 15px;
        }}
        .sig-box {{
            border: 1px solid #444;
            padding: 8px;
            min-height: 75px;
            text-align: center;
            font-size: 9.5px;
        }}

        @media print {{
            body {{
                background: white;
                padding: 0;
                margin: 0;
            }}
            .print-btn-bar {{
                display: none !important;
            }}
            .bolla-sheet {{
                box-shadow: none;
                border: none;
                margin: 0;
                padding: 10mm 12mm;
                page-break-after: always;
            }}
        }}
    </style>
</head>
<body>
    <div class="print-btn-bar">
        <button class="btn-print" onclick="window.print()">🖨️ Stampa Documento (Tutte le Bolle)</button>
        <span style="margin-left: 15px; color: #555;">Totale Bolle generate: <strong>{len(bolla_records)}</strong></span>
    </div>
    {"".join(html_pages)}
</body>
</html>
"""
    return full_html
