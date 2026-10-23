import os
import smtplib
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any


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
    If SMTP credentials are provided in smtp_config or environment variables,
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

    cfg = smtp_config or {}
    smtp_host = cfg.get("host") or os.getenv("SMTP_HOST")
    smtp_port = cfg.get("port") or int(os.getenv("SMTP_PORT", "587"))
    smtp_user = cfg.get("user") or os.getenv("SMTP_USER")
    smtp_pass = cfg.get("password") or os.getenv("SMTP_PASSWORD")
    use_tls = cfg.get("use_tls", True)

    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_user
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
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                if use_tls:
                    server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, all_dest, msg.as_string())

            return True, f"Email inviata con successo a {len(clean_recipients)} destinatari con {len(valid_attachments)} allegati."
        except Exception as e:
            return False, f"Errore durante l'invio SMTP: {e}"

    # Dry-run / simulation mode
    att_names = [p.name for p in valid_attachments]
    return True, (
        f"Simulazione invio completata con successo a {', '.join(clean_recipients)}. "
        f"Allegati inclusi: {', '.join(att_names) if att_names else 'Nessuno'}. "
        "Per l'invio reale definitivo, configurare le variabili d'ambiente SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)."
    )
