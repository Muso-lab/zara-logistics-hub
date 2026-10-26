import base64
import json
import os
import sqlite3
import urllib.request
import urllib.error
import pandas as pd
from pathlib import Path
from src.config import DATA_DIR, DB_PATH

CLOUD_CONFIG_FILE = DATA_DIR / "cloud_config.json"
DEFAULT_GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyPQbjCSCFU76LwNESVB5FT6z4J0mQpqoPvP7Lo8rsn7Vj8rhhtz6p5Es5H3zU0ccsoYQ/exec"
_DEFAULT_EXT_U = "plt_it_transmec_ro"
_DEFAULT_EXT_P = base64.b64decode("aVNtUEV2dnVrVjkt").decode("utf-8")


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
    "bolle",
    "runs",
    "planning_results",
    "spunta_arrivi",
    "forecast_raw",
    "app_settings",
]


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
    url = get_cloud_url()
    if not url:
        return {"status": "skipped", "message": "Nessun URL Google Apps Script configurato."}

    targets = table_names if table_names else ALL_SYNC_TABLES
    payload_tables = {}

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {r[0] for r in cur.fetchall()}

        for t in targets:
            if t not in existing_tables:
                continue
            if t == "bolle":
                df = pd.read_sql_query("SELECT * FROM bolle ORDER BY id DESC LIMIT 800", conn)
            else:
                df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
            # SAFETY GUARD: Never overwrite cloud data with an empty table if local table has 0 rows!
            if df.empty and t in ["runs", "planning_results", "spunta_arrivi", "forecast_raw", "bolle", "stores", "store_delivery_profiles", "vehicles"]:
                continue
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
    restored_counts = {}

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {r[0] for r in cur.fetchall()}

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

            if t_name != "bolle":
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

        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Errore durante il ripristino SQLite: {e}"}
    finally:
        conn.close()

    return {"status": "ok", "restored": restored_counts}


def auto_sync_tables(table_names: list[str]):
    """
    Sincronizza automaticamente in background (thread asincrono non bloccante)
    le tabelle modificate verso Google Sheets se l'URL Cloud e' configurato.
    """
    url = get_cloud_url()
    if not url:
        return
    import threading

    def _bg_push():
        try:
            push_tables_to_cloud(table_names=table_names, timeout=20)
        except Exception:
            pass

    threading.Thread(target=_bg_push, daemon=True).start()
