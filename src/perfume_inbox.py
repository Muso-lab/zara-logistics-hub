"""
Modulo di Lettura e Parsing Automatico delle Email per lo Scorporo Profumi.
Permette all'applicazione e allo scheduler di prelevare in automatico i pezzi profumi
inviati via email (nel corpo del testo o in allegato Excel/CSV) senza che l'operatore
debba accedere alla webapp.
"""
from __future__ import annotations

import email
from email.header import decode_header
import imaplib
import io
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import DATA_DIR
from src.db import get_email_config

PERFUME_INBOX_CONFIG_FILE = DATA_DIR / "perfume_inbox_config.json"

DEFAULT_PERFUME_INBOX_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "imap_host": "",
    "imap_port": 993,
    "imap_user": "",
    "imap_password": "",
    "use_ssl": True,
    "subject_keywords": ["profum", "scorporo", "pezzi"],
    "sender_filter": "",
    "max_age_hours": 48,
    "last_check_timestamp": "",
    "last_found_subject": "",
    "last_found_sender": "",
    "last_found_perfumes": {},
}


def _infer_imap_host(smtp_host: str) -> str:
    """Deduce l'host IMAP in base all'host SMTP configurato."""
    s = (smtp_host or "").strip().lower()
    if not s:
        return "imap.gmail.com"
    if "gmail" in s:
        return "imap.gmail.com"
    if "office365" in s or "outlook" in s:
        return "outlook.office365.com"
    if "aruba" in s:
        return "imaps.aruba.it"
    if s.startswith("smtp."):
        return "imap." + s[5:]
    if s.startswith("smtps."):
        return "imaps." + s[6:]
    return f"imap.{s}"


