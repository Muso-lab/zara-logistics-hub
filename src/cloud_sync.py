import base64
import json
import os
import sqlite3
import urllib.request
import urllib.error
from typing import Any, Optional
import pandas as pd
from pathlib import Path
from src.config import DATA_DIR, DB_PATH

CLOUD_CONFIG_FILE = DATA_DIR / "cloud_config.json"
DEFAULT_GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyPQbjCSCFU76LwNESVB5FT6z4J0mQpqoPvP7Lo8rsn7Vj8rhhtz6p5Es5H3zU0ccsoYQ/exec"
_DEFAULT_EXT_U = "plt_it_transmec_ro"
_DEFAULT_EXT_P = base64.b64decode("aVNtUEV2dnVrVjkt").decode("utf-8")


def is_test_environment() -> bool:
    """Rileva se il codice e' eseguito all'interno di una suite di test (es. pytest) per bloccare ogni chiamata verso Google Sheets di produzione."""
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        or os.environ.get("ENV") == "test"
        or os.environ.get("DISABLE_CLOUD_SYNC") == "1"
    )


def get_extranet_credentials() -> tuple[str, str]:
    """
    Restituisce (username, password) salvati per Extranet Inditex
    verificando env, Streamlit secrets, DB app_settings, cloud_config.json e fallback.
    """
    u = os.environ.get("EXTRANET_USER", "").strip()
    p = os.environ.get("EXTRANET_PASS", "").strip()
    if u and p:
        return u, p

    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            if "EXTRANET_USER" in st.secrets and "EXTRANET_PASS" in st.secrets:
                return str(st.secrets["EXTRANET_USER"]).strip(), str(st.secrets["EXTRANET_PASS"]).strip()
            if "extranet" in st.secrets:
                su = str(st.secrets["extranet"].get("user", "")).strip()
                sp = str(st.secrets["extranet"].get("password", "")).strip()
                if su and sp:
                    return su, sp
    except Exception:
        pass

    try:
        from src.db import get_app_setting
        db_u = get_app_setting("extranet_user", "").strip()
        db_p = get_app_setting("extranet_pass", "").strip()
        if db_u and db_p:
            return db_u, db_p
    except Exception:
        pass

    if CLOUD_CONFIG_FILE.exists():
        try:
            data = json.loads(CLOUD_CONFIG_FILE.read_text(encoding="utf-8"))
            cu = str(data.get("extranet_user", "")).strip()
            cp = str(data.get("extranet_pass", "")).strip()
            if cu and cp:
                return cu, cp
        except Exception:
            pass

    return _DEFAULT_EXT_U, _DEFAULT_EXT_P


