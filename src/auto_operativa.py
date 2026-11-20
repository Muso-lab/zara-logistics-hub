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

    lav_lines = []
    spec_bd = run_res.get("special_breakdowns", {})
    if spec_bd:
        spec_stores = spec_bd.get("special_stores", {})
        zh_stores = spec_bd.get("zara_home", {})
        tot_pezzi_lav = spec_bd.get("totale_pezzi_lavorati", 0)

        lav_lines.append("Sintesi Lavorazioni di Piattaforma del Giorno:")
        if spec_stores:
            lav_lines.append("- Lavorazione Speciale Tessile:")
            for sid, sdata in spec_stores.items():
                sname = sdata.get("store_name", sid)
                app = int(sdata.get("appesi", 0))
                stnd = int(sdata.get("stender", sdata.get("stander", 0)))
                ste = int(sdata.get("stesi", 0))
                plt = int(sdata.get("bancali", sdata.get("bancali_stesi", 0)))
                prf = int(sdata.get("correzione_profumi", 0))
                tot_s = int(sdata.get("totale_pezzi", app + ste))
                lav_lines.append(f"  • {sid} {sname}: {format_number_it(tot_s, 0)} capi tot | {format_number_it(app, 0)} appesi ({format_number_it(stnd, 0)} stender) | {format_number_it(ste, 0)} stesi ({format_number_it(plt, 0)} bancali) | profumi: {format_number_it(prf, 0)}")

        if zh_stores:
            lav_lines.append("- Lavorazione Zara Home (50% /0 e 50% /8):")
            for sid, zdata in zh_stores.items():
                zsname = zdata.get("store_name", sid)
                paq = int(zdata.get("totale_paqueteria", zdata.get("totale", 0)))
                q0 = int(zdata.get("quota_barra0", zdata.get("barra0", 0)))
                q8 = int(zdata.get("quota_barra8", zdata.get("barra8", 0)))
                lav_lines.append(f"  • {sid} {zsname}: {format_number_it(paq, 0)} pz totali (50% /0: {format_number_it(q0, 0)} pz — 50% /8: {format_number_it(q8, 0)} pz)")

        if tot_pezzi_lav:
            lav_lines.append(f"- Totale Pezzi Lavorati in Piattaforma: {format_number_it(tot_pezzi_lav, 0)} pz")

    lav_section = ("\n" + "\n".join(lav_lines) + "\n") if lav_lines else ""

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
        f"- Pedane Stimate: {format_number_it(totals.get('total_pedane', 0.0), 0)} PLT\n"
        f"{lav_section}\n"
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
    # 0. Inizializza schema DB locale + Sincronizzazione preventiva da Google Sheets
    # (ripristina credenziali, anagrafica negozi e storico PRIMA di elaborare)
    try:
        from src.db import init_db
        from src.bolle_manager import init_bolle_tables
        init_db()
        init_bolle_tables()
    except Exception as init_err:
        print(f"Pre-run DB init warning: {init_err}")

    try:
        from src.cloud_sync import pull_all_from_cloud
        pull_res = pull_all_from_cloud(timeout=35)
        print(f"Pre-run Cloud Pull: {pull_res.get('status')} | restored={pull_res.get('restored')}")
    except Exception as pull_err:
        print(f"Pre-run Cloud Pull warning: {pull_err}")

    cfg = get_auto_operativa_config()
    dt = target_date or now_rome().date()
    dt_iso = dt.strftime("%Y-%m-%d")

    if not force:
        # 1. Day-of-week guard (solo Martedì e Venerdì, più eventuale Sabato configurato)
        wd = dt.weekday()  # 1 = Martedì, 4 = Venerdì, 5 = Sabato (opzionale)
        allowed_wds = {1, 4}
        if cfg.get("run_on_saturday", False):
            allowed_wds.add(5)
        if wd not in allowed_wds:
            return {
                "status": "skipped",
                "message": f"Giorno {dt.strftime('%A')} ({format_date_it(dt_iso)}) non previsto per l'automazione schedulata (solo Martedì e Venerdì).",
            }

        # 2. Time-window guard (evita invii notturni / fuori orario in caso di ritardo cron)
        cur_rome = now_rome()
        if target_date is None and not (12 <= cur_rome.hour < 17):
            return {
                "status": "skipped",
                "message": f"Esecuzione schedulata fuori dalla finestra oraria consentita 12:00-17:00 (ora attuale: {cur_rome.strftime('%H:%M')}) — ignorata per evitare invii fuori orario.",
            }

        # 3. Config file duplicate guard
        if cfg.get("last_auto_run_date") == dt_iso and cfg.get("last_auto_run_status") == "ok":
            return {
                "status": "skipped",
                "message": f"Operativa automatica del {format_date_it(dt_iso)} già eseguita (Run #{cfg.get('last_auto_run_run_id')}).",
                "run_id": cfg.get("last_auto_run_run_id"),
            }

        # 4. Database duplicate guard (verifica sulle run sincronizzate da Google Sheets/SQLite)
        try:
            from src.db import get_all_runs
            df_existing = get_all_runs()
            if not df_existing.empty:
                for _, r_ex in df_existing.iterrows():
                    r_dt = str(r_ex.get("run_date", "") or "")[:10]
                    r_cr = str(r_ex.get("created_at", "") or "")[:10]
                    if dt_iso in (r_dt, r_cr):
                        ex_id = r_ex.get("id")
                        return {
                            "status": "skipped",
                            "message": f"Operativa del {format_date_it(dt_iso)} già presente a database (Run #{ex_id}) — nessun invio duplicato.",
                            "run_id": ex_id,
                        }
        except Exception as db_chk_err:
            print(f"Warning check runs duplicate: {db_chk_err}")

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
                print(f"Verifica automatica profumi da email: {inbox_res.get('status')} - {inbox_res.get('message')}")
                if inbox_res.get("status") == "ok" and inbox_res.get("perfumes"):
                    perf_from_email = inbox_res["perfumes"]
                    perf_map.update(perf_from_email)
                    p_details = ", ".join([f"{k}: {int(v)}pz" for k, v in perf_from_email.items()])
                    perf_source_note = f" (Scorporo profumi rilevato via email: {p_details})"
                    print(f"Profumi applicati: {p_details}")
                else:
                    print(f"Nessun dato profumi applicato: {inbox_res.get('message')}")
            except Exception as e:
                print(f"Errore lettura profumi da email: {e}")

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
        to_raw = str(email_cfg.get("default_to") or email_cfg.get("to_recipients") or "")
        cc_raw = str(email_cfg.get("default_cc") or email_cfg.get("cc_recipients") or "")
        to_list = [x.strip() for x in to_raw.split(",") if x.strip()]
        cc_list = [x.strip() for x in cc_raw.split(",") if x.strip()]

        email_ok = False
        email_msg = "Nessun destinatario configurato in Configurazione Email."
        if to_list:
            subj, body, att_paths = build_auto_email_payload(res, cfg)
            print(f"Invio email automatica a {to_list} (CC: {cc_list}) con {len(att_paths)} allegati...")
            email_ok, email_msg = send_operativa_email(
                recipients=to_list,
                subject=subj,
                body_text=body,
                attachment_paths=att_paths,
                cc_recipients=cc_list,
                smtp_config=email_cfg,
            )
            print(f"Esito invio email: ok={email_ok}, msg={email_msg}")

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

    # Verifica se una run per oggi è già presente nel DB per prevenire esecuzioni duplicate
    try:
        from src.db import get_all_runs
        df_r = get_all_runs()
        if not df_r.empty and "run_date" in df_r.columns:
            existing_today = df_r[df_r["run_date"].astype(str).str.startswith(today_iso)]
            if not existing_today.empty:
                return None
    except Exception:
        pass

    sched_str = str(cfg.get("schedule_time", "14:00") or "14:00").strip()
    try:
        sh, sm = [int(x) for x in sched_str.split(":")[:2]]
    except Exception:
        sh, sm = 14, 0

    if (cur.hour, cur.minute) >= (sh, sm):
        return execute_auto_operativa_run(target_date=cur.date(), force=False)
    return None


