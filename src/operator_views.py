"""
Interfacce Semplificate "Zero Distrazioni" per gli Operatori (Ufficio, Magazzino, Mobile Banchina).
Mantiene al 100% la compatibilità con la modalità Admin / Vista Classica Completa di backup.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.bolle_manager import (
    add_colli_to_bolla_spuntata,
    compute_inditex_delivery_dates,
    confirm_bolla_spunta,
    export_bolle_excel,
    generate_bolle_from_forecast,
    get_bolla_by_id,
    get_bolle_by_date,
    get_bolle_dates,
    render_bolla_printable_html,
)
from src.cloud_sync import get_extranet_credentials, set_extranet_credentials
from src.config import DATA_DIR
from src.db import get_stores_df, load_run_data
from src.scraper import InditexExtranetScraper
from src.utils import get_cycle_date_range
from src.pipeline import run_pipeline


def format_date_it(d_val: Any) -> str:
    if not d_val:
        return ""
    if isinstance(d_val, (date, datetime)):
        return d_val.strftime("%d/%m/%Y")
    s = str(d_val).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return s


def format_date_weekday_it(d_str: str) -> str:
    days_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    try:
        dt = datetime.strptime(str(d_str).strip()[:10], "%Y-%m-%d").date()
        return f"{days_it[dt.weekday()]} {dt.strftime('%d/%m/%Y')}"
    except Exception:
        return format_date_it(d_str)


def format_number_it(val: Any, decimals: int = 0) -> str:
    try:
        num = float(val or 0)
    except Exception:
        num = 0.0
    if decimals <= 0:
        return f"{int(round(num)):,}".replace(",", ".")
    formatted = f"{num:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def ensure_bolle_for_latest_run(runs_df: pd.DataFrame) -> bool:
    """
    Se l'Ufficio ha appena creato una previsione ma per le due date di consegna (/0 e /9)
    dell'ultima Run non risultano ancora generate le bolle nel DB locale, le genera automaticamente
    senza sovrascrivere eventuali spunte già presenti (overwrite=False).
    """
    if runs_df is None or runs_df.empty:
        return False
    try:
        latest = runs_df.iloc[0]
        latest_id = int(latest["id"])
        r_date_str = str(latest["run_date"])[:10]
        r_cycle = str(latest.get("cycle_type", "LUN-MER"))
        dt_base = datetime.strptime(r_date_str, "%Y-%m-%d").date()
        date_dop, date_std = compute_inditex_delivery_dates(dt_base, r_cycle)
        b_std = get_bolle_by_date(date_std)
        b_dop = get_bolle_by_date(date_dop)
        if b_std.empty and b_dop.empty:
            generate_bolle_from_forecast(latest_id, overwrite=False)
            return True
    except Exception:
        pass
    return False


# ==============================================================================
# 1. MODALITÀ UFFICIO SEMPLIFICATA (SOLO CREAZIONE NUOVI GIRI + INVIO/DOWNLOAD)
# ==============================================================================
def render_ufficio_simplified_view(
    runs_side: pd.DataFrame,
    df_stores_side: pd.DataFrame,
    render_operativa_files_and_email_fn: Callable,
    classify_uploaded_files_fn: Callable,
):
    """
    Interfaccia ultra-snella per l'Operatore Ufficio:
    1) Selezione Date & Ciclo
    2) Correzione Profumi
    3) TASTONE per partire (Scarico Extranet -> Elaborazione -> XML su Cloud -> Bolle)
    4) Box immediato con file pronti (Sintesi_Operativa.xlsx, ZARA.xlsx, SGA, ZIP) e Invio Email.
    """
    if "flash_email_success" in st.session_state:
        st.success(f"🎉 **{st.session_state.pop('flash_email_success')}**")
    if "flash_run_msg" in st.session_state:
        st.success(f"🎉 **{st.session_state.pop('flash_run_msg')}**")

    st.markdown("""
    <div style="background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%);
                border: 2px solid #3B82F6; border-radius: 14px; padding: 16px 22px; margin-bottom: 18px;">
        <div style="font-size: 20px; font-weight: 900; color: #1E3A8A;">
            💼 CREAZIONE NUOVI GIRI OPERATIVI (MODALITÀ RAPIDA UFFICIO)
        </div>
        <div style="font-size: 13.5px; color: #1E40AF; margin-top: 4px;">
            <strong>1.</strong> Controlla le date &bull; <strong>2.</strong> Inserisci eventuali profumi &bull; <strong>3.</strong> Premi il tastone per scaricare da Extranet, creare i giri e caricare gli XML sul Cloud.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- STEP 1: SELEZIONE DATE & CICLO ---
    with st.container(border=True):
        st.markdown("#### 📅 1. Selezione Date e Ciclo Settimanale")
        c_dt1, c_dt2 = st.columns([1.1, 1.9])
        with c_dt1:
            run_date = st.date_input(
                "Data Riferimento Operativa",
                value=date.today(),
                format="DD/MM/YYYY",
                key="uff_simp_run_date",
            )
        with c_dt2:
            default_cycle_idx = 0 if run_date.weekday() <= 2 else 1
            cycle_choice = st.radio(
                "Ciclo Settimanale",
                options=[
                    "LUN-MER (Arrivo Lun/Mar → Consegna Mer /0 e Gio /9)",
                    "GIOV-DOM (Arrivo Gio/Ven → Consegna Sab /0 e Dom /9)",
                ],
                index=default_cycle_idx,
                horizontal=True,
                key="uff_simp_cycle_choice",
            )
            cycle_type = "LUN-MER" if "LUN-MER" in cycle_choice else "GIOV-DOM"

        cycle_desde, cycle_hasta = get_cycle_date_range(cycle_type, run_date)
        c_ex1, c_ex2 = st.columns(2)
        with c_ex1:
            sc_desde = st.date_input(
                "📅 Scarico Extranet Dal (Inizio)",
                value=cycle_desde,
                format="DD/MM/YYYY",
                key=f"uff_simp_desde_{cycle_type}_{run_date}",
            )
        with c_ex2:
            sc_hasta = st.date_input(
                "📅 Scarico Extranet Al (Fine)",
                value=cycle_hasta,
                format="DD/MM/YYYY",
                key=f"uff_simp_hasta_{cycle_type}_{run_date}",
            )

    # --- STEP 2: CORREZIONE PROFUMI ---
    perfume_corrections: Dict[str, float] = {}
    with st.container(border=True):
        st.markdown("#### 🧴 2. Scorporo Profumi (Pezzi da scalare, lascia 0 se assenti)")
        df_all_stores = get_stores_df()
        sid_col = "store_id" if "store_id" in df_all_stores.columns else "id_store"
        perf_stores_df = (
            df_all_stores[df_all_stores["scorporo_profumi"].fillna("NO").astype(str).str.upper() == "SI"]
            if not df_all_stores.empty and "scorporo_profumi" in df_all_stores.columns
            else pd.DataFrame()
        )
        if perf_stores_df.empty:
            fallback_ids = ["3680", "9226", "3591"]
            perf_cols = st.columns(3)
            for idx, p_sid in enumerate(fallback_ids):
                with perf_cols[idx]:
                    val = st.number_input(
                        f"🏪 Store {p_sid} (Pezzi)",
                        min_value=0,
                        value=0,
                        step=1,
                        key=f"uff_simp_perf_{p_sid}",
                    )
                    perfume_corrections[p_sid] = float(val)
        else:
            n_cols = min(len(perf_stores_df), 4)
            perf_cols = st.columns(n_cols)
            for idx, (_, p_row) in enumerate(perf_stores_df.iterrows()):
                p_sid = str(p_row.get(sid_col, "")).strip()
                p_name = str(p_row.get("store_name", "")).strip()
                with perf_cols[idx % n_cols]:
                    val = st.number_input(
                        f"🏪 {p_sid} — {p_name[:18]}",
                        min_value=0,
                        value=0,
                        step=1,
                        key=f"uff_simp_perf_{p_sid}",
                    )
                    perfume_corrections[p_sid] = float(val)

    # --- STEP 3: TASTONE PER PARTIRE ---
    notes = f"Elaborazione W{run_date.isocalendar()[1]} ({cycle_type})"
    ex_user, ex_pass = get_extranet_credentials()

    st.markdown("""
    <style>
    div[data-testid="stButton"] > button[kind="primary"] {
        min-height: 62px !important;
        font-size: 18px !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    btn_start_operativa = st.button(
        "🚀 AVVIA NUOVA OPERATIVA (SCARICA DA EXTRANET, CREA GIRI & CARICA XML CLOUD)",
        type="primary",
        use_container_width=True,
        key="btn_uff_simp_big_start",
    )

    if btn_start_operativa:
        status_banner = st.empty()
        prog_bar = st.progress(5)
        status_banner.markdown("""
        <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
                    border: 2px solid #38BDF8; border-radius: 12px;
                    padding: 18px 24px; margin: 12px 0 16px 0;">
            <div style="font-size: 16px; font-weight: 800; color: #38BDF8;">
                🚀 AVVIO OPERATIVA IN CORSO — ATTENDERE PREGO (5%)
            </div>
            <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 4px;">
                Connessione a Inditex Extranet e scarico automatico file...
            </div>
        </div>
        """, unsafe_allow_html=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_extract_dir = DATA_DIR / "downloads" / f"extranet_{ts}"
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        def update_progress(msg: str, pct: int):
            prog_bar.progress(pct)
            status_banner.markdown(f"""
            <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
                        border: 2px solid #38BDF8; border-radius: 12px;
                        padding: 18px 24px; margin: 12px 0 16px 0;">
                <div style="font-size: 16px; font-weight: 800; color: #38BDF8;">
                    🔄 ELABORAZIONE IN CORSO ({pct}%)
                </div>
                <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 4px;">
                    {html.escape(msg)}
                </div>
            </div>
            """, unsafe_allow_html=True)

        try:
            scraper = InditexExtranetScraper(
                username=ex_user,
                password=ex_pass,
                headless=True,
                progress_callback=update_progress,
            )
            scraper.scrape_all(
                desde_date=sc_desde,
                hasta_date=sc_hasta,
                output_dir=temp_extract_dir,
            )
            update_progress("Calcolo Giri, Generazione File Excel/XML e Upload Cloud...", 95)
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
            st.session_state["last_run"] = res
            st.session_state["active_view_run_id"] = res["run_id"]
            st.session_state["p1_subview"] = "view"
            st.session_state[f"show_op_panel_{res['run_id']}"] = True
            gcs_info = res.get("gcs_upload")
            extra_gcs_msg = ""
            if gcs_info and gcs_info.get("status") in ("ok", "partial"):
                extra_gcs_msg = f" ☁️ {gcs_info.get('uploaded_count')} file XML caricati su Google Cloud Storage!"
            st.session_state["flash_run_msg"] = (
                f"Nuovi Giri creati con successo (Run #{res['run_id']})!{extra_gcs_msg}"
            )
            st.rerun()
        except Exception as e:
            status_banner.empty()
            st.error(f"❌ Errore durante lo scarico da Extranet: {e}")

    # --- OPZIONE SECONDARIA DI EMERGENZA (UPLOAD MANUALE / CREDENZIALI) ---
    with st.expander("📤 Opzioni di Emergenza (Carica File Excel Manualmente o Modifica Password Extranet)", expanded=False):
        c_em1, c_em2 = st.columns([2, 1])
        with c_em1:
            uploaded_batch = st.file_uploader(
                "Trascina qui i file scaricati manualmente (TOTAL, SHOES, TEXILE, ECOM, OTHER o .zip)",
                type=["xls", "xlsx", "csv", "zip"],
                accept_multiple_files=True,
                key="uff_simp_manual_uploader",
            )
            classified = classify_uploaded_files_fn(uploaded_batch) if uploaded_batch else None
            if st.button(
                "🚀 AVVIA DA FILE CARICATI MANUALMENTE",
                type="secondary",
                use_container_width=True,
                disabled=not bool(classified and (classified["total"] or classified["texile"])),
                key="btn_uff_simp_manual_go",
            ):
                with st.spinner("Elaborazione file manuali e caricamento XML sul Cloud..."):
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
                    st.session_state["active_view_run_id"] = res["run_id"]
                    st.session_state["p1_subview"] = "view"
                    gcs_info = res.get("gcs_upload")
                    extra_gcs_msg = ""
                    if gcs_info and gcs_info.get("status") in ("ok", "partial"):
                        extra_gcs_msg = f" ☁️ {gcs_info.get('uploaded_count')} file XML caricati su Cloud!"
                    st.session_state["flash_run_msg"] = f"Giri creati da file manuali (Run #{res['run_id']})!{extra_gcs_msg}"
                    st.rerun()
        with c_em2:
            st.markdown("**🔐 Credenziali Extranet Inditex**")
            new_u = st.text_input("Utente Extranet", value=ex_user, key="uff_simp_ext_u")
            new_p = st.text_input("Password Extranet", value=ex_pass, type="password", key="uff_simp_ext_p")
            if st.button("💾 Salva Credenziali", use_container_width=True, key="btn_uff_simp_save_cred"):
                set_extranet_credentials(new_u, new_p)
                st.success("Credenziali salvate!")
                st.rerun()

    # --- SEZIONE FILE GENERATI E INVIO EMAIL DELL'OPERATIVA ATTIVA ---
    active_run_data = None
    if not runs_side.empty:
        latest_run_id = int(runs_side.iloc[0]["id"])
        curr_rid = st.session_state.get("active_view_run_id") or latest_run_id
        if curr_rid not in list(runs_side["id"]):
            curr_rid = latest_run_id
            st.session_state["active_view_run_id"] = curr_rid

        if "last_run" in st.session_state and st.session_state["last_run"] and st.session_state["last_run"].get("run_id") == curr_rid:
            active_run_data = st.session_state["last_run"]
        else:
            active_run_data = load_run_data(curr_rid)

    if active_run_data:
        st.markdown("---")
        rid_disp = active_run_data.get("run_id") or active_run_data.get("id")
        r_dt_disp = format_date_it(active_run_data.get("run_date", ""))
        r_cyc_disp = active_run_data.get("cycle_type", "")
        tots = active_run_data.get("totals", {})

        c_hdr_run, c_sel_run = st.columns([2.2, 1.3])
        with c_hdr_run:
            st.markdown(
                f"### 📦 Ultima Operativa Pronta: **Run #{rid_disp}** del **{r_dt_disp}** (`{r_cyc_disp}`)"
            )
        with c_sel_run:
            if len(runs_side) > 1:
                run_opts = {
                    int(r["id"]): f"Run #{int(r['id'])} ({format_date_it(r['run_date'])} - {int(r['total_bultos'])} colli)"
                    for _, r in runs_side.head(20).iterrows()
                }
                sel_r = st.selectbox(
                    "Cambia Operativa",
                    options=list(run_opts.keys()),
                    index=list(run_opts.keys()).index(int(rid_disp)) if int(rid_disp) in run_opts else 0,
                    format_func=lambda k: run_opts[k],
                    key="uff_simp_switch_run",
                    label_visibility="collapsed",
                )
                if sel_r != int(rid_disp):
                    st.session_state["active_view_run_id"] = sel_r
                    st.rerun()

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Totale Colli", format_number_it(tots.get("total_bultos", 0), 0))
        k2.metric("Pedane Stimate", format_number_it(tots.get("total_pedane", 0), 1))
        k3.metric("Volume Totale", f"{format_number_it(tots.get('total_volume', 0), 2)} m³")
        k4.metric("Peso Totale", f"{format_number_it(tots.get('total_weight', 0), 0)} kg")

        render_operativa_files_and_email_fn(
            active_run_data,
            df_stores_side,
            key_prefix=f"uff_simp_{rid_disp}",
        )


# ==============================================================================
# 2. MODALITÀ MAGAZZINO SEMPLIFICATA (SOLO SELEZIONE DATA, NEGOZI E STAMPA BOLLE)
# ==============================================================================
def render_magazzino_simplified_view(
    runs_side: pd.DataFrame,
    df_stores_side: pd.DataFrame,
):
    """
    Interfaccia ultra-snella per l'Operatore Magazzino:
    1) Seleziona la Data di Consegna
    2) Seleziona Giro / Negozi
    3) TASTONE STAMPA BOLLE (più bottoni rapidi /0, /9, Excel)
    """
    if "flash_bolle_msg" in st.session_state:
        st.success(f"🎉 **{st.session_state.pop('flash_bolle_msg')}**")

    # Assicura automaticamente che le bolle dell'ultima previsione siano state create
    ensure_bolle_for_latest_run(runs_side)

    st.markdown("""
    <div style="background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
                border: 2px solid #10B981; border-radius: 14px; padding: 16px 22px; margin-bottom: 18px;">
        <div style="font-size: 20px; font-weight: 900; color: #065F46;">
            🖨️ STAMPA BOLLE DI CONSEGNA (MODALITÀ RAPIDA MAGAZZINO)
        </div>
        <div style="font-size: 13.5px; color: #047857; margin-top: 4px;">
            <strong>1.</strong> Scegli la data &bull; <strong>2.</strong> Scegli il giro o i negozi &bull; <strong>3.</strong> Premi <strong>STAMPA BOLLE</strong>.
        </div>
    </div>
    """, unsafe_allow_html=True)

    today_str = str(date.today())
    tomorrow_str = str(date.today() + timedelta(days=1))
    all_dates = get_bolle_dates(120)
    if not all_dates:
        all_dates = [tomorrow_str, today_str]

    # Scelta predefinita intelligente: oggi o domani se presenti, altrimenti la prima data disponibile
    if "mag_simp_date" not in st.session_state or st.session_state["mag_simp_date"] not in all_dates:
        if tomorrow_str in all_dates:
            st.session_state["mag_simp_date"] = tomorrow_str
        elif today_str in all_dates:
            st.session_state["mag_simp_date"] = today_str
        else:
            st.session_state["mag_simp_date"] = all_dates[0]

    # --- STEP 1: SELEZIONE DATA DI CONSEGNA ---
    with st.container(border=True):
        st.markdown("#### 📅 1. Seleziona la Data di Consegna")
        c_d_sel, c_b1, c_b2, c_b3 = st.columns([2.4, 0.9, 0.9, 1.0])
        with c_d_sel:
            target_date = st.selectbox(
                "Data di Consegna",
                options=all_dates,
                index=all_dates.index(st.session_state["mag_simp_date"]),
                format_func=lambda d: f"📅 {format_date_weekday_it(d)} ({d})",
                key="mag_simp_date_sb",
                label_visibility="collapsed",
            )
            if target_date != st.session_state["mag_simp_date"]:
                st.session_state["mag_simp_date"] = target_date
                st.rerun()
        with c_b1:
            if st.button("📅 Oggi", use_container_width=True, key="mag_btn_today"):
                if today_str not in all_dates:
                    all_dates.insert(0, today_str)
                st.session_state["mag_simp_date"] = today_str
                st.rerun()
        with c_b2:
            if st.button("📅 Domani", use_container_width=True, key="mag_btn_tom"):
                if tomorrow_str not in all_dates:
                    all_dates.insert(0, tomorrow_str)
                st.session_state["mag_simp_date"] = tomorrow_str
                st.rerun()
        with c_b3:
            if st.button("🆕 Ultima Data", use_container_width=True, key="mag_btn_latest"):
                st.session_state["mag_simp_date"] = all_dates[0]
                st.rerun()

    df_bolle = get_bolle_by_date(target_date)

    # Se non ci sono bolle per questa data ma esiste una previsione, offri generazione 1-click
    if df_bolle.empty:
        st.warning(f"⚠️ Nessuna bolla presente per la data **{format_date_weekday_it(target_date)}**.")
        if not runs_side.empty:
            latest_rid = int(runs_side.iloc[0]["id"])
            if st.button(
                f"⚡ GENERA ORA LE BOLLE DALL'ULTIMA PREVISIONE (Run #{latest_rid})",
                type="primary",
                use_container_width=True,
                key="mag_btn_gen_bolle_now",
            ):
                created_cnt, _ = generate_bolle_from_forecast(latest_rid, overwrite=False)
                st.session_state["flash_bolle_msg"] = f"Generate {created_cnt} bolle dall'ultima previsione!"
                st.rerun()
        return

    # Arricchimento Giro da anagrafica negozi
    store_giro_map: Dict[str, str] = {}
    if not df_stores_side.empty and "giro" in df_stores_side.columns:
        s_col = "store_id" if "store_id" in df_stores_side.columns else "id_store"
        if s_col in df_stores_side.columns:
            for _, s_row in df_stores_side.iterrows():
                store_giro_map[str(s_row[s_col]).strip()] = str(s_row.get("giro", "") or "").strip()

    def _lookup_giro(sid_val: Any) -> str:
        s_clean = str(sid_val or "").strip()
        base_s = s_clean[:-1] if s_clean.endswith("B") else s_clean
        return store_giro_map.get(s_clean) or store_giro_map.get(base_s) or ""

    df_bolle = df_bolle.copy()
    df_bolle["giro"] = df_bolle["id_store"].map(_lookup_giro)
    for col_k in ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario"]:
        if col_k not in df_bolle.columns:
            df_bolle[col_k] = 0
        df_bolle[col_k] = pd.to_numeric(df_bolle[col_k], errors="coerce").fillna(0).astype(int)
    df_bolle["tot_colli"] = (
        df_bolle["colli_abbigl"]
        + df_bolle["colli_calzat"]
        + df_bolle["colli_ecom"]
        + df_bolle["colli_others"]
        + df_bolle["colli_vario"]
    )
    df_bolle = df_bolle.sort_values(by=["giro", "id_store", "tipo_cons"]).reset_index(drop=True)

    # --- STEP 2: SELEZIONA GIRO E NEGOZI ---
    with st.container(border=True):
        st.markdown("#### 🏪 2. Seleziona Giro e Negozi da Stampare")
        all_giri = sorted([g for g in df_bolle["giro"].unique() if str(g).strip()])
        c_f_giro, c_f_tipo = st.columns([1.4, 1.6])
        with c_f_giro:
            sel_giro = st.selectbox(
                "🚛 Filtra per Giro",
                options=["TUTTI I GIRI"] + all_giri,
                key="mag_simp_giro",
            )
        with c_f_tipo:
            sel_tipo = st.radio(
                "📑 Tipo Bolla",
                options=["TUTTE (/0 + /9)", "Solo Barra 0 (/0 STD)", "Solo Barra 9 (/9 DOPPIA)"],
                horizontal=True,
                key="mag_simp_tipo",
            )

        df_filtered = df_bolle.copy()
        if sel_giro != "TUTTI I GIRI":
            df_filtered = df_filtered[df_filtered["giro"] == sel_giro]
        if "Solo Barra 0" in sel_tipo:
            df_filtered = df_filtered[df_filtered["tipo_cons"].astype(str).str.upper() == "STD"]
        elif "Solo Barra 9" in sel_tipo:
            df_filtered = df_filtered[df_filtered["tipo_cons"].astype(str).str.upper() == "DOPPIA"]

        store_options: Dict[int, str] = {}
        for _, brow in df_filtered.iterrows():
            bid = int(brow["id"])
            sid = str(brow["id_store"])
            sname = str(brow.get("store_name", ""))
            t_c = "/9 DOPPIA" if str(brow.get("tipo_cons", "")).upper() == "DOPPIA" else "/0 STD"
            g_lbl = str(brow.get("giro", "")) or "—"
            tot_c = int(brow["tot_colli"])
            store_options[bid] = f"{sid} - {sname} [{g_lbl} • {t_c}] ({tot_c} colli)"

        selected_bolla_ids = st.multiselect(
            "🏪 Seleziona Negozi specifici (Lascia vuoto per stampare TUTTI i negozi del filtro)",
            options=list(store_options.keys()),
            default=[],
            format_func=lambda bid: store_options.get(bid, str(bid)),
            placeholder=f"Tutti i {len(store_options)} negozi selezionati automaticamente...",
            key="mag_simp_stores_multi",
        )

        if selected_bolla_ids:
            df_to_print = df_filtered[df_filtered["id"].isin(selected_bolla_ids)].copy()
        else:
            df_to_print = df_filtered.copy()

    # --- STEP 3: TASTONE STAMPA BOLLE ---
    n_bolle = len(df_to_print)
    tot_colli_print = int(df_to_print["tot_colli"].sum()) if not df_to_print.empty else 0

    st.markdown("""
    <style>
    div[data-testid="stButton"] > button[kind="primary"] {
        min-height: 68px !important;
        font-size: 20px !important;
        font-weight: 900 !important;
        border-radius: 14px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    if st.button(
        f"🖨️ STAMPA BOLLE SELEZIONATE ({n_bolle} BOLLE — {tot_colli_print} COLLI)",
        type="primary",
        use_container_width=True,
        disabled=(n_bolle == 0),
        key="mag_simp_big_print_btn",
    ):
        recs = [get_bolla_by_id(int(r["id"])) for _, r in df_to_print.iterrows()]
        recs = [r for r in recs if r]
        html_out = render_bolla_printable_html(recs, auto_print=True)
        # Timestamp comment per forzare sempre il trigger window.print() anche su clic multipli
        html_out += f"\n<!-- print_ts: {datetime.now().isoformat()} -->"
        st.session_state["mag_simp_print_html"] = html_out
        st.session_state["mag_simp_print_title"] = f"Bolle_{target_date}_{n_bolle}.html"

    # Bottoni rapidi /0, /9, Excel
    c_q1, c_q2, c_q3 = st.columns(3)
    df_only_b0 = df_to_print[df_to_print["tipo_cons"].astype(str).str.upper() == "STD"]
    df_only_b9 = df_to_print[df_to_print["tipo_cons"].astype(str).str.upper() == "DOPPIA"]

    with c_q1:
        if st.button(
            f"🚚 Stampa Solo /0 STD ({len(df_only_b0)})",
            use_container_width=True,
            disabled=df_only_b0.empty,
            key="mag_simp_print_b0",
        ):
            recs = [get_bolla_by_id(int(r["id"])) for _, r in df_only_b0.iterrows()]
            recs = [r for r in recs if r]
            html_out = render_bolla_printable_html(recs, auto_print=True) + f"\n<!-- print_ts: {datetime.now().isoformat()} -->"
            st.session_state["mag_simp_print_html"] = html_out
            st.session_state["mag_simp_print_title"] = f"Bolle_Barra0_{target_date}.html"

    with c_q2:
        if st.button(
            f"🔁 Stampa Solo /9 DOPPIA ({len(df_only_b9)})",
            use_container_width=True,
            disabled=df_only_b9.empty,
            key="mag_simp_print_b9",
        ):
            recs = [get_bolla_by_id(int(r["id"])) for _, r in df_only_b9.iterrows()]
            recs = [r for r in recs if r]
            html_out = render_bolla_printable_html(recs, auto_print=True) + f"\n<!-- print_ts: {datetime.now().isoformat()} -->"
            st.session_state["mag_simp_print_html"] = html_out
            st.session_state["mag_simp_print_title"] = f"Bolle_Barra9_{target_date}.html"

    with c_q3:
        if not df_to_print.empty:
            excel_bytes = export_bolle_excel(df_to_print, target_date)
            st.download_button(
                "📊 Scarica Riepilogo Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"Riepilogo_Bolle_{target_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="mag_simp_dl_excel",
            )

    # Trigger dialogo di stampa immediato del browser
    if "mag_simp_print_html" in st.session_state and st.session_state["mag_simp_print_html"]:
        st.components.v1.html(st.session_state["mag_simp_print_html"], height=0, width=0)
        st.success("✅ **Finestra di stampa inviata al browser!** (Se bloccata dal browser, scarica il file qui sotto)")
        st.download_button(
            "💾 Scarica File Stampa (.html)",
            data=st.session_state["mag_simp_print_html"].encode("utf-8"),
            file_name=st.session_state.get("mag_simp_print_title", f"Bolle_{target_date}.html"),
            mime="text/html",
            key="mag_simp_dl_html_fallback",
        )

    # Riepilogo pulito in sola lettura
    if not df_to_print.empty:
        with st.expander(f"📋 Anteprima Elenco Bolle Selezionate ({n_bolle} negozi — {tot_colli_print} colli)", expanded=True):
            disp_df = pd.DataFrame({
                "Giro": df_to_print["giro"],
                "Store ID": df_to_print["id_store"],
                "Punto Vendita": df_to_print["store_name"],
                "Tipo": df_to_print["tipo_cons"].map(lambda x: "/9 DOPPIA" if str(x).upper() == "DOPPIA" else "/0 STD"),
                "Totale Colli": df_to_print["tot_colli"],
                "Abbigl.": df_to_print["colli_abbigl"],
                "Calzat.": df_to_print["colli_calzat"],
                "E-Com": df_to_print["colli_ecom"],
                "Altri": df_to_print["colli_others"],
                "Vettore": df_to_print["vettore"] if "vettore" in df_to_print.columns else "",
                "Spunta": df_to_print["spuntato"].map(lambda s: "🟢 Spuntato" if int(s or 0) == 1 else "⏳ Da contare"),
            })
            st.dataframe(disp_df, use_container_width=True, hide_index=True)


# ==============================================================================
# 3. MODALITÀ MOBILE BANCHINA SEMPLIFICATA (SOLO DUE TASTI GIGANTI)
# ==============================================================================
def render_mobile_two_buttons_view(
    runs_side: pd.DataFrame,
    df_stores_side: pd.DataFrame,
    allow_classic_toggle: bool = False,
):
    """
    Interfaccia Smartphone / Palmare a 2 soli tasti giganti:
    - TASTO 1: 📋 SPUNTA NEGOZIO
    - TASTO 2: ➕ AGGIUNGI COLLI (A NEGOZI GIÀ SPUNTATI)
    """
    if "flash_bolle_msg" in st.session_state:
        st.success(f"🎉 **{st.session_state.pop('flash_bolle_msg')}**")

    ensure_bolle_for_latest_run(runs_side)

    if allow_classic_toggle:
        c_title_m, c_tog_m = st.columns([3, 1.2])
        with c_title_m:
            st.markdown("### 📱 Spunta Banchina Mobile (2 Tasti)")
        with c_tog_m:
            if st.button("🔧 Vista Completa Spunta", use_container_width=True, key="btn_mob_to_classic"):
                st.session_state["mob_use_classic_spunta"] = True
                st.rerun()

    today_str = str(date.today())
    tomorrow_str = str(date.today() + timedelta(days=1))
    all_dates = get_bolle_dates(120)
    if not all_dates:
        all_dates = [tomorrow_str, today_str]

    if "mob2_date" not in st.session_state or st.session_state["mob2_date"] not in all_dates:
        if tomorrow_str in all_dates:
            st.session_state["mob2_date"] = tomorrow_str
        elif today_str in all_dates:
            st.session_state["mob2_date"] = today_str
        else:
            st.session_state["mob2_date"] = all_dates[0]

    # Barra compatta Data + Giro
    c_m_dt, c_m_giro = st.columns([1.6, 1.2])
    with c_m_dt:
        mob_date = st.selectbox(
            "📅 Data Consegna",
            options=all_dates,
            index=all_dates.index(st.session_state["mob2_date"]),
            format_func=lambda d: f"{format_date_weekday_it(d)}",
            key="mob2_date_sb",
        )
        if mob_date != st.session_state["mob2_date"]:
            st.session_state["mob2_date"] = mob_date
            st.session_state["mob2_idx"] = 0
            st.rerun()

    df_b_date = get_bolle_by_date(mob_date)
    if df_b_date.empty:
        st.warning(f"Nessuna bolla presente per **{format_date_weekday_it(mob_date)}**.")
        if not runs_side.empty:
            latest_rid = int(runs_side.iloc[0]["id"])
            if st.button("⚡ Carica Bolle dall'Ultima Previsione", type="primary", use_container_width=True, key="mob2_gen_btn"):
                generate_bolle_from_forecast(latest_rid, overwrite=False)
                st.rerun()
        return

    store_giro_map: Dict[str, str] = {}
    if not df_stores_side.empty and "giro" in df_stores_side.columns:
        s_col = "store_id" if "store_id" in df_stores_side.columns else "id_store"
        if s_col in df_stores_side.columns:
            for _, s_row in df_stores_side.iterrows():
                store_giro_map[str(s_row[s_col]).strip()] = str(s_row.get("giro", "") or "").strip()

    def _lookup_giro_mob(sid_val: Any) -> str:
        s_clean = str(sid_val or "").strip()
        base_s = s_clean[:-1] if s_clean.endswith("B") else s_clean
        return store_giro_map.get(s_clean) or store_giro_map.get(base_s) or ""

    df_b_date = df_b_date.copy()
    df_b_date["giro_num"] = df_b_date["id_store"].map(_lookup_giro_mob)
    all_giri_m = sorted([g for g in df_b_date["giro_num"].unique() if str(g).strip()])

    with c_m_giro:
        mob_giro = st.selectbox(
            "🚛 Giro",
            options=["TUTTI"] + all_giri_m,
            key="mob2_giro_sb",
        )

    if mob_giro != "TUTTI":
        df_b_date = df_b_date[df_b_date["giro_num"] == mob_giro].copy()

    df_b_date["spuntato"] = pd.to_numeric(df_b_date.get("spuntato", 0), errors="coerce").fillna(0).astype(int)
    df_b_date = df_b_date.sort_values(by=["giro_num", "id_store", "tipo_cons"]).reset_index(drop=True)

    tot_stores = len(df_b_date)
    spuntati_df = df_b_date[df_b_date["spuntato"] == 1].reset_index(drop=True)
    da_spuntare_df = df_b_date[df_b_date["spuntato"] == 0].reset_index(drop=True)
    n_spuntati = len(spuntati_df)
    n_da_spuntare = len(da_spuntare_df)

    # Pill stato avanzamento
    pct_done = int(round((n_spuntati / tot_stores) * 100)) if tot_stores > 0 else 0
    st.markdown(f"""
    <div style="background: #0F172A; color: #FFFFFF; border-radius: 10px; padding: 8px 14px; margin-bottom: 12px;
                display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 700;">
        <span>📊 Avanzamento Spunta: <strong style="color: #34D399;">{n_spuntati}/{tot_stores}</strong> negozi ({pct_done}%)</span>
        <span style="color: #FBBF24;">⏳ Da contare: {n_da_spuntare}</span>
    </div>
    """, unsafe_allow_html=True)

    # ==========================================================================
    # I DUE GRANDI TASTI MOBILE (SCELTA OPERAZIONE)
    # ==========================================================================
    if "mob2_mode" not in st.session_state:
        st.session_state["mob2_mode"] = "spunta"

    st.markdown("""
    <style>
    div[data-testid="stButton"] > button {
        min-height: 60px !important;
        font-size: 16px !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        is_spunta_mode = (st.session_state["mob2_mode"] == "spunta")
        if st.button(
            f"📋 1. SPUNTA NEGOZIO ({n_da_spuntare})",
            type="primary" if is_spunta_mode else "secondary",
            use_container_width=True,
            key="mob2_big_btn_spunta",
        ):
            st.session_state["mob2_mode"] = "spunta"
            st.rerun()

    with col_btn2:
        is_add_mode = (st.session_state["mob2_mode"] == "aggiungi")
        if st.button(
            f"➕ 2. AGGIUNGI COLLI ({n_spuntati})",
            type="primary" if is_add_mode else "secondary",
            use_container_width=True,
            key="mob2_big_btn_aggiungi",
        ):
            st.session_state["mob2_mode"] = "aggiungi"
            st.rerun()

    st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

    # ==========================================================================
    # MODALITÀ 1: 📋 SPUNTA NEGOZIO
    # ==========================================================================
    if st.session_state["mob2_mode"] == "spunta":
        show_all = st.checkbox(
            f"Mostra anche i negozi già spuntati ({tot_stores} totali)",
            value=(n_da_spuntare == 0),
            key="mob2_show_all_chk",
        )
        working_df = df_b_date if (show_all or n_da_spuntare == 0) else da_spuntare_df

        if working_df.empty:
            st.success("🎉 Tutti i negozi del giro sono stati spuntati!")
            return

        if "mob2_idx" not in st.session_state or st.session_state["mob2_idx"] >= len(working_df):
            st.session_state["mob2_idx"] = 0

        curr_idx = int(st.session_state["mob2_idx"])

        # Navigatore Precedente / Scelta Negozio / Successivo
        c_prev, c_pick, c_next = st.columns([1, 2.6, 1])
        with c_prev:
            if st.button("◀️ PREC", use_container_width=True, disabled=(curr_idx <= 0), key="mob2_prev_btn"):
                st.session_state["mob2_idx"] = max(0, curr_idx - 1)
                st.rerun()
        with c_pick:
            store_labels = [
                f"{'🟢' if int(r['spuntato']) == 1 else '⏳'} {r['id_store']} - {str(r['store_name'])[:18]} ({'/9' if str(r['tipo_cons']).upper() == 'DOPPIA' else '/0'})"
                for _, r in working_df.iterrows()
            ]
            picked_idx = st.selectbox(
                "Scegli Negozio",
                options=list(range(len(working_df))),
                index=curr_idx,
                format_func=lambda i: store_labels[i],
                key="mob2_pick_store_sb",
                label_visibility="collapsed",
            )
            if picked_idx != curr_idx:
                st.session_state["mob2_idx"] = picked_idx
                st.rerun()
        with c_next:
            if st.button("SUCC ▶️", use_container_width=True, disabled=(curr_idx >= len(working_df) - 1), key="mob2_next_btn"):
                st.session_state["mob2_idx"] = min(len(working_df) - 1, curr_idx + 1)
                st.rerun()

        b_row = working_df.iloc[curr_idx]
        bid = int(b_row["id"])
        sid = str(b_row["id_store"])
        sname = str(b_row.get("store_name", ""))
        giro_lbl = str(b_row.get("giro_num", "")) or "—"
        tipo_lbl = "/9 DOPPIA" if str(b_row.get("tipo_cons", "")).upper() == "DOPPIA" else "/0 STD"
        is_done = int(b_row.get("spuntato", 0)) == 1

        prev_abb = int(round(float(b_row.get("prev_abbigl", b_row.get("colli_abbigl", 0)) or 0)))
        prev_cal = int(round(float(b_row.get("prev_calzat", b_row.get("colli_calzat", 0)) or 0)))
        prev_eco = int(round(float(b_row.get("prev_ecom", b_row.get("colli_ecom", 0)) or 0)))
        prev_oth = int(round(float(b_row.get("prev_others", b_row.get("colli_others", 0)) or 0)))
        prev_var = int(round(float(b_row.get("prev_vario", b_row.get("colli_vario", 0)) or 0)))
        prev_tot = prev_abb + prev_cal + prev_eco + prev_oth + prev_var

        cur_abb = int(round(float(b_row.get("colli_abbigl", 0) or 0)))
        cur_cal = int(round(float(b_row.get("colli_calzat", 0) or 0)))
        cur_eco = int(round(float(b_row.get("colli_ecom", 0) or 0)))
        cur_oth = int(round(float(b_row.get("colli_others", 0) or 0)))
        cur_var = int(round(float(b_row.get("colli_vario", 0) or 0)))

        badge_bg = "#065F46" if is_done else "#1E3A8A"
        badge_status = "🟢 GIÀ SPUNTATO" if is_done else "⏳ DA SPUNTARE"

        st.markdown(f"""
        <div style="background: {badge_bg}; color: white; border-radius: 14px; padding: 14px 18px; margin: 8px 0 12px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 12px; font-weight: 800; background: rgba(255,255,255,0.2); padding: 3px 10px; border-radius: 99px;">
                    {giro_lbl} • {tipo_lbl}
                </span>
                <span style="font-size: 12px; font-weight: 800;">{badge_status}</span>
            </div>
            <div style="font-size: 24px; font-weight: 900; margin-top: 6px;">
                🏪 {sid} — {html.escape(sname)}
            </div>
            <div style="font-size: 15px; font-weight: 700; color: #93C5FD; margin-top: 4px;">
                📦 Totale Previsto: <strong style="color: #FDE047; font-size: 18px;">{prev_tot} colli</strong>
                (Abb: {prev_abb} | Calz: {prev_cal} | Ecom: {prev_eco} | Altri: {prev_oth})
            </div>
        </div>
        """, unsafe_allow_html=True)

        # TASTONE 1-TAP: CONFORME AL PREVISTO (SALVA SUBITO!)
        if st.button(
            f"⚡ CONFORME AL PREVISTO ({prev_tot} COLLI) — CONFERMA 1-TAP",
            type="primary",
            use_container_width=True,
            key=f"mob2_1tap_ok_{bid}",
        ):
            res_sp = confirm_bolla_spunta(bid, use_expected=True)
            if res_sp["status"] == "ok":
                st.session_state["flash_bolle_msg"] = (
                    f"Spunta confermata per Store {sid} ({sname}): {res_sp['total_colli']} colli!"
                )
                st.session_state["_scroll_to_top"] = True
                st.rerun()

        # MODIFICA MANUALE COLLI SE DIVERSI DAL PREVISTO
        with st.container(border=True):
            st.markdown("**✏️ Oppure inserisci le quantità effettive contate:**")
            c_i1, c_i2 = st.columns(2)
            with c_i1:
                in_abb = st.number_input(f"👗 Abbigliamento (Prev: {prev_abb})", min_value=0, value=cur_abb, step=1, key=f"m2_abb_{bid}")
                in_eco = st.number_input(f"📦 E-Commerce (Prev: {prev_eco})", min_value=0, value=cur_eco, step=1, key=f"m2_eco_{bid}")
            with c_i2:
                in_cal = st.number_input(f"👟 Calzature (Prev: {prev_cal})", min_value=0, value=cur_cal, step=1, key=f"m2_cal_{bid}")
                in_oth = st.number_input(f"📦 Altri Bultos (Prev: {prev_oth})", min_value=0, value=cur_oth, step=1, key=f"m2_oth_{bid}")
            in_var = st.number_input(f"📦 Materiale Vario (Prev: {prev_var})", min_value=0, value=cur_var, step=1, key=f"m2_var_{bid}")
            in_note = st.text_input("📝 Note Banchina (opzionale)", value=str(b_row.get("note", "") or ""), key=f"m2_note_{bid}")

            manual_tot = int(in_abb + in_cal + in_eco + in_oth + in_var)
            if st.button(
                f"💾 CONFERMA SPUNTA ({manual_tot} COLLI)",
                type="secondary",
                use_container_width=True,
                key=f"mob2_save_manual_{bid}",
            ):
                res_sp = confirm_bolla_spunta(
                    bid,
                    use_expected=False,
                    colli_abbigl=int(in_abb),
                    colli_calzat=int(in_cal),
                    colli_ecom=int(in_eco),
                    colli_others=int(in_oth),
                    colli_vario=int(in_var),
                    note=in_note,
                )
                if res_sp["status"] == "ok":
                    st.session_state["flash_bolle_msg"] = (
                        f"Spunta salvata per Store {sid} ({sname}): {res_sp['total_colli']} colli!"
                    )
                    st.session_state["_scroll_to_top"] = True
                    st.rerun()

    # ==========================================================================
    # MODALITÀ 2: ➕ AGGIUNGI COLLI A NEGOZI GIÀ SPUNTATI
    # ==========================================================================
    else:
        if spuntati_df.empty:
            st.info("ℹ️ Nessun negozio risulta ancora spuntato per questa data/giro. Spunta prima almeno un negozio!")
            if st.button("📋 Vai a Spunta Negozio", type="primary", use_container_width=True, key="mob2_back_to_spunta"):
                st.session_state["mob2_mode"] = "spunta"
                st.rerun()
            return

        with st.container(border=True):
            st.markdown("#### ➕ Aggiungi Colli a Negozio Già Spuntato (`🟢`)")

            spuntati_opts: Dict[int, str] = {}
            for _, s_r in spuntati_df.iterrows():
                s_bid = int(s_r["id"])
                s_id = str(s_r["id_store"])
                s_nm = str(s_r.get("store_name", ""))
                s_gr = str(s_r.get("giro_num", "")) or "—"
                s_tc = "/9" if str(s_r.get("tipo_cons", "")).upper() == "DOPPIA" else "/0"
                s_tot = sum(
                    int(round(float(s_r.get(k, 0) or 0)))
                    for k in ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario"]
                )
                spuntati_opts[s_bid] = f"🟢 {s_id} - {s_nm} [{s_gr} • {s_tc}] — Attuali: {s_tot} colli"

            target_bid = st.selectbox(
                "1️⃣ Seleziona il Negozio Già Spuntato",
                options=list(spuntati_opts.keys()),
                format_func=lambda k: spuntati_opts[k],
                key="mob2_add_store_sb",
            )

            if "mob2_add_qty" not in st.session_state:
                st.session_state["mob2_add_qty"] = 1

            st.markdown("**2️⃣ Tocca un tasto rapido o inserisci i colli da aggiungere:**")
            q_c1, q_c2, q_c3, q_c4 = st.columns(4)
            with q_c1:
                if st.button("➕ 1", use_container_width=True, key="mob2_q_1"):
                    st.session_state["mob2_add_qty"] = 1
                    st.rerun()
            with q_c2:
                if st.button("➕ 2", use_container_width=True, key="mob2_q_2"):
                    st.session_state["mob2_add_qty"] = 2
                    st.rerun()
            with q_c3:
                if st.button("➕ 5", use_container_width=True, key="mob2_q_5"):
                    st.session_state["mob2_add_qty"] = 5
                    st.rerun()
            with q_c4:
                if st.button("➕ 10", use_container_width=True, key="mob2_q_10"):
                    st.session_state["mob2_add_qty"] = 10
                    st.rerun()

            c_qty, c_cat = st.columns([1, 1.4])
            with c_qty:
                qty_to_add = st.number_input(
                    "🔢 Quantità da aggiungere",
                    min_value=1,
                    max_value=500,
                    value=int(st.session_state["mob2_add_qty"]),
                    step=1,
                    key="mob2_add_qty_input",
                )
                st.session_state["mob2_add_qty"] = int(qty_to_add)
            with c_cat:
                cat_map = {
                    "colli_abbigl": "👗 Abbigliamento",
                    "colli_calzat": "👟 Calzature",
                    "colli_ecom": "📦 E-Commerce",
                    "colli_others": "📦 Altri Bultos",
                    "colli_vario": "📦 Materiale Vario",
                }
                cat_choice = st.selectbox(
                    "📦 Categoria Colli",
                    options=list(cat_map.keys()),
                    format_func=lambda k: cat_map[k],
                    key="mob2_add_cat_sb",
                )

            reason_note = st.text_input(
                "📝 Nota opzionale (es. fine scarico, bancale extra)",
                placeholder="Opzionale...",
                key="mob2_add_reason",
            )

            if st.button(
                f"✅ AGGIUNGI +{int(qty_to_add)} COLLI ORA",
                type="primary",
                use_container_width=True,
                key="mob2_confirm_add_btn",
            ):
                res_add = add_colli_to_bolla_spuntata(
                    bolla_id=int(target_bid),
                    colli_to_add=int(qty_to_add),
                    category=cat_choice,
                    note_reason=reason_note,
                )
                if res_add.get("status") == "ok":
                    st.session_state["flash_bolle_msg"] = (
                        f"Aggiunti +{res_add['added_colli']} colli ({res_add['category_label']}) a Store {res_add['id_store']} ({res_add['store_name']})! "
                        f"Nuovo totale: {res_add['new_total_colli']} colli."
                    )
                    st.session_state["_scroll_to_top"] = True
                    st.rerun()
                else:
                    st.error(res_add.get("message", "Errore durante l'aggiunta colli."))
