"""
Modulo di Automazione Operativa del Martedì e del Venerdì (Inditex Extranet -> Pipeline -> XML GCS -> Email).
- Martedì: Arrivi mezzi ciclo LUN-MER -> Consegne Mercoledì (/0 STD) e Giovedì (/9 DOPPIA).
- Venerdì: Arrivi mezzi ciclo GIOV-DOM ->
    * Fino al 12/12/2026: Consegne Sabato (/0 STD) e Domenica (/9 DOPPIA)
    * Dal 13/12/2026 in poi: Consegne Domenica (/0 STD) e Lunedì (/9 DOPPIA)
Supporta inoltre il recupero automatico dei profumi direttamente da email prima dell'avvio.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from src.bolle_manager import SUNDAY_MONDAY_SWITCH_DATE, compute_inditex_delivery_dates
from src.cloud_sync import get_extranet_credentials
from src.config import DATA_DIR, DB_PATH
from src.db import get_email_config
from src.mailer import send_operativa_email
from src.pipeline import run_pipeline
from src.scraper import InditexExtranetScraper
from src.utils import format_date_it, format_number_it, get_cycle_date_range

AUTO_OP_CONFIG_FILE = DATA_DIR / "auto_operativa_config.json"

DEFAULT_AUTO_OP_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "run_on_tuesday": True,
    "run_on_friday": True,
    "run_on_saturday": False,
    "schedule_time": "14:00",
    "attach_sintesi": True,
    "attach_zara": True,
    "attach_sga0": False,
    "attach_sga9": False,
    "auto_fetch_perfumes_from_email": True,
    "preset_perfumes": {"3680": 0, "9226": 0, "3591": 0},
    "last_auto_run_date": "",
    "last_auto_run_status": "",
    "last_auto_run_run_id": 0,
    "last_auto_run_timestamp": "",
}

_daemon_started = False
_daemon_lock = threading.Lock()


def now_rome() -> datetime:
    """Restituisce data e ora corrente nel fuso orario italiano (Europe/Rome)."""
    try:
        return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception:
        return datetime.now()


def get_auto_operativa_config() -> Dict[str, Any]:
    """Legge la configurazione dell'automazione Martedì/Sabato da disco."""
    cfg = dict(DEFAULT_AUTO_OP_CONFIG)
    if AUTO_OP_CONFIG_FILE.exists():
        try:
            loaded = json.loads(AUTO_OP_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass
    return cfg


def save_auto_operativa_config(new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Salva la configurazione dell'automazione Martedì/Sabato su disco."""
    cfg = get_auto_operativa_config()
    cfg.update(new_cfg)
    AUTO_OP_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTO_OP_CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return cfg


def resolve_cycle_for_arrival_date(target_date: Optional[date] = None) -> Tuple[str, date, date]:
    """
    Determina il ciclo operativo ('LUN-MER' per Martedì/inizio settimana, 'GIOV-DOM' per Sabato/fine settimana)
    e restituisce (cycle_type, date_b0_std, date_b9_doppia).
    Rispetta il cambio calendario dal 13 Dicembre 2026:
    - Martedì -> LUN-MER -> Consegne Mercoledì (/0 STD) e Giovedì (/9 DOPPIA)
    - Sabato -> GIOV-DOM ->
        * Prima del 13/12/2026: Consegne Sabato (/0 STD) e Domenica (/9 DOPPIA)
        * Dal 13/12/2026 in poi: Consegne Domenica (/0 STD) e Lunedì (/9 DOPPIA)
    """
    dt = target_date or now_rome().date()
    # Martedì è weekday() == 1 (<= 2 -> LUN-MER); Sabato è weekday() == 5 (> 2 -> GIOV-DOM)
    cycle_type = "LUN-MER" if dt.weekday() <= 2 else "GIOV-DOM"
    date_b9, date_b0 = compute_inditex_delivery_dates(dt, cycle_type)
    return cycle_type, date_b0, date_b9


def build_auto_email_payload(
    run_res: Dict[str, Any],
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, List[Path]]:
    """
    Costruisce oggetto, corpo del messaggio e lista allegati per l'invio automatico dell'email operativa.
    """
    c = cfg or get_auto_operativa_config()
    r_date = str(run_res.get("run_date", now_rome().strftime("%Y-%m-%d")))
    cycle_type = str(run_res.get("cycle_type", "LUN-MER"))
    date_b9, date_b0 = compute_inditex_delivery_dates(r_date, cycle_type)
    totals = run_res.get("totals", {})
    exp_files = run_res.get("exported_files", {})

    att_paths: List[Path] = []
    att_desc_lines: List[str] = []

    if c.get("attach_sintesi", True) and exp_files.get("sintesi") and Path(exp_files["sintesi"]).exists():
        att_paths.append(Path(exp_files["sintesi"]))
        att_desc_lines.append("- Sintesi Operativa Giri & Lavorazioni (Sintesi_Operativa.xlsx)")
    if c.get("attach_zara", True) and exp_files.get("zara") and Path(exp_files["zara"]).exists():
        att_paths.append(Path(exp_files["zara"]))
        att_desc_lines.append("- Foglio Spunta Arrivi ZARA Banchina (ZARA.xlsx)")
    if c.get("attach_sga0", False) and exp_files.get("sga0") and Path(exp_files["sga0"]).exists():
        att_paths.append(Path(exp_files["sga0"]))
        att_desc_lines.append("- Flusso Viaggi TMS Barra 0 (barrazero_Sga.xlsx)")
    if c.get("attach_sga9", False) and exp_files.get("sga9") and Path(exp_files["sga9"]).exists():
        att_paths.append(Path(exp_files["sga9"]))
        att_desc_lines.append("- Flusso Viaggi TMS Barra 9 Sdoppiati (barranove_Sga.xlsx)")

    subject = (
        f" Previsione & Pianificazione Operativa Zara — Arrivi {format_date_it(r_date)} "
        f"(Consegne /0: {format_date_it(date_b0)} | /9: {format_date_it(date_b9)})"
    ).strip()

    att_str = "\n".join(att_desc_lines) if att_desc_lines else "- Nessun allegato"
    body = (
        f"Gentili Colleghi,\n\n"
        f"in allegato trasmettiamo i file operativi generati automaticamente per gli arrivi del {format_date_it(r_date)} ({cycle_type}):\n"
        f"- Consegna Barra 0 (/0 STD): {format_date_it(date_b0)}\n"
        f"- Consegna Barra 9 (/9 DOPPIA): {format_date_it(date_b9)}\n\n"
        f"Documenti allegati:\n{att_str}\n\n"
        f"Riepilogo Totali Spedizione:\n"
        f"- Totale Colli: {format_number_it(totals.get('total_bultos', 0), 0)}\n"
        f"- Volume Complessivo: {format_number_it(totals.get('total_volume', 0.0), 2)} m³\n"
        f"- Peso Complessivo: {format_number_it(totals.get('total_weight', 0.0), 0)} kg\n"
        f"- Pedane Stimate: {format_number_it(totals.get('total_pedane', 0.0), 0)} PLT\n\n"
        f"I flussi XML TMS sono stati generati e caricati automaticamente su Google Cloud Storage per l'importazione locale.\n\n"
        f"Cordiali saluti,\n"
        f"Ufficio Logistica & Traffico Zara Hub (Automazione Operativa)"
    )
    return subject, body, att_paths


def execute_auto_operativa_run(
    target_date: Optional[date] = None,
    force: bool = False,
    perfume_override: Optional[Dict[str, float]] = None,
    progress_callback: Optional[ Any ] = None,
) -> Dict[str, Any]:
    """
    Esegue l'intero flusso automatico dell'operativa del giorno (Martedì o Sabato):
    1) Scarica i file da Inditex Extranet per il ciclo corrispondente (LUN-MER il Martedì, GIOV-DOM il Sabato)
    2) Esegue run_pipeline -> Genera Excel + Bolle (/0 e /9 con regola 13 Dicembre) + XML TMS su GCS
    3) Invia automaticamente l'email operativa con gli allegati configurati.
    """
    cfg = get_auto_operativa_config()
    dt = target_date or now_rome().date()
    dt_iso = dt.strftime("%Y-%m-%d")

    if not force and cfg.get("last_auto_run_date") == dt_iso and cfg.get("last_auto_run_status") == "ok":
        return {
            "status": "skipped",
            "message": f"Operativa automatica del {format_date_it(dt_iso)} già eseguita (Run #{cfg.get('last_auto_run_run_id')}).",
            "run_id": cfg.get("last_auto_run_run_id"),
        }

    cycle_type, date_b0, date_b9 = resolve_cycle_for_arrival_date(dt)
    desde_dt, hasta_dt = get_cycle_date_range(cycle_type, dt)

    ex_user, ex_pass = get_extranet_credentials()
    ts = now_rome().strftime("%Y%m%d_%H%M%S")
    temp_extract_dir = DATA_DIR / "downloads" / f"auto_extranet_{ts}"
    temp_extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        scraper = InditexExtranetScraper(
            username=ex_user,
            password=ex_pass,
            headless=True,
            progress_callback=progress_callback,
        )
        scraper.scrape_all(
            desde_date=desde_dt,
            hasta_date=hasta_dt,
            output_dir=temp_extract_dir,
        )

        perf_source_note = ""
        perf_map = dict(cfg.get("preset_perfumes", {}))
        if perfume_override is not None:
            perf_map.update(perfume_override)
            perf_source_note = " (override manuale)"
        elif cfg.get("auto_fetch_perfumes_from_email", True):
            try:
                from src.perfume_inbox import fetch_latest_perfumes_from_email
                inbox_res = fetch_latest_perfumes_from_email()
                if inbox_res.get("status") == "ok" and inbox_res.get("perfumes"):
                    perf_from_email = inbox_res["perfumes"]
                    perf_map.update(perf_from_email)
                    p_details = ", ".join([f"{k}: {int(v)}pz" for k, v in perf_from_email.items()])
                    perf_source_note = f" (Scorporo profumi rilevato via email: {p_details})"
            except Exception:
                pass

        clean_perf = {str(k): float(v or 0) for k, v in (perf_map or {}).items()}

        notes = (
            f"Automazione {dt.strftime('%A')} W{dt.isocalendar()[1]} ({cycle_type}) "
            f"[Consegne /0: {format_date_it(date_b0)} - /9: {format_date_it(date_b9)}]{perf_source_note}"
        )

        res = run_pipeline(
            total_source=temp_extract_dir / "TOTAL.xls",
            shoes_source=(temp_extract_dir / "SHOES.xls") if (temp_extract_dir / "SHOES.xls").exists() else None,
            texile_source=(temp_extract_dir / "TEXILE.xls") if (temp_extract_dir / "TEXILE.xls").exists() else None,
            ecom_source=(temp_extract_dir / "ECOM.xls") if (temp_extract_dir / "ECOM.xls").exists() else None,
            other_source=(temp_extract_dir / "OTHER"),
            esportazione_source=None,
            run_date=dt_iso,
            cycle_type=cycle_type,
            notes=notes,
            perfume_corrections=clean_perf,
            save_to_network=True,
        )

        # Invio automatico Email Operativa
        email_cfg = get_email_config()
        to_raw = str(email_cfg.get("to_recipients", "") or "")
        cc_raw = str(email_cfg.get("cc_recipients", "") or "")
        to_list = [x.strip() for x in to_raw.split(",") if x.strip()]
        cc_list = [x.strip() for x in cc_raw.split(",") if x.strip()]

        email_ok = False
        email_msg = "Nessun destinatario configurato in Configurazione Email."
        if to_list:
            subj, body, att_paths = build_auto_email_payload(res, cfg)
            email_ok, email_msg = send_operativa_email(
                recipients=to_list,
                subject=subj,
                body_text=body,
                attachment_paths=att_paths,
                cc_recipients=cc_list,
                smtp_config=email_cfg,
            )

        gcs_res = res.get("gcs_upload") or {}
        xml_cnt = len(res.get("tms_xml_files") or [])

        save_auto_operativa_config({
            "last_auto_run_date": dt_iso,
            "last_auto_run_status": "ok",
            "last_auto_run_run_id": int(res["run_id"]),
            "last_auto_run_timestamp": now_rome().strftime("%d/%m/%Y %H:%M:%S"),
            "last_auto_run_summary": (
                f"Run #{res['run_id']} ({cycle_type}: /0 {format_date_it(date_b0)}, /9 {format_date_it(date_b9)}) • "
                f"{xml_cnt} XML generati • Email: {email_msg}"
            ),
        })

        return {
            "status": "ok",
            "run_id": int(res["run_id"]),
            "run_result": res,
            "cycle_type": cycle_type,
            "date_b0": str(date_b0),
            "date_b9": str(date_b9),
            "xml_count": xml_cnt,
            "gcs_upload": gcs_res,
            "email_ok": email_ok,
            "email_message": email_msg,
        }
    except Exception as exc:
        save_auto_operativa_config({
            "last_auto_run_date": dt_iso,
            "last_auto_run_status": "error",
            "last_auto_run_timestamp": now_rome().strftime("%d/%m/%Y %H:%M:%S"),
            "last_auto_run_summary": f"Errore: {exc}",
        })
        return {
            "status": "error",
            "message": str(exc),
        }


def check_and_trigger_scheduled_operativa(now_dt: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """
    Controlla se oggi è Martedì (weekday=1) o Venerdì (weekday=4), se l'automazione è attiva
    e se l'ora corrente (Europe/Rome) ha raggiunto o superato `schedule_time` senza che
    l'operativa di oggi sia già stata eseguita. In tal caso avvia `execute_auto_operativa_run`.
    """
    cfg = get_auto_operativa_config()
    if not cfg.get("enabled", True):
        return None

    cur = now_dt or now_rome()
    wd = cur.weekday()  # 1 = Martedì, 4 = Venerdì, (5 = Sabato opzionale legacy)
    if wd == 1 and not cfg.get("run_on_tuesday", True):
        return None
    if wd == 4 and not cfg.get("run_on_friday", True):
        return None
    if wd == 5 and not cfg.get("run_on_saturday", False):
        return None
    if wd not in (1, 4, 5):
        return None

    today_iso = cur.strftime("%Y-%m-%d")
    if cfg.get("last_auto_run_date") == today_iso and cfg.get("last_auto_run_status") == "ok":
        return None

    sched_str = str(cfg.get("schedule_time", "14:00") or "14:00").strip()
    try:
        sh, sm = [int(x) for x in sched_str.split(":")[:2]]
    except Exception:
        sh, sm = 14, 0

    if (cur.hour, cur.minute) >= (sh, sm):
        return execute_auto_operativa_run(target_date=cur.date(), force=False)
    return None


def start_auto_operativa_daemon() -> None:
    """
    Avvia (una sola volta per processo) il thread scheduler in background che controlla
    ogni 60 secondi se scatta l'estrazione automatica del Martedì o del Venerdì.
    """
    global _daemon_started
    with _daemon_lock:
        if _daemon_started:
            return
        _daemon_started = True

    def _loop():
        while True:
            try:
                check_and_trigger_scheduled_operativa()
            except Exception:
                pass
            time.sleep(60)

    t = threading.Thread(target=_loop, name="ZaraAutoOperativaScheduler", daemon=True)
    t.start()


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Zara Logistics Hub — CLI Esecuzione Automatica Operativa")
    parser.add_argument("--force", action="store_true", help="Forza l'esecuzione anche se già eseguita oggi")
    parser.add_argument("--run-now", action="store_true", help="Esegue immediatamente il ciclo completo")
    parser.add_argument("--date", type=str, default="", help="Data target specifica (YYYY-MM-DD)")
    parser.add_argument("--fetch-perfumes", action="store_true", help="Verifica e scarica profumi da email prima dell'avvio")

    args = parser.parse_args()

    t_date = None
    if args.date:
        t_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    out = execute_auto_operativa_run(target_date=t_date, force=(args.force or args.run_now))
    clean_out = {k: v for k, v in out.items() if k != "run_result"}
    print(json.dumps(clean_out, indent=2, ensure_ascii=False))