def execute_delta_check_run(
    target_date: Optional[date] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Controllo variazioni pomeridiano (ore 17:00 Martedì e Venerdì):
    1) Scarica in modo silenzioso i file aggiornati da Inditex Extranet in cartella temporanea.
    2) Confronta i totali (colli, m³) e i singoli negozi rispetto alla Run già elaborata oggi alle 14:00.
    3) Se NON è cambiato nulla: termina in silenzio (nessuna sovrascrittura, nessuna email).
    4) Se rileva variazioni reali (es. mezzi aggiunti alle 16:00):
       - Sostituisce la Run delle 14:00 preservando i profumi e tutte le bolle già spuntate (spuntato=1);
       - Rigenera Excel, Bolle non spuntate e XML su Cloud Storage;
       - Invia una mail di ALERT chiara con riepilogo Prima vs Dopo ed elenco dei soli negozi variati.
    """
    try:
        from src.db import init_db, get_all_runs, delete_run, get_connection, get_stores_df
        from src.bolle_manager import init_bolle_tables
        init_db()
        init_bolle_tables()
    except Exception as init_err:
        print(f"Delta-check DB init warning: {init_err}")

    try:
        from src.cloud_sync import pull_all_from_cloud
        pull_res = pull_all_from_cloud(timeout=35)
        print(f"Delta-check Cloud Pull: {pull_res.get('status')} | restored={pull_res.get('restored')}")
    except Exception as pull_err:
        print(f"Delta-check Cloud Pull warning: {pull_err}")

    cfg = get_auto_operativa_config()
    dt = target_date or now_rome().date()
    dt_iso = dt.strftime("%Y-%m-%d")

    if not force:
        wd = dt.weekday()  # 1 = Martedì, 4 = Venerdì
        allowed_wds = {1, 4}
        if cfg.get("run_on_saturday", False):
            allowed_wds.add(5)
        if wd not in allowed_wds:
            return {
                "status": "skipped",
                "message": f"Controllo 17:00 ignorato: {dt.strftime('%A')} ({format_date_it(dt_iso)}) non è Martedì/Venerdì.",
            }
        cur_rome = now_rome()
        if target_date is None and not (16 <= cur_rome.hour < 20):
            return {
                "status": "skipped",
                "message": f"Controllo 17:00 fuori finestra oraria 16:00-20:00 (ora attuale: {cur_rome.strftime('%H:%M')}).",
            }

    # Cerca la Run di oggi già esistente (es. quella delle 14:00)
    df_runs = get_all_runs()
    old_run = None
    if not df_runs.empty:
        for _, r_row in df_runs.iterrows():
            r_dt = str(r_row.get("run_date", "") or "")[:10]
            r_cr = str(r_row.get("created_at", "") or "")[:10]
            if dt_iso in (r_dt, r_cr):
                old_run = r_row.to_dict()
                break

    if old_run is None:
        print("Nessuna Run trovata oggi alle 14:00: avvio elaborazione completa standard.")
        return execute_auto_operativa_run(target_date=dt, force=True)

    old_run_id = int(old_run["id"])
    old_bultos_tot = float(old_run.get("total_bultos") or 0.0)
    old_vol_tot = float(old_run.get("total_volume") or 0.0)
    old_ped_tot = float(old_run.get("total_pedane") or 0.0)

    # Recupera dettaglio per negozio della Run precedente (da forecast_raw TOTAL)
    old_store_map: Dict[str, Dict[str, float]] = {}
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            rows_fr = cur.execute(
                "SELECT store_code, SUM(bultos), SUM(volume) FROM forecast_raw WHERE run_id = ? AND UPPER(COALESCE(source_file, 'TOTAL')) = 'TOTAL' GROUP BY store_code",
                (old_run_id,),
            ).fetchall()
            if not rows_fr:
                rows_fr = cur.execute(
                    "SELECT store_code, SUM(textile_attesi + other_attesi + shoes_attesi + ecom_attesi), SUM(mc) FROM spunta_arrivi WHERE run_id = ? AND COALESCE(is_barra9, 0) = 0 GROUP BY store_code",
                    (old_run_id,),
                ).fetchall()
            for sc, sb, sv in rows_fr:
                sc_str = str(sc or "").strip()
                if sc_str:
                    old_store_map[sc_str] = {"bultos": float(sb or 0.0), "vol": float(sv or 0.0)}
    except Exception as e:
        print(f"Warning lettura old_store_map: {e}")

    cycle_type, date_b0, date_b9 = resolve_cycle_for_arrival_date(dt)
    desde_dt, hasta_dt = get_cycle_date_range(cycle_type, dt)

    ex_user, ex_pass = get_extranet_credentials()
    ts = now_rome().strftime("%Y%m%d_%H%M%S")
    temp_extract_dir = DATA_DIR / "downloads" / f"delta_check_{ts}"
    temp_extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        scraper = InditexExtranetScraper(
            username=ex_user,
            password=ex_pass,
            headless=True,
        )
        scraper.scrape_all(
            desde_date=desde_dt,
            hasta_date=hasta_dt,
            output_dir=temp_extract_dir,
        )

        # Parsing silenzioso del solo TOTAL.xls per confrontare colli e volumi
        from src.parsers import parse_grupo_envio
        df_tot_new = parse_grupo_envio(temp_extract_dir / "TOTAL.xls")
        if df_tot_new.empty:
            return {"status": "error", "message": "Controllo 17:00: TOTAL.xls scaricato da Extranet risulta vuoto."}

        new_store_map: Dict[str, Dict[str, float]] = {}
        for _, nr in df_tot_new.iterrows():
            sid = str(nr.get("store_id") or "").strip()
            if not sid:
                continue
            if sid not in new_store_map:
                new_store_map[sid] = {"bultos": 0.0, "vol": 0.0}
            new_store_map[sid]["bultos"] += float(nr.get("bultos") or 0.0)
            new_store_map[sid]["vol"] += float(nr.get("volumen") or 0.0)

        new_bultos_tot = sum(v["bultos"] for v in new_store_map.values())
        new_vol_tot = sum(v["vol"] for v in new_store_map.values())

        delta_bultos = round(new_bultos_tot - old_bultos_tot)
        delta_vol = round(new_vol_tot - old_vol_tot, 2)

        # Confronto puntuale negozio per negozio
        df_stores_m = get_stores_df()
        stores_info = {}
        if not df_stores_m.empty:
            for _, sr in df_stores_m.iterrows():
                stores_info[str(sr["store_id"]).strip()] = {
                    "name": str(sr.get("store_name") or ""),
                    "giro": str(sr.get("giro") or ""),
                    "brand": str(sr.get("brand") or ""),
                }

        changed_stores = []
        all_sids = sorted(set(old_store_map.keys()) | set(new_store_map.keys()))
        for sid in all_sids:
            ob = old_store_map.get(sid, {}).get("bultos", 0.0)
            nb = new_store_map.get(sid, {}).get("bultos", 0.0)
            ov = old_store_map.get(sid, {}).get("vol", 0.0)
            nv = new_store_map.get(sid, {}).get("vol", 0.0)
            db_s = round(nb - ob)
            dv_s = round(nv - ov, 2)
            if abs(db_s) >= 1 or abs(dv_s) >= 0.1:
                info = stores_info.get(sid, {})
                changed_stores.append({
                    "store_id": sid,
                    "store_name": info.get("name", ""),
                    "brand": info.get("brand", ""),
                    "giro": info.get("giro", ""),
                    "old_bultos": int(round(ob)),
                    "new_bultos": int(round(nb)),
                    "delta_bultos": int(db_s),
                    "old_vol": round(ov, 2),
                    "new_vol": round(nv, 2),
                    "delta_vol": round(dv_s, 2),
                })

        # Se non ci sono variazioni reali: silenzio totale, zero sovrascritture, zero email!
        if abs(delta_bultos) < 1 and abs(delta_vol) < 0.1 and not changed_stores:
            msg_ok = (
                f"Controllo ore 17:00 completato ({format_date_it(dt_iso)}): nessuna variazione rilevata rispetto "
                f"alla Run #{old_run_id} ({int(round(old_bultos_tot))} colli, {old_vol_tot:.2f} m³). Nessuna email inviata."
            )
            print(msg_ok)
            return {
                "status": "unchanged",
                "old_run_id": old_run_id,
                "message": msg_ok,
            }

        # VARIAZIONE RILEVATA! Preserva profumi, sostituisce la Run e aggiorna le bolle non spuntate
        print(f"⚠️ VARIAZIONE RILEVATA ORE 17:00: Delta Colli={delta_bultos:+d}, Delta m³={delta_vol:+.2f}, Negozi variati={len(changed_stores)}")

        perf_map: Dict[str, float] = {}
        try:
            old_p_raw = old_run.get("perfume_data")
            if old_p_raw:
                parsed_p = json.loads(old_p_raw) if isinstance(old_p_raw, str) else old_p_raw
                if isinstance(parsed_p, dict):
                    perf_map.update({str(k): float(v or 0) for k, v in parsed_p.items()})
        except Exception:
            pass

        if cfg.get("auto_fetch_perfumes_from_email", True):
            try:
                from src.perfume_inbox import fetch_latest_perfumes_from_email
                inbox_res = fetch_latest_perfumes_from_email()
                if inbox_res.get("status") == "ok" and inbox_res.get("perfumes"):
                    perf_map.update({str(k): float(v or 0) for k, v in inbox_res["perfumes"].items()})
            except Exception as pe:
                print(f"Warning rilettura profumi alle 17:00: {pe}")

        clean_perf = {str(k): float(v or 0) for k, v in perf_map.items()}

        # Elimina vecchia Run delle 14:00 e rigenera solo le bolle NON ancora spuntate (spuntato=0)
        delete_run(old_run_id)
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM bolle WHERE data_consegna IN (?, ?) AND COALESCE(spuntato, 0) = 0",
                    (str(date_b0), str(date_b9)),
                )
                conn.commit()
        except Exception as be:
            print(f"Warning pulizia bolle non spuntate: {be}")

        delta_sign_c = f"{delta_bultos:+d}"
        delta_sign_v = f"{delta_vol:+.2f}"
        notes = (
            f"⚠️ AGGIORNAMENTO ORE 17:00 ({delta_sign_c} colli / {delta_sign_v} m³) — "
            f"{dt.strftime('%A')} W{dt.isocalendar()[1]} ({cycle_type}) "
            f"[Consegne /0: {format_date_it(date_b0)} - /9: {format_date_it(date_b9)}]"
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

        new_totals = res.get("totals") or {}
        new_ped_tot = float(new_totals.get("total_pedane") or 0.0)
        delta_ped = round(new_ped_tot - old_ped_tot)

        # Invio EMAIL DI ALERT CHIARA con dettaglio variazioni
        email_cfg = get_email_config()
        to_raw = str(email_cfg.get("default_to") or email_cfg.get("to_recipients") or "")
        cc_raw = str(email_cfg.get("default_cc") or email_cfg.get("cc_recipients") or "")
        to_list = [x.strip() for x in to_raw.split(",") if x.strip()]
        cc_list = [x.strip() for x in cc_raw.split(",") if x.strip()]

        email_ok = False
        email_msg = "Nessun destinatario configurato."
        if to_list:
            _, _, att_paths = build_auto_email_payload(res, cfg)
            alert_subject = (
                f"⚠️ AGGIORNAMENTO VOLUMI ORE 17:00 — Operativa Zara {format_date_it(dt_iso)} "
                f"({delta_sign_c} colli / {delta_sign_v} m³)"
            )
            lines = [
                "⚠️ ATTENZIONE: RILEVATA VARIAZIONE VOLUMI INDITEX (CONTROLLO ORE 17:00)",
                "=" * 72,
                f"Data Elaborazione: {format_date_it(dt_iso)} | Ciclo: {cycle_type}",
                f"Consegne /0 STD: {format_date_it(date_b0)} | Consegne /9 DOPPIA: {format_date_it(date_b9)}",
                "",
                "CONFRONTO TOTALI (ORE 14:00 -> ORE 17:00):",
                f"  • Totale Colli : {int(round(old_bultos_tot)):,} -> {int(round(new_bultos_tot)):,}  ({delta_bultos:+d} colli)",
                f"  • Volume (m³)  : {old_vol_tot:.2f} -> {new_vol_tot:.2f} m³  ({delta_vol:+.2f} m³)",
                f"  • Pedane (PLT) : {int(round(old_ped_tot))} -> {int(round(new_ped_tot))} PLT  ({delta_ped:+d} PLT)",
                "",
                f"DETTAGLIO NEGOZI VARIATI ({len(changed_stores)}):",
            ]
            for cs in changed_stores:
                lines.append(
                    f"  - Store {cs['store_id']} ({cs['brand']} {cs['store_name']} | Giro {cs['giro']}): "
                    f"{cs['old_bultos']} -> {cs['new_bultos']} colli ({cs['delta_bultos']:+d}) | "
                    f"{cs['old_vol']:.2f} -> {cs['new_vol']:.2f} m³ ({cs['delta_vol']:+.2f} m³)"
                )
            lines.extend([
                "",
                "AZIONI GIA' ESEGUITE AUTOMATICAMENTE:",
                f"  ✓ La Run precedente (#{old_run_id}) è stata sostituita con la nuova Run #{res['run_id']}.",
                "  ✓ Le bolle non ancora spuntate sono state aggiornate (eventuali spunte già confermate sono rimaste protette).",
                "  ✓ I file XML su Cloud Storage e i file Excel in allegato sono stati rigenerati con i nuovi volumi.",
                "",
                "Cordiali saluti,",
                "Zara Logistics Hub — Sistema di Controllo Automatico Ore 17:00",
            ])
            alert_body = "\n".join(lines)
            email_ok, email_msg = send_operativa_email(
                recipients=to_list,
                subject=alert_subject,
                body_text=alert_body,
                attachment_paths=att_paths,
                cc_recipients=cc_list,
                smtp_config=email_cfg,
            )

        return {
            "status": "updated",
            "old_run_id": old_run_id,
            "run_id": int(res["run_id"]),
            "delta_bultos": int(delta_bultos),
            "delta_vol": float(delta_vol),
            "changed_stores_count": len(changed_stores),
            "email_ok": email_ok,
            "email_message": email_msg,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Errore controllo 17:00: {exc}"}


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
    parser.add_argument("--scheduled", action="store_true", help="Esecuzione da scheduler automatico (applica filtri giorno, fascia oraria 12-17 e anti-duplicato DB)")
    parser.add_argument("--check-delta", action="store_true", help="Controllo variazioni ore 17:00: aggiorna e invia email ALERT solo se i volumi Inditex sono cambiati")
    parser.add_argument("--date", type=str, default="", help="Data target specifica (YYYY-MM-DD)")
    parser.add_argument("--fetch-perfumes", action="store_true", help="Verifica e scarica profumi da email prima dell'avvio")

    args = parser.parse_args()

    t_date = None
    if args.date:
        t_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    if args.check_delta:
        out = execute_delta_check_run(target_date=t_date, force=bool(args.force))
    else:
        is_forced = bool(args.force) or (bool(args.run_now) and not bool(args.scheduled))
        out = execute_auto_operativa_run(target_date=t_date, force=is_forced)

    clean_out = {k: v for k, v in out.items() if k != "run_result"}
    print(json.dumps(clean_out, indent=2, ensure_ascii=False))
    if out.get("status") in ("ok", "updated") and not out.get("email_ok"):
        print(f"ERRORE CRITICO: Elaborazione completata ma invio email fallito: {out.get('email_message')}", file=sys.stderr)
        sys.exit(2)