def set_extranet_credentials(username: str, password: str):
    """Salva le credenziali Extranet Inditex nel file locale, nel DB e sincronizza su Google Sheets."""
    username = str(username).strip()
    password = str(password).strip()

    CLOUD_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CLOUD_CONFIG_FILE.exists():
        try:
            data = json.loads(CLOUD_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["extranet_user"] = username
    data["extranet_pass"] = password
    CLOUD_CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    try:
        from src.db import set_app_setting
        set_app_setting("extranet_user", username)
        set_app_setting("extranet_pass", password)
        auto_sync_tables(["app_settings"])
    except Exception:
        pass

ALL_SYNC_TABLES = [
    "stores",
    "vehicles",
    "store_delivery_profiles",
    "deleted_stores",
    "bolle",
    "deleted_bolle",
    "runs",
    "deleted_runs",
    "planning_results",
    "spunta_arrivi",
    "forecast_raw",
    "app_settings",
]


def _normalize_date_str(val: Any) -> Optional[str]:
    """Converts timestamps, ISO formats and date objects to standard YYYY-MM-DD."""
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    from src.utils import parse_date_obj
    try:
        return parse_date_obj(val).strftime("%Y-%m-%d")
    except Exception:
        return str(val).split("T")[0].split(" ")[0].strip()


def get_cloud_url() -> str:
    """
    Recupera l'URL della Web App Google Apps Script da:
    1. Variabile d'ambiente GOOGLE_SCRIPT_URL
    2. Streamlit secrets (st.secrets["GOOGLE_SCRIPT_URL"])
    3. File di configurazione locale data/cloud_config.json
    4. URL predefinito configurato nel progetto
    """
    env_url = os.environ.get("GOOGLE_SCRIPT_URL", "").strip()
    if env_url:
        return env_url

    try:
        import streamlit as st
        if hasattr(st, "secrets") and "GOOGLE_SCRIPT_URL" in st.secrets:
            sec_url = str(st.secrets["GOOGLE_SCRIPT_URL"]).strip()
            if sec_url:
                return sec_url
    except Exception:
        pass

    if CLOUD_CONFIG_FILE.exists():
        try:
            data = json.loads(CLOUD_CONFIG_FILE.read_text(encoding="utf-8"))
            url = str(data.get("google_script_url", "")).strip()
            if url:
                return url
        except Exception:
            pass

    return DEFAULT_GOOGLE_SCRIPT_URL


def set_cloud_url(url: str):
    """Salva l'URL della Web App Google Apps Script nel file di configurazione."""
    CLOUD_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CLOUD_CONFIG_FILE.exists():
        try:
            data = json.loads(CLOUD_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["google_script_url"] = str(url).strip()
    CLOUD_CONFIG_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def push_tables_to_cloud(table_names=None, timeout: int = 25) -> dict:
    """
    Invia le tabelle specificate (o quelle operative se table_names=None) dal DB SQLite
    al Foglio Google tramite la Web App di Google Apps Script.
    Per la tabella 'bolle' (che contiene 30.000+ bolle storiche ex-Access già nel file .db),
    sincronizza su Google Sheets le ultime 800 bolle operative per garantire velocità istantanea.
    """
    if is_test_environment():
        return {"status": "skipped", "message": "Test environment - cloud push disabilitato per proteggere i dati di produzione."}

    url = get_cloud_url()
    if not url:
        return {"status": "skipped", "message": "Nessun URL Google Apps Script configurato."}

    targets = table_names if table_names else ALL_SYNC_TABLES
    payload_tables = {}

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        try:
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            pass
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {r[0] for r in cur.fetchall()}

        del_bolla_ids_local = set()
        if "deleted_bolle" in existing_tables:
            try:
                cur.execute("SELECT bolla_id FROM deleted_bolle")
                del_bolla_ids_local = {int(r[0]) for r in cur.fetchall() if str(r[0]).isdigit()}
            except Exception:
                pass

        for t in targets:
            if t not in existing_tables:
                continue
            if t == "bolle":
                df = pd.read_sql_query("""
                    SELECT * FROM bolle 
                    WHERE data NOT LIKE '%2098%' AND data NOT LIKE '%2099%' AND data NOT LIKE '%2100%'
                      AND (data_consegna IS NULL OR (data_consegna NOT LIKE '%2098%' AND data_consegna NOT LIKE '%2099%' AND data_consegna NOT LIKE '%2100%'))
                      AND id_store != '9999'
                    ORDER BY id DESC LIMIT 800
                """, conn)
            else:
                df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
            # SAFETY GUARD: Never overwrite cloud data with an empty table if local table has 0 rows!
            if df.empty and t in ["runs", "planning_results", "spunta_arrivi", "forecast_raw", "bolle", "stores", "store_delivery_profiles", "vehicles"]:
                continue

            # IRONCLAD GUARD PER STORES: impedisce a un container non inizializzato (dove i negozi
            # sono stati auto-inseriti come 'DA ASSEGNARE') di sovrascrivere l'anagrafica sul Cloud!
            if t == "stores" and not df.empty:
                if len(df) < 10:
                    print(f"SAFETY GUARD: push di 'stores' bloccato (solo {len(df)} negozi in locale).")
                    continue
                if "giro" in df.columns:
                    da_ass_cnt = int((df["giro"].astype(str).str.strip().str.upper() == "DA ASSEGNARE").sum())
                    if da_ass_cnt > max(10, int(len(df) * 0.3)):
                        print(f"SAFETY GUARD: push di 'stores' bloccato ({da_ass_cnt}/{len(df)} negozi con giro 'DA ASSEGNARE').")
                        continue

            if t == "bolle" and not df.empty:
                # Extra Cloud Guard per BOLLE: non sovrascrivere MAI una spunta confermata sul cloud (spuntato=1)
                # con un record locale non ancora spuntato (spuntato=0), e preserva le bolle cloud mancanti in locale.
                try:
                    sep = "&" if "?" in url else "?"
                    req_cb = urllib.request.Request(f"{url}{sep}table=bolle", method="GET")
                    with urllib.request.urlopen(req_cb, timeout=10) as resp_cb:
                        d_cb = json.loads(resp_cb.read().decode("utf-8"))
                        if d_cb.get("status") == "ok" and "tables" in d_cb and "bolle" in d_cb["tables"]:
                            cloud_bolle = d_cb["tables"]["bolle"]
                            if cloud_bolle:
                                df_cb = pd.DataFrame(cloud_bolle)
                                if "id" in df_cb.columns and "id" in df.columns:
                                    if "data" in df_cb.columns:
                                        df_cb["data"] = df_cb["data"].apply(_normalize_date_str)
                                    if "data_consegna" in df_cb.columns:
                                        df_cb["data_consegna"] = df_cb["data_consegna"].apply(_normalize_date_str)
                                    if "id_store" in df_cb.columns:
                                        df_cb["id_store"] = df_cb["id_store"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
                                    df_cb["id_num"] = pd.to_numeric(df_cb["id"], errors="coerce")
                                    df_cb = df_cb[df_cb["id_num"].notna()].copy()
                                    df_cb["id"] = df_cb["id_num"].astype(int)
                                    df_cb = df_cb.drop(columns=["id_num"])
                                    if del_bolla_ids_local:
                                        df_cb = df_cb[~df_cb["id"].isin(del_bolla_ids_local)]

                                    # Mappa (id_store, data_consegna, tipo_cons) -> riga cloud spuntata
                                    cloud_spuntati_by_key = {}
                                    if "spuntato" in df_cb.columns:
                                        for _, cr in df_cb.iterrows():
                                            if str(cr.get("spuntato", "0")).strip() in ("1", "1.0", "True", "true"):
                                                k_b = (
                                                    str(cr.get("id_store", "")).strip(),
                                                    str(cr.get("data_consegna", "") or "")[:10],
                                                    str(cr.get("tipo_cons", "STD") or "STD").strip().upper(),
                                                )
                                                cloud_spuntati_by_key[k_b] = cr

                                    # Se una riga locale ha spuntato=0 ma sul cloud ha spuntato=1, preserva i valori cloud!
                                    if cloud_spuntati_by_key and "spuntato" in df.columns:
                                        common_upd_cols = [c for c in df.columns if c in df_cb.columns and c != "id"]
                                        for idx_l, lr in df.iterrows():
                                            if str(lr.get("spuntato", "0")).strip() not in ("1", "1.0", "True", "true"):
                                                k_l = (
                                                    str(lr.get("id_store", "")).strip(),
                                                    str(lr.get("data_consegna", "") or "")[:10],
                                                    str(lr.get("tipo_cons", "STD") or "STD").strip().upper(),
                                                )
                                                if k_l in cloud_spuntati_by_key:
                                                    cr_win = cloud_spuntati_by_key[k_l]
                                                    for cc in common_upd_cols:
                                                        df.at[idx_l, cc] = cr_win[cc]

                                    # Preserva bolle cloud non presenti in locale (non in deleted_bolle)
                                    local_ids = set(df["id"].astype(int).tolist())
                                    missing_cb = df_cb[~df_cb["id"].isin(local_ids)]
                                    if not missing_cb.empty:
                                        common_c = [c for c in df.columns if c in missing_cb.columns]
                                        df = pd.concat([df, missing_cb[common_c]], ignore_index=True).sort_values("id", ascending=False).head(800)
                except Exception:
                    pass

            if t == "runs" and not df.empty:
                # Extra Cloud Guard: ensure older cloud runs are never overwritten by an ephemeral runner
                try:
                    sep = "&" if "?" in url else "?"
                    req_c = urllib.request.Request(f"{url}{sep}table=runs", method="GET")
                    with urllib.request.urlopen(req_c, timeout=10) as resp_c:
                        d_c = json.loads(resp_c.read().decode("utf-8"))
                        if d_c.get("status") == "ok" and "tables" in d_c and "runs" in d_c["tables"]:
                            cloud_runs = d_c["tables"]["runs"]
                            if cloud_runs:
                                df_c = pd.DataFrame(cloud_runs)
                                if "id" in df_c.columns and "id" in df.columns:
                                    local_ids = set(df["id"].tolist())
                                    missing_c = df_c[~df_c["id"].isin(local_ids)]
                                    if not missing_c.empty:
                                        common_c = [c for c in df.columns if c in missing_c.columns]
                                        df = pd.concat([df, missing_c[common_c]], ignore_index=True).sort_values("id")
                except Exception:
                    pass

            payload_tables[t] = json.loads(df.to_json(orient="records"))
    finally:
        conn.close()

    body = json.dumps({"tables": payload_tables}, default=str).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if "accounts.google.com" in final_url:
                return {
                    "status": "error",
                    "message": "Permesso negato da Google: nell'implementazione Apps Script imposta 'Chi ha accesso' su 'Chiunque' (non 'Chiunque abbia un account Google').",
                }
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as e:
        return {"status": "error", "message": str(e)}


def pull_all_from_cloud(timeout: int = 25) -> dict:
    """
    Scarica le tabelle dal Foglio Google (tramite Google Apps Script)
    e aggiorna il database SQLite locale.
    """
    if is_test_environment():
        return {"status": "skipped", "message": "Test environment - cloud pull disabilitato per proteggere i dati di produzione."}

    url = get_cloud_url()
    if not url:
        return {"status": "skipped", "message": "Nessun URL Google Apps Script configurato."}

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if "accounts.google.com" in final_url:
                return {
                    "status": "error",
                    "message": "Permesso negato da Google: nell'implementazione Apps Script imposta 'Chi ha accesso' su 'Chiunque' (non 'Chiunque abbia un account Google').",
                }
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except Exception as e:
        return {"status": "error", "message": str(e)}

    if data.get("status") != "ok" or "tables" not in data:
        return {"status": "error", "message": data.get("message", "Risposta non valida da Google Sheets.")}

    tables_dict = data["tables"]

    # Google Apps Script default doGet only returns primary tables.
    # Explicitly fetch any table from ALL_SYNC_TABLES that is missing from the initial response.
    for extra_t in ALL_SYNC_TABLES:
        if extra_t not in tables_dict:
            try:
                sep = "&" if "?" in url else "?"
                req_extra = urllib.request.Request(f"{url}{sep}table={extra_t}", method="GET")
                with urllib.request.urlopen(req_extra, timeout=10) as resp_extra:
                    d_extra = json.loads(resp_extra.read().decode("utf-8"))
                    if d_extra.get("status") == "ok" and "tables" in d_extra and extra_t in d_extra["tables"]:
                        tables_dict[extra_t] = d_extra["tables"][extra_t]
            except Exception:
                pass

    # CRITICAL: Assicura che lo schema SQLite (tabelle stores, runs, bolle, ecc.) esista PRIMA del pull,
    # altrimenti in un container effimero (Cloud Run Job / GitHub Actions) existing_tables sarebbe vuoto!
    try:
        from src.db import init_db
        from src.bolle_manager import init_bolle_tables
        init_db()
        init_bolle_tables(DB_PATH)
    except Exception as init_err:
        print(f"Warning schema init before cloud pull: {init_err}")

    restored_counts = {}

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        try:
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            pass
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {r[0] for r in cur.fetchall()}

        # Load local blacklist sets to ensure deleted records are never revived
        cur.execute("CREATE TABLE IF NOT EXISTS deleted_stores (store_id TEXT PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS deleted_runs (run_id INTEGER PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        cur.execute("CREATE TABLE IF NOT EXISTS deleted_bolle (bolla_id INTEGER PRIMARY KEY, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

        cur.execute("SELECT store_id FROM deleted_stores")
        del_store_ids = {str(r[0]).strip() for r in cur.fetchall()}
        cur.execute("SELECT run_id FROM deleted_runs")
        del_run_ids = {int(r[0]) for r in cur.fetchall() if str(r[0]).isdigit()}
        cur.execute("SELECT bolla_id FROM deleted_bolle")
        del_bolla_ids = {int(r[0]) for r in cur.fetchall() if str(r[0]).isdigit()}

        # Also merge any blacklist records returned from cloud
        if "deleted_stores" in tables_dict:
            for item in tables_dict["deleted_stores"]:
                if isinstance(item, dict) and "store_id" in item:
                    del_store_ids.add(str(item["store_id"]).strip())
        if "deleted_runs" in tables_dict:
            for item in tables_dict["deleted_runs"]:
                if isinstance(item, dict) and "run_id" in item and str(item["run_id"]).isdigit():
                    del_run_ids.add(int(item["run_id"]))
        if "deleted_bolle" in tables_dict:
            for item in tables_dict["deleted_bolle"]:
                if isinstance(item, dict) and "bolla_id" in item and str(item["bolla_id"]).isdigit():
                    del_bolla_ids.add(int(item["bolla_id"]))

        for t_name, rows in tables_dict.items():
            if t_name not in existing_tables or not rows:
                continue

            cur.execute(f"PRAGMA table_info({t_name})")
            valid_cols = [r[1] for r in cur.fetchall()]

            df = pd.DataFrame(rows)
            common_cols = [c for c in valid_cols if c in df.columns]
            if not common_cols:
                continue

            df_clean = df[common_cols].copy()
            for str_col in ["store_id", "store_code", "id_store", "ID_STORE"]:
                if str_col in df_clean.columns:
                    df_clean[str_col] = (
                        df_clean[str_col]
                        .astype(str)
                        .str.replace(r"\.0$", "", regex=True)
                        .str.strip()
                    )

            if t_name == "bolle":
                # Normalize dates to standard YYYY-MM-DD
                if "data" in df_clean.columns:
                    df_clean["data"] = df_clean["data"].apply(_normalize_date_str)
                if "data_consegna" in df_clean.columns:
                    df_clean["data_consegna"] = df_clean["data_consegna"].apply(_normalize_date_str)
                # Strip out any dummy/test dates that leaked into Google Sheets
                if "data" in df_clean.columns:
                    df_clean = df_clean[~df_clean["data"].astype(str).str.contains("2098|2099|2100", na=False)]
                if "data_consegna" in df_clean.columns:
                    df_clean = df_clean[~df_clean["data_consegna"].astype(str).str.contains("2098|2099|2100", na=False)]
                if "id_store" in df_clean.columns:
                    df_clean = df_clean[df_clean["id_store"].astype(str).str.strip() != "9999"]
                # Filter out any blacklisted bolle IDs
                if "id" in df_clean.columns and del_bolla_ids:
                    df_clean = df_clean[~df_clean["id"].isin(del_bolla_ids)]
            elif t_name == "runs":
                if "run_date" in df_clean.columns:
                    df_clean["run_date"] = df_clean["run_date"].apply(_normalize_date_str)
                if df_clean.empty:
                    continue
                # Never wipe runs if df_clean is empty, and do not let legacy deleted_runs blacklist wipe valid runs
                cur.execute(f"DELETE FROM {t_name}")
            elif t_name in ["planning_results", "spunta_arrivi", "forecast_raw", "other_items", "sga_flows"]:
                if df_clean.empty:
                    continue
                cur.execute(f"DELETE FROM {t_name}")
            elif t_name in ["stores", "store_delivery_profiles"]:
                target_col = "store_id" if "store_id" in df_clean.columns else "id_store"
                if target_col in df_clean.columns and del_store_ids:
                    df_clean = df_clean[~df_clean[target_col].isin(del_store_ids)]
                if t_name == "stores" and "cod_sga" in df_clean.columns:
                    from src.config import ANAGRAFICA_FILE
                    if ANAGRAFICA_FILE.exists():
                        try:
                            _df_anag = pd.read_excel(ANAGRAFICA_FILE)
                            _sga_c = [c for c in _df_anag.columns if "sga" in c.lower()]
                            if _sga_c:
                                _map_sga = _df_anag.set_index(_df_anag["STORE_ID"].astype(str))[_sga_c[0]].dropna().to_dict()
                                for idx_r, row_st in df_clean.iterrows():
                                    val_sga = row_st.get("cod_sga")
                                    if pd.isna(val_sga) or str(val_sga).strip() in ["", "None", "0"]:
                                        sid_val = str(row_st.get("store_id", "")).strip()
                                        base_sid = sid_val[:-1] if sid_val.endswith("B") else sid_val
                                        if sid_val in _map_sga and pd.notna(_map_sga[sid_val]):
                                            df_clean.at[idx_r, "cod_sga"] = int(_map_sga[sid_val])
                                        elif base_sid in _map_sga and pd.notna(_map_sga[base_sid]):
                                            df_clean.at[idx_r, "cod_sga"] = int(_map_sga[base_sid])
                        except Exception:
                            pass
                cur.execute(f"DELETE FROM {t_name}")
            elif t_name not in ["bolle", "deleted_bolle", "deleted_runs", "deleted_stores"]:
                cur.execute(f"DELETE FROM {t_name}")

            col_names_sql = ", ".join(common_cols)
            placeholders_sql = ", ".join("?" for _ in common_cols)
            records = []
            for _, row_s in df_clean.iterrows():
                rec = []
                for c in common_cols:
                    val = row_s[c]
                    if pd.isna(val) or val == "":
                        rec.append(None)
                    else:
                        rec.append(val)
                records.append(tuple(rec))

            cur.executemany(
                f"INSERT OR REPLACE INTO {t_name} ({col_names_sql}) VALUES ({placeholders_sql})",
                records,
            )
            restored_counts[t_name] = len(records)

            if t_name == "app_settings":
                for rec in records:
                    try:
                        k_idx = common_cols.index("setting_key")
                        v_idx = common_cols.index("setting_value")
                        if rec[k_idx] == "email_config_json" and rec[v_idx]:
                            em_file = DATA_DIR / "email_config.json"
                            em_file.parent.mkdir(parents=True, exist_ok=True)
                            em_file.write_text(str(rec[v_idx]), encoding="utf-8")
                    except Exception:
                        pass

        # Enforce blacklists so deleted items are permanently purged
        # (Protegge le bolle recenti dal 2026-11-01+ da vecchi ID legacy di ottobre in deleted_bolle)
        try:
            cur.execute("DELETE FROM stores WHERE store_id IN (SELECT store_id FROM deleted_stores)")
            cur.execute("DELETE FROM store_delivery_profiles WHERE id_store IN (SELECT store_id FROM deleted_stores)")
            cur.execute("DELETE FROM bolle WHERE data LIKE '%2098%' OR data LIKE '%2099%' OR data LIKE '%2100%' OR data_consegna LIKE '%2098%' OR data_consegna LIKE '%2099%' OR data_consegna LIKE '%2100%' OR data_consegna = '2026-10-23' OR (data_consegna = '2026-10-24' AND tipo_cons = 'DOPPIA') OR id_store = '9999'")
            cur.execute("DELETE FROM bolle WHERE id IN (SELECT bolla_id FROM deleted_bolle) AND COALESCE(data_consegna, data, '') < '2026-11-01'")
            # Do NOT blanket delete active runs: if a run exists in the runs table, it is valid and must be kept.
        except Exception:
            pass

        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Errore durante il ripristino SQLite: {e}"}
    finally:
        conn.close()

    try:
        from src.bolle_manager import heal_shifted_bolle_dates
        heal_shifted_bolle_dates(DB_PATH)
    except Exception:
        pass

    return {"status": "ok", "restored": restored_counts}


def pull_single_table_from_cloud(table_name: str, timeout: int = 20) -> dict:
    """
    Scarica rapidamente una SINGOLA tabella (es. 'bolle') da Google Sheets (~2-3 secondi)
    e la aggiorna in SQLite locale senza ricaricare tutte le altre 11 tabelle.
    Ideale per allineare istantaneamente PC Magazzino e Mobile Banchina.
    """
    if is_test_environment():
        return {"status": "skipped", "message": "Test environment."}

    url = get_cloud_url()
    if not url:
        return {"status": "skipped", "message": "Nessun URL Google Apps Script configurato."}

    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}table={table_name}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if "accounts.google.com" in final_url:
                return {"status": "error", "message": "Permesso negato da Google Apps Script."}
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "message": str(e)}

    if data.get("status") != "ok" or "tables" not in data or table_name not in data["tables"]:
        return {"status": "error", "message": data.get("message", f"Tabella '{table_name}' non restituita dal Cloud.")}

    rows = data["tables"][table_name]
    if not rows:
        return {"status": "ok", "count": 0}

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        try:
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("PRAGMA journal_mode = WAL;")
        except Exception:
            pass
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        valid_cols = [r[1] for r in cur.fetchall()]
        df = pd.DataFrame(rows)
        common_cols = [c for c in valid_cols if c in df.columns]
        if not common_cols:
            return {"status": "error", "message": f"Nessuna colonna compatibile per '{table_name}'."}

        df_clean = df[common_cols].copy()
        for str_col in ["store_id", "store_code", "id_store", "ID_STORE"]:
            if str_col in df_clean.columns:
                df_clean[str_col] = (
                    df_clean[str_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
                )
        if table_name == "bolle":
            if "data" in df_clean.columns:
                df_clean["data"] = df_clean["data"].apply(_normalize_date_str)
            if "data_consegna" in df_clean.columns:
                df_clean["data_consegna"] = df_clean["data_consegna"].apply(_normalize_date_str)
            if "data" in df_clean.columns:
                df_clean = df_clean[~df_clean["data"].astype(str).str.contains("2098|2099|2100", na=False)]
            if "data_consegna" in df_clean.columns:
                df_clean = df_clean[~df_clean["data_consegna"].astype(str).str.contains("2098|2099|2100", na=False)]
            if "id_store" in df_clean.columns:
                df_clean = df_clean[df_clean["id_store"].astype(str).str.strip() != "9999"]

        col_names_sql = ", ".join(common_cols)
        placeholders_sql = ", ".join("?" for _ in common_cols)
        records = []
        for _, row_s in df_clean.iterrows():
            records.append(tuple(None if (pd.isna(row_s[c]) or row_s[c] == "") else row_s[c] for c in common_cols))

        cur.executemany(
            f"INSERT OR REPLACE INTO {table_name} ({col_names_sql}) VALUES ({placeholders_sql})",
            records,
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

    if table_name == "bolle":
        try:
            from src.bolle_manager import heal_shifted_bolle_dates
            heal_shifted_bolle_dates(DB_PATH)
        except Exception:
            pass

    return {"status": "ok", "count": len(records)}


import threading as _threading
import time as _time
from datetime import datetime as _dt

_sync_queue_lock = _threading.Lock()
_sync_exec_lock = _threading.Lock()
_pending_sync_tables: set = set()
_sync_worker_active: bool = False
_last_sync_status: dict = {"status": "idle", "time": "", "message": ""}


def get_last_sync_status() -> dict:
    """Restituisce lo stato dell'ultima sincronizzazione verso Google Sheets."""
    return dict(_last_sync_status)


def _record_sync_status(res: dict):
    global _last_sync_status
    _last_sync_status = {
        "status": res.get("status", "error"),
        "time": _dt.now().strftime("%H:%M:%S"),
        "message": str(res.get("message", "") or (", ".join(res.get("updated", [])) if res.get("updated") else "")),
    }


def sync_tables_now(table_names: list[str], timeout: int = 25) -> dict:
    """
    Sincronizza IMMEDIATAMENTE e in modo SERIALIZZATO (un solo push alla volta) le tabelle
    indicate verso Google Sheets, con 1 retry automatico in caso di lock temporaneo.
    Impedisce a Cloud Run di uccidere/throttlare la sincronizzazione prima del completamento.
    """
    if is_test_environment():
        return {"status": "skipped", "message": "Test environment."}
    if not get_cloud_url():
        return {"status": "skipped", "message": "Nessun URL Cloud configurato."}

    with _sync_exec_lock:
        last_res = {"status": "error", "message": "Sync non eseguito."}
        for attempt in range(2):
            last_res = push_tables_to_cloud(table_names=table_names, timeout=timeout)
            if last_res.get("status") == "ok":
                break
            if attempt == 0:
                _time.sleep(1.5)
        _record_sync_status(last_res)
        return last_res


def auto_sync_tables(table_names: list[str]):
    """
    Sincronizza in modo SERIALIZZATO (1 solo worker alla volta con accorpamento coda)
    le tabelle modificate verso Google Sheets, evitando collisioni di thread concorrenti
    sul LockService di Google Apps Script e picchi di memoria RAM su Cloud Run.
    """
    global _sync_worker_active
    if is_test_environment():
        return
    if not get_cloud_url():
        return

    with _sync_queue_lock:
        _pending_sync_tables.update(table_names)
        if _sync_worker_active:
            return
        _sync_worker_active = True

    def _serialized_worker():
        global _sync_worker_active
        try:
            while True:
                # Breve attesa per accorpare modifiche ravvicinate in un unico push pulito
                _time.sleep(0.4)
                with _sync_queue_lock:
                    if not _pending_sync_tables:
                        _sync_worker_active = False
                        return
                    batch = sorted(_pending_sync_tables)
                    _pending_sync_tables.clear()
                sync_tables_now(batch, timeout=30)
        except Exception:
            with _sync_queue_lock:
                _sync_worker_active = False

    _threading.Thread(target=_serialized_worker, name="ZaraCloudSyncWorker", daemon=True).start()
