"""
Modulo di Integrazione Google Cloud Storage (GCS) per File XML TMS.
Consente all'applicazione su Google Cloud di depositare i file XML generati
in un bucket Cloud Storage gratuito (5 GB/mese Free Tier perenne).
Fornisce inoltre lo script Windows nativo (.bat / .ps1) per prelevare
automaticamente i file dall'ufficio e depositarli nella cartella di BeOne.
"""

from datetime import datetime
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
import streamlit as st

from src.config import DATA_DIR, DB_PATH, OUTPUT_DIR

# File di persistenza configurazione GCS locale
GCS_CONFIG_FILE = DATA_DIR / "gcs_tms_config.json"

DEFAULT_GCS_CONFIG = {
    "bucket_name": "lacchi-tms-zara",
    "remote_prefix": "IMPORT_SGA/RICEZIONE_ORDINI/ZARA",
    "local_destination_dir": r"C:\IMPORT_SGA\RICEZIONE_ORDINI\ZARA",
}


def get_gcs_config() -> Dict[str, Any]:
    """Recupera la configurazione del bucket Google Cloud Storage."""
    cfg = dict(DEFAULT_GCS_CONFIG)

    if os.getenv("GCS_TMS_BUCKET"):
        cfg["bucket_name"] = os.getenv("GCS_TMS_BUCKET")
    if os.getenv("GCS_TMS_PREFIX"):
        cfg["remote_prefix"] = os.getenv("GCS_TMS_PREFIX")

    if GCS_CONFIG_FILE.exists():
        try:
            disk_cfg = json.loads(GCS_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(disk_cfg, dict):
                for k, v in disk_cfg.items():
                    cfg[k] = str(v).strip()
        except Exception:
            pass

    try:
        if hasattr(st, "session_state"):
            if "cfg_gcs_bucket" in st.session_state and st.session_state["cfg_gcs_bucket"]:
                cfg["bucket_name"] = str(st.session_state["cfg_gcs_bucket"]).strip()
            if "cfg_gcs_prefix" in st.session_state and st.session_state["cfg_gcs_prefix"]:
                cfg["remote_prefix"] = str(st.session_state["cfg_gcs_prefix"]).strip()
            if "cfg_gcs_local_dir" in st.session_state and st.session_state["cfg_gcs_local_dir"]:
                cfg["local_destination_dir"] = str(st.session_state["cfg_gcs_local_dir"]).strip()
    except Exception:
        pass

    return cfg


def save_gcs_config(cfg: Dict[str, Any]) -> bool:
    """Salva le impostazioni del bucket GCS su file locale permanente."""
    try:
        to_save = {
            "bucket_name": str(cfg.get("bucket_name", "lacchi-tms-zara")).strip(),
            "remote_prefix": str(cfg.get("remote_prefix", "IMPORT_SGA/RICEZIONE_ORDINI/ZARA")).strip(),
            "local_destination_dir": str(cfg.get("local_destination_dir", r"C:\IMPORT_SGA\RICEZIONE_ORDINI\ZARA")).strip(),
        }
        GCS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        GCS_CONFIG_FILE.write_text(json.dumps(to_save, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def get_gcp_metadata_token() -> Optional[str]:
    """
    Recupera il token di accesso OAuth2 dal server di metadati interno di Google Cloud
    (attivo su Cloud Run, Compute Engine e App Engine con zero credenziali necessarie).
    """
    metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
    try:
        resp = requests.get(metadata_url, headers={"Metadata-Flavor": "Google"}, timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token")
    except Exception:
        pass
    return None


def upload_xml_files_to_gcs(
    files: List[Union[Path, str, Tuple[str, Union[bytes, str]]]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Carica i file XML generati nel bucket Google Cloud Storage specificato.
    Usa la libreria google-cloud-storage se presente, altrimenti effettua la chiamata
    diretta REST API con il token del service account nativo di Cloud Run.
    """
    cfg = config or get_gcs_config()
    bucket_name = cfg.get("bucket_name", "lacchi-tms-zara").strip()
    prefix = cfg.get("remote_prefix", "IMPORT_SGA/RICEZIONE_ORDINI/ZARA").strip().strip("/")

    if not files:
        return {
            "status": "error",
            "uploaded_count": 0,
            "total_count": 0,
            "uploaded_files": [],
            "failed_files": [],
            "bucket": bucket_name,
            "message": "Nessun file XML fornito per il caricamento su GCS.",
        }

    # Prova prima con la libreria ufficiale se disponibile
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        uploaded = []
        failed = []
        for item in files:
            fname = ""
            fdata = b""
            if isinstance(item, (tuple, list)) and len(item) == 2:
                fname = str(item[0])
                fdata = item[1].encode("utf-8") if isinstance(item[1], str) else bytes(item[1])
            else:
                p = Path(item)
                fname = p.name
                fdata = p.read_bytes()

            if not fname.lower().endswith(".xml"):
                fname += ".xml"

            blob_name = f"{prefix}/{fname}" if prefix else fname
            try:
                blob = bucket.blob(blob_name)
                blob.upload_from_string(fdata, content_type="application/xml")
                uploaded.append(fname)
            except Exception as e:
                failed.append((fname, str(e)))

        return {
            "status": "ok" if not failed else ("partial" if uploaded else "error"),
            "uploaded_count": len(uploaded),
            "total_count": len(files),
            "uploaded_files": uploaded,
            "failed_files": failed,
            "bucket": bucket_name,
            "prefix": prefix,
            "message": f"Caricati con successo {len(uploaded)} su {len(files)} file XML nel bucket GCS '{bucket_name}/{prefix}'.",
        }
    except ImportError:
        pass
    except Exception as gcs_lib_err:
        # Se fallisce con la libreria, prova fallback REST
        pass

    # Fallback: Google Cloud Storage JSON REST API
    token = get_gcp_metadata_token()
    headers = {"Content-Type": "application/xml"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    uploaded = []
    failed = []

    for item in files:
        fname = ""
        fdata = b""
        if isinstance(item, (tuple, list)) and len(item) == 2:
            fname = str(item[0])
            fdata = item[1].encode("utf-8") if isinstance(item[1], str) else bytes(item[1])
        else:
            p = Path(item)
            fname = p.name
            fdata = p.read_bytes()

        if not fname.lower().endswith(".xml"):
            fname += ".xml"

        blob_path = f"{prefix}/{fname}" if prefix else fname
        import urllib.parse
        enc_name = urllib.parse.quote(blob_path, safe="")
        upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket_name}/o?uploadType=media&name={enc_name}"

        try:
            r = requests.post(upload_url, data=fdata, headers=headers, timeout=15)
            if r.status_code in (200, 201):
                uploaded.append(fname)
            else:
                failed.append((fname, f"HTTP {r.status_code}: {r.text[:120]}"))
        except Exception as e:
            failed.append((fname, str(e)))

    status = "ok" if not failed else ("partial" if uploaded else "error")
    msg = f"Caricati con successo {len(uploaded)} su {len(files)} file XML nel bucket GCS '{bucket_name}/{prefix}'."
    if failed:
        msg += f" {len(failed)} file non caricati."

    return {
        "status": status,
        "uploaded_count": len(uploaded),
        "total_count": len(files),
        "uploaded_files": uploaded,
        "failed_files": failed,
        "bucket": bucket_name,
        "prefix": prefix,
        "message": msg,
    }


def generate_windows_download_script(config: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """
    Genera il codice per due file nativi per Windows:
    1. scarica_xml_tms.ps1 (Script PowerShell nativo che preleva i file dal bucket e li deposita in C:\\IMPORT_SGA\\...)
    2. scarica_xml_tms.bat (Lanciatore 1-click da doppio clic o per Utilità di Pianificazione Windows)
    """
    cfg = config or get_gcs_config()
    bucket = cfg.get("bucket_name", "lacchi-tms-zara").strip()
    prefix = cfg.get("remote_prefix", "IMPORT_SGA/RICEZIONE_ORDINI/ZARA").strip().strip("/")
    loc_dir = cfg.get("local_destination_dir", r"C:\IMPORT_SGA\RICEZIONE_ORDINI\ZARA").strip()

    ps1_content = f"""<#
===============================================================================
 Sincronizzatore Automatico XML TMS da Google Cloud Storage a Cartella BeOne
 Generato automaticamente da Zara Logistics Hub
===============================================================================
#>

$BucketName = "{bucket}"
$RemotePrefix = "{prefix}"
$LocalDir = "{loc_dir}"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   SINCRONIZZAZIONE XML TMS DA GOOGLE CLOUD STORAGE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Bucket Remoto : gs://$BucketName/$RemotePrefix"
Write-Host "Cartella Locale : $LocalDir"
Write-Host ""

# Crea cartella locale se non presente
if (-not (Test-Path -Path $LocalDir)) {{
    New-Item -ItemType Directory -Path $LocalDir -Force | Out-Null
    Write-Host "[OK] Cartella locale creata: $LocalDir" -ForegroundColor Green
}}

# Metodo 1: Se gcloud CLI e installato nel sistema, usa gcloud storage rsync
$hasGcloud = (Get-Command gcloud -ErrorAction SilentlyContinue)
if ($hasGcloud) {{
    Write-Host "-> Rilevato Google Cloud CLI (gcloud). Avvio sincronizzazione veloce..." -ForegroundColor Yellow
    & gcloud storage rsync "gs://$BucketName/$RemotePrefix" "$LocalDir"
    Write-Host "[OK] Sincronizzazione completata con successo tramite gcloud!" -ForegroundColor Green
    exit 0
}}

# Metodo 2: Download diretto HTTP HTTPS nativo PowerShell (senza installare nessun software)
Write-Host "-> Download diretto HTTPS da Google Cloud Storage..." -ForegroundColor Yellow
$apiUrl = "https://storage.googleapis.com/storage/v1/b/$BucketName/o?prefix=$RemotePrefix"

try {{
    $response = Invoke-RestMethod -Uri $apiUrl -Method Get -TimeoutSec 15
    if ($response.items) {{
        $count = 0
        foreach ($item in $response.items) {{
            $blobName = $item.name
            $fileName = Split-Path $blobName -Leaf
            if ($fileName -like "*.xml") {{
                $destPath = Join-Path $LocalDir $fileName
                $downloadUrl = "https://storage.googleapis.com/$BucketName/$blobName"
                Invoke-WebRequest -Uri $downloadUrl -OutFile $destPath -UseBasicParsing
                Write-Host " [+] Scaricato: $fileName" -ForegroundColor Green
                $count++
            }}
        }}
        Write-Host ""
        Write-Host "[OK] Scaricati con successo $count file XML in $LocalDir" -ForegroundColor Green
    }} else {{
        Write-Host "Nessun file trovato nel bucket con prefisso $RemotePrefix" -ForegroundColor DarkGray
    }}
}} catch {{
    Write-Host "[ERRORE] Impossibile contattare il bucket GCS: $_" -ForegroundColor Red
    Write-Host "Suggerimento: Verifica che il bucket '$BucketName' sia accessibile o che gcloud CLI sia autenticato." -ForegroundColor Yellow
}}

Write-Host ""
"""

    bat_content = f"""@echo off
REM ==============================================================================
REM Lanciatore 1-Click Sincronizzazione XML TMS Zara Hub
REM ==============================================================================
title Sincronizzazione XML TMS Zara Hub
echo Avvio sincronizzazione file XML da Google Cloud Storage...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scarica_xml_tms.ps1"
if %ERRORLEVEL% EQU 0 (
    echo [OK] Operazione completata.
) else (
    echo [ERRORE] Si e verificato un problema durante la sincronizzazione.
    pause
)
"""
    return ps1_content, bat_content
