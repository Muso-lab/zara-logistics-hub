import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
import io
import sqlite3
import json
import threading

from src.cloud_sync import (
    get_cloud_url,
    set_cloud_url,
    push_tables_to_cloud,
    pull_all_from_cloud,
    get_extranet_credentials,
    set_extranet_credentials,
)

from src.config import (
    OUTPUT_DIR,
    DATA_DIR,
    DB_PATH,
    PLANNER_TEMPLATE_FILE,
    EXTRANET_LOGIN_URL,
    EXTRANET_DEFAULT_USER,
    EXTRANET_DEFAULT_PASS,
)
from src.db import (
    init_db,
    seed_anagrafica_if_empty,
    get_stores_df,
    get_all_runs,
    get_run_details,
    update_store_record,
    add_store_record,
    delete_store_record,
    delete_run,
    delete_runs,
    clear_all_runs,
    bulk_update_stores,
    update_giro_driver,
    get_giro_summary,
    get_store_latest_planned_data,
)
from src.parsers import classify_uploaded_files
from src.engine import evaluate_pedane, compute_planning_roma
from src.pipeline import run_pipeline
from src.bolle_manager import (
    init_bolle_tables,
    get_bolle_dates,
    get_all_drivers,
    get_all_carriers,
    get_store_delivery_profile,
    get_bolle,
    get_bolla_by_id,
    save_or_update_bolla,
    delete_bolla,
    delete_bolle_by_date,
    generate_bolle_from_forecast,
    get_actuals_for_planner,
    render_bolla_printable_html,
    format_intershops_string,
)
from src.exporters import export_planner_roma
from src.scraper import InditexExtranetScraper
from src.utils import get_cycle_date_range, format_number_it, format_date_it
from src.components import render_lavorazioni_piattaforma

