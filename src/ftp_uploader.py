"""
Modulo di Caricamento FTP per File XML TMS (BeOne / Nova Systems).
Supporta il caricamento diretto a singolo clic di file XML non compressi
sul server FTP aziendale Lacchi con diagnostica di rete avanzata.
"""

from datetime import datetime
import ftplib
import io
import json
import os
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional, Tuple, Union
import streamlit as st

from src.config import DATA_DIR, DB_PATH, OUTPUT_DIR

# File di persistenza configurazione FTP locale
FTP_CONFIG_FILE = DATA_DIR / "ftp_tms_config.json"

# Configurazione predefinita server FTP TMS Lacchi
DEFAULT_FTP_CONFIG = {
    "host": "servizi.lacchi.com",
    "port": 2121,
    "user": "user-sga-464531",
    "password": "CHyFe9u!R3y@gJQr2hvs8nyd*ddxYb",
    "remote_dir": "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA",
    "timeout": 30,
    "passive_mode": True,
    "use_tls": False,
}


def get_tms_ftp_config() -> Dict[str, Any]:
    """
    Recupera i parametri di connessione FTP unificando (in ordine di priorità):
    1. Session state Streamlit (se modificati dall'utente nell'interfaccia)
    2. File locale DATA_DIR / "ftp_tms_config.json"
    3. Streamlit secrets (st.secrets["ftp_tms"])
    4. Variabili d'ambiente (TMS_FTP_HOST, TMS_FTP_PORT, etc.)
    5. Valori standard aziendali Lacchi
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
    if os.getenv("TMS_FTP_TLS"):
        cfg["use_tls"] = os.getenv("TMS_FTP_TLS").lower() in ("1", "true", "si", "yes")

    # 2. File di configurazione locale
    if FTP_CONFIG_FILE.exists():
        try:
            disk_cfg = json.loads(FTP_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(disk_cfg, dict):
                for k, v in disk_cfg.items():
                    if k == "port":
                        try:
                            cfg[k] = int(v)
                        except ValueError:
                            pass
                    elif k in ("passive_mode", "use_tls"):
                        cfg[k] = bool(v)
                    else:
                        cfg[k] = str(v)
        except Exception:
            pass

    # 3. Streamlit secrets
    try:
        if hasattr(st, "secrets") and "ftp_tms" in st.secrets:
            sec = st.secrets["ftp_tms"]
            for k in ["host", "port", "user", "password", "remote_dir", "timeout", "use_tls"]:
                if k in sec:
                    if k in ("port", "timeout"):
                        cfg[k] = int(sec[k])
                    elif k == "use_tls":
                        cfg[k] = bool(sec[k])
                    else:
                        cfg[k] = str(sec[k])
    except Exception:
        pass

    # 4. Session state overrides
    try:
        if hasattr(st, "session_state"):
            if "cfg_ftp_host" in st.session_state and st.session_state["cfg_ftp_host"]:
                cfg["host"] = str(st.session_state["cfg_ftp_host"]).strip()
            if "cfg_ftp_port" in st.session_state and st.session_state["cfg_ftp_port"]:
                try:
                    cfg["port"] = int(st.session_state["cfg_ftp_port"])
                except ValueError:
                    pass
            if "cfg_ftp_user" in st.session_state and st.session_state["cfg_ftp_user"]:
                cfg["user"] = str(st.session_state["cfg_ftp_user"]).strip()
            if "cfg_ftp_pass" in st.session_state and st.session_state["cfg_ftp_pass"]:
                cfg["password"] = str(st.session_state["cfg_ftp_pass"]).strip()
            if "cfg_ftp_dir" in st.session_state and st.session_state["cfg_ftp_dir"]:
                cfg["remote_dir"] = str(st.session_state["cfg_ftp_dir"]).strip()
            if "cfg_ftp_tls" in st.session_state:
                cfg["use_tls"] = bool(st.session_state["cfg_ftp_tls"])
    except Exception:
        pass

    return cfg


def save_tms_ftp_config(cfg: Dict[str, Any]) -> bool:
    """Salva le impostazioni FTP su file di configurazione permanente."""
    try:
        to_save = {
            "host": str(cfg.get("host", "servizi.lacchi.com")).strip(),
            "port": int(cfg.get("port", 2121)),
            "user": str(cfg.get("user", "")).strip(),
            "password": str(cfg.get("password", "")).strip(),
            "remote_dir": str(cfg.get("remote_dir", "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA")).strip(),
            "timeout": int(cfg.get("timeout", 30)),
            "passive_mode": bool(cfg.get("passive_mode", True)),
            "use_tls": bool(cfg.get("use_tls", False)),
        }
        FTP_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        FTP_CONFIG_FILE.write_text(json.dumps(to_save, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def ensure_ftp_directory(ftp: Union[ftplib.FTP, ftplib.FTP_TLS], remote_dir: str):
    """
    Assicura che il percorso remoto esista creandolo cartella per cartella se necessario,
    e posiziona la sessione FTP all'interno di esso.
    """
    remote_dir = remote_dir.strip().replace("\\", "/")
    if not remote_dir:
        return

    parts = [p for p in remote_dir.split("/") if p]
    if remote_dir.startswith("/"):
        try:
            ftp.cwd("/")
        except Exception:
            pass

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
    """
    cfg = config or get_tms_ftp_config()
    host = cfg.get("host", "servizi.lacchi.com")
    port = int(cfg.get("port", 2121))
    user = cfg.get("user", "")
    password = cfg.get("password", "")
    remote_dir = cfg.get("remote_dir", "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA")
    timeout = int(cfg.get("timeout", 30))
    passive = bool(cfg.get("passive_mode", True))
    use_tls = bool(cfg.get("use_tls", False))

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

    ftp: Union[ftplib.FTP, ftplib.FTP_TLS] = ftplib.FTP_TLS() if use_tls else ftplib.FTP()
    try:
        ftp.connect(host, port, timeout=timeout)
        ftp.login(user, password)
        if use_tls and hasattr(ftp, "prot_p"):
            ftp.prot_p()
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


