import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime, date
import pandas as pd

from src.config import DATA_DIR

DEFAULT_ACCESS_PATH = Path(os.getenv("ZARA_LEGACY_MDB_PATH", str(DATA_DIR / "BOLLE INDITEX_rev.6.mdb")))


def get_oledb_connection(mdb_path: Union[str, Path] = DEFAULT_ACCESS_PATH):
    """
    Creates and opens an ADODB connection to Microsoft Access .mdb / .accdb
    using the 64-bit ACE OLEDB provider.
    """
    import win32com.client
    p = Path(mdb_path)
    if not p.exists():
        raise FileNotFoundError(f"File Access non trovato: {p}")
    
    conn = win32com.client.Dispatch("ADODB.Connection")
    providers = ["Microsoft.ACE.OLEDB.16.0", "Microsoft.ACE.OLEDB.12.0", "Microsoft.Jet.OLEDB.4.0"]
    last_err = None
    for prov in providers:
        try:
            conn_str = f"Provider={prov};Data Source={str(p)};"
            conn.Open(conn_str)
            return conn
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Impossibile connettersi ad Access tramite i provider OLEDB: {last_err}")


def check_access_connection(mdb_path: Union[str, Path] = DEFAULT_ACCESS_PATH) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Checks if the Access database is accessible and retrieves basic stats.
    """
    try:
        p = Path(mdb_path)
        if not p.exists():
            return False, f"File non trovato nel percorso: {p}", {}
        
        conn = get_oledb_connection(p)
        import win32com.client
        rs = win32com.client.Dispatch("ADODB.Recordset")
        
        # Check TBL_DATI count and max date
        rs.Open("SELECT COUNT(*), MAX(DATA) FROM [TBL_DATI]", conn, 1, 1)
        total_records = int(rs.Fields(0).Value or 0)
        max_dt = rs.Fields(1).Value
        max_dt_str = str(max_dt)[:10] if max_dt else "N/D"
        rs.Close()
        
        # Check DETTAGLIATO count
        rs.Open("SELECT COUNT(*) FROM [DETTAGLIATO]", conn, 1, 1)
        stores_count = int(rs.Fields(0).Value or 0)
        rs.Close()
        
        conn.Close()
        info = {
            "path": str(p),
            "file_size_mb": round(p.stat().st_size / (1024 * 1024), 2),
            "total_deliveries": total_records,
            "max_date": max_dt_str,
            "stores_count": stores_count
        }
        return True, "Connessione riuscita a Microsoft Access!", info
    except Exception as e:
        return False, f"Errore di connessione: {e}", {}


def get_available_dates(mdb_path: Union[str, Path] = DEFAULT_ACCESS_PATH, limit: int = 50) -> List[str]:
    """
    Returns unique delivery dates present in TBL_DATI, sorted descending (YYYY-MM-DD).
    """
    try:
        conn = get_oledb_connection(mdb_path)
        import win32com.client
        rs = win32com.client.Dispatch("ADODB.Recordset")
        rs.Open("SELECT DISTINCT DATA FROM [TBL_DATI] WHERE DATA IS NOT NULL ORDER BY DATA DESC", conn, 1, 1)
        
        dates = []
        while not rs.EOF and len(dates) < limit:
            v = rs.Fields(0).Value
            if v:
                d_str = str(v)[:10]
                if d_str not in dates and len(d_str) == 10 and d_str[0].isdigit():
                    dates.append(d_str)
            rs.MoveNext()
        rs.Close()
        conn.Close()
        return dates
    except Exception as e:
        print(f"Error fetching dates from Access: {e}")
        return []


def fetch_actual_deliveries_df(
    mdb_path: Union[str, Path] = DEFAULT_ACCESS_PATH,
    target_date: Optional[Union[str, date]] = None
) -> pd.DataFrame:
    """
    Queries TBL_DATI from Access for the specified date and formats it into the
    exact schema expected by compute_planning_roma:
    ['ID_STORE', 'TIPO_CONS', 'TOT_ABBIGL', 'TOT_CALZAT', 'TOT_ECOM', 'TOT_OTHERS', 'TOT_VARIO', 'TOT_CONT', 'colli_mat_vario', 'stringa']
    """
    p = Path(mdb_path)
    if not p.exists():
        return pd.DataFrame()

    conn = get_oledb_connection(p)
    import win32com.client
    rs = win32com.client.Dispatch("ADODB.Recordset")

    if target_date:
        d_str = str(target_date)[:10]
        # Access date literal format #YYYY-MM-DD#
        sql = f"SELECT * FROM [TBL_DATI] WHERE DATA >= #{d_str}# AND DATA < #{d_str} 23:59:59#"
    else:
        # Default: latest date in DB
        sql = "SELECT * FROM [TBL_DATI] WHERE DATA = (SELECT MAX(DATA) FROM [TBL_DATI])"

    rs.Open(sql, conn, 1, 1)
    cols = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    rows = []
    while not rs.EOF:
        row = []
        for i in range(rs.Fields.Count):
            v = rs.Fields(i).Value
            if v is not None and hasattr(v, "strftime"):
                row.append(str(v)[:19])
            else:
                row.append(v)
        rows.append(row)
        rs.MoveNext()

    rs.Close()
    conn.Close()

    if not rows:
        return pd.DataFrame(columns=[
            "ID_STORE", "TIPO_CONS", "TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM",
            "TOT_OTHERS", "TOT_VARIO", "TOT_CONT", "colli_mat_vario", "stringa"
        ])

    df_raw = pd.DataFrame(rows, columns=cols)

    # Process intershops (stringa) and aggregate per store
    cleaned_records = []
    for _, r in df_raw.iterrows():
        sid_raw = str(r.get("ID_STORE", "")).strip()
        if not sid_raw or sid_raw.upper() in ("NONE", "NAN", ""):
            continue
        # Clean store id (e.g. 1265.0 -> 1265)
        if sid_raw.endswith(".0"):
            sid = sid_raw[:-2]
        else:
            sid = sid_raw.split("-")[0].strip()

        tipo_cons = str(r.get("TIPO_CONS", "STD")).strip().upper()
        if not tipo_cons or tipo_cons == "NONE":
            tipo_cons = "STD"

        # Build intershops description
        inter_parts = []
        for i in range(1, 11):
            m = r.get(f"MITTENTE{i}")
            c = r.get(f"COLLI{i}")
            t = r.get(f"TIPO_MERCE{i}")
            try:
                c_val = float(c) if pd.notna(c) and str(c).strip() else 0.0
            except:
                c_val = 0.0

            if c_val > 0:
                p_desc = f"{int(c_val)}C"
                if pd.notna(t) and str(t).strip() and str(t).strip().upper() != "NONE":
                    p_desc += f" {str(t).strip()}"
                if pd.notna(m) and str(m).strip() and str(m).strip().upper() != "NONE":
                    m_str = str(m).strip()
                    if m_str.endswith(".0"):
                        m_str = m_str[:-2]
                    p_desc += f" da {m_str}"
                inter_parts.append(p_desc)

        stringa_val = " ".join(inter_parts)

        def to_f(v):
            try:
                return float(v) if pd.notna(v) and str(v).strip() != "" else 0.0
            except:
                return 0.0

        cleaned_records.append({
            "ID_STORE": sid,
            "TIPO_CONS": tipo_cons,
            "TOT_ABBIGL": to_f(r.get("COLLI_ABBIGL")),
            "TOT_CALZAT": to_f(r.get("COLLI_CALZAT")),
            "TOT_ECOM": to_f(r.get("COLLI_ECOM")),
            "TOT_OTHERS": to_f(r.get("COLLI_OTHERS")),
            "TOT_VARIO": to_f(r.get("COLLI_VARIO")),
            "TOT_CONT": to_f(r.get("COLLI_CONT")),
            "colli_mat_vario": to_f(r.get("COLLI_MAT_VARIO")),
            "stringa": stringa_val
        })

    df_clean = pd.DataFrame(cleaned_records)
    if df_clean.empty:
        return df_clean

    # Group by ID_STORE and TIPO_CONS so each store has aggregated quantities
    agg_funcs = {
        "TOT_ABBIGL": "sum",
        "TOT_CALZAT": "sum",
        "TOT_ECOM": "sum",
        "TOT_OTHERS": "sum",
        "TOT_VARIO": "sum",
        "TOT_CONT": "sum",
        "colli_mat_vario": "sum",
        "stringa": lambda s: " ".join([x for x in s if x.strip()])
    }
    df_agg = df_clean.groupby(["ID_STORE", "TIPO_CONS"], as_index=False).agg(agg_funcs)
    return df_agg


def fetch_bolle_summary_df(
    mdb_path: Union[str, Path] = DEFAULT_ACCESS_PATH,
    target_date: Optional[Union[str, date]] = None
) -> pd.DataFrame:
    """
    Fetches full delivery note details for a date by joining TBL_DATI with DETTAGLIATO.
    """
    p = Path(mdb_path)
    if not p.exists():
        return pd.DataFrame()

    conn = get_oledb_connection(p)
    import win32com.client
    rs = win32com.client.Dispatch("ADODB.Recordset")

    if target_date:
        d_str = str(target_date)[:10]
        sql = f"""
        SELECT t.id, t.DATA, t.ID_STORE, d.[PUNTO VENDITA], d.Store, d.Provincia,
               t.VETTORE, t.CELL_AUTISTA, d.AUTISTA, d.[TIPOLOGIA AUTOMEZZO],
               t.TIPO_CONS, t.COLLI_ABBIGL, t.COLLI_CALZAT, t.COLLI_ECOM, t.COLLI_OTHERS,
               t.COLLI_VARIO, t.COLLI_CONT, t.COLLI_MAT_VARIO, t.INDIRIZZO_DESTINO
        FROM [TBL_DATI] AS t
        LEFT JOIN [DETTAGLIATO] AS d ON t.ID_STORE = d.[Store ID]
        WHERE t.DATA >= #{d_str}# AND t.DATA < #{d_str} 23:59:59#
        ORDER BY t.id DESC
        """
    else:
        sql = """
        SELECT t.id, t.DATA, t.ID_STORE, d.[PUNTO VENDITA], d.Store, d.Provincia,
               t.VETTORE, t.CELL_AUTISTA, d.AUTISTA, d.[TIPOLOGIA AUTOMEZZO],
               t.TIPO_CONS, t.COLLI_ABBIGL, t.COLLI_CALZAT, t.COLLI_ECOM, t.COLLI_OTHERS,
               t.COLLI_VARIO, t.COLLI_CONT, t.COLLI_MAT_VARIO, t.INDIRIZZO_DESTINO
        FROM [TBL_DATI] AS t
        LEFT JOIN [DETTAGLIATO] AS d ON t.ID_STORE = d.[Store ID]
        WHERE t.DATA = (SELECT MAX(DATA) FROM [TBL_DATI])
        ORDER BY t.id DESC
        """

    rs.Open(sql, conn, 1, 1)
    cols = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    rows = []
    while not rs.EOF:
        row = []
        for i in range(rs.Fields.Count):
            v = rs.Fields(i).Value
            if v is not None and hasattr(v, "strftime"):
                row.append(str(v)[:19])
            else:
                row.append(v)
        rows.append(row)
        rs.MoveNext()

    rs.Close()
    conn.Close()

    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        # Calculate total delivered crts
        num_cols = ["COLLI_ABBIGL", "COLLI_CALZAT", "COLLI_ECOM", "COLLI_OTHERS", "COLLI_VARIO", "COLLI_CONT"]
        for c in num_cols:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        df["TOTALE_COLLI"] = df[num_cols].sum(axis=1)
    return df