# ==============================================================================
# CONFIGURAZIONE PAGINA & STILE
# ==============================================================================
st.set_page_config(
    page_title="Zara Logistics Hub",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header {
        font-size: 25px;
        font-weight: 700;
        color: #1F497D;
        margin-bottom: 2px;
    }
    .sub-header {
        font-size: 14px;
        color: #595959;
        margin-bottom: 16px;
    }
    .quick-bar {
        background-color: #F4F7FB;
        border: 1px solid #D6E0F0;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def _initialize_system_once():
    """Esegue l'inizializzazione del DB una sola volta all'avvio del server."""
    init_db()
    init_bolle_tables()
    seed_anagrafica_if_empty()
    return True

_initialize_system_once()

# ==============================================================================
# SISTEMA DI LOGIN SEMPLICE (ADMIN vs SOLA VISUALIZZAZIONE)
# ==============================================================================
def _get_auth_users() -> dict:
    """
    Restituisce la mappa degli utenti abilitati e il rispettivo ruolo:
    - 'admin': accesso operativo completo (lettura e modifica)
    - 'viewer': accesso di sola consultazione (visualizzazione dati)
    Personalizzabile tramite Streamlit Secrets (sezione [users]) o variabili d'ambiente.
    """
    import os
    admin_pwd = os.getenv("ZARA_ADMIN_PASS", "zara2026")
    viewer_pwd = os.getenv("ZARA_VIEWER_PASS", "ospite2026")
    try:
        if hasattr(st, "secrets") and "ZARA_ADMIN_PASS" in st.secrets:
            admin_pwd = str(st.secrets["ZARA_ADMIN_PASS"])
        if hasattr(st, "secrets") and "ZARA_VIEWER_PASS" in st.secrets:
            viewer_pwd = str(st.secrets["ZARA_VIEWER_PASS"])
    except Exception:
        pass

    return {
        "admin": {"password": admin_pwd, "role": "admin", "label": "Amministratore (Operativo)"},
        "luciano": {"password": admin_pwd, "role": "admin", "label": "Luciano (Amministratore)"},
        "ospite": {"password": viewer_pwd, "role": "viewer", "label": "Ospite (Sola Visualizzazione)"},
        "visualizzatore": {"password": viewer_pwd, "role": "viewer", "label": "Consultazione (Sola Lettura)"},
    }


if not st.session_state.get("authenticated", False):
    c_l1, c_l2, c_l3 = st.columns([1.2, 1.6, 1.2])
    with c_l2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown('<div class="main-header" style="text-align:center;">🔐 Zara Logistics Hub</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-header" style="text-align:center;">Piattaforma Logistica Monterotondo — Accesso Riservato</div>', unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            inp_user = st.text_input("👤 Utente", placeholder="es. admin oppure ospite").strip().lower()
            inp_pass = st.text_input("🔑 Password", type="password", placeholder="Inserisci password").strip()
            btn_login = st.form_submit_button("ACCEDI ALLA PIATTAFORMA", type="primary", use_container_width=True)
            if btn_login:
                users_map = _get_auth_users()
                if inp_user in users_map and inp_pass == users_map[inp_user]["password"]:
                    st.session_state["authenticated"] = True
                    st.session_state["auth_user"] = inp_user
                    st.session_state["auth_role"] = users_map[inp_user]["role"]
                    st.session_state["auth_label"] = users_map[inp_user]["label"]
                    st.rerun()
                else:
                    st.error("❌ Credenziali non valide. Riprova.")
    st.stop()

USER_ROLE = st.session_state.get("auth_role", "viewer")
IS_ADMIN = USER_ROLE == "admin"

# ==============================================================================
# SIDEBAR: NAVIGAZIONE & STATO OPERATIVO
# ==============================================================================
st.sidebar.markdown("## 🚚 Zara Logistics Hub")
st.sidebar.caption("Gestione Previsioni, Flussi SGA, Bolle & Consuntivo Inditex")

if IS_ADMIN:
    st.sidebar.success(f"👤 **{st.session_state.get('auth_label', 'Admin')}**")
else:
    st.sidebar.info(f"👁️ **{st.session_state.get('auth_label', 'Sola Lettura')}**")

if st.sidebar.button("🚪 Esci (Logout)", use_container_width=True):
    for k in ["authenticated", "auth_user", "auth_role", "auth_label"]:
        st.session_state.pop(k, None)
    st.rerun()

if IS_ADMIN:
    MENU_OPTIONS = [
        "📥 1. Previsione & Arrivi",
        "🚚 2. Bolle di Consegna",
        "📊 3. Consuntivo & Planner Inditex",
        "🏢 4. Anagrafica Negozi & Giri",
        "🗄️ 5. Storico & Backup Cloud",
    ]
else:
    MENU_OPTIONS = [
        "📥 1. Previsione & Arrivi",
        "🚚 2. Bolle di Consegna",
        "📊 3. Consuntivo & Planner Inditex",
    ]

if "nav_menu" not in st.session_state or st.session_state["nav_menu"] not in MENU_OPTIONS:
    st.session_state["nav_menu"] = MENU_OPTIONS[0]

menu = st.sidebar.radio(
    "Flusso Operativo",
    MENU_OPTIONS,
    index=MENU_OPTIONS.index(st.session_state["nav_menu"]),
    key="sidebar_nav_radio",
)
st.session_state["nav_menu"] = menu

# Riepilogo sintetico in Sidebar
st.sidebar.markdown("---")
df_stores_side = get_stores_df()
runs_side = get_all_runs()
active_stores_cnt = int((df_stores_side["attivo"].fillna("SI").str.upper() == "SI").sum()) if not df_stores_side.empty else 0
sdopp_stores_cnt = int((df_stores_side["sdoppiamento_b9"].fillna("NO").str.upper() == "SI").sum()) if not df_stores_side.empty else 0

total_bolle_db = 0
try:
    with sqlite3.connect(DB_PATH) as c_b:
        total_bolle_db = c_b.cursor().execute("SELECT COUNT(*) FROM bolle").fetchone()[0]
except Exception:
    pass

st.sidebar.markdown("##### 📌 Riepilogo Rapido")
st.sidebar.write(f"🏢 Negozi Attivi: **{active_stores_cnt}** (Sdopp. /9: **{sdopp_stores_cnt}**)")
if not runs_side.empty:
    last_r = runs_side.iloc[0]
    st.sidebar.write(f"📦 Ultima Run: **#{int(last_r['id'])}** ({format_date_it(last_r['run_date'])})")
else:
    st.sidebar.write("📦 Ultima Run: *Nessuna*")
st.sidebar.write(f"📋 Bolle in Archivio: **{format_number_it(total_bolle_db, 0)}**")
if get_cloud_url():
    st.sidebar.success("☁️ Google Sheets Sync: **ATTIVO**")
else:
    st.sidebar.caption("☁️ Google Sheets Sync: *Non collegato*")


# ==============================================================================
# PAGE 1: PREVISIONE & ARRIVI (IMPORT + SPUNTA + SGA + LAVORAZIONI)
# ==============================================================================
if menu == "📥 1. Previsione & Arrivi":
    st.markdown('<div class="main-header">📥 Previsione Arrivi, Spunta & Flussi SGA</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Carica i file previsionali da qualsiasi dispositivo (o scaricali da Extranet), calcola pedane e lavorazioni, ed emetti le bolle in 1 clic.</div>', unsafe_allow_html=True)

    # 1. Parametri Ciclo
    col_meta1, col_meta2, col_meta3 = st.columns([1.2, 2, 1.8])
    with col_meta1:
        run_date = st.date_input("📅 Data Riferimento", value=date.today(), format="DD/MM/YYYY")
    with col_meta2:
        default_idx = 0 if run_date.weekday() <= 2 else 1
        cycle_choice = st.selectbox(
            "🔄 Ciclo Settimanale Operativo",
            [
                "LUN-MER (Consegna Mercoledì — Spedizioni da Lunedì a Mercoledì)",
                "GIOV-DOM (Consegna Sabato — Spedizioni da Giovedì a Domenica)",
            ],
            index=default_idx,
        )
        cycle_type = "LUN-MER" if "LUN-MER" in cycle_choice else "GIOV-DOM"
    with col_meta3:
        notes = st.text_input("📝 Note / Riferimento", value=f"Elaborazione W{run_date.isocalendar()[1]} ({cycle_type})")

    cycle_desde, cycle_hasta = get_cycle_date_range(cycle_type, run_date)

    # 2. Scorporo Profumi SEMPRE VISIBILE (letto dinamicamente dai negozi con Scorporo Profumi = 'SI' in Anagrafica)
    df_all_stores = get_stores_df()
    if "scorporo_profumi" in df_all_stores.columns:
        df_prof_stores = df_all_stores[df_all_stores["scorporo_profumi"].fillna("NO").astype(str).str.upper() == "SI"].copy()
    else:
        df_prof_stores = df_all_stores[df_all_stores["store_id"].isin(["3680", "9226", "3591"])].copy()

    st.markdown('<div class="quick-bar">', unsafe_allow_html=True)
    st.markdown("##### 🧴 Scorporo Profumi (Negozi Abilitati in Anagrafica)")
    st.caption("Pezzi di profumi da scorporare dai capi piegati per il calcolo netto dei bancali (PLT) e dei capi lavorati. Puoi abilitare/disabilitare i negozi dall'Anagrafica Negozi:")

    perfume_corrections = {}
    if not df_prof_stores.empty:
        prof_cols = st.columns(min(len(df_prof_stores), 4))
        for idx_p, (_, prow) in enumerate(df_prof_stores.iterrows()):
            p_sid = str(prow["store_id"]).strip()
            p_sname = str(prow.get("store_name", "")).strip()
            default_pz = int(float(prow.get("pezzi_profumi", 0) or 0))
            with prof_cols[idx_p % len(prof_cols)]:
                val_pz = st.number_input(
                    f"Negozio {p_sid} ({p_sname}) — Pezzi Profumi",
                    value=default_pz,
                    min_value=0,
                    step=1,
                    key=f"perfume_{p_sid}",
                )
                perfume_corrections[p_sid] = float(val_pz)
    else:
        st.info("Nessun negozio ha l'opzione 'Scorporo Profumi = SI' attiva in Anagrafica Negozi.")
    st.markdown('</div>', unsafe_allow_html=True)

    # 3. Sorgente Dati: Default = Prelievo Automatico da Extranet | Secondario = Caricamento Manuale (Emergenza)
    tab_src_extranet, tab_src_upload = st.tabs([
        "🌐 Prelievo Automatico da Extranet Inditex (Default)",
        "📤 Caricamento Manuale File (Emergenza)",
    ])

    with tab_src_extranet:
        st.caption(
            f"In base alla **Data Riferimento ({format_date_it(run_date)})** e al ciclo **{cycle_type}**, "
            f"il sistema ricerca automaticamente su Extranet le spedizioni della settimana dal **{format_date_it(cycle_desde)}** al **{format_date_it(cycle_hasta)}** (modificabili qui sotto se necessario):"
        )
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            sc_desde = st.date_input("📅 Spedizioni Dal (Inizio)", value=cycle_desde, format="DD/MM/YYYY", key=f"sc_d_{cycle_type}_{run_date}")
        with col_ex2:
            sc_hasta = st.date_input("📅 Spedizioni Al (Fine)", value=cycle_hasta, format="DD/MM/YYYY", key=f"sc_h_{cycle_type}_{run_date}")

        ex_user, ex_pass = get_extranet_credentials()

        if st.button("🌐 SCARICA DA EXTRANET ED ELABORA", type="primary", use_container_width=True, key="btn_ask_scrape"):
            st.session_state["confirm_perfume_mode"] = "extranet"

        if st.session_state.get("confirm_perfume_mode") == "extranet":
            prof_summary_str = " | ".join([f"**{k}** = `{int(v)}` pz" for k, v in perfume_corrections.items()]) or "Nessuno"
            st.warning(
                f"🧴 **Hai aggiornato correttamente i profumi?**\n\n"
                f"Valori impostati: {prof_summary_str}"
            )
            c_cf1, c_cf2 = st.columns(2)
            with c_cf1:
                confirm_extranet_go = st.button("✅ SÌ, HO AGGIORNATO I PROFUMI — AVVIA ESTRAZIONE ED ELABORAZIONE", type="primary", use_container_width=True, key="btn_go_extranet_confirmed")
            with c_cf2:
                if st.button("✏️ No, annulla e modifica i profumi sopra", use_container_width=True, key="btn_cancel_extranet_confirm"):
                    st.session_state.pop("confirm_perfume_mode", None)
                    st.rerun()

            if confirm_extranet_go:
                st.session_state.pop("confirm_perfume_mode", None)
                # Salva i valori aggiornati dei profumi direttamente in Anagrafica Negozi
                for p_sid, p_val in perfume_corrections.items():
                    update_store_record(p_sid, {"pezzi_profumi": int(p_val)})
                st.toast("✅ Hai aggiornato correttamente i profumi in anagrafica!", icon="🧴")

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_extract_dir = DATA_DIR / "downloads" / f"extranet_{ts}"
                temp_extract_dir.mkdir(parents=True, exist_ok=True)

                prog_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(msg: str, pct: int):
                    prog_bar.progress(pct)
                    status_text.write(f"🔄 **{pct}%** - {msg}")

                try:
                    scraper = InditexExtranetScraper(
                        username=ex_user,
                        password=ex_pass,
                        headless=True,
                        progress_callback=update_progress,
                    )
                    scrape_res = scraper.scrape_all(
                        desde_date=sc_desde,
                        hasta_date=sc_hasta,
                        output_dir=temp_extract_dir,
                    )
                    update_progress("Elaborazione Spunta Arrivi e Flussi SGA...", 95)
                    res = run_pipeline(
                        total_source=temp_extract_dir / "TOTAL.xls",
                        shoes_source=(temp_extract_dir / "SHOES.xls") if (temp_extract_dir / "SHOES.xls").exists() else None,
                        texile_source=(temp_extract_dir / "TEXILE.xls") if (temp_extract_dir / "TEXILE.xls").exists() else None,
                        ecom_source=(temp_extract_dir / "ECOM.xls") if (temp_extract_dir / "ECOM.xls").exists() else None,
                        other_source=(temp_extract_dir / "OTHER"),
                        esportazione_source=None,
                        run_date=str(run_date),
                        cycle_type=cycle_type,
                        notes=f"{notes} [Extranet {format_date_it(sc_desde)}-{format_date_it(sc_hasta)}]",
                        perfume_corrections=perfume_corrections,
                        save_to_network=False,
                    )
                    prog_bar.progress(100)
                    status_text.write("✅ **100%** - Estrazione ed elaborazione completate!")
                    st.session_state["last_run"] = res
                    st.success("🧴 Hai aggiornato correttamente i profumi!")
                    st.success(f"🎉 Elaborazione completata! Run ID: **#{res['run_id']}**")
                except Exception as e:
                    st.error(f"Errore durante l'estrazione da Extranet: {e}")

    with tab_src_upload:
        st.caption("Modalità di emergenza: seleziona o trascina qui **tutti insieme** i file scaricati manualmente (`TOTAL`, `SHOES`, `TEXILE`, `ECOM` ed eventuali file di dettaglio `OTHER`, oppure un file `.zip`). Il sistema li riconosce e smista in automatico:")
        uploaded_batch = st.file_uploader(
            "Trascina qui tutti i file (.xls, .xlsx, .csv, .zip)",
            type=["xls", "xlsx", "csv", "zip"],
            accept_multiple_files=True,
            key="smart_batch_uploader",
        )

        classified = classify_uploaded_files(uploaded_batch) if uploaded_batch else None
        if classified:
            s_info = classified["summary"]
            c_s1, c_s2, c_s3, c_s4, c_s5 = st.columns(5)
            c_s1.success(f"TOTALE: {s_info['total']}") if s_info["total"] else c_s1.warning("TOTALE: Non caricato")
            c_s2.success(f"CALZATURE: {s_info['shoes']}") if s_info["shoes"] else c_s2.info("CALZATURE: Assente (0)")
            c_s3.success(f"TESSILE: {s_info['texile']}") if s_info["texile"] else c_s3.info("TESSILE: Assente (0)")
            c_s4.success(f"E-COMMERCE: {s_info['ecom']}") if s_info["ecom"] else c_s4.info("E-COMMERCE: Assente (0)")
            c_s5.success(f"ALTRI (OTHER): {s_info['other_count']} file") if s_info["other_count"] > 0 else c_s5.info("ALTRI (OTHER): 0 file")

        if st.button("🚀 ELABORA FILE CARICATI", type="primary", use_container_width=True, disabled=not bool(classified and (classified["total"] or classified["texile"])), key="btn_ask_upload"):
            st.session_state["confirm_perfume_mode"] = "upload"

        if st.session_state.get("confirm_perfume_mode") == "upload":
            prof_summary_str = " | ".join([f"**{k}** = `{int(v)}` pz" for k, v in perfume_corrections.items()]) or "Nessuno"
            st.warning(
                f"🧴 **Hai aggiornato correttamente i profumi?**\n\n"
                f"Valori impostati: {prof_summary_str}"
            )
            c_cu1, c_cu2 = st.columns(2)
            with c_cu1:
                confirm_upload_go = st.button("✅ SÌ, HO AGGIORNATO I PROFUMI — AVVIA ELABORAZIONE", type="primary", use_container_width=True, key="btn_go_upload_confirmed")
            with c_cu2:
                if st.button("✏️ No, annulla e modifica i profumi sopra", use_container_width=True, key="btn_cancel_upload_confirm"):
                    st.session_state.pop("confirm_perfume_mode", None)
                    st.rerun()

            if confirm_upload_go:
                st.session_state.pop("confirm_perfume_mode", None)
                for p_sid, p_val in perfume_corrections.items():
                    update_store_record(p_sid, {"pezzi_profumi": int(p_val)})
                st.success("🧴 Hai aggiornato correttamente i profumi!")
                with st.spinner("Calcolo Spunta Arrivi, suddivisione Sdoppiamenti /0-/9 e salvataggio storico..."):
                    try:
                        res = run_pipeline(
                            total_source=classified["total"],
                            shoes_source=classified["shoes"],
                            texile_source=classified["texile"],
                            ecom_source=classified["ecom"],
                            other_source=classified["other"],
                            esportazione_source=None,
                            run_date=str(run_date),
                            cycle_type=cycle_type,
                            notes=notes,
                            perfume_corrections=perfume_corrections,
                            save_to_network=False,
                        )
                        st.session_state["last_run"] = res
                        st.success(f"✅ Elaborazione completata! Run registrata: **#{res['run_id']}**")
                    except Exception as e:
                        st.error(f"Errore durante l'elaborazione: {e}")

    # 3. Visualizzazione Risultati (mostra la run appena eseguita oppure l'ultima disponibile nel DB)
    active_run_data = st.session_state.get("last_run")
    if not active_run_data and not runs_side.empty:
        latest_id = int(runs_side.iloc[0]["id"])
        det = get_run_details(latest_id)
        if det and det.get("run"):
            r_info = det["run"]
            active_run_data = {
                "run_id": latest_id,
                "run_date": r_info.get("run_date", ""),
                "cycle_type": r_info.get("cycle_type", ""),
                "totals": {
                    "total_bultos": r_info.get("total_bultos", 0),
                    "total_volume": r_info.get("total_volume", 0),
                    "total_weight": r_info.get("total_weight", 0),
                    "total_pedane": r_info.get("total_pedane", 0),
                },
                "df_analisi": det.get("planning", pd.DataFrame()),
                "df_spunta": det.get("spunta", pd.DataFrame()),
                "special_breakdowns": det.get("special_breakdowns", {}),
                "exported_files": {
                    "zara": OUTPUT_DIR / "ZARA.xlsx",
                    "sga0": OUTPUT_DIR / "barrazero_Sga.xlsx",
                    "sga9": OUTPUT_DIR / "barranove_Sga.xlsx",
                    "planner": OUTPUT_DIR / "Planning ITX_RM.xlsx",
                },
                "new_stores_alert": [],
            }

    if active_run_data:
        curr_rid = active_run_data["run_id"]
        totals = active_run_data["totals"]

        # Alert nuovi punti vendita inseriti automaticamente
        new_stores = active_run_data.get("new_stores_alert", [])
        if new_stores:
            st.warning(f"⚠️ **Rilevati {len(new_stores)} nuovi punti vendita non presenti in anagrafica (inseriti automaticamente):**")
            for ns in new_stores:
                st.markdown(
                    f"- Negozio **{ns['store_id']}** (`{ns['store_name']}`) | Brand: **{ns['brand']}** | "
                    f"Colli: **{format_number_it(ns['bultos'], 0)}** | Volume: **{format_number_it(ns['volumen'], 2)} m³** "
                    f"→ Censito con stato `ATTIVO` e giro `DA ASSEGNARE`."
                )

        st.markdown("---")
        col_hdr_l, col_hdr_r = st.columns([3, 2])
        with col_hdr_l:
            st.markdown(f"### 📊 Riepilogo Previsione Attiva — Run #{curr_rid}")
        with col_hdr_r:
            if st.button("⚡ GENERA BOLLE DI CONSEGNA E VAI ALLE BOLLE 🚚", type="primary", use_container_width=True, key="btn_top_gen_bolle"):
                n_c, n_s = generate_bolle_from_forecast(curr_rid)
                st.session_state["flash_bolle_msg"] = f"✅ Generate {n_c} bolle dalla Run #{curr_rid} ({n_s} già presenti mantenute)."
                st.session_state["nav_menu"] = "🚚 2. Bolle di Consegna"
                st.rerun()

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Totale Colli", format_number_it(totals["total_bultos"], 0))
        kpi2.metric("Volume Complessivo", format_number_it(totals["total_volume"], 2) + " m³")
        kpi3.metric("Peso Complessivo", format_number_it(totals["total_weight"], 0) + " kg")
        kpi4.metric("Pedane Stimate", format_number_it(totals["total_pedane"], 0))

        # Pulsanti Download File Generati
        exp_files = active_run_data.get("exported_files", {})
        if exp_files:
            col_d1, col_d2, col_d3, col_d4 = st.columns(4)
            labels_map = {
                "zara": ("📄 Scarica Spunta (ZARA.xlsx)", col_d1),
                "sga0": ("🚛 Scarica SGA Barra 0 (.xlsx)", col_d2),
                "sga9": ("🚚 Scarica SGA Barra 9 (.xlsx)", col_d3),
                "planner": ("📅 Scarica Planner Roma (.xlsx)", col_d4),
            }
            for k, (lbl, col_obj) in labels_map.items():
                p = exp_files.get(k)
                if p and Path(p).exists():
                    with col_obj:
                        with open(p, "rb") as f:
                            st.download_button(
                                lbl,
                                data=f.read(),
                                file_name=Path(p).name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key=f"dl_{k}_{curr_rid}",
                            )

        tab_spunta, tab_lav, tab_prev = st.tabs([
            "📋 Spunta Arrivi & Pedane per Giro",
            "🏭 Lavorazioni Piattaforma (Tessile 3680/9226/3591 & Home)",
            "📊 Tabella Previsioni per Punto Vendita",
        ])

        with tab_spunta:
            df_sp_view = active_run_data.get("df_spunta", pd.DataFrame())
            if not df_sp_view.empty:
                st.caption("Include la divisione automatica dei volumi 70% (Barra 0) e 30% (Barra 9 'B') per i negozi con Sdoppiamento attivo:")
                cols_sp = [c for c in ["store_code", "store_name", "brand", "giro", "mc", "textile_attesi", "shoes_attesi", "other_attesi", "ecom_attesi", "pedane", "totale_pedane", "is_barra9"] if c in df_sp_view.columns]
                st.dataframe(df_sp_view[cols_sp], use_container_width=True, height=480)
            else:
                st.info("Nessun dato di spunta disponibile.")

        with tab_lav:
            render_lavorazioni_piattaforma(active_run_data.get("special_breakdowns", {}), key_prefix=f"p1_{curr_rid}")

        with tab_prev:
            df_an_view = active_run_data.get("df_analisi", pd.DataFrame())
            if not df_an_view.empty:
                st.dataframe(df_an_view, use_container_width=True, height=450)


# ==============================================================================
# PAGE 2: BOLLE DI CONSEGNA (ELENCO, STAMPA PER GIRO/AUTISTA, COMPILAZIONE)
# ==============================================================================
elif menu == "🚚 2. Bolle di Consegna":
    st.markdown('<div class="main-header">🚚 Gestione Bolle di Consegna</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Generazione automatica da previsione, stampa distinte per Giro/Autista e compilazione rapida con controllo Sdoppiamento (/0 STD e /9 DOPPIA).</div>', unsafe_allow_html=True)

    if "flash_bolle_msg" in st.session_state:
        st.success(st.session_state.pop("flash_bolle_msg"))

    # Barra Superiore Rapida: Selezione Data + Generazione 1-Clic da Previsione
    all_dates = get_bolle_dates(120)
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    if not all_dates:
        all_dates = [tomorrow_str]

    date_labels = [f"{format_date_it(d)} ({d})" for d in all_dates]

    col_top1, col_top2, col_top3 = st.columns([2, 2.2, 1.8])
    with col_top1:
        sel_date_idx = st.selectbox(
            "📅 Data di Consegna Attiva",
            range(len(all_dates)),
            format_func=lambda i: date_labels[i],
            key="bolle_tab1_date_sel",
        )
        target_date = all_dates[sel_date_idx]

    with col_top2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        qb1, qb2, qb3 = st.columns(3)
        with qb1:
            if st.button("📅 Oggi", use_container_width=True, key="b_q_tod"):
                if today_str not in all_dates:
                    all_dates.insert(0, today_str)
                st.session_state["bolle_tab1_date_sel"] = all_dates.index(today_str)
                st.rerun()
        with qb2:
            if st.button("📅 Domani", use_container_width=True, key="b_q_tom"):
                if tomorrow_str not in all_dates:
                    all_dates.insert(0, tomorrow_str)
                st.session_state["bolle_tab1_date_sel"] = all_dates.index(tomorrow_str)
                st.rerun()
        with qb3:
            if st.button("📅 Ultima", use_container_width=True, key="b_q_lat"):
                st.session_state["bolle_tab1_date_sel"] = 0
                st.rerun()

    with col_top3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        with st.popover("⚡ Genera Bolle da Previsione", use_container_width=True):
            if runs_side.empty:
                st.warning("Nessuna previsione salvata nello storico.")
            else:
                run_opts = {
                    int(r["id"]): f"Run #{int(r['id'])} ({format_date_it(r['run_date'])}, {r['cycle_type']}) - {format_number_it(r['total_bultos'], 0)} colli"
                    for _, r in runs_side.head(20).iterrows()
                }
                sel_gen_run = st.selectbox("Previsione (Run)", list(run_opts.keys()), format_func=lambda x: run_opts[x], key="pop_gen_run")
                sel_gen_dt = st.date_input("Data Consegna Bolle", value=date.today() + timedelta(days=1), format="DD/MM/YYYY", key="pop_gen_dt")
                ovw_gen = st.checkbox("Sovrascrivi bolle esistenti della data", value=False, key="pop_gen_ovw")
                if st.button("🚀 Genera Tutte le Bolle Ora", type="primary", use_container_width=True, key="btn_exec_gen_bolle"):
                    c_cnt, s_cnt = generate_bolle_from_forecast(sel_gen_run, delivery_date=str(sel_gen_dt), overwrite=ovw_gen)
                    st.session_state["flash_bolle_msg"] = f"🎉 Generate **{c_cnt}** bolle per il **{format_date_it(sel_gen_dt)}** ({s_cnt} già esistenti)."
                    st.rerun()

    tab_b_list, tab_b_form = st.tabs([
        "📋 Elenco, Filtri Giro/Autista & Stampa",
        "✏️ Compila / Modifica Singola Bolla",
    ])

    # --------------------------------------------------------------------------
    # SOTTO-SCHEDA 1: ELENCO, FILTRI & STAMPA
    # --------------------------------------------------------------------------
    with tab_b_list:
        store_giro_map = {}
        all_giri_list = []
        if not df_stores_side.empty:
            store_giro_map = df_stores_side.set_index("store_id")["giro"].fillna("").to_dict()
            all_giri_list = sorted([g for g in df_stores_side["giro"].dropna().unique() if str(g).strip()])

        f_c1, f_c2, f_c3, f_c4, f_c5 = st.columns([1.2, 1.5, 1.2, 1.2, 1.8])
        with f_c1:
            f_giro = st.selectbox("Filtra Giro", ["TUTTI"] + all_giri_list, key="bolle_f_giro")
        with f_c2:
            f_driver = st.selectbox("Filtra Autista", ["TUTTI"] + get_all_drivers(), key="bolle_f_driver")
        with f_c3:
            f_tipo = st.selectbox("Tipo Consegna", ["TUTTI", "STD", "DOPPIA"], key="bolle_f_tipo")
        with f_c4:
            f_carrier = st.selectbox("Filtra Vettore", ["TUTTI"] + get_all_carriers(), key="bolle_f_carrier")
        with f_c5:
            f_search = st.text_input("🔍 Cerca Store ID o Nome", "", key="bolle_f_search")

        df_bolle = get_bolle(
            data=target_date,
            vettore=f_carrier if f_carrier != "TUTTI" else None,
            autista=f_driver if f_driver != "TUTTI" else None,
            tipo_cons=f_tipo if f_tipo != "TUTTI" else None,
            search=f_search if f_search else None,
        )

        if not df_bolle.empty:
            df_bolle["giro"] = df_bolle["id_store"].astype(str).map(lambda s: store_giro_map.get(s, ""))
            if f_giro != "TUTTI":
                df_bolle = df_bolle[df_bolle["giro"] == f_giro].copy()

        # Metriche rapide sulla selezione
        tot_colli_b = (
            df_bolle["colli_abbigl"] + df_bolle["colli_calzat"] +
            df_bolle["colli_ecom"] + df_bolle["colli_others"] + df_bolle["colli_vario"]
        ).sum() if not df_bolle.empty else 0

        mk1, mk2, mk3, mk4, mk5 = st.columns(5)
        mk1.metric("Bolle Visualizzate", len(df_bolle))
        mk2.metric("Colli Totali", format_number_it(tot_colli_b, 0))
        mk3.metric("Abbigliamento", format_number_it(df_bolle["colli_abbigl"].sum() if not df_bolle.empty else 0, 0))
        mk4.metric("Calzature", format_number_it(df_bolle["colli_calzat"].sum() if not df_bolle.empty else 0, 0))
        mk5.metric("Altri + E-Com", format_number_it((df_bolle["colli_others"].sum() + df_bolle["colli_ecom"].sum()) if not df_bolle.empty else 0, 0))

        # Barra Pulsanti Stampa & Export
        b_act1, b_act2, b_act3, b_act4, b_act5 = st.columns(5)
        with b_act1:
            if st.button("🖨️ Stampa STD (/0)", type="primary", use_container_width=True):
                df_std = df_bolle[df_bolle["tipo_cons"] == "STD"] if not df_bolle.empty else pd.DataFrame()
                if not df_std.empty:
                    st.session_state["print_html"] = render_bolla_printable_html(df_std.to_dict(orient="records"), title=f"Bolle STD - {format_date_it(target_date)}")
                    st.session_state["print_title"] = f"Bolle_STD_{target_date}"
                else:
                    st.warning("Nessuna bolla STD nella selezione.")
        with b_act2:
            if st.button("🖨️ Stampa DOPPIA (/9)", use_container_width=True):
                df_dop = df_bolle[df_bolle["tipo_cons"] == "DOPPIA"] if not df_bolle.empty else pd.DataFrame()
                if not df_dop.empty:
                    st.session_state["print_html"] = render_bolla_printable_html(df_dop.to_dict(orient="records"), title=f"Bolle DOPPIA (/9) - {format_date_it(target_date)}")
                    st.session_state["print_title"] = f"Bolle_DOPPIA_{target_date}"
                else:
                    st.warning("Nessuna bolla DOPPIA nella selezione.")
        with b_act3:
            is_filt = (f_giro != "TUTTI" or f_driver != "TUTTI" or f_tipo != "TUTTI" or f_carrier != "TUTTI" or bool(f_search))
            lbl_print = f"🖨️ Stampa Selezione ({len(df_bolle)})" if is_filt else f"🖨️ Stampa Tutte ({len(df_bolle)})"
            if st.button(lbl_print, use_container_width=True):
                if not df_bolle.empty:
                    st.session_state["print_html"] = render_bolla_printable_html(df_bolle.to_dict(orient="records"), title=f"Bolle Consegna - {format_date_it(target_date)}")
                    st.session_state["print_title"] = f"Bolle_{target_date}"
                else:
                    st.warning("Nessuna bolla da stampare.")
        with b_act4:
            if not df_bolle.empty:
                b_buf = io.BytesIO()
                with pd.ExcelWriter(b_buf, engine="openpyxl") as b_writer:
                    df_bolle.to_excel(b_writer, index=False, sheet_name="Bolle")
                b_buf.seek(0)
                st.download_button(
                    "📥 Esporta Excel",
                    data=b_buf.read(),
                    file_name=f"Riepilogo_Bolle_{target_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                st.button("📥 Esporta Excel", disabled=True, use_container_width=True)
        with b_act5:
            with st.popover("🗑️ Svota Bolle Data", use_container_width=True):
                st.warning(f"Eliminare tutte le bolle del **{format_date_it(target_date)}**?")
                if st.button("Conferma Eliminazione", type="primary", use_container_width=True, key="btn_del_bolle_dt"):
                    n_d = delete_bolle_by_date(target_date)
                    st.success(f"Eliminate {n_d} bolle.")
                    st.rerun()

        # Pannello di Stampa se attivo
        if "print_html" in st.session_state:
            with st.expander("🖨️ Documento Pronto per la Stampa (Clicca per stampare o scaricare)", expanded=True):
                cp1, cp2, cp3 = st.columns([2, 2, 1])
                with cp1:
                    st.download_button(
                        "💾 Scarica File Stampa (.html)",
                        data=st.session_state["print_html"].encode("utf-8"),
                        file_name=f"{st.session_state.get('print_title', 'Bolle')}.html",
                        mime="text/html",
                        type="primary",
                        use_container_width=True,
                    )
                with cp2:
                    if st.button("❌ Chiudi Anteprima Stampa", use_container_width=True):
                        del st.session_state["print_html"]
                        st.rerun()
                st.components.v1.html(st.session_state["print_html"], height=520, scrolling=True)

        # Tabella Bolle
        if df_bolle.empty:
            st.info(f"Nessuna bolla presente per il **{format_date_it(target_date)}**. Clicca su **⚡ Genera Bolle da Previsione** in alto a destra per crearle in automatico!")
        else:
            df_b_disp = df_bolle.copy()
            df_b_disp["TOT_COLLI"] = (
                df_b_disp["colli_abbigl"] + df_b_disp["colli_calzat"] +
                df_b_disp["colli_ecom"] + df_b_disp["colli_others"] + df_b_disp["colli_vario"]
            )
            cols_show = [
                "id", "giro", "id_store", "punto_vendita", "store_name", "tipo_cons",
                "TOT_COLLI", "colli_abbigl", "colli_calzat", "colli_others", "colli_ecom",
                "autista", "tipo_mezzo", "stringa"
            ]
            st.dataframe(df_b_disp[[c for c in cols_show if c in df_b_disp.columns]], use_container_width=True, height=420)

    # --------------------------------------------------------------------------
    # SOTTO-SCHEDA 2: COMPILA O MODIFICA SINGOLA BOLLA
    # --------------------------------------------------------------------------
    with tab_b_form:
        mode_bolla = st.radio(
            "Modalità Operativa",
            ["➕ Compila Nuova Bolla", "✏️ Modifica Bolla Esistente"],
            horizontal=True,
            key="bolle_edit_mode",
        )

        store_choices = [f"{r['store_id']} - {r['store_name']} ({r['brand']}) [{r['giro']}]" for _, r in df_stores_side.iterrows()] if not df_stores_side.empty else []

        bolla_to_edit = {}
        if "Modifica" in mode_bolla:
            recent_bolle = get_bolle(data=target_date)
            if recent_bolle.empty:
                recent_bolle = get_bolle()
            if recent_bolle.empty:
                st.warning("Nessuna bolla in archivio da modificare.")
            else:
                b_edit_opts = {
                    int(r["id"]): f"Bolla #{int(r['id'])} ({format_date_it(r['data_consegna'] or r['data'])}) - Store {r['id_store']} ({r['store_name']}) [{r['tipo_cons']}]"
                    for _, r in recent_bolle.head(150).iterrows()
                }
                sel_edit_id = st.selectbox(
                    "Seleziona Bolla da Modificare",
                    list(b_edit_opts.keys()),
                    format_func=lambda bid: b_edit_opts[bid],
                    key="sel_edit_bolla_id",
                )
                bolla_to_edit = get_bolla_by_id(sel_edit_id) or {}

        def_sid = str(bolla_to_edit.get("id_store", "3680"))
        def_tipo = str(bolla_to_edit.get("tipo_cons", "STD"))

        col_t1, col_t2, col_t3 = st.columns([2, 1.3, 1.3])
        with col_t1:
            default_store_idx = 0
            for i, opt in enumerate(store_choices):
                if opt.startswith(def_sid + " -"):
                    default_store_idx = i
                    break
            sel_store_str = st.selectbox("Punto Vendita", store_choices, index=default_store_idx if store_choices else 0, key="form_store_sel")
            current_sid = sel_store_str.split(" - ")[0].strip() if sel_store_str else def_sid

        # Verifica flag sdoppiamento_b9 in anagrafica per consentire o bloccare DOPPIA
        is_sdoppia = False
        if not df_stores_side.empty:
            m_row = df_stores_side[df_stores_side["store_id"].astype(str) == current_sid]
            if not m_row.empty:
                is_sdoppia = str(m_row.iloc[0].get("sdoppiamento_b9", "NO")).strip().upper() == "SI"

        tipo_options = ["STD", "DOPPIA"] if is_sdoppia else ["STD"]
        if def_tipo == "DOPPIA" and "DOPPIA" not in tipo_options:
            tipo_options.append("DOPPIA")
        curr_tipo_idx = tipo_options.index(def_tipo) if def_tipo in tipo_options else 0

        with col_t2:
            form_tipo_cons = st.selectbox(
                "Tipologia Consegna",
                tipo_options,
                index=curr_tipo_idx,
                key="form_tipo_cons",
                help="La consegna DOPPIA (/9 'B') è abilitata esclusivamente per i negozi con flag Sdoppiamento = SI in Anagrafica.",
            )
            if is_sdoppia:
                st.caption("✨ Sdoppiamento attivo (/0 STD e /9 'B' DOPPIA)")
            else:
                st.caption("ℹ️ Consegna unica STD (Sdoppiamento = NO)")

        prof = get_store_delivery_profile(current_sid, form_tipo_cons)
        current_cache_key = f"{mode_bolla}_{bolla_to_edit.get('id', 'new')}_{current_sid}_{form_tipo_cons}"
        if st.session_state.get("_last_bolla_form_key") != current_cache_key:
            st.session_state["_last_bolla_form_key"] = current_cache_key
            st.session_state["form_pv"] = bolla_to_edit.get("punto_vendita") or prof.get("punto_vendita") or "ZARA"
            st.session_state["form_vettore"] = bolla_to_edit.get("vettore") or prof.get("vettore") or "LACCHI SPA"
            st.session_state["form_autista"] = bolla_to_edit.get("autista") or prof.get("autista", "")
            st.session_state["form_cell"] = bolla_to_edit.get("cell_autista") or prof.get("cell_autista", "")
            st.session_state["form_mezzo"] = bolla_to_edit.get("tipo_mezzo") or prof.get("tipo_mezzo", "")
            st.session_state["form_indirizzo"] = bolla_to_edit.get("indirizzo_destino") or prof.get("indirizzo", "")
            st.session_state["form_c_abb"] = float(bolla_to_edit.get("colli_abbigl", 0))
            st.session_state["form_c_calz"] = float(bolla_to_edit.get("colli_calzat", 0))
            st.session_state["form_c_eco"] = float(bolla_to_edit.get("colli_ecom", 0))
            st.session_state["form_c_oth"] = float(bolla_to_edit.get("colli_others", 0))
            st.session_state["form_c_var"] = float(bolla_to_edit.get("colli_vario", 0))
            st.session_state["form_c_mat"] = float(bolla_to_edit.get("colli_mat_vario", 0))
            st.session_state["form_c_cont"] = float(bolla_to_edit.get("colli_cont", 0))
            st.session_state["form_c_dann"] = float(bolla_to_edit.get("colli_dann", 0))
            st.session_state["form_c_nonconf"] = float(bolla_to_edit.get("colli_non_conf", 0))

        with col_t3:
            form_pv = st.text_input("Insegna / Brand", key="form_pv")

        col_v1, col_v2, col_v3, col_v4 = st.columns(4)
        with col_v1:
            form_data_carico = st.date_input("Data Spedizione", value=date.today(), format="DD/MM/YYYY", key="form_dt_carico")
        with col_v2:
            form_data_cons = st.date_input("Data Consegna", value=date.today() + timedelta(days=1), format="DD/MM/YYYY", key="form_dt_cons")
        with col_v3:
            form_autista = st.text_input("Autista", key="form_autista")
        with col_v4:
            form_cell = st.text_input("Cellulare Autista", key="form_cell")

        col_m1, col_m2, col_m3 = st.columns([1.2, 1.2, 2.2])
        with col_m1:
            form_mezzo = st.text_input("Mezzo", key="form_mezzo")
        with col_m2:
            form_vettore = st.text_input("Vettore", key="form_vettore")
        with col_m3:
            form_indirizzo = st.text_input("Indirizzo di Destino", key="form_indirizzo")

        st.markdown("---")
        col_q_title, col_q_prefill = st.columns([3, 2])
        with col_q_title:
            st.markdown("##### 📦 Quantità Colli in Uscita")
        with col_q_prefill:
            if st.button("📥 Precompila con Colli Previsti dalla Run", key="btn_prefill_planned", use_container_width=True):
                pl_data = get_store_latest_planned_data(current_sid)
                if pl_data.get("has_data"):
                    sdop_factor = 0.3 if form_tipo_cons == "DOPPIA" else (0.7 if is_sdoppia else 1.0)
                    st.session_state["form_c_abb"] = float(round(pl_data.get("textile", 0.0) * sdop_factor, 1))
                    st.session_state["form_c_calz"] = float(round(pl_data.get("shoes", 0.0) * sdop_factor, 1))
                    st.session_state["form_c_eco"] = float(round(pl_data.get("ecom", 0.0) * sdop_factor, 1))
                    st.session_state["form_c_oth"] = float(round(pl_data.get("others", 0.0) * sdop_factor, 1))
                    st.rerun()
                else:
                    st.warning("Nessun dato previsionale trovato per questo negozio nell'ultima run.")

        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        with col_q1:
            c_abb = st.number_input("Abbigliamento + Profumi", min_value=0.0, step=1.0, key="form_c_abb")
            c_var = st.number_input("Mat. Vario Piattaforma", min_value=0.0, step=1.0, key="form_c_var")
        with col_q2:
            c_calz = st.number_input("Calzature (Shoes)", min_value=0.0, step=1.0, key="form_c_calz")
            c_mat = st.number_input("Mat. Vario", min_value=0.0, step=1.0, key="form_c_mat")
        with col_q3:
            c_oth = st.number_input("Others (Altri Bultos)", min_value=0.0, step=1.0, key="form_c_oth")
            c_cont = st.number_input("Contenitori", min_value=0.0, step=1.0, key="form_c_cont")
        with col_q4:
            c_eco = st.number_input("E-Commerce", min_value=0.0, step=1.0, key="form_c_eco")
            c_dann = st.number_input("Danneggiati", min_value=0.0, step=1.0, key="form_c_dann")
            c_nonconf = st.number_input("Non Conformi", min_value=0.0, step=1.0, key="form_c_nonconf")

        tot_operativa_calc = c_abb + c_calz + c_eco + c_oth + c_var
        st.info(f"📦 **Totale Colli Operativa Consegna: {int(tot_operativa_calc)} colli**")

        with st.expander("🔄 Trasferimenti tra Negozi (Intershops / Stand / Ceste) & Note Scarico", expanded=False):
            inter_rows_data = []
            existing_inter = []
            try:
                if bolla_to_edit.get("intershops_json"):
                    existing_inter = json.loads(bolla_to_edit["intershops_json"])
            except Exception:
                existing_inter = []

            for row_i in range(3):
                cur_item = existing_inter[row_i] if row_i < len(existing_inter) else {}
                ci1, ci2, ci3 = st.columns([1, 1, 2])
                with ci1:
                    m_val = st.text_input(f"Negozio Mittente #{row_i+1}", value=str(cur_item.get("mittente", "")), key=f"inter_m_{row_i}")
                with ci2:
                    c_val = st.number_input(f"Colli #{row_i+1}", min_value=0, value=int(cur_item.get("colli", 0)), step=1, key=f"inter_c_{row_i}")
                with ci3:
                    t_val = st.text_input(f"Tipologia #{row_i+1}", value=str(cur_item.get("tipo", "")), placeholder="es. MERCE, CESTE, STAND", key=f"inter_t_{row_i}")
                if c_val > 0:
                    inter_rows_data.append({"mittente": m_val, "colli": c_val, "tipo": t_val})

            form_stringa_custom = st.text_input("Note / Intershops libere sulla bolla", value=bolla_to_edit.get("stringa", ""), key="form_stringa_custom")
            form_anomalie = st.text_area("Anomalie allo Scarico", value=bolla_to_edit.get("anomalie_scarico", ""), key="form_anomalie")

        col_sv1, col_sv2 = st.columns(2)
        with col_sv1:
            save_clicked = st.button("💾 SALVA BOLLA DI TRASPORTO", type="primary", use_container_width=True, key="btn_save_bolla")
        with col_sv2:
            save_next_clicked = st.button("💾 Salva e Passa al Prossimo Negozio ➡️", use_container_width=True, key="btn_save_next_bolla")

        if save_clicked or save_next_clicked:
            if inter_rows_data:
                computed_stringa = format_intershops_string(inter_rows_data)
                if form_stringa_custom and form_stringa_custom not in computed_stringa:
                    computed_stringa += f" {form_stringa_custom}"
            else:
                computed_stringa = form_stringa_custom

            bolla_save_payload = {
                "id": bolla_to_edit.get("id"),
                "data": str(form_data_carico),
                "data_consegna": str(form_data_cons),
                "id_store": current_sid,
                "punto_vendita": form_pv,
                "store_name": sel_store_str.split(" - ")[1].split(" (")[0] if " - " in sel_store_str else "",
                "tipo_cons": form_tipo_cons,
                "vettore": form_vettore,
                "cell_autista": form_cell,
                "autista": form_autista,
                "tipo_mezzo": form_mezzo,
                "indirizzo_destino": form_indirizzo,
                "colli_abbigl": c_abb,
                "colli_calzat": c_calz,
                "colli_ecom": c_eco,
                "colli_others": c_oth,
                "colli_vario": c_var,
                "colli_cont": c_cont,
                "colli_mat_vario": c_mat,
                "colli_dann": c_dann,
                "colli_non_conf": c_nonconf,
                "anomalie_scarico": form_anomalie,
                "intershops_list": inter_rows_data,
                "stringa": computed_stringa,
            }
            new_id = save_or_update_bolla(bolla_save_payload)
            if save_next_clicked and store_choices:
                try:
                    curr_idx = store_choices.index(sel_store_str)
                    if curr_idx + 1 < len(store_choices):
                        st.session_state["form_store_sel"] = store_choices[curr_idx + 1]
                except Exception:
                    pass
            st.success(f"🎉 Bolla #{new_id} per Store **{current_sid}** salvata!")
            st.rerun()


# ==============================================================================
# PAGE 3: CONSUNTIVO & PLANNER INDITEX (CONFRONTO PREVISIONE VS BOLLE REALI)
# ==============================================================================
elif menu == "📊 3. Consuntivo & Planner Inditex":
    st.markdown('<div class="main-header">📊 Consuntivo & Confronto Planner Roma (Form Inditex)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Quadratura tra colli previsti ed effettivamente consegnati nelle bolle (con seconde consegne contraddistinte dalla lettera "B") ed esportazione diretta del file ufficiale Inditex.</div>', unsafe_allow_html=True)

    bolle_dates_plan = get_bolle_dates(60)
    if runs_side.empty:
        st.warning("Nessuna previsione presente nello storico. Esegui prima un'elaborazione nella pagina '📥 1. Previsione & Arrivi'.")
    elif not bolle_dates_plan:
        st.info("ℹ️ Nessuna bolla registrata in archivio. Genera prima le bolle dalla pagina '🚚 2. Bolle di Consegna'.")
    else:
        col_p1, col_p2, col_p3 = st.columns([2, 2, 1.5])
        with col_p1:
            run_opts_p = {
                int(r["id"]): f"Run #{int(r['id'])} ({format_date_it(r['run_date'])}, {r['cycle_type']}) - {format_number_it(r['total_bultos'], 0)} colli"
                for _, r in runs_side.head(30).iterrows()
            }
            sel_plan_run = st.selectbox(
                "1. Previsione di Riferimento (Run)",
                list(run_opts_p.keys()),
                format_func=lambda rid: run_opts_p[rid],
                key="plan_comp_run",
            )
        with col_p2:
            sel_plan_date = st.selectbox(
                "2. Data Consegna Bolle (Uscite Reali)",
                bolle_dates_plan,
                format_func=lambda d: f"{format_date_it(d)} ({d})",
                key="plan_comp_date",
            )
        with col_p3:
            only_diff = st.checkbox("Mostra solo differenze (Delta ≠ 0)", value=False, key="chk_only_diff")
            only_b9 = st.checkbox("Mostra solo seconde consegne ('B')", value=False, key="chk_only_b9")

        det_plan = get_run_details(sel_plan_run)
        df_a_target = det_plan.get("planning_results")
        df_actuals_bolle = get_actuals_for_planner(sel_plan_date)

        if df_a_target is None or df_a_target.empty:
            st.warning("Dati previsionali non trovati per la Run selezionata.")
        elif df_actuals_bolle.empty:
            st.info(f"ℹ️ Nessuna bolla trovata per la data **{format_date_it(sel_plan_date)}**.")
        else:
            df_planner_real = compute_planning_roma(df_a_target, df_actuals_bolle, df_stores=df_stores_side)
            df_planner_real["delta_crts"] = (df_planner_real["total_received_crts"] - df_planner_real["total_planned_crts"]).round(1)

            tot_plan = df_planner_real["total_planned_crts"].sum()
            tot_rec = df_planner_real["total_received_crts"].sum()
            delta_tot = round(tot_rec - tot_plan, 1)
            pos_deltas = int((df_planner_real["delta_crts"] > 0.1).sum())

            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
            c_m1.metric("Totale Colli Pianificati", format_number_it(tot_plan, 0))
            c_m2.metric("Totale Colli Usciti (Bolle)", format_number_it(tot_rec, 0))
            c_m3.metric("Delta (Reale - Previsto)", f"{delta_tot:+,.1f}".replace(",", "."))
            c_m4.metric("Anomalie Delta Positivo", f"{pos_deltas}", delta="OK (0 anomalie)" if pos_deltas == 0 else "Verificare", delta_color="normal" if pos_deltas == 0 else "inverse")

            # Esportazione immediata del file ufficiale Planning ITX_RM.xlsx
            out_planner_path = OUTPUT_DIR / f"Planning_ITX_RM_{sel_plan_date}.xlsx"
            export_planner_roma(df_planner_real, PLANNER_TEMPLATE_FILE, out_planner_path, sel_plan_date)
            if out_planner_path.exists():
                with open(out_planner_path, "rb") as f_pl:
                    st.download_button(
                        "📥 SCARICA MODULO UFFICIALE INDITEX COMPILATO (Planning_ITX_RM.xlsx)",
                        data=f_pl.read(),
                        file_name=f"Planning_ITX_RM_{sel_plan_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True,
                    )

            disp_cols = [
                "store_code", "store_name", "brand", "delivery_day",
                "total_planned_crts", "total_received_crts", "delta_crts",
                "planned_textile", "received_textile",
                "planned_shoes", "received_shoes",
                "planned_others", "received_others",
                "planned_ecom", "received_ecom",
                "intershops",
            ]
            df_disp = df_planner_real[[c for c in disp_cols if c in df_planner_real.columns]].copy()
            if only_diff:
                df_disp = df_disp[df_disp["delta_crts"].abs() > 0.05]
            if only_b9:
                df_disp = df_disp[df_disp["store_code"].astype(str).str.endswith("B")]

            st.dataframe(df_disp, use_container_width=True, height=480)


# ==============================================================================
# PAGE 4: ANAGRAFICA NEGOZI & GIRI
# ==============================================================================
elif menu == "🏢 4. Anagrafica Negozi & Giri":
    st.markdown('<div class="main-header">🏢 Anagrafica Negozi, Giri & Autisti</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Configura stato attivo, lavorazioni (SI TESSILE / SI HOME), sdoppiamento consegna (/0 e /9 "B"), formule pedane e autisti per giro.</div>', unsafe_allow_html=True)

    df_stores = get_stores_df()

    col_k1, col_k2, col_k3, col_k4, col_k5, col_k6 = st.columns(6)
    col_k1.metric("🏢 Negozi Censiti", len(df_stores))
    col_k2.metric("🟢 Negozi Attivi", int((df_stores["attivo"].str.upper() == "SI").sum()))
    col_k3.metric("🚚 Giri Mappati", int(df_stores["giro"].dropna().nunique()))
    col_k4.metric("👤 Autisti Assegnati", len([a for a in df_stores["autista"].dropna().unique() if str(a).strip() != ""]))
    col_k5.metric("✨ Sdopp. /9 ('B')", int((df_stores["sdoppiamento_b9"].fillna("NO").astype(str).str.upper() == "SI").sum()))
    col_k6.metric("🏭 Con Lavorazione", int((df_stores["lavorazione"].fillna("NO").astype(str).str.upper() != "NO").sum()))

    tab_grid, tab_edit, tab_giri = st.tabs([
        "📋 Tabella Interattiva Negozi (Modifica Rapida)",
        "✏️ Scheda Dettaglio Singolo Negozio / Nuovo",
        "🚚 Giri & Assegnazione Autisti per Giro",
    ])

    # --------------------------------------------------------------------------
    # TAB 1: GRIGLIA INTERATTIVA (MODIFICA DIRETTA)
    # --------------------------------------------------------------------------
    with tab_grid:
        st.caption("Modifica direttamente sulla tabella qualsiasi opzione (`Giro`, `Attivo`, `Lavorazione`, `Sdopp. /0-/9`, `Formula Pedane`, `Autista`) e clicca su **Salva Modifiche**:")

        col_gf1, col_gf2, col_gf3, col_gf4 = st.columns(4)
        with col_gf1:
            g_filter_giro = st.selectbox("Filtra Giro", ["TUTTI"] + sorted(df_stores["giro"].dropna().unique().tolist()), key="grid_f_giro")
        with col_gf2:
            g_filter_brand = st.selectbox("Filtra Brand", ["TUTTI"] + sorted(df_stores["brand"].dropna().unique().tolist()), key="grid_f_brand")
        with col_gf3:
            g_filter_sdop = st.selectbox("Filtra Sdoppiamento /9", ["TUTTI", "SI", "NO"], key="grid_f_sdop")
        with col_gf4:
            g_search = st.text_input("🔍 Cerca Negozio", "", key="grid_f_search")

        df_grid = df_stores.copy()
        if g_filter_giro != "TUTTI":
            df_grid = df_grid[df_grid["giro"] == g_filter_giro]
        if g_filter_brand != "TUTTI":
            df_grid = df_grid[df_grid["brand"] == g_filter_brand]
        if g_filter_sdop != "TUTTI":
            df_grid = df_grid[df_grid["sdoppiamento_b9"].fillna("NO").str.upper() == g_filter_sdop]
        if g_search:
            q = g_search.strip().lower()
            df_grid = df_grid[
                df_grid["store_id"].astype(str).str.lower().str.contains(q) |
                df_grid["store_name"].astype(str).str.lower().str.contains(q)
            ]

        grid_cols = [
            "store_id", "store_name", "brand", "giro", "attivo", "lavorazione",
            "scorporo_profumi", "pezzi_profumi", "sdoppiamento_b9",
            "formula", "autista", "cell_autista", "tipo_mezzo", "autista_doppia", "tipo_mezzo_doppia",
            "indirizzo", "provincia", "cod_sga", "cc"
        ]
        df_grid_show = df_grid[[c for c in grid_cols if c in df_grid.columns]].copy()

        edited_df = st.data_editor(
            df_grid_show,
            column_config={
                "store_id": st.column_config.TextColumn("Store ID", disabled=True),
                "store_name": st.column_config.TextColumn("Nome Negozio", required=True),
                "brand": st.column_config.SelectboxColumn("Brand", options=["ZARA", "BERSHKA", "PULL&BEAR", "MASSIMO DUTTI", "OYSHO", "STRADIVARIUS", "ZARA HOME", "ALTRO"], required=True),
                "giro": st.column_config.TextColumn("Giro", required=True),
                "attivo": st.column_config.SelectboxColumn("Attivo", options=["SI", "NO"], required=True),
                "lavorazione": st.column_config.SelectboxColumn("Lavorazione", options=["NO", "SI TESSILE", "SI HOME"], required=True),
                "scorporo_profumi": st.column_config.SelectboxColumn("Scorporo Profumi", options=["NO", "SI"], required=True),
                "pezzi_profumi": st.column_config.NumberColumn("Pezzi Profumi", min_value=0, step=1, format="%d"),
                "sdoppiamento_b9": st.column_config.SelectboxColumn("Sdopp. /0-/9", options=["NO", "SI"], required=True),
                "formula": st.column_config.TextColumn("Formula Pedane", required=True),
                "autista": st.column_config.TextColumn("Autista STD"),
                "cell_autista": st.column_config.TextColumn("Cellulare"),
                "tipo_mezzo": st.column_config.SelectboxColumn("Mezzo STD", options=["MOTRICE 18 PLT", "BILICO", "EUROCARGO 75", "FURG", "MOTRICE", "FURGONE"]),
                "autista_doppia": st.column_config.TextColumn("Autista /9 (DOPPIA)"),
                "tipo_mezzo_doppia": st.column_config.TextColumn("Mezzo /9 (DOPPIA)"),
                "indirizzo": st.column_config.TextColumn("Indirizzo"),
                "provincia": st.column_config.TextColumn("Prov."),
                "cod_sga": st.column_config.NumberColumn("Cod. SGA", format="%d"),
                "cc": st.column_config.TextColumn("Centro Comm."),
            },
            use_container_width=True,
            height=450,
            key="grid_editor",
        )

        cg1, cg2 = st.columns([2, 1])
        with cg1:
            if st.button("💾 SALVA MODIFICHE TABELLA", type="primary", use_container_width=True):
                bulk_update_stores(edited_df)
                st.success("✅ Anagrafica aggiornata con successo!")
                st.rerun()
        with cg2:
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                df_stores.to_excel(writer, index=False, sheet_name="Anagrafica Negozi")
            excel_buf.seek(0)
            st.download_button(
                "📥 Esporta Anagrafica (.xlsx)",
                data=excel_buf.read(),
                file_name="anagrafica_negozi.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    # --------------------------------------------------------------------------
    # TAB 2: SCHEDA DETTAGLIO SINGOLO NEGOZIO / NUOVO NEGOZIO
    # --------------------------------------------------------------------------
    with tab_edit:
        store_options = [f"{r['store_id']} - {r['store_name']} ({r['brand']}) [{r['giro']}]" for _, r in df_stores.iterrows()]
        selected_store_str = st.selectbox("Seleziona Punto Vendita da Esaminare o Modificare", store_options, key="sel_store_detail")
        sel_store_id = selected_store_str.split(" - ")[0].strip()
        curr_row = df_stores[df_stores["store_id"] == sel_store_id].iloc[0]

        # Banner Previsioni Carico dall'Ultima Elaborazione
        latest_planned = get_store_latest_planned_data(sel_store_id)
        if latest_planned.get("has_data"):
            st.markdown(f"##### 📦 Ultima Previsione Carico (Run #{latest_planned['run_id']} del {format_date_it(latest_planned['run_date'])})")
            kp1, kp2, kp3, kp4, kp5, kp6 = st.columns(6)
            kp1.metric("Colli Totali", format_number_it(latest_planned["total_crts"], 0))
            kp2.metric("Tessile", format_number_it(latest_planned["textile"], 0))
            kp3.metric("Calzature", format_number_it(latest_planned["shoes"], 0))
            kp4.metric("Others / E-Com", format_number_it(latest_planned["others"] + latest_planned["ecom"], 0))
            kp5.metric("Volume m³", format_number_it(latest_planned["volume"], 2))
            kp6.metric("Pedane Stimate", str(latest_planned["pedane"]))
        else:
            st.info("ℹ️ Nessun carico previsto per questo punto vendita nell'ultima elaborazione.")

        st.markdown("---")
        col_ed1, col_ed2, col_ed3 = st.columns(3)
        with col_ed1:
            st.markdown("##### 🏢 Identificativi & Giro")
            e_name = st.text_input("Nome Negozio", value=str(curr_row.get("store_name", "") or ""), key=f"e_name_{sel_store_id}")
            brands_list = ["ZARA", "BERSHKA", "PULL&BEAR", "MASSIMO DUTTI", "OYSHO", "STRADIVARIUS", "ZARA HOME", "ALTRO"]
            curr_b = str(curr_row.get("brand", "ZARA") or "ZARA").strip()
            e_brand = st.selectbox("Brand", brands_list, index=brands_list.index(curr_b) if curr_b in brands_list else 0, key=f"e_brand_{sel_store_id}")
            e_giro = st.text_input("Giro (es. ZA1..ZA20)", value=str(curr_row.get("giro", "") or ""), key=f"e_giro_{sel_store_id}")
            e_cc = st.text_input("Centro Commerciale", value=str(curr_row.get("cc", "") or ""), key=f"e_cc_{sel_store_id}")
            curr_sga = int(curr_row["cod_sga"]) if pd.notna(curr_row.get("cod_sga")) and str(curr_row.get("cod_sga")).isdigit() else 0
            e_sga = st.number_input("Codice SGA", value=curr_sga, step=1, key=f"e_sga_{sel_store_id}")

        with col_ed2:
            st.markdown("##### 🚚 Logistica, Autista & Indirizzo")
            e_autista = st.text_input("Autista STD", value=str(curr_row.get("autista", "") or ""), key=f"e_autista_{sel_store_id}")
            e_cell = st.text_input("Cellulare Autista", value=str(curr_row.get("cell_autista", "") or ""), key=f"e_cell_{sel_store_id}")
            e_mezzo = st.text_input("Mezzo STD", value=str(curr_row.get("tipo_mezzo", "MOTRICE 18 PLT") or "MOTRICE 18 PLT"), key=f"e_mezzo_{sel_store_id}")
            e_vettore = st.text_input("Vettore", value=str(curr_row.get("vettore", "LACCHI SPA") or "LACCHI SPA"), key=f"e_vettore_{sel_store_id}")
            e_ind = st.text_input("Indirizzo Scarico", value=str(curr_row.get("indirizzo", "") or ""), key=f"e_ind_{sel_store_id}")
            e_prov = st.text_input("Provincia", value=str(curr_row.get("provincia", "RM") or "RM"), key=f"e_prov_{sel_store_id}")

        with col_ed3:
            st.markdown("##### ⚙️ Opzioni & Formula Pedane")
            curr_att = str(curr_row.get("attivo", "SI")).strip().upper()
            e_attivo = st.radio("Stato Punto Vendita", ["SI (Attivo)", "NO (Disattivato)"], index=0 if curr_att == "SI" else 1, horizontal=True, key=f"e_att_{sel_store_id}")

            curr_lav = str(curr_row.get("lavorazione", "NO")).strip().upper()
            lav_opts = ["NO", "SI TESSILE", "SI HOME"]
            e_lav = st.selectbox("Lavorazione Piattaforma", lav_opts, index=lav_opts.index(curr_lav) if curr_lav in lav_opts else 0, key=f"e_lav_{sel_store_id}")

            curr_scorp = str(curr_row.get("scorporo_profumi", "NO") or "NO").strip().upper()
            e_scorp = st.selectbox("🧴 Scorporo Profumi", ["NO", "SI"], index=1 if curr_scorp == "SI" else 0, key=f"e_scorp_{sel_store_id}")
            curr_pz_prof = int(float(curr_row.get("pezzi_profumi", 0) or 0))
            if e_scorp == "SI":
                e_pz_prof = st.number_input("🧴 Pezzi Profumi da Scorporare", value=curr_pz_prof, min_value=0, step=1, key=f"e_pz_prof_{sel_store_id}")
            else:
                e_pz_prof = curr_pz_prof

            curr_sdop = str(curr_row.get("sdoppiamento_b9", "NO")).strip().upper()
            e_sdop = st.radio("Sdoppiamento Consegna /0 e /9 ('B')", ["NO (Consegna unica)", "SI (Divide 70% /0 e 30% /9 'B')"], index=1 if curr_sdop == "SI" else 0, key=f"e_sdop_{sel_store_id}")

            val_sdop_now = "SI" if e_sdop.startswith("SI") else "NO"
            if val_sdop_now == "SI":
                e_aut_d = st.text_input("Autista /9 (DOPPIA)", value=str(curr_row.get("autista_doppia", "") or ""), key=f"e_aut_d_{sel_store_id}")
                e_mezzo_d = st.text_input("Mezzo /9 (DOPPIA)", value=str(curr_row.get("tipo_mezzo_doppia", "FURGONE") or "FURGONE"), key=f"e_mezzo_d_{sel_store_id}")
            else:
                e_aut_d = str(curr_row.get("autista_doppia", "") or "")
                e_mezzo_d = str(curr_row.get("tipo_mezzo_doppia", "") or "")

            new_formula = st.text_input("Formula Calcolo Pedane", value=str(curr_row.get("formula", "MC/1,9") or "MC/1,9"), key=f"e_form_{sel_store_id}")
            st.caption(f"Es. con 15 m³ → **{evaluate_pedane(15.0, new_formula)} pedane**")

        cs1, cs2 = st.columns([3, 1])
        with cs1:
            if st.button(f"💾 SALVA SCHEDA NEGOZIO {sel_store_id}", type="primary", use_container_width=True, key=f"btn_save_st_{sel_store_id}"):
                update_store_record(sel_store_id, {
                    "store_name": e_name,
                    "punto_vendita": e_brand,
                    "brand": e_brand,
                    "giro": e_giro.strip().upper(),
                    "autista": e_autista.strip(),
                    "cell_autista": e_cell.strip(),
                    "tipo_mezzo": e_mezzo.strip(),
                    "vettore": e_vettore.strip(),
                    "indirizzo": e_ind.strip(),
                    "provincia": e_prov.strip().upper(),
                    "cod_sga": int(e_sga) if e_sga > 0 else None,
                    "cc": e_cc.strip(),
                    "attivo": "SI" if e_attivo.startswith("SI") else "NO",
                    "lavorazione": e_lav,
                    "scorporo_profumi": e_scorp,
                    "pezzi_profumi": int(e_pz_prof),
                    "sdoppiamento_b9": val_sdop_now,
                    "autista_doppia": e_aut_d if val_sdop_now == "SI" else "",
                    "tipo_mezzo_doppia": e_mezzo_d if val_sdop_now == "SI" else "",
                    "formula": new_formula.strip(),
                })
                st.success(f"✅ Scheda del negozio **{sel_store_id}** aggiornata!")
                st.rerun()
        with cs2:
            with st.popover(f"🗑️ Elimina {sel_store_id}", use_container_width=True):
                st.warning(f"Eliminare il negozio {sel_store_id}?")
                if st.button("Conferma", type="primary", use_container_width=True, key=f"del_st_{sel_store_id}"):
                    delete_store_record(sel_store_id)
                    st.rerun()

        with st.expander("➕ Censimento Nuovo Punto Vendita", expanded=False):
            ca1, ca2, ca3 = st.columns(3)
            with ca1:
                new_sid = st.text_input("Nuovo Store ID", key="add_sid").strip()
                new_sname = st.text_input("Nome Negozio", key="add_sname").strip()
                new_brand = st.selectbox("Brand", ["ZARA", "BERSHKA", "PULL&BEAR", "MASSIMO DUTTI", "OYSHO", "STRADIVARIUS", "ZARA HOME", "ALTRO"], key="add_brand")
            with ca2:
                new_giro = st.text_input("Giro", value="ZA1", key="add_giro").strip().upper()
                new_autista = st.text_input("Autista", key="add_autista").strip()
                new_ind = st.text_input("Indirizzo", key="add_indirizzo").strip()
            with ca3:
                new_lav = st.selectbox("Lavorazione", ["NO", "SI TESSILE", "SI HOME"], key="add_lav")
                new_sdop = st.selectbox("Sdoppiamento /0-/9", ["NO", "SI"], key="add_sdop")
                new_form = st.text_input("Formula Pedane", value="MC/1,9", key="add_formula").strip()

            if st.button("➕ REGISTRA NUOVO NEGOZIO", type="primary", use_container_width=True):
                if not new_sid or not new_sname:
                    st.error("Inserire Store ID e Nome Negozio.")
                else:
                    add_store_record({
                        "store_id": new_sid,
                        "store_name": new_sname,
                        "punto_vendita": new_brand,
                        "brand": new_brand,
                        "giro": new_giro,
                        "autista": new_autista,
                        "indirizzo": new_ind,
                        "attivo": "SI",
                        "lavorazione": new_lav,
                        "sdoppiamento_b9": new_sdop,
                        "formula": new_form or "MC/1,9",
                    })
                    st.success(f"✅ Negozio {new_sid} inserito!")
                    st.rerun()

    # --------------------------------------------------------------------------
    # TAB 3: GIRI & ASSEGNAZIONE AUTISTI PER GIRO
    # --------------------------------------------------------------------------
    with tab_giri:
        df_giro_sum = get_giro_summary()
        st.dataframe(df_giro_sum, use_container_width=True, height=340)

        st.markdown("##### 🔄 Aggiorna Autista e Mezzo per un Intero Giro")
        giri_avail = sorted([g for g in df_stores["giro"].dropna().unique().tolist() if str(g).strip() != ""])
        if giri_avail:
            cg_1, cg_2, cg_3, cg_4 = st.columns(4)
            with cg_1:
                sel_g = st.selectbox("Seleziona Giro", giri_avail, key="g_assign_sel")
                g_row = df_giro_sum[df_giro_sum["giro"] == sel_g].iloc[0] if not df_giro_sum[df_giro_sum["giro"] == sel_g].empty else {}
            with cg_2:
                g_aut = st.text_input("Autista del Giro", value="" if g_row.get("autista") == "Non Assegnato" else str(g_row.get("autista", "")), key=f"ga_{sel_g}")
            with cg_3:
                g_cel = st.text_input("Cellulare Autista", value=str(g_row.get("cell_autista", "")), key=f"gc_{sel_g}")
            with cg_4:
                g_mez = st.text_input("Mezzo", value=str(g_row.get("tipo_mezzo", "MOTRICE 18 PLT")), key=f"gm_{sel_g}")

            if st.button(f"💾 APPLICA AUTISTA A TUTTI I NEGOZI DEL GIRO {sel_g}", type="primary", use_container_width=True):
                n_up = update_giro_driver(sel_g, g_aut, g_cel, g_mez, "LACCHI SPA")
                st.success(f"✅ Aggiornati **{n_up}** punti vendita del giro **{sel_g}**!")
                st.rerun()


# ==============================================================================
# PAGE 5: STORICO, CANCELLAZIONE MASSIVA & BACKUP CLOUD
# ==============================================================================
elif menu == "🗄️ 5. Storico & Backup Cloud":
    st.markdown('<div class="main-header">🗄️ Storico Elaborazioni, Cancellazione Massiva & Backup</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Gestione archivio elaborazioni, pulizia massiva e portabilità completa del database SQLite su qualsiasi PC o server.</div>', unsafe_allow_html=True)

    tab_cloud_gs, tab_hist, tab_backup = st.tabs([
        "🟢 Cloud Google Sheets (Apps Script)",
        "📊 Archivio & Cancellazione Massiva Storico",
        "💾 Backup File Database (.db)",
    ])

    with tab_cloud_gs:
        st.markdown("#### 🟢 Collegamento Permanente a Google Sheets (tramite Apps Script)")
        st.info("""
        Collegando l'applicazione a un **Foglio Google** sul tuo Drive, ogni modifica a **Negozi, Giri, Autisti, Bolle e Previsioni** viene salvata in tempo reale anche sul tuo Google Sheet.
        Inoltre, quando l'app gira su **Streamlit Cloud**, ricarica automaticamente tutti i tuoi dati da Google Sheets ad ogni avvio.
        """)

        curr_url = get_cloud_url()
        new_url = st.text_input(
            "🔗 URL Web App di Google Apps Script (termina con `/exec`):",
            value=curr_url,
            placeholder="https://script.google.com/macros/s/AKfycb.../exec",
        )

        col_gs1, col_gs2, col_gs3 = st.columns(3)
        with col_gs1:
            if st.button("💾 Salva URL Google Script", type="primary", use_container_width=True):
                set_cloud_url(new_url)
                st.success("✅ URL Google Apps Script salvato!")
                st.rerun()
        with col_gs2:
            if st.button("☁️ Invia Dati Attuali a Google Sheets (Push)", use_container_width=True, disabled=not bool(curr_url)):
                with st.spinner("Invio di tutte le tabelle (Negozi, Bolle, Storico) al tuo Foglio Google..."):
                    res_push = push_tables_to_cloud()
                    if res_push.get("status") == "ok":
                        st.success(f"✅ Sincronizzazione completata! Fogli aggiornati: {', '.join(res_push.get('updated', []))}")
                    else:
                        st.error(f"❌ Errore sincronizzazione: {res_push.get('message')}")
        with col_gs3:
            if st.button("📥 Ricarica Dati da Google Sheets (Pull)", use_container_width=True, disabled=not bool(curr_url)):
                with st.spinner("Lettura tabelle dal Foglio Google..."):
                    res_pull = pull_all_from_cloud()
                    if res_pull.get("status") == "ok":
                        st.success(f"✅ Dati ricaricati da Google Sheets: {res_pull.get('restored')}")
                        st.rerun()
                    else:
                        st.error(f"❌ Errore lettura: {res_pull.get('message')}")

        with st.expander("📜 Clicca qui per copiare il codice Google Apps Script da incollare nel tuo Foglio Google"):
            script_path = Path(__file__).resolve().parent / "google_apps_script_db.js"
            if script_path.exists():
                st.code(script_path.read_text(encoding="utf-8"), language="javascript")

        with st.expander("🔐 Credenziali Extranet Inditex (Salvate per il Prelievo Automatico)"):
            st.caption("Queste credenziali sono già salvate nel sistema per non doverle mai inserire nella schermata giornaliera. Modificale qui solo in caso di cambio password su Inditex:")
            saved_u, saved_p = get_extranet_credentials()
            c_eu, c_ep = st.columns(2)
            with c_eu:
                new_ext_u = st.text_input("Utente Extranet", value=saved_u, key="cfg_ext_u")
            with c_ep:
                new_ext_p = st.text_input("Password Extranet", value=saved_p, type="password", key="cfg_ext_p")
            if st.button("💾 Salva Credenziali Extranet", type="primary", key="btn_save_ext_creds"):
                set_extranet_credentials(new_ext_u, new_ext_p)
                st.success("✅ Credenziali Extranet salvate con successo!")

    with tab_hist:
        runs = get_all_runs()
        if runs.empty:
            st.info("Nessuna elaborazione salvata nello storico.")
        else:
            # Cancellazione Massiva in primo piano
            st.markdown("#### 🗑️ Cancellazione Massiva Elaborazioni")
            run_id_list = [int(r["id"]) for _, r in runs.iterrows()]
            run_label_map = {
                int(r["id"]): f"Run #{int(r['id'])} - {format_date_it(r['run_date'])} ({r['cycle_type']}) : {format_number_it(r['total_bultos'], 0)} colli | {format_number_it(r['total_volume'], 2)} m³"
                for _, r in runs.iterrows()
            }

            cs_b1, cs_b2, cs_b3, cs_b4 = st.columns([1.2, 1.2, 1.8, 1.8])
            with cs_b1:
                if st.button("☑️ Seleziona Tutte", use_container_width=True, key="btn_sel_all_runs"):
                    st.session_state["mass_del_sel_runs"] = list(run_id_list)
                    st.rerun()
            with cs_b2:
                if st.button("🔄 Deseleziona Tutte", use_container_width=True, key="btn_desel_all_runs"):
                    st.session_state["mass_del_sel_runs"] = []
                    st.rerun()

            default_sel = [x for x in st.session_state.get("mass_del_sel_runs", []) if x in run_id_list]
            selected_mass_ids = st.multiselect(
                "Seleziona le elaborazioni da eliminare:",
                options=run_id_list,
                default=default_sel,
                format_func=lambda x: run_label_map.get(x, f"Run #{x}"),
                key="mass_del_multiselect",
            )
            st.session_state["mass_del_sel_runs"] = selected_mass_ids

            with cs_b3:
                if selected_mass_ids:
                    with st.popover(f"🗑️ Elimina Selezionate ({len(selected_mass_ids)})", use_container_width=True):
                        st.warning(f"Confermi l'eliminazione definitiva di **{len(selected_mass_ids)}** elaborazioni?")
                        if st.button("Conferma Eliminazione Multipla", type="primary", use_container_width=True, key="btn_confirm_mass_del"):
                            n_del = delete_runs(selected_mass_ids)
                            st.session_state["mass_del_sel_runs"] = []
                            if "last_run" in st.session_state and st.session_state["last_run"].get("run_id") in selected_mass_ids:
                                del st.session_state["last_run"]
                            st.success(f"Eliminate {n_del} elaborazioni!")
                            st.rerun()
                else:
                    st.button("🗑️ Elimina Selezionate (0)", disabled=True, use_container_width=True)

            with cs_b4:
                with st.popover("⚠️ Svuota Intero Storico", use_container_width=True):
                    st.error("Questa azione azzera tutte le elaborazioni dallo storico (anagrafica e bolle restano intatte).")
                    if st.button("Conferma Svuotamento Totale", type="primary", use_container_width=True, key="btn_confirm_clear_all"):
                        n_del = clear_all_runs()
                        st.session_state["mass_del_sel_runs"] = []
                        if "last_run" in st.session_state:
                            del st.session_state["last_run"]
                        st.success(f"Storico azzerato ({n_del} run eliminate)!")
                        st.rerun()

            st.markdown("---")
            runs_disp = runs.copy()
            runs_disp["run_date"] = runs_disp["run_date"].apply(format_date_it)
            show_cols = [c for c in ["id", "run_date", "cycle_type", "total_bultos", "total_volume", "total_weight", "total_pedane", "notes", "created_at"] if c in runs_disp.columns]
            st.dataframe(runs_disp[show_cols], use_container_width=True, height=320)

    with tab_backup:
        st.markdown("#### ☁️ Portabilità del Sistema (Indipendenza dal Singolo PC)")
        st.info("""
        Tutti i dati dell'applicazione (**Anagrafica Negozi, Giri, Autisti, Bolle di Consegna e Storico Previsioni**) sono contenuti in un unico database portabile SQLite (`zara_history.db`).
        - Puoi **scaricare una copia di backup** in qualsiasi momento.
        - Puoi **ripristinare il database** su qualsiasi altro PC o server cloud semplicemente caricando il file `.db` qui sotto.
        """)

        cb1, cb2 = st.columns(2)
        with cb1:
            st.markdown("##### 📥 1. Scarica Backup Completo Database")
            if DB_PATH.exists():
                with open(DB_PATH, "rb") as f_db:
                    st.download_button(
                        "💾 SCARICA DATABASE COMPLETO (zara_history.db)",
                        data=f_db.read(),
                        file_name=f"zara_history_backup_{datetime.now().strftime('%Y%m%d')}.db",
                        mime="application/octet-stream",
                        type="primary",
                        use_container_width=True,
                    )
        with cb2:
            st.markdown("##### 📤 2. Ripristina Database da File `.db`")
            up_db = st.file_uploader("Seleziona file database (.db / .sqlite)", type=["db", "sqlite", "sqlite3"], key="restore_db_uploader")
            if up_db is not None:
                if st.button("🔄 RIPRISTINA DATABASE CARICATO", type="primary", use_container_width=True):
                    raw_db = up_db.read()
                    with open(DB_PATH, "wb") as f_out:
                        f_out.write(raw_db)
                    init_db()
                    init_bolle_tables()
                    st.success("✅ Database ripristinato con successo!")
                    st.rerun()
