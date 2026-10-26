import os
import smtplib
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime


def build_operativa_zip(files_to_zip: Dict[str, Path], output_zip_path: Path) -> Path:
    """
    Creates a zip archive containing the operational files (Sintesi and SGA files).
    """
    output_zip_path = Path(output_zip_path)
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, fpath in files_to_zip.items():
            fpath = Path(fpath)
            if fpath.exists():
                zf.write(fpath, arcname=arcname)

    return output_zip_path


def send_operativa_email(
    recipients: List[str],
    subject: str,
    body_text: str,
    attachment_paths: List[Path],
    cc_recipients: Optional[List[str]] = None,
    smtp_config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Prepares and sends (or simulates) the email with operational files.
    If SMTP credentials are provided in smtp_config or in DB settings/environment variables,
    attempts live sending. Otherwise completes in simulation/dry-run mode.
    """
    clean_recipients = [r.strip() for r in recipients if r and str(r).strip()]
    if not clean_recipients:
        return False, "Nessun destinatario specificato per l'invio email."

    clean_cc = [r.strip() for r in (cc_recipients or []) if r and str(r).strip()]

    # Verify attachments
    valid_attachments = []
    for ap in attachment_paths:
        p = Path(ap)
        if p.exists():
            valid_attachments.append(p)

    if smtp_config is None:
        try:
            from src.db import get_email_config
            smtp_config = get_email_config()
        except Exception:
            smtp_config = {}

    cfg = smtp_config or {}
    smtp_host = str(cfg.get("smtp_host") or cfg.get("host") or os.getenv("SMTP_HOST", "")).strip()
    try:
        smtp_port = int(cfg.get("smtp_port") or cfg.get("port") or os.getenv("SMTP_PORT", "587"))
    except (ValueError, TypeError):
        smtp_port = 587
    smtp_user = str(cfg.get("smtp_user") or cfg.get("user") or os.getenv("SMTP_USER", "")).strip()
    smtp_pass = str(cfg.get("smtp_password") or cfg.get("password") or os.getenv("SMTP_PASSWORD", "")).strip()
    if "gmail" in smtp_host.lower():
        clean_p = smtp_pass.replace(" ", "").replace("\xa0", "").strip()
        if len(clean_p) == 16:
            smtp_pass = clean_p
    sender_name = str(cfg.get("sender_name") or "Logistica Zara Hub").strip()
    security = str(cfg.get("smtp_security") or ("SSL" if smtp_port == 465 else "STARTTLS")).upper()

    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{sender_name} <{smtp_user}>" if sender_name else smtp_user
            msg["To"] = ", ".join(clean_recipients)
            if clean_cc:
                msg["Cc"] = ", ".join(clean_cc)
            msg["Subject"] = subject
            msg.attach(MIMEText(body_text, "plain", "utf-8"))

            for att_path in valid_attachments:
                part = MIMEBase("application", "octet-stream")
                with open(att_path, "rb") as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{att_path.name}"'
                )
                msg.attach(part)

            all_dest = clean_recipients + clean_cc

            if "SSL" in security or smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
                if "STARTTLS" in security or smtp_port == 587:
                    server.starttls()

            with server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, all_dest, msg.as_string())

            dest_str = f"{len(clean_recipients)} destinatari"
            if clean_cc:
                dest_str += f" e {len(clean_cc)} in copia (CC)"
            return True, f"Email inviata con successo a {dest_str} con {len(valid_attachments)} allegati."

        except smtplib.SMTPAuthenticationError as e:
            return False, f"Autenticazione SMTP fallita: controlla Utente e Password (se usi Gmail/Outlook verifica di usare una App Password dedicata). Dettaglio: {e}"
        except smtplib.SMTPConnectError as e:
            return False, f"Impossibile connettersi al server SMTP ({smtp_host}:{smtp_port}): verifica host e porta. Dettaglio: {e}"
        except Exception as e:
            return False, f"Errore durante l'invio SMTP: {e}"

    # Dry-run / simulation mode
    att_names = [p.name for p in valid_attachments]
    return True, (
        f"Simulazione invio completata con successo a {', '.join(clean_recipients)}. "
        f"Allegati inclusi: {', '.join(att_names) if att_names else 'Nessuno'}. "
        "Per l'invio reale definitivo, configura i parametri SMTP nella scheda 'Configurazione Email' o inserisci le credenziali nel sistema."
    )


def send_test_email(
    test_to: str,
    smtp_config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Sends a lightweight test email to verify SMTP credentials and server connectivity.
    """
    test_to = str(test_to).strip()
    if not test_to or "@" not in test_to:
        return False, "Indirizzo email di test non valido."

    if smtp_config is None:
        try:
            from src.db import get_email_config
            smtp_config = get_email_config()
        except Exception:
            smtp_config = {}

    cfg = smtp_config or {}
    smtp_host = str(cfg.get("smtp_host") or cfg.get("host") or os.getenv("SMTP_HOST", "")).strip()
    try:
        smtp_port = int(cfg.get("smtp_port") or cfg.get("port") or os.getenv("SMTP_PORT", "587"))
    except (ValueError, TypeError):
        smtp_port = 587
    smtp_user = str(cfg.get("smtp_user") or cfg.get("user") or os.getenv("SMTP_USER", "")).strip()
    smtp_pass = str(cfg.get("smtp_password") or cfg.get("password") or os.getenv("SMTP_PASSWORD", "")).strip()
    if "gmail" in smtp_host.lower():
        clean_p = smtp_pass.replace(" ", "").replace("\xa0", "").strip()
        if len(clean_p) == 16:
            smtp_pass = clean_p
    sender_name = str(cfg.get("sender_name") or "Logistica Zara Hub").strip()
    security = str(cfg.get("smtp_security") or ("SSL" if smtp_port == 465 else "STARTTLS")).upper()

    if not (smtp_host and smtp_user and smtp_pass):
        return False, "Parametri SMTP incompleti: Host, Nome Utente e Password sono obbligatori."

    try:
        now_str = datetime.now().strftime("%d/%m/%Y alle ore %H:%M:%S")
        msg = MIMEMultipart()
        msg["From"] = f"{sender_name} <{smtp_user}>" if sender_name else smtp_user
        msg["To"] = test_to
        msg["Subject"] = f"✅ Test Connessione Email SMTP - {now_str}"

        body = (
            f"Gentile Utente,\n\n"
            f"questa è un'email di prova inviata con successo dalla piattaforma Logistica Zara Hub!\n\n"
            f"Parametri utilizzati per la connessione:\n"
            f"- Server SMTP: {smtp_host}\n"
            f"- Porta: {smtp_port}\n"
            f"- Sicurezza: {security}\n"
            f"- Account Mittente: {smtp_user}\n"
            f"- Timestamp Invio: {now_str}\n\n"
            f"La configurazione è corretta e pronta per l'invio automatico dei file operativi.\n\n"
            f"Cordiali saluti,\n"
            f"Logistica Zara Hub"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if "SSL" in security or smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
            if "STARTTLS" in security or smtp_port == 587:
                server.starttls()

        with server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [test_to], msg.as_string())

        return True, f"Email di test inviata con successo a {test_to} tramite {smtp_host}:{smtp_port}."

    except smtplib.SMTPAuthenticationError as e:
        return False, f"Autenticazione SMTP fallita: username o password errati. (Dettaglio: {e})"
    except smtplib.SMTPConnectError as e:
        return False, f"Impossibile raggiungere il server SMTP ({smtp_host}:{smtp_port}). Verifica indirizzo host e porta. (Dettaglio: {e})"
    except Exception as e:
        return False, f"Errore durante l'invio della mail di test: {e}"
