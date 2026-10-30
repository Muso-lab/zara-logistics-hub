"""
Modulo di Caricamento FTP per File XML TMS (BeOne / Nova Systems).
Supporta il caricamento diretto a singolo clic di file XML non compressi
sul server FTP aziendale Lacchi.
"""

from datetime import datetime
import ftplib
import io
import os
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional, Tuple, Union
import streamlit as st

from src.config import DB_PATH, OUTPUT_DIR

# Configurazione predefinita server FTP TMS Lacchi
DEFAULT_FTP_CONFIG = {
    "host": "servizi.lacchi.com",
    "port": 2121,
    "user": "user-sga-464531",
    "password": "CHyFe9u!R3y@gJQr2hvs8nyd*ddxYb",
    "remote_dir": "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA",
    "timeout": 30,
    "passive_mode": True,
}


def get_tms_ftp_config() -> Dict[str, Any]:
    """
    Recupera i parametri di connessione FTP unificando (in ordine di priorità):
    1. Session state Streamlit (se modificati dall'utente nell'interfaccia)
    2. Streamlit secrets (st.secrets["ftp_tms"])
    3. Variabili d'ambiente (TMS_FTP_HOST, TMS_FTP_PORT, etc.)
    4. Valori standard aziendali Lacchi
    """
    cfg = dict(DEFAULT_FTP_CONFIG)

    # 1. Variabili d'ambiente
    if os.getenv("TMS_FTP_HOST"):
        cfg["host"] = os.getenv("TMS_FTP_HOST")
    if os.getenv("TMS_FTP_PORT"):
        try:
            cfg["port"] = int(os.getenv("TMS_FTP_PORT"))
        except ValueError:
            pass
    if os.getenv("TMS_FTP_USER"):
        cfg["user"] = os.getenv("TMS_FTP_USER")
    if os.getenv("TMS_FTP_PASS"):
        cfg["password"] = os.getenv("TMS_FTP_PASS")
    if os.getenv("TMS_FTP_DIR"):
        cfg["remote_dir"] = os.getenv("TMS_FTP_DIR")

    # 2. Streamlit secrets
    try:
        if hasattr(st, "secrets") and "ftp_tms" in st.secrets:
            sec = st.secrets["ftp_tms"]
            for k in ["host", "port", "user", "password", "remote_dir", "timeout"]:
                if k in sec:
                    cfg[k] = int(sec[k]) if k == "port" else str(sec[k])
    except Exception:
        pass

    # 3. Session state overrides
    try:
        if hasattr(st, "session_state"):
            if "override_ftp_host" in st.session_state and st.session_state["override_ftp_host"]:
                cfg["host"] = str(st.session_state["override_ftp_host"]).strip()
            if "override_ftp_port" in st.session_state and st.session_state["override_ftp_port"]:
                try:
                    cfg["port"] = int(st.session_state["override_ftp_port"])
                except ValueError:
                    pass
            if "override_ftp_user" in st.session_state and st.session_state["override_ftp_user"]:
                cfg["user"] = str(st.session_state["override_ftp_user"]).strip()
            if "override_ftp_pass" in st.session_state and st.session_state["override_ftp_pass"]:
                cfg["password"] = str(st.session_state["override_ftp_pass"]).strip()
            if "override_ftp_dir" in st.session_state and st.session_state["override_ftp_dir"]:
                cfg["remote_dir"] = str(st.session_state["override_ftp_dir"]).strip()
    except Exception:
        pass

    return cfg


def ensure_ftp_directory(ftp: ftplib.FTP, remote_dir: str):
    """
    Assicura che il percorso remoto esista creandolo cartella per cartella se necessario,
    e posiziona la sessione FTP all'interno di esso.
    """
    remote_dir = remote_dir.strip().replace("\\", "/")
    if not remote_dir:
        return

    parts = [p for p in remote_dir.split("/") if p]
    if remote_dir.startswith("/"):
        ftp.cwd("/")

    for part in parts:
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            try:
                ftp.mkd(part)
            except ftplib.error_perm:
                pass
            ftp.cwd(part)