def get_perfume_inbox_config() -> Dict[str, Any]:
    """Recupera la configurazione dell'inbox profumi da file o defaults."""
    cfg = dict(DEFAULT_PERFUME_INBOX_CONFIG)
    if PERFUME_INBOX_CONFIG_FILE.exists():
        try:
            loaded = json.loads(PERFUME_INBOX_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass

    # Se mancano host/utente/pass, usa quelli del server SMTP principale
    email_cfg = get_email_config()
    if not cfg.get("imap_host"):
        cfg["imap_host"] = _infer_imap_host(email_cfg.get("smtp_host", ""))
    if not cfg.get("imap_user"):
        cfg["imap_user"] = email_cfg.get("smtp_user", "")
    if not cfg.get("imap_password"):
        cfg["imap_password"] = email_cfg.get("smtp_password", "")

    return cfg


def save_perfume_inbox_config(new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Salva la configurazione aggiornata."""
    cfg = get_perfume_inbox_config()
    cfg.update(new_cfg)
    try:
        PERFUME_INBOX_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        PERFUME_INBOX_CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return cfg


def _decode_mime_header(header_val: Optional[str]) -> str:
    """Decodifica un header email (Subject, From, etc.) RFC 2047."""
    if not header_val:
        return ""
    parts = decode_header(header_val)
    decoded_fragments = []
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                decoded_fragments.append(text.decode(enc or "utf-8", errors="ignore"))
            except Exception:
                decoded_fragments.append(text.decode("latin1", errors="ignore"))
        else:
            decoded_fragments.append(str(text))
    return " ".join(decoded_fragments).strip()


def parse_perfumes_from_text(text: str) -> Dict[str, float]:
    """
    Estrae coppie {codice_negozio: quantita_pezzi} da una stringa di testo.
    Supporta formati come:
    - 3680: 120
    - 3680 - 120 pz
    - Negozio 3680 = 120
    - Store 9226 45
    - 3591 | 80 pezzi
    """
    res: Dict[str, float] = {}
    if not text:
        return res

    lines = text.splitlines()
    # Pattern regex per righe con codice negozio (3-5 cifre) e quantità (1-5 cifre)
    # Esempi:
    # "3680: 120", "Negozio 3680 - 120 pz", "3680  120", "3680 = 120 colli"
    pattern = re.compile(
        r"(?:(?:neg(?:ozio)?|store|cod(?:ice)?)\s*)?(?P<store>\b\d{3,5}\b)\s*[:=\-|\t ]+\s*(?P<qty>\b\d{1,6}\b)(?:\s*(?:pz|pezzi|colli|profumi|bt|bultos))?",
        re.IGNORECASE
    )

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        # Cerca match
        matches = pattern.finditer(line_clean)
        for m in matches:
            sid = m.group("store").strip()
            qty_str = m.group("qty").strip()
            try:
                q_val = float(qty_str)
                # Filtra anni (es. 2026) o numeri improbabili
                if 100 <= int(sid) <= 99999 and int(sid) != 2026 and int(sid) != 2025:
                    res[sid] = q_val
            except Exception:
                pass

    return res


def parse_perfumes_from_excel_bytes(file_bytes: bytes, filename: str = "") -> Dict[str, float]:
    """Estrae profumi da un allegato Excel o CSV."""
    res: Dict[str, float] = {}
    if not file_bytes:
        return res

    try:
        import pandas as pd
        df = None
        if filename.lower().endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python")
            except Exception:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=";")
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))

        if df is None or df.empty:
            return res

        # Normalizza nomi colonne
        store_col = None
        qty_col = None

        for col in df.columns:
            c_norm = str(col).strip().lower()
            if any(k in c_norm for k in ["store", "negozio", "codice", "id", "cod"]):
                store_col = col
            if any(k in c_norm for k in ["pezzi", "pz", "quant", "profum", "colli"]):
                qty_col = col

        if store_col and qty_col:
            for _, r in df.iterrows():
                try:
                    s_raw = str(r[store_col]).strip().split(".")[0]
                    q_raw = float(r[qty_col])
                    if s_raw.isdigit():
                        res[s_raw] = q_raw
                except Exception:
                    pass
        elif len(df.columns) >= 2:
            # Fallback: prime due colonne numeriche
            for _, r in df.iterrows():
                try:
                    s_raw = str(r.iloc[0]).strip().split(".")[0]
                    q_raw = float(r.iloc[1])
                    if s_raw.isdigit():
                        res[s_raw] = q_raw
                except Exception:
                    pass
    except Exception:
        pass

    return res


def fetch_latest_perfumes_from_email(config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Connette la casella IMAP, cerca l'email più recente relativa ai profumi,
    estrae le quantità e restituisce un dizionario strutturato:
    {
        "status": "ok" | "not_found" | "error",
        "perfumes": {"3680": 120.0, ...},
        "subject": "...",
        "sender": "...",
        "date": "...",
        "source": "body" | "attachment" | "none",
        "message": "..."
    }
    """
    cfg = get_perfume_inbox_config()
    if config_override:
        cfg.update(config_override)

    if not cfg.get("enabled", True):
        return {
            "status": "disabled",
            "perfumes": {},
            "message": "Scorporo profumi da email disabilitato nelle impostazioni."
        }

    host = cfg.get("imap_host", "").strip()
    port = int(cfg.get("imap_port", 993))
    user = cfg.get("imap_user", "").strip()
    password = cfg.get("imap_password", "").strip()
    use_ssl = bool(cfg.get("use_ssl", True))

    if not host or not user or not password:
        return {
            "status": "error",
            "perfumes": {},
            "message": "Parametri IMAP incompleti (mancano Host, Utente o Password)."
        }

    try:
        if use_ssl:
            client = imaplib.IMAP4_SSL(host, port, timeout=20)
        else:
            client = imaplib.IMAP4(host, port, timeout=20)
    except Exception as exc:
        return {
            "status": "error",
            "perfumes": {},
            "message": f"Connessione al server IMAP {host}:{port} fallita: {exc}"
        }

    try:
        client.login(user, password)
    except Exception as exc:
        return {
            "status": "error",
            "perfumes": {},
            "message": f"Autenticazione IMAP fallita per {user}: {exc}"
        }

    try:
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            return {
                "status": "error",
                "perfumes": {},
                "message": "Impossibile aprire la cartella INBOX."
            }

        # Ricerca email negli ultimi max_age_hours
        hours = int(cfg.get("max_age_hours", 48))
        since_date = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
        search_criterion = f'(SINCE "{since_date}")'

        typ, msg_ids = client.search(None, search_criterion)
        if typ != "OK" or not msg_ids or not msg_ids[0]:
            # Prova ricerca ALL (ultimi 20 messaggi)
            typ, msg_ids = client.search(None, "ALL")

        if not msg_ids or not msg_ids[0]:
            client.logout()
            return {
                "status": "not_found",
                "perfumes": {},
                "message": "Nessuna email recente trovata nella casella di posta."
            }

        all_ids = msg_ids[0].split()
        # Esamina a ritroso dai più recenti (massimo ultimi 30)
        recent_ids = all_ids[-30:][::-1]

        keywords = [k.lower() for k in cfg.get("subject_keywords", ["profum", "scorporo", "pezzi"])]
        sender_flt = (cfg.get("sender_filter", "") or "").lower().strip()

        matched_perfumes: Dict[str, float] = {}
        matched_subject = ""
        matched_sender = ""
        matched_date = ""
        matched_source = "none"

        for mid in recent_ids:
            res_typ, data = client.fetch(mid, "(RFC822)")
            if res_typ != "OK" or not data or not data[0]:
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_mime_header(msg.get("Subject", ""))
            sender = _decode_mime_header(msg.get("From", ""))
            msg_date = _decode_mime_header(msg.get("Date", ""))

            # Filtro mittente se configurato
            if sender_flt and sender_flt not in sender.lower():
                continue

            # Filtro oggetto
            subject_lower = subject.lower()
            if not any(kw in subject_lower for kw in keywords):
                continue

            # Email candidata trovata! Estraiamo testo e allegati
            body_text = ""
            attachment_perfumes: Dict[str, float] = {}

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    filename = part.get_filename() or ""
                    if filename:
                        filename = _decode_mime_header(filename)

                    if "attachment" in content_disposition.lower() or filename.lower().endswith((".xlsx", ".xls", ".csv")):
                        payload = part.get_payload(decode=True)
                        if payload:
                            att_res = parse_perfumes_from_excel_bytes(payload, filename)
                            if att_res:
                                attachment_perfumes.update(att_res)
                    elif content_type in ("text/plain", "text/html") and "attachment" not in content_disposition.lower():
                        payload = part.get_payload(decode=True)
                        if payload:
                            try:
                                body_text += payload.decode("utf-8", errors="ignore") + "\n"
                            except Exception:
                                body_text += payload.decode("latin1", errors="ignore") + "\n"
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    try:
                        body_text = payload.decode("utf-8", errors="ignore")
                    except Exception:
                        body_text = payload.decode("latin1", errors="ignore")

            text_perfumes = parse_perfumes_from_text(body_text)

            # Preferenza: allegato se trovato, altrimenti corpo testo
            if attachment_perfumes:
                matched_perfumes = attachment_perfumes
                matched_source = "attachment"
            elif text_perfumes:
                matched_perfumes = text_perfumes
                matched_source = "body"

            if matched_perfumes:
                matched_subject = subject
                matched_sender = sender
                matched_date = msg_date
                break

        client.logout()

        if matched_perfumes:
            # Salva telemetry
            save_perfume_inbox_config({
                "last_check_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_found_subject": matched_subject,
                "last_found_sender": matched_sender,
                "last_found_perfumes": matched_perfumes,
            })
            return {
                "status": "ok",
                "perfumes": matched_perfumes,
                "subject": matched_subject,
                "sender": matched_sender,
                "date": matched_date,
                "source": matched_source,
                "message": f"Trovati {len(matched_perfumes)} negozi nell'email '{matched_subject}' (Fonte: {matched_source}).",
            }
        else:
            return {
                "status": "not_found",
                "perfumes": {},
                "message": "Nessuna email recente contiene quantità profumi nei formati supportati."
            }

    except Exception as exc:
        try:
            client.logout()
        except Exception:
            pass
        return {
            "status": "error",
            "perfumes": {},
            "message": f"Errore durante la lettura delle email: {exc}"
        }