def diagnose_tms_ftp_connection(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Diagnostica avanzata passo-passo della connettività FTP:
    1. Risoluzione DNS (mostra IP risolto)
    2. Raggiungibilità porta TCP (socket test)
    3. Handshake protocollo FTP / FTPS
    4. Autenticazione (User & Password)
    5. Accesso e permessi sulla cartella remota
    """
    cfg = config or get_tms_ftp_config()
    host = cfg.get("host", "servizi.lacchi.com")
    port = int(cfg.get("port", 2121))
    user = cfg.get("user", "")
    password = cfg.get("password", "")
    remote_dir = cfg.get("remote_dir", "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA")
    timeout = int(cfg.get("timeout", 10))
    use_tls = bool(cfg.get("use_tls", False))

    steps: List[Dict[str, str]] = []

    # Step 1: Risoluzione DNS
    resolved_ip = None
    try:
        resolved_ip = socket.gethostbyname(host)
        steps.append({
            "step": "1. Risoluzione DNS",
            "status": "ok",
            "detail": f"Host '{host}' risolto all'indirizzo IP: {resolved_ip}"
        })
    except Exception as e:
        steps.append({
            "step": "1. Risoluzione DNS",
            "status": "error",
            "detail": f"Impossibile risolvere l'host '{host}': {e}"
        })
        return {
            "status": "error",
            "steps": steps,
            "error_phase": "DNS",
            "message": f"Errore di risoluzione DNS per '{host}': {e}"
        }

    # Step 2: Raggiungibilità Socket TCP
    try:
        sock = socket.create_connection((resolved_ip, port), timeout=timeout)
        sock.close()
        steps.append({
            "step": "2. Raggiungibilità Porta TCP",
            "status": "ok",
            "detail": f"Porta TCP {port} su {resolved_ip} aperta e raggiungibile."
        })
    except socket.timeout:
        steps.append({
            "step": "2. Raggiungibilità Porta TCP",
            "status": "error",
            "detail": f"TIMEOUT: Il server {resolved_ip}:{port} non risponde. La porta {port} è bloccata dal firewall o la connessione richiede VPN / IP abilitato."
        })
        return {
            "status": "error",
            "steps": steps,
            "error_phase": "TCP_TIMEOUT",
            "message": f"Timeout porta TCP {port} su {host} ({resolved_ip}). Il server non risponde entro {timeout}s: la porta è filtrata o bloccata da firewall."
        }
    except Exception as e:
        steps.append({
            "step": "2. Raggiungibilità Porta TCP",
            "status": "error",
            "detail": f"Connessione TCP non riuscita verso {resolved_ip}:{port}: {e}"
        })
        return {
            "status": "error",
            "steps": steps,
            "error_phase": "TCP_ERROR",
            "message": f"Errore connessione socket {resolved_ip}:{port}: {e}"
        }

    # Step 3: Handshake FTP
    ftp: Union[ftplib.FTP, ftplib.FTP_TLS] = ftplib.FTP_TLS() if use_tls else ftplib.FTP()
    try:
        ftp.connect(host, port, timeout=timeout)
        banner = ftp.getwelcome()[:120] if hasattr(ftp, "getwelcome") else "OK"
        steps.append({
            "step": "3. Handshake Protocollo FTP",
            "status": "ok",
            "detail": f"Connesso con successo ({'FTPS TLS' if use_tls else 'FTP Standard'}). Banner: {banner}"
        })
    except Exception as e:
        steps.append({
            "step": "3. Handshake Protocollo FTP",
            "status": "error",
            "detail": f"Errore handshake FTP: {e}"
        })
        return {
            "status": "error",
            "steps": steps,
            "error_phase": "FTP_HANDSHAKE",
            "message": f"Errore handshake FTP con {host}:{port}: {e}"
        }

    # Step 4: Login Utente & Password
    try:
        ftp.login(user, password)
        if use_tls and hasattr(ftp, "prot_p"):
            ftp.prot_p()
        steps.append({
            "step": "4. Autenticazione Credenziali",
            "status": "ok",
            "detail": f"Login effettuato con successo come '{user}'."
        })
    except Exception as e:
        steps.append({
            "step": "4. Autenticazione Credenziali",
            "status": "error",
            "detail": f"Autenticazione fallita per '{user}': {e}"
        })
        try:
            ftp.quit()
        except Exception:
            pass
        return {
            "status": "error",
            "steps": steps,
            "error_phase": "FTP_AUTH",
            "message": f"Errore autenticazione credenziali per utente '{user}': {e}"
        }

    # Step 5: Verifica Cartella Remota
    try:
        ensure_ftp_directory(ftp, remote_dir)
        curr = ftp.pwd()
        steps.append({
            "step": "5. Accesso Cartella Remota",
            "status": "ok",
            "detail": f"Cartella verificata: {curr}"
        })
        ftp.quit()
    except Exception as e:
        steps.append({
            "step": "5. Accesso Cartella Remota",
            "status": "error",
            "detail": f"Impossibile accedere alla cartella '{remote_dir}': {e}"
        })
        try:
            ftp.quit()
        except Exception:
            pass
        return {
            "status": "error",
            "steps": steps,
            "error_phase": "REMOTE_DIR",
            "message": f"Errore di accesso alla cartella remota '{remote_dir}': {e}"
        }

    return {
        "status": "ok",
        "steps": steps,
        "message": f"Connessione FTP stabilita con successo a {host}:{port} ({resolved_ip}). Cartella: {remote_dir}"
    }


def test_tms_ftp_connection(config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Verifica rapida della connessione e login al server FTP senza caricare file.
    """
    diag = diagnose_tms_ftp_connection(config=config)
    return (diag["status"] == "ok", diag["message"])