def upload_xml_files_to_ftp(
    files: List[Union[Path, str, Tuple[str, Union[bytes, str]]]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Carica una lista di file XML su server FTP in formato singolo non compresso (.xml).

    Parametri:
    - files: lista di percorsi Path/str oppure tuple (filename, bytes_o_str)
    - config: dizionario parametri FTP (se None, usa get_tms_ftp_config())

    Ritorna:
    {
        "status": "ok" | "partial" | "error",
        "uploaded_count": int,
        "total_count": int,
        "uploaded_files": List[str],
        "failed_files": List[Tuple[str, str]],
        "remote_dir": str,
        "host": str,
        "port": int,
        "message": str
    }
    """
    cfg = config or get_tms_ftp_config()
    host = cfg.get("host", "servizi.lacchi.com")
    port = int(cfg.get("port", 2121))
    user = cfg.get("user", "")
    password = cfg.get("password", "")
    remote_dir = cfg.get("remote_dir", "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA")
    timeout = int(cfg.get("timeout", 30))
    passive = bool(cfg.get("passive_mode", True))

    if not files:
        return {
            "status": "error",
            "uploaded_count": 0,
            "total_count": 0,
            "uploaded_files": [],
            "failed_files": [],
            "remote_dir": remote_dir,
            "host": host,
            "port": port,
            "message": "Nessun file XML fornito per il caricamento FTP.",
        }

    uploaded_files: List[str] = []
    failed_files: List[Tuple[str, str]] = []

    ftp = ftplib.FTP()
    try:
        ftp.connect(host, port, timeout=timeout)
        ftp.login(user, password)
        ftp.set_pasv(passive)
        ensure_ftp_directory(ftp, remote_dir)

        for item in files:
            fname = ""
            fdata: Optional[bytes] = None

            if isinstance(item, (tuple, list)) and len(item) == 2:
                fname = str(item[0])
                raw_data = item[1]
                if isinstance(raw_data, str):
                    fdata = raw_data.encode("utf-8")
                else:
                    fdata = bytes(raw_data)
            else:
                p = Path(item)
                fname = p.name
                if not p.exists():
                    failed_files.append((fname, f"File locale non trovato: {p}"))
                    continue
                fdata = p.read_bytes()

            if not fname.lower().endswith(".xml"):
                fname += ".xml"

            try:
                bio = io.BytesIO(fdata)
                ftp.storbinary(f"STOR {fname}", bio)
                uploaded_files.append(fname)
            except Exception as e:
                failed_files.append((fname, str(e)))

        ftp.quit()

    except Exception as conn_err:
        try:
            ftp.close()
        except Exception:
            pass
        return {
            "status": "error",
            "uploaded_count": len(uploaded_files),
            "total_count": len(files),
            "uploaded_files": uploaded_files,
            "failed_files": failed_files or [(f.name if hasattr(f, 'name') else str(f), str(conn_err)) for f in files],
            "remote_dir": remote_dir,
            "host": host,
            "port": port,
            "message": f"Errore di connessione o autenticazione FTP ({host}:{port}): {conn_err}",
        }

    status = "ok" if len(failed_files) == 0 else ("partial" if uploaded_files else "error")
    msg = f"Caricati con successo {len(uploaded_files)} di {len(files)} file XML sul server FTP {host}:{port} in {remote_dir}."
    if failed_files:
        msg += f" {len(failed_files)} file falliti."

    return {
        "status": status,
        "uploaded_count": len(uploaded_files),
        "total_count": len(files),
        "uploaded_files": uploaded_files,
        "failed_files": failed_files,
        "remote_dir": remote_dir,
        "host": host,
        "port": port,
        "message": msg,
    }


def upload_tms_xml_from_run(
    run_id: str,
    output_dir: Optional[Union[str, Path]] = None,
    config: Optional[Dict[str, Any]] = None,
    db_path: Union[str, Path] = DB_PATH,
) -> Dict[str, Any]:
    """
    Genera i file XML per la Run selezionata (se non già presenti) e li carica
    immediatamente sul server FTP in formato singolo non compresso.
    """
    from src.tms_xml_exporter import generate_tms_xml_from_run

    out_d = Path(output_dir) if output_dir else Path(OUTPUT_DIR) / f"run_{run_id}" / "tms_xml"
    xml_paths, _ = generate_tms_xml_from_run(run_id, output_dir=out_d, db_path=db_path)
    return upload_xml_files_to_ftp(xml_paths, config=config)


def upload_tms_xml_from_bolle(
    delivery_date: Union[str, List[str], Tuple[str, ...]],
    output_dir: Optional[Union[str, Path]] = None,
    config: Optional[Dict[str, Any]] = None,
    db_path: Union[str, Path] = DB_PATH,
) -> Dict[str, Any]:
    """
    Genera i file XML per la data/e di consegna bolle specificata/e e li carica
    immediatamente sul server FTP in formato singolo non compresso.
    """
    from src.tms_xml_exporter import generate_tms_xml_from_bolle

    clean_tag = str(delivery_date).replace("___", "_").replace(" ", "_")[:20]
    out_d = Path(output_dir) if output_dir else Path(OUTPUT_DIR) / "bolle_tms_xml" / clean_tag
    xml_paths, _ = generate_tms_xml_from_bolle(delivery_date, output_dir=out_d, db_path=db_path)
    return upload_xml_files_to_ftp(xml_paths, config=config)


def test_tms_ftp_connection(config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Verifica rapida della connessione e login al server FTP senza caricare file.
    """
    cfg = config or get_tms_ftp_config()
    host = cfg.get("host", "servizi.lacchi.com")
    port = int(cfg.get("port", 2121))
    user = cfg.get("user", "")
    password = cfg.get("password", "")
    remote_dir = cfg.get("remote_dir", "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA")
    timeout = int(cfg.get("timeout", 15))

    ftp = ftplib.FTP()
    try:
        ftp.connect(host, port, timeout=timeout)
        ftp.login(user, password)
        ftp.set_pasv(True)
        ensure_ftp_directory(ftp, remote_dir)
        curr = ftp.pwd()
        ftp.quit()
        return True, f"Connessione FTP stabilita con successo a {host}:{port}. Directory remota: {curr}"
    except Exception as e:
        try:
            ftp.close()
        except Exception:
            pass
        return False, f"Impossibile connettersi al server FTP {host}:{port}: {e}"
