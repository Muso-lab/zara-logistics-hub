from typing import Dict, Any, List, Optional, Tuple, Union
import sys
import importlib
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
import io
import sqlite3
import json
import threading
import html
import hmac
import hashlib

# Optional dynamic module reload for development mode only (disabled in production for fast load)
import os
if os.getenv("DEV_RELOAD_MODULES") == "1":
    for _mod in [
        "src.config", "src.utils", "src.cloud_sync", "src.db", "src.parsers",
        "src.engine", "src.pipeline", "src.bolle_manager", "src.exporters",
        "src.mailer", "src.components"
    ]:
        if _mod in sys.modules:
            try:
                importlib.reload(sys.modules[_mod])
            except Exception:
                pass

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
    load_run_data,
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
    get_vehicles_df,
    add_vehicle_record,
    update_vehicle_record,
    delete_vehicle_record,
    bulk_update_vehicles,
    get_email_config,
    save_email_config,
)
from src.parsers import classify_uploaded_files
from src.engine import evaluate_pedane, compute_planning_roma
from src.pipeline import run_pipeline
import src.bolle_manager as bm

# Safe resolution of bolle manager functions with auto-reload protection
if not hasattr(bm, "export_bolle_excel"):
    try:
        importlib.reload(bm)
    except Exception:
        pass

init_bolle_tables = bm.init_bolle_tables
get_bolle_dates = bm.get_bolle_dates
get_all_drivers = bm.get_all_drivers
get_all_carriers = bm.get_all_carriers
get_store_delivery_profile = bm.get_store_delivery_profile
get_bolle = bm.get_bolle
get_bolla_by_id = bm.get_bolla_by_id
save_or_update_bolla = bm.save_or_update_bolla
delete_bolla = bm.delete_bolla
delete_bolle_by_date = bm.delete_bolle_by_date
generate_bolle_from_forecast = bm.generate_bolle_from_forecast
get_actuals_for_planner = bm.get_actuals_for_planner
render_bolla_printable_html = bm.render_bolla_printable_html
format_intershops_string = bm.format_intershops_string
export_bolle_excel = getattr(bm, "export_bolle_excel", None)
if export_bolle_excel is None:
    from src.exporters import export_bolle_excel
from src.exporters import export_planner_roma, export_sintesi_operativa, export_sga_file
from src.mailer import send_operativa_email, send_test_email, build_operativa_zip
from src.scraper import InditexExtranetScraper
from src.utils import get_cycle_date_range, format_number_it, format_date_it, parse_date_obj
from src.components import (
    render_lavorazioni_piattaforma,
    render_spunta_arrivi_modern,
    render_riepilogo_giri_modern,
    render_anagrafica_negozi_modern,
    render_parco_mezzi_modern,
    _giro_sort_key,
    _inject_modern_css,
)

# ==============================================================================
# CONFIGURAZIONE PAGINA & STILE
# ==============================================================================
st.set_page_config(
    page_title="Zara Logistics Hub",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# PWA & Mobile Installation Manifest, Meta-Tags & Icons
st.markdown("""
<head>
    <meta name="application-name" content="Zara Logistics Hub">
    <meta name="apple-mobile-web-app-title" content="Zara Logistics">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="theme-color" content="#1E3A8A">
    <link rel="manifest" href="/app/static/manifest.json">
    <link rel="apple-touch-icon" href="/app/static/icon-192.png">
    <link rel="icon" type="image/png" sizes="192x192" href="/app/static/icon-192.png">
    <link rel="icon" type="image/png" sizes="512x512" href="/app/static/icon-512.png">
</head>
<script>
    try {
        const topDoc = (window.parent && window.parent.document) ? window.parent.document : document;
        topDoc.title = "Zara Logistics Hub";
        
        let linkManifest = topDoc.querySelector('link[rel="manifest"]');
        if (!linkManifest) {
            linkManifest = topDoc.createElement('link');
            linkManifest.rel = 'manifest';
            linkManifest.href = '/app/static/manifest.json';
            topDoc.head.appendChild(linkManifest);
        }
        
        let appleTitle = topDoc.querySelector('meta[name="apple-mobile-web-app-title"]');
        if (!appleTitle) {
            appleTitle = topDoc.createElement('meta');
            appleTitle.name = 'apple-mobile-web-app-title';
            appleTitle.content = 'Zara Logistics';
            topDoc.head.appendChild(appleTitle);
        }

        let appName = topDoc.querySelector('meta[name="application-name"]');
        if (!appName) {
            appName = topDoc.createElement('meta');
            appName.name = 'application-name';
            appName.content = 'Zara Logistics';
            topDoc.head.appendChild(appName);
        }

        let appleIcon = topDoc.querySelector('link[rel="apple-touch-icon"]');
        if (!appleIcon) {
            appleIcon = topDoc.createElement('link');
            appleIcon.rel = 'apple-touch-icon';
            appleIcon.href = '/app/static/icon-192.png';
            topDoc.head.appendChild(appleIcon);
        }
    } catch(e) {}
</script>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    
    /* Hide Streamlit Default UI elements for full custom branding */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    header {visibility: hidden !important;}
    [data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
    [data-testid="stDecoration"] {visibility: hidden !important; display: none !important;}
    [data-testid="stStatusWidget"] {visibility: hidden !important;}

    /* =========================================================================
       PREVIENE LA TRASLUCIDITA' E MOSTRA UN CHIARO INDICATORE DI ELABORAZIONE
       ========================================================================= */
    /* Evita che l'app sbiadisca in modo trasparente e dia l'impressione di blocco */
    div[data-test-script-state="running"] [data-testid="stAppViewContainer"] > .main {
        opacity: 0.72 !important;
        filter: grayscale(10%) blur(0.2px) !important;
        pointer-events: none !important;
        transition: opacity 0.15s ease-in-out !important;
    }

    /* Barra di Navigazione Mobile Touch (Pulsanti Chiari in Basso su Smartphone) */
    .mobile-bottom-nav {
        display: none;
    }
    .mobile-top-bar {
        display: none;
    }
    @media (max-width: 900px) {
        .mobile-bottom-nav {
            display: block !important;
            position: fixed !important;
            bottom: 0 !important;
            left: 0 !important;
            right: 0 !important;
            background: #FFFFFF !important;
            border-top: 2px solid #CBD5E1 !important;
            box-shadow: 0 -4px 18px rgba(15, 23, 42, 0.15) !important;
            padding: 8px 10px 14px 10px !important;
            z-index: 999999 !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            padding-bottom: 95px !important;
        }
        .mobile-top-bar {
            display: flex !important;
            gap: 6px !important;
            margin-bottom: 14px !important;
            overflow-x: auto !important;
            padding-bottom: 4px !important;
        }
        .mobile-top-bar button {
            white-space: nowrap !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            padding: 8px 14px !important;
            border-radius: 8px !important;
        }
    }

    /* Floating Processing Banner centrale ad alto impatto visivo */
    div[data-test-script-state="running"]::after {
        content: "⏳ Elaborazione in corso... Attendere prego";
        position: fixed;
        top: 22px;
        left: 50%;
        transform: translateX(-50%);
        background: #0F172A;
        color: #FFFFFF;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 14px;
        font-weight: 700;
        padding: 10px 26px;
        border-radius: 9999px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 0 0 2px #38BDF8;
        z-index: 9999999 !important;
        letter-spacing: 0.3px;
        display: block !important;
        animation: pulse-loader 1.5s infinite ease-in-out;
        pointer-events: none;
    }

    @keyframes pulse-loader {
        0%, 100% {
            transform: translateX(-50%) scale(1);
            box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.6), 0 0 0 2px #38BDF8;
        }
        50% {
            transform: translateX(-50%) scale(1.03);
            box-shadow: 0 14px 30px -5px rgba(15, 23, 42, 0.8), 0 0 0 3px #0284C7;
        }
    }

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

    
    /* =========================================================================
       FORCE GLOBAL LIGHT MODE & BRANDED CORPORATE PALETTE
       ========================================================================= */
    :root {
        color-scheme: light !important;
    }
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        color-scheme: light !important;
    }
    [data-testid="stAppViewContainer"] > .main {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
    }

    /* Force all form inputs to readable light mode */
    input, select, textarea, [data-baseweb="input"], [data-baseweb="select"] {
        color: #0F172A !important;
        background-color: #FFFFFF !important;
        -webkit-text-fill-color: #0F172A !important;
    }

    /* Radio navigation labels in sidebar - crystal clear high contrast */
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
        color: #64748B !important;
        font-weight: 700 !important;
        font-size: 11px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        margin-bottom: 6px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 8px !important;
        padding: 6px 10px !important;
        margin-bottom: 6px !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
        display: flex !important;
        align-items: center !important;
        transition: all 0.15s ease !important;
        width: 100% !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background-color: #F1F5F9 !important;
        border-color: #CBD5E1 !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label p {
        color: #0F172A !important;
        font-size: 13.5px !important;
        font-weight: 700 !important;
        line-height: 1.3 !important;
        margin: 0 !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] {
        width: 100% !important;
    }

    /* Executive Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.2rem !important;
    }
    .sidebar-brand-card {
        background: linear-gradient(135deg, #1E3A8A 0%, #0F172A 100%);
        padding: 14px 16px;
        border-radius: 12px;
        margin-bottom: 12px;
        color: white;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.15);
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .sidebar-brand-icon {
        font-size: 26px;
        line-height: 1;
    }
    .sidebar-brand-title {
        font-size: 14.5px;
        font-weight: 800;
        letter-spacing: 0.5px;
        color: #FFFFFF;
        line-height: 1.2;
    }
    .sidebar-brand-subtitle {
        font-size: 11px;
        opacity: 0.85;
        font-weight: 500;
        color: #93C5FD;
    }
    .sidebar-user-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .role-badge {
        padding: 2.5px 8px;
        border-radius: 9999px;
        font-size: 10px;
        font-weight: 800;
        letter-spacing: 0.4px;
        display: inline-block;
    }
    .sidebar-metrics-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 10px 12px;
        margin-top: 14px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .sidebar-metric-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px;
        margin-top: 6px;
    }
    .sidebar-metric-box {
        background: #F8FAFC;
        border: 1px solid #EDF2F7;
        border-radius: 8px;
        padding: 6px 8px;
        text-align: center;
    }
    .sidebar-metric-box .metric-val {
        font-size: 13.5px;
        font-weight: 800;
        color: #0F172A;
    }
    .sidebar-metric-box .metric-lbl {
        font-size: 9.5px;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
    }
    .sidebar-cloud-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource(show_spinner=False)
def _initialize_system_once():
    """Esegue l'inizializzazione del database una sola volta all'avvio del processo (veloce e non bloccante)."""
    try:
        init_db()
        init_bolle_tables()
        seed_anagrafica_if_empty()
    except Exception:
        pass
    return True

_initialize_system_once()

# ==============================================================================
# SISTEMA DI LOGIN CON PERSISTENZA SESSIONE (PC & SMARTPHONE REFRESH)
# ==============================================================================
AUTH_SECRET = "zara_monterotondo_hub_secret_2026"

def create_auth_token(username: str, role: str) -> str:
    """Generates an HMAC-signed session token to persist authentication across browser reloads."""
    msg = f"{username}:{role}".encode("utf-8")
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:24]
    return f"{username}_{role}_{sig}"

def verify_auth_token(token: str):
    """Verifies HMAC signature of session token."""
    if not token or not isinstance(token, str):
        return None
    parts = token.split("_")
    if len(parts) != 3:
        return None
    u, r, sig = parts
    expected = create_auth_token(u, r)
    if hmac.compare_digest(token, expected):
        return u, r
    return None

# ==============================================================================
# CONFIGURAZIONE DEI 3 LIVELLI DI ACCESSO (RUOLI & PERMESSI)
# ==============================================================================
ROLE_CONFIG = {
    "admin": {
        "label": "Amministratore (Admin)",
        "badge_color": "#B45309",
        "badge_bg": "#FEF3C7",
        "badge_border": "#F59E0B",
        "icon": "👑",
        "menu_options": [
            "📥 1. Previsione & Arrivi",
            "🚚 2. Bolle di Consegna",
            "📱 3. Spunta Banchina (Mobile)",
            "📊 4. Consuntivo & Planner Inditex",
            "🏢 5. Anagrafica Negozi & Giri",
            "⚙️ 6. Impostazioni, Email & Backup",
        ],
        "can_edit_settings": True,
        "can_delete_runs": True,
        "can_delete_bolle": True,
        "can_edit_master_data": True,
        "can_send_emails": True,
        "can_execute_runs": True,
        "can_edit_bolle": True,
    },
    "ufficio": {
        "label": "Ufficio Traffico & Logistica",
        "badge_color": "#0369A1",
        "badge_bg": "#E0F2FE",
        "badge_border": "#38BDF8",
        "icon": "💼",
        "menu_options": [
            "📥 1. Previsione & Arrivi",
            "🚚 2. Bolle di Consegna",
            "📱 3. Spunta Banchina (Mobile)",
            "📊 4. Consuntivo & Planner Inditex",
            "🏢 5. Anagrafica Negozi & Giri",
        ],
        "can_edit_settings": False,
        "can_delete_runs": True,
        "can_delete_bolle": True,
        "can_edit_master_data": True,
        "can_send_emails": True,
        "can_execute_runs": True,
        "can_edit_bolle": True,
    },
    "magazzino": {
        "label": "Banchina & Magazzino",
        "badge_color": "#047857",
        "badge_bg": "#D1FAE5",
        "badge_border": "#34D399",
        "icon": "📦",
        "menu_options": [
            "📱 1. Spunta Banchina (Mobile)",
            "📥 2. Previsione & Arrivi",
            "🚚 3. Bolle di Consegna",
        ],
        "can_edit_settings": False,
        "can_delete_runs": False,
        "can_delete_bolle": False,
        "can_edit_master_data": False,
        "can_send_emails": False,
        "can_execute_runs": False,
        "can_edit_bolle": False,
    },
}

def get_role_info():
    r = st.session_state.get("auth_role", "magazzino")
    return ROLE_CONFIG.get(r, ROLE_CONFIG["magazzino"])

def has_perm(perm_key: str) -> bool:
    return get_role_info().get(perm_key, False)

def is_admin() -> bool:
    return st.session_state.get("auth_role") == "admin"

def is_ufficio() -> bool:
    return st.session_state.get("auth_role") in ("admin", "ufficio")

def is_magazzino() -> bool:
    return st.session_state.get("auth_role") == "magazzino"

def _get_auth_users() -> dict:
    """
    Restituisce la mappa degli utenti abilitati sui 3 livelli di accesso:
    - 'admin': Amministratore (pieno accesso operativo e configurazioni)
    - 'ufficio': Ufficio Traffico & Gestione Spedizioni
    - 'magazzino': Magazzino & Banchina (spunta arrivi, pedane e stampa bolle)
    """
    import os
    admin_pwd = os.getenv("ZARA_ADMIN_PASS", "zara2026").strip()
    ufficio_pwd = os.getenv("ZARA_UFFICIO_PASS", "traffico2026").strip()
    magazzino_pwd = os.getenv("ZARA_MAGAZZINO_PASS", os.getenv("ZARA_VIEWER_PASS", "banchina2026")).strip()

    try:
        if hasattr(st, "secrets"):
            if "ZARA_ADMIN_PASS" in st.secrets:
                admin_pwd = str(st.secrets["ZARA_ADMIN_PASS"]).strip()
            if "ZARA_UFFICIO_PASS" in st.secrets:
                ufficio_pwd = str(st.secrets["ZARA_UFFICIO_PASS"]).strip()
            if "ZARA_MAGAZZINO_PASS" in st.secrets:
                magazzino_pwd = str(st.secrets["ZARA_MAGAZZINO_PASS"]).strip()
            elif "ZARA_VIEWER_PASS" in st.secrets:
                magazzino_pwd = str(st.secrets["ZARA_VIEWER_PASS"]).strip()
    except Exception:
        pass

    return {
        "admin": {"password": admin_pwd, "role": "admin", "label": "Amministratore (Admin)"},
        "luciano": {"password": admin_pwd, "role": "admin", "label": "Luciano (Admin)"},
        "ufficio": {"password": ufficio_pwd, "role": "ufficio", "label": "Ufficio Traffico & Logistica"},
        "traffico": {"password": ufficio_pwd, "role": "ufficio", "label": "Ufficio Traffico & Logistica"},
        "magazzino": {"password": magazzino_pwd, "role": "magazzino", "label": "Banchina & Magazzino"},
        "banchina": {"password": magazzino_pwd, "role": "magazzino", "label": "Banchina & Magazzino"},
        "ospite": {"password": magazzino_pwd, "role": "magazzino", "label": "Ospite (Consultazione)"},
        "viewer": {"password": magazzino_pwd, "role": "magazzino", "label": "Consultazione Banchina"},
    }

users_map = _get_auth_users()

# Recupera automaticamente la sessione autenticata dai query params dell'URL
if not st.session_state.get("authenticated", False):
    tok = st.query_params.get("session")
    if tok:
        verified = verify_auth_token(tok)
        if verified:
            u, r = verified
            if u in users_map and users_map[u]["role"] == r:
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = u
                st.session_state["auth_role"] = r
                st.session_state["auth_label"] = users_map[u]["label"]

if not st.session_state.get("authenticated", False):
    c_l1, c_l2, c_l3 = st.columns([1.1, 1.8, 1.1])
    with c_l2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background: white; border: 1px solid #E2E8F0; border-radius: 14px; padding: 24px; box-shadow: 0 4px 16px rgba(15,23,42,0.08); margin-bottom: 20px;">
            <div style="text-align: center; margin-bottom: 16px;">
                <span style="font-size: 38px;">🚚</span>
                <h2 style="color: #1E3A8A; margin: 6px 0 2px 0; font-size: 22px; font-weight: 800;">ZARA LOGISTICS HUB</h2>
                <div style="color: #64748B; font-size: 13px;">Hub Monterotondo (RM) — Accesso Operativo Riservato</div>
            </div>
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; font-size: 12px; color: #334155;">
                <div style="font-weight: 700; margin-bottom: 4px;">Profili Operativi Configurati:</div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span style="background:#FEF3C7; color:#B45309; border:1px solid #F59E0B; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700;">👑 Admin</span>
                    <span style="background:#E0F2FE; color:#0369A1; border:1px solid #38BDF8; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700;">💼 Ufficio Traffico</span>
                    <span style="background:#D1FAE5; color:#047857; border:1px solid #34D399; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700;">📦 Magazzino / Banchina</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            inp_user = st.text_input("👤 Nome Utente", placeholder="es. admin, ufficio, oppure magazzino").strip().lower()
            inp_pass = st.text_input("🔑 Password", type="password", placeholder="Inserisci la password").strip()
            btn_login = st.form_submit_button("ACCEDI ALLA PIATTAFORMA", type="primary", use_container_width=True)
            if btn_login:
                if inp_user in users_map and inp_pass == users_map[inp_user]["password"]:
                    role = users_map[inp_user]["role"]
                    st.session_state["authenticated"] = True
                    st.session_state["auth_user"] = inp_user
                    st.session_state["auth_role"] = role
                    st.session_state["auth_label"] = users_map[inp_user]["label"]
                    st.query_params["session"] = create_auth_token(inp_user, role)
                    st.rerun()
                else:
                    st.error("❌ Credenziali non valide. Verifica utente e password.")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

USER_ROLE = st.session_state.get("auth_role", "magazzino")
IS_ADMIN = USER_ROLE == "admin"

# ==============================================================================
# SIDEBAR: NAVIGAZIONE & STATO OPERATIVO ELEGANTE
# ==============================================================================
role_info = get_role_info()
r_color = role_info["badge_color"]
r_bg = role_info["badge_bg"]
r_border = role_info["badge_border"]
r_icon = role_info["icon"]
r_label = st.session_state.get("auth_label", role_info["label"])

st.sidebar.markdown(f"""
<div class="sidebar-brand-card">
    <div class="sidebar-brand-icon">🚚</div>
    <div>
        <div class="sidebar-brand-title">ZARA LOGISTICS</div>
        <div class="sidebar-brand-subtitle">Hub Monterotondo (RM)</div>
    </div>
</div>

<div class="sidebar-user-card">
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
        <span style="font-size: 10px; font-weight: 700; color: #64748B; text-transform: uppercase;">PROFILO ATTIVO</span>
        <span class="role-badge" style="background: {r_bg}; color: {r_color}; border: 1px solid {r_border};">
            {r_icon} {USER_ROLE.upper()}
        </span>
    </div>
    <div style="font-size: 13px; font-weight: 700; color: #0F172A;">{r_label}</div>
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("🚪 Esci dalla Sessione", use_container_width=True, key="btn_logout_sidebar"):
    for k in ["authenticated", "auth_user", "auth_role", "auth_label"]:
        st.session_state.pop(k, None)
    st.query_params.clear()
    st.rerun()

MENU_OPTIONS = role_info["menu_options"]
if st.session_state.get("nav_menu") not in MENU_OPTIONS:
    st.session_state["nav_menu"] = MENU_OPTIONS[0]

menu = st.sidebar.radio(
    "Flusso Operativo",
    MENU_OPTIONS,
    index=MENU_OPTIONS.index(st.session_state["nav_menu"]),
    key="sidebar_nav_radio",
)
st.session_state["nav_menu"] = menu

# Barra Tasti Rapidi Touch per Mobile (Alternativa al menu laterale su smartphone)
st.markdown('<div class="mobile-top-bar">', unsafe_allow_html=True)
mob_nav_cols = st.columns(len(MENU_OPTIONS))
for m_idx, m_opt in enumerate(MENU_OPTIONS):
    m_short = m_opt.split(". ")[-1] if ". " in m_opt else m_opt
    m_icon = m_opt.split(" ")[0] if " " in m_opt else "📌"
    m_is_act = (menu == m_opt)
    with mob_nav_cols[m_idx]:
        if st.button(f"{m_icon} {m_short}", key=f"mob_nav_btn_{m_idx}", type="primary" if m_is_act else "secondary", use_container_width=True):
            st.session_state["nav_menu"] = m_opt
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

df_stores_side = get_stores_df()
runs_side = get_all_runs()

# Auto-restore trasparente da Google Sheets all'avvio se il database locale del container è vuoto
if "cloud_auto_checked" not in st.session_state:
    st.session_state["cloud_auto_checked"] = True
    if get_cloud_url():
        try:
            if runs_side.empty or len(df_stores_side) < 10:
                r_pull = pull_all_from_cloud(timeout=15)
                if r_pull.get("status") == "ok":
                    df_stores_side = get_stores_df()
                    runs_side = get_all_runs()
        except Exception:
            pass

base_stores_side = df_stores_side[~df_stores_side["store_id"].astype(str).str.endswith("B")] if not df_stores_side.empty else pd.DataFrame()
active_stores_cnt = int((base_stores_side["attivo"].fillna("SI").str.upper() == "SI").sum()) if not base_stores_side.empty else 0
sdopp_stores_cnt = int((base_stores_side["sdoppiamento_b9"].fillna("NO").str.upper() == "SI").sum()) if not base_stores_side.empty else 0

total_bolle_db = 0
try:
    with sqlite3.connect(DB_PATH) as c_b:
        total_bolle_db = c_b.cursor().execute("SELECT COUNT(*) FROM bolle").fetchone()[0]
except Exception:
    pass

last_run_disp = f"#{int(runs_side.iloc[0]['id'])}" if not runs_side.empty else "—"

st.sidebar.markdown(f"""
<div class="sidebar-metrics-card">
    <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; margin-bottom: 8px;">📊 Stato Piattaforma</div>
    <div class="sidebar-metric-grid">
        <div class="sidebar-metric-box">
            <div class="metric-val">{active_stores_cnt}</div>
            <div class="metric-lbl">Negozi Attivi</div>
        </div>
        <div class="sidebar-metric-box">
            <div class="metric-val">{sdopp_stores_cnt}</div>
            <div class="metric-lbl">Sdopp. /9</div>
        </div>
        <div class="sidebar-metric-box">
            <div class="metric-val">{last_run_disp}</div>
            <div class="metric-lbl">Ultima Run</div>
        </div>
        <div class="sidebar-metric-box">
            <div class="metric-val">{format_number_it(total_bolle_db, 0)}</div>
            <div class="metric-lbl">Bolle DB</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if get_cloud_url():
    st.sidebar.markdown("""
    <div class="sidebar-cloud-card">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-size: 10px; font-weight: 700; color: #64748B; text-transform: uppercase;">CLOUD SYNC</span>
            <span style="font-size: 11px; font-weight: 800; color: #059669;">🟢 CONNESSO</span>
        </div>
        <div style="font-size: 11px; color: #64748B;">Replica Google Sheets attiva.</div>
    </div>
    """, unsafe_allow_html=True)
    if is_ufficio():
        if st.sidebar.button("🔄 Sincronizza Cloud Ora", use_container_width=True, key="side_btn_pull_cloud", help="Ripristina tutte le run e le bolle salvate sul Foglio Google"):
            with st.spinner("Sincronizzazione in corso da Google Sheets..."):
                r_p = pull_all_from_cloud()
                if r_p.get("status") == "ok":
                    st.session_state.pop("last_run", None)
                    st.session_state.pop("active_view_run_id", None)
                    st.rerun()
else:
    st.sidebar.caption("☁️ Google Sheets Sync: *Non configurato*")


def render_operativa_files_and_email_section(
    run_data: Dict[str, Any],
    df_stores: pd.DataFrame,
    key_prefix: str = "op"
):
    """
    Renders the unified Operative Files download toolbar (Sintesi Operativa, SGA 0, SGA 9, ZARA, ZIP)
    and an expandable Email sending form without duplicating buttons or cluttering the dashboard.
    """
    if not run_data or not isinstance(run_data, dict):
        return

    rid = run_data.get("run_id") or run_data.get("id") or "curr"
    r_date = run_data.get("run_date", "")
    out_dir = OUTPUT_DIR / f"run_{rid}_{r_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    p_sintesi = out_dir / "Sintesi_Operativa.xlsx"
    p_sga0 = out_dir / "barrazero_Sga.xlsx"
    p_sga9 = out_dir / "barranove_Sga.xlsx"
    p_sga0_csv = out_dir / "barrazero_Sga.csv"
    p_sga9_csv = out_dir / "barranove_Sga.csv"
    p_zip = out_dir / f"File_Operativa_{rid}_{r_date}.zip"
    p_zara = out_dir / "ZARA.xlsx"
    if not p_zara.exists():
        exp_f = run_data.get("exported_files", {})
        if "zara" in exp_f and Path(exp_f["zara"]).exists():
            p_zara = Path(exp_f["zara"])

    # Export Sintesi Operativa
    export_sintesi_operativa(
        run_data.get("df_spunta", pd.DataFrame()),
        run_data.get("special_breakdowns", {}),
        df_stores,
        p_sintesi,
        run_date=r_date
    )

    s0_df = run_data.get("df_sga0")
    if s0_df is None or s0_df.empty:
        det_s = get_run_details(rid)
        s0_df = det_s.get("sga0", pd.DataFrame())
    if s0_df is None or s0_df.empty:
        from src.engine import compute_sga_flows
        s0_df, s9_calc = compute_sga_flows(run_data.get("df_spunta", pd.DataFrame()), df_stores, r_date)
        run_data["df_sga0"] = s0_df
        if run_data.get("df_sga9") is None or run_data["df_sga9"].empty:
            run_data["df_sga9"] = s9_calc

    if s0_df is not None and not s0_df.empty:
        export_sga_file(s0_df, p_sga0)

    s9_df = run_data.get("df_sga9")
    if s9_df is None or s9_df.empty:
        det_s = get_run_details(rid)
        s9_df = det_s.get("sga9", pd.DataFrame())
    if s9_df is None or s9_df.empty:
        from src.engine import compute_sga_flows
        _, s9_df = compute_sga_flows(run_data.get("df_spunta", pd.DataFrame()), df_stores, r_date)
        run_data["df_sga9"] = s9_df

    if s9_df is not None and not s9_df.empty:
        export_sga_file(s9_df, p_sga9)

    zip_items = {
        "Sintesi_Operativa.xlsx": p_sintesi,
        "barrazero_Sga.xlsx": p_sga0,
        "barranove_Sga.xlsx": p_sga9,
        "barrazero_Sga.csv": p_sga0_csv,
        "barranove_Sga.csv": p_sga9_csv,
    }
    if p_zara.exists():
        zip_items["ZARA.xlsx"] = p_zara

    build_operativa_zip(zip_items, p_zip)

    st.markdown('<div class="modern-card" style="border-left: 5px solid #0284C7; margin-bottom: 20px; padding: 18px 20px;">', unsafe_allow_html=True)
    st.markdown('<div class="modern-section-title">📦 Download Documenti Ufficiali & Spedizione Email</div>', unsafe_allow_html=True)
    st.caption("Scarica i documenti operativi ufficiali generati per questa spedizione (Sintesi Operativa, SGA Barra 0, SGA Barra 9, Spunta ZARA) oppure espandi la sezione email per la trasmissione:")

    dl_cols = st.columns(5)
    with dl_cols[0]:
        if p_sintesi.exists():
            with open(p_sintesi, "rb") as f_s:
                st.download_button(
                    "📊 Sintesi Operativa (.xlsx)",
                    data=f_s.read(),
                    file_name=p_sintesi.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"dl_box_sintesi_{key_prefix}_{rid}"
                )
    with dl_cols[1]:
        if p_sga0.exists():
            with open(p_sga0, "rb") as f_0:
                st.download_button(
                    "🚛 SGA Barra 0 (.xlsx)",
                    data=f_0.read(),
                    file_name=p_sga0.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"dl_box_sga0_{key_prefix}_{rid}"
                )
        else:
            st.button("🚛 SGA Barra 0 (N.D.)", disabled=True, use_container_width=True, key=f"dl_box_sga0_nd_{key_prefix}_{rid}")
    with dl_cols[2]:
        if p_sga9.exists():
            with open(p_sga9, "rb") as f_9:
                st.download_button(
                    "🚚 SGA Barra 9 (.xlsx)",
                    data=f_9.read(),
                    file_name=p_sga9.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"dl_box_sga9_{key_prefix}_{rid}"
                )
        else:
            st.button("🚚 SGA Barra 9 (N.D.)", disabled=True, use_container_width=True, key=f"dl_box_sga9_nd_{key_prefix}_{rid}")
    with dl_cols[3]:
        if p_zara.exists():
            with open(p_zara, "rb") as f_zara:
                st.download_button(
                    "📄 Spunta ZARA (.xlsx)",
                    data=f_zara.read(),
                    file_name=p_zara.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"dl_box_zara_{key_prefix}_{rid}"
                )
        else:
            st.button("📄 Spunta ZARA (N.D.)", disabled=True, use_container_width=True, key=f"dl_box_zara_nd_{key_prefix}_{rid}")
    with dl_cols[4]:
        if p_zip.exists():
            with open(p_zip, "rb") as f_z:
                st.download_button(
                    "🗂️ Tutto in ZIP (.zip)",
                    data=f_z.read(),
                    file_name=p_zip.name,
                    mime="application/zip",
                    use_container_width=True,
                    key=f"dl_box_zip_{key_prefix}_{rid}"
                )

    email_cfg = get_email_config()
    def_to = email_cfg.get("default_to", "operativa@trasporti.it, traffico@trasporti.it")
    def_cc = email_cfg.get("default_cc", "")
    has_smtp = bool(email_cfg.get("smtp_host") and email_cfg.get("smtp_user"))

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    with st.expander("✉️ Spedisci File Operativa via Email (Sintesi & Flussi SGA)", expanded=False):
        col_em_head1, col_em_head2 = st.columns([3, 1.2])
        with col_em_head1:
            if has_smtp:
                st.markdown(f"<div style='font-size:12.5px; color:#10B981; font-weight:600;'>🟢 Connessione SMTP Attiva: <code>{email_cfg.get('smtp_host')}:{email_cfg.get('smtp_port')}</code> (Mittente: {email_cfg.get('smtp_user')})</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='font-size:12.5px; color:#F59E0B; font-weight:600;'>🟡 Modalità Simulazione / SMTP non configurato. Configura i parametri nella scheda ⚙️ Impostazioni.</div>", unsafe_allow_html=True)
        with col_em_head2:
            with st.popover("⚙️ Destinatari Standard", use_container_width=True):
                st.markdown("##### ✉️ Indirizzi Standard")
                p_to = st.text_input("Destinatari Standard (TO)", value=def_to, key=f"pop_to_{key_prefix}_{rid}")
                p_cc = st.text_input("Destinatari in Copia (CC)", value=def_cc, key=f"pop_cc_{key_prefix}_{rid}")
                if st.button("💾 Salva come Predefiniti", key=f"btn_save_pop_email_{key_prefix}_{rid}", use_container_width=True):
                    email_cfg["default_to"] = p_to
                    email_cfg["default_cc"] = p_cc
                    save_email_config(email_cfg)
                    st.success("Indirizzi standard aggiornati!")
                    st.rerun()

        em_col1, em_col2 = st.columns([1.5, 1.5])
        with em_col1:
            em_to = st.text_input("Destinatari (separati da virgola)", value=def_to, key=f"em_to_in_{key_prefix}_{rid}")
        with em_col2:
            em_cc = st.text_input("In Copia (CC - opzionale)", value=def_cc, key=f"em_cc_in_{key_prefix}_{rid}")

        tmpl_subj = email_cfg.get("subject_template") or "[ZARA LOGISTICS] File Operativa & Flussi SGA - Spedizione del {date}"
        default_subj = tmpl_subj.replace("{date}", str(r_date))
        em_subj = st.text_input(
            "Oggetto Email",
            value=default_subj,
            key=f"em_subj_in_{key_prefix}_{rid}"
        )

        totals = run_data.get("totals", {})
        spec_bd = run_data.get("special_breakdowns", {})
        lav_lines = []
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

        default_body = (
            f"Gentili Colleghi,\n\n"
            f"in allegato trasmettiamo i file operativi relativi alla spedizione del {format_date_it(r_date)}:\n\n"
            f"- Sintesi Operativa Giri & Lavorazioni (Sintesi_Operativa.xlsx)\n"
            f"- Flusso Viaggi TMS Barra 0 (barrazero_Sga.xlsx / .csv)\n"
            f"- Flusso Viaggi TMS Barra 9 Sdoppiati (barranove_Sga.xlsx / .csv)\n\n"
            f"Riepilogo Totali Spedizione:\n"
            f"- Totale Colli: {format_number_it(totals.get('total_bultos', 0), 0)}\n"
            f"- Volume Complessivo: {format_number_it(totals.get('total_volume', 0.0), 2)} m³\n"
            f"- Peso Complessivo: {format_number_it(totals.get('total_weight', 0.0), 0)} kg\n"
            f"- Pedane Stimate: {format_number_it(totals.get('total_pedane', 0), 0)} PLT\n"
            f"{lav_section}\n"
            f"Restiamo a disposizione per qualsiasi chiarimento operativo.\n\n"
            f"Cordiali saluti,\n"
            f"Ufficio Logistica & Traffico Zara Hub"
        )

        em_body = st.text_area("Testo del Messaggio", value=default_body, height=180, key=f"em_body_in_{key_prefix}_{rid}")

        if st.button("🚀 INVIA EMAIL ORA", type="primary", use_container_width=True, key=f"btn_send_now_{key_prefix}_{rid}"):
            to_list = [x.strip() for x in em_to.split(",") if x.strip()]
            cc_list = [x.strip() for x in em_cc.split(",") if x.strip()]
            att_files = [p_sintesi, p_sga0, p_sga9]
            if p_zara.exists():
                att_files.append(p_zara)
            with st.spinner("📧 Invio email operativa con documenti allegati in corso..."):
                success, msg = send_operativa_email(
                    recipients=to_list,
                    subject=em_subj,
                    body_text=em_body,
                    attachment_paths=att_files,
                    cc_recipients=cc_list,
                    smtp_config=email_cfg
                )
                if success:
                    st.session_state["flash_email_success"] = msg
                    st.session_state["active_view_run_id"] = rid
                    st.session_state["last_run"] = run_data
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")

    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# PAGE 1: PREVISIONE & ARRIVI (IMPORT + SPUNTA + SGA + LAVORAZIONI)
# ==============================================================================
if "Previsione & Arrivi" in menu:
    st.markdown('<div class="main-header">📥 Previsione Arrivi, Spunta & Flussi SGA</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Carica i file previsionali da qualsiasi dispositivo (o scaricali da Extranet), calcola pedane e lavorazioni, ed emetti le bolle in 1 clic.</div>', unsafe_allow_html=True)

    if has_perm("can_execute_runs"):
        tab_view_active, tab_new_exec = st.tabs([
            "📊 Elaborazione Aperta (Visualizzazione & File Operativa)",
            "⚡ Nuova Elaborazione (Extranet Inditex / Caricamento File)",
        ])
    else:
        tab_view_active = st.container()
        tab_new_exec = None

    with tab_view_active:
        if "flash_email_success" in st.session_state:
            st.success(f"🎉 **{st.session_state.pop('flash_email_success')}**")
        active_run_data = None
        latest_run_id = int(runs_side.iloc[0]["id"]) if not runs_side.empty else None

        if not runs_side.empty:
            valid_ids = list(runs_side["id"])
            if "active_view_run_id" not in st.session_state or st.session_state["active_view_run_id"] not in valid_ids:
                st.session_state["active_view_run_id"] = latest_run_id

            if has_perm("can_delete_runs"):
                col_r_sel, col_r_btn, col_r_del = st.columns([2.6, 1.1, 1.1])
            else:
                col_r_sel, col_r_btn = st.columns([3.5, 1.3])
                col_r_del = None
            with col_r_sel:
                run_opts_map = {
                    int(r["id"]): f"Run #{int(r['id'])} ({format_date_it(r['run_date'])}, {r['cycle_type']}) — {format_number_it(r['total_bultos'], 0)} colli ({format_number_it(r['total_pedane'], 0)} PLT)"
                    for _, r in runs_side.head(50).iterrows()
                }
                curr_selected_id = st.session_state.get("active_view_run_id") or latest_run_id
                sel_idx = list(run_opts_map.keys()).index(curr_selected_id) if curr_selected_id in run_opts_map else 0
                chosen_id = st.selectbox(
                    "📂 Elaborazione Visualizzata (Seleziona Run dallo Storico)",
                    list(run_opts_map.keys()),
                    index=sel_idx,
                    format_func=lambda rid: ("⭐ [ULTIMA RUN] " if rid == latest_run_id else "") + run_opts_map[rid],
                    key="p1_run_selector_sb",
                )
                if chosen_id != st.session_state.get("active_view_run_id"):
                    st.session_state["active_view_run_id"] = chosen_id
                    st.rerun()

            with col_r_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("🔄 Riapri Ultima Run", use_container_width=True, key="btn_reopen_latest"):
                    st.session_state["active_view_run_id"] = latest_run_id
                    st.rerun()

            if col_r_del is not None:
                with col_r_del:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    with st.popover("🗑️ Elimina Run", use_container_width=True):
                        st.warning(f"Vuoi eliminare la **Run #{chosen_id}** e tutti i suoi dati associati?")
                        if st.button("Conferma Eliminazione", type="primary", use_container_width=True, key=f"btn_confirm_del_run_{chosen_id}"):
                            with st.spinner(f"🗑️ Eliminazione Run #{chosen_id} in corso..."):
                                delete_run(chosen_id)
                                st.session_state.pop("active_view_run_id", None)
                                st.session_state.pop("last_run", None)
                                st.success(f"Run #{chosen_id} eliminata con successo.")
                                st.rerun()

            # Caricamento effettivo della run
            if "last_run" in st.session_state and st.session_state["last_run"] and st.session_state["last_run"].get("run_id") == st.session_state["active_view_run_id"]:
                active_run_data = st.session_state["last_run"]
            else:
                active_run_data = load_run_data(st.session_state["active_view_run_id"])
        else:
            st.info("ℹ️ Nessuna elaborazione presente nello storico. Passa alla scheda **'⚡ Nuova Elaborazione'** qui sopra per eseguire il primo scarico da Extranet o caricare i file Inditex.")

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
            st.markdown("### 📊 Riepilogo Previsione Attiva")

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Totale Colli", format_number_it(totals["total_bultos"], 0))
            kpi2.metric("Volume Complessivo", format_number_it(totals["total_volume"], 2) + " m³")
            kpi3.metric("Peso Complessivo", format_number_it(totals["total_weight"], 0) + " kg")
            kpi4.metric("Pedane Stimate", format_number_it(totals["total_pedane"], 0))

            render_operativa_files_and_email_section(active_run_data, df_stores_side, key_prefix=f"vis_{curr_rid}")

            tab_spunta, tab_giri, tab_lav = st.tabs([
                "📋 Spunta Arrivi (Per Negozio)",
                "🚛 Vista per Giro & Vettori",
                "🏭 Lavorazioni Piattaforma (Tessile 3680/9226/3591 & Home)",
            ])

            df_sp_view = active_run_data.get("df_spunta", pd.DataFrame())

            with tab_spunta:
                render_spunta_arrivi_modern(df_sp_view, df_stores=df_stores_side)

            with tab_giri:
                render_riepilogo_giri_modern(
                    df_sp_view,
                    df_stores=df_stores_side,
                    special_breakdowns=active_run_data.get("special_breakdowns", {}),
                )

            with tab_lav:
                render_lavorazioni_piattaforma(active_run_data.get("special_breakdowns", {}), key_prefix=f"p1_{curr_rid}")


    # ==============================================================================
    # PAGE 2: BOLLE DI CONSEGNA (ELENCO, STAMPA PER GIRO/AUTISTA, COMPILAZIONE)
    # ==============================================================================

    if tab_new_exec is not None:
        with tab_new_exec:
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
            st.markdown("##### 🧴 Scorporo Profumi (Dato Dinamico per questa Operativa)")
            st.caption("I pezzi profumi sono un dato dinamico da inserire manualmente ad ogni specifica run per i negozi abilitati. Se non pervenuti o assenti per questo ciclo, lasciare a 0:")

            perfume_corrections = {}
            if not df_prof_stores.empty:
                prof_cols = st.columns(min(len(df_prof_stores), 4))
                for idx_p, (_, prow) in enumerate(df_prof_stores.iterrows()):
                    p_sid = str(prow["store_id"]).strip()
                    p_sname = str(prow.get("store_name", "")).strip()
                    with prof_cols[idx_p % len(prof_cols)]:
                        val_pz = st.number_input(
                            f"Negozio {p_sid} ({p_sname}) — Pezzi Profumi",
                            value=0,
                            min_value=0,
                            step=1,
                            key=f"perfume_{p_sid}",
                            help="Dato dinamico per questa specifica run. Se mancante o assente, lasciare a 0."
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

                col_cred1, col_cred2 = st.columns([2.5, 1.5])
                with col_cred1:
                    st.markdown(f"<div style='font-size:13px; color:#475569; margin: 4px 0 10px 0;'>🔑 Accesso configurato: <strong><code>{ex_user}</code></strong></div>", unsafe_allow_html=True)
                with col_cred2:
                    with st.popover("⚙️ Modifica Credenziali Inditex", use_container_width=True):
                        st.markdown("##### 🔐 Credenziali Extranet Inditex")
                        new_u = st.text_input("Utente", value=ex_user, key="pop_ext_u")
                        new_p = st.text_input("Password", value=ex_pass, type="password", key="pop_ext_p")
                        if st.button("💾 Salva Nuove Credenziali", use_container_width=True, key="btn_save_pop_ext_creds"):
                            set_extranet_credentials(new_u, new_p)
                            st.success("Credenziali Extranet aggiornate!")
                            st.rerun()

                prof_summary_str = " | ".join([f"**{k}** = `{int(v)}` pz" for k, v in perfume_corrections.items()]) or "Nessuno (0 pz)"
                st.caption(f"🧴 Scorporo profumi attivo per questa elaborazione: {prof_summary_str}")
                btn_scrape_go = st.button("🌐 SCARICA DA EXTRANET ED AVVIA ESTRAZIONE", type="primary", use_container_width=True, key="btn_ask_scrape")

                if btn_scrape_go:
                    status_banner = st.empty()
                    prog_bar = st.progress(5)
                    status_banner.markdown("""
                    <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
                                border: 2px solid #38BDF8; border-radius: 12px;
                                padding: 18px 24px; margin: 12px 0 16px 0; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.25);">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 14px;">
                                <div style="font-size: 28px;">⚙️</div>
                                <div>
                                    <div style="font-size: 16px; font-weight: 800; color: #38BDF8; letter-spacing: 0.5px;">
                                        🚀 ESTRAZIONE ED ELABORAZIONE AVVIATA — ATTENDERE PREGO
                                    </div>
                                    <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 3px;">
                                        Connessione a Inditex Extranet in corso e download automatico file...
                                    </div>
                                </div>
                            </div>
                            <div style="font-size: 18px; font-weight: 800; color: #F59E0B;">5%</div>
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
                                    padding: 18px 24px; margin: 12px 0 16px 0; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.25);">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <div style="display: flex; align-items: center; gap: 14px;">
                                    <div style="font-size: 28px;">🔄</div>
                                    <div>
                                        <div style="font-size: 16px; font-weight: 800; color: #38BDF8; letter-spacing: 0.5px;">
                                            ESTRAZIONE ED ELABORAZIONE IN CORSO...
                                        </div>
                                        <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 3px;">
                                            {html.escape(msg)}
                                        </div>
                                    </div>
                                </div>
                                <div style="font-size: 18px; font-weight: 800; color: #F59E0B;">{pct}%</div>
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
                        status_banner.markdown("""
                        <div style="background: linear-gradient(135deg, #064E3B 0%, #022C22 100%);
                                    border: 2px solid #10B981; border-radius: 12px;
                                    padding: 18px 24px; margin: 12px 0 16px 0;">
                            <div style="display: flex; align-items: center; gap: 14px;">
                                <div style="font-size: 28px;">✅</div>
                                <div>
                                    <div style="font-size: 16px; font-weight: 800; color: #34D399;">
                                        ELABORAZIONE COMPLETATA CON SUCCESSO!
                                    </div>
                                    <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 3px;">
                                        File TOTAL, SHOES, TEXILE, ECOM e OTHER estratti e calcolati con successo. Dati archiviati nel DB.
                                    </div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.session_state["last_run"] = res
                        st.session_state["active_view_run_id"] = res["run_id"]
                        st.session_state[f"show_op_panel_{res['run_id']}"] = True

                        # Mostra subito i file operativi generati e l'invio email
                        render_operativa_files_and_email_section(res, df_stores_side, key_prefix=f"extranet_{res['run_id']}")

                        if st.button("📊 APRI TUTTI I DETTAGLI (ELABORAZIONE APERTA)", type="primary", use_container_width=True, key="btn_go_active_extranet"):
                            st.session_state["active_view_run_id"] = res["run_id"]
                            st.session_state["last_run"] = res
                            st.rerun()

                    except Exception as e:
                        status_banner.empty()
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

                prof_summary_str = " | ".join([f"**{k}** = `{int(v)}` pz" for k, v in perfume_corrections.items()]) or "Nessuno (0 pz)"
                st.caption(f"🧴 Scorporo profumi attivo per questa elaborazione: {prof_summary_str}")
                btn_upload_go = st.button("🚀 ELABORA FILE CARICATI ORA", type="primary", use_container_width=True, disabled=not bool(classified and (classified["total"] or classified["texile"])), key="btn_ask_upload")

                if btn_upload_go:
                    status_banner_up = st.empty()
                    prog_bar_up = st.progress(25)
                    status_banner_up.markdown("""
                    <div style="background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
                                border: 2px solid #38BDF8; border-radius: 12px;
                                padding: 18px 24px; margin: 12px 0 16px 0; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.25);">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 14px;">
                                <div style="font-size: 28px;">⚙️</div>
                                <div>
                                    <div style="font-size: 16px; font-weight: 800; color: #38BDF8; letter-spacing: 0.5px;">
                                        🚀 ELABORAZIONE FILE AVVIATA — ATTENDERE PREGO
                                    </div>
                                    <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 3px;">
                                        Calcolo Spunta Arrivi, suddivisione Sdoppiamenti /0-/9 e salvataggio storico...
                                    </div>
                                </div>
                            </div>
                            <div style="font-size: 18px; font-weight: 800; color: #F59E0B;">25%</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

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
                        prog_bar_up.progress(100)
                        status_banner_up.markdown("""
                        <div style="background: linear-gradient(135deg, #064E3B 0%, #022C22 100%);
                                    border: 2px solid #10B981; border-radius: 12px;
                                    padding: 18px 24px; margin: 12px 0 16px 0;">
                            <div style="display: flex; align-items: center; gap: 14px;">
                                <div style="font-size: 28px;">✅</div>
                                <div>
                                    <div style="font-size: 16px; font-weight: 800; color: #34D399;">
                                        ELABORAZIONE COMPLETATA CON SUCCESSO!
                                    </div>
                                    <div style="font-size: 13.5px; color: #F8FAFC; margin-top: 3px;">
                                        Spunta Arrivi, Flussi SGA e Riepilogo Giri calcolati con successo.
                                    </div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.session_state["last_run"] = res
                        st.session_state["active_view_run_id"] = res["run_id"]
                        st.session_state[f"show_op_panel_{res['run_id']}"] = True

                        # Mostra subito i file operativi generati e l'invio email
                        render_operativa_files_and_email_section(res, df_stores_side, key_prefix=f"upload_{res['run_id']}")

                        if st.button("📊 APRI TUTTI I DETTAGLI (ELABORAZIONE APERTA)", type="primary", use_container_width=True, key="btn_go_active_upload"):
                            st.session_state["active_view_run_id"] = res["run_id"]
                            st.session_state["last_run"] = res
                            st.rerun()

                    except Exception as e:
                        status_banner_up.empty()
                        st.error(f"Errore durante l'elaborazione: {e}")


elif "Bolle di Consegna" in menu:
    st.markdown('<div class="main-header">🚚 Gestione Bolle di Consegna</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Generazione automatica da previsione, stampa distinte per Giro/Autista e compilazione rapida con controllo Sdoppiamento (/0 STD e /9 DOPPIA).</div>', unsafe_allow_html=True)

    if "flash_bolle_msg" in st.session_state:
        st.success(st.session_state.pop("flash_bolle_msg"))

    # Cleanup any ghost/test bolle with dummy future dates
    try:
        with sqlite3.connect(DB_PATH) as _c_purge:
            _c_purge.execute("DELETE FROM bolle WHERE data LIKE '%2098%' OR data LIKE '%2099%' OR data_consegna LIKE '%2098%' OR data_consegna LIKE '%2099%' OR id_store = '9999'")
            _c_purge.commit()
    except Exception:
        pass

    # Barra Superiore Rapida: Selezione Data + Generazione 1-Clic da Previsione
    all_dates = get_bolle_dates(120)
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    if not all_dates:
        all_dates = [tomorrow_str]

    # Handle pending date override BEFORE selectbox instantiation
    if "_target_date_override" in st.session_state:
        override_dt = st.session_state.pop("_target_date_override")
        if override_dt not in all_dates:
            all_dates.insert(0, override_dt)
        st.session_state["bolle_tab1_date_val"] = override_dt

    if "bolle_tab1_date_val" not in st.session_state or st.session_state["bolle_tab1_date_val"] not in all_dates:
        st.session_state["bolle_tab1_date_val"] = all_dates[0]

    col_top1, col_top2, col_top3 = st.columns([2, 2.2, 1.8])
    with col_top1:
        target_date = st.selectbox(
            "📅 Data di Consegna Attiva",
            all_dates,
            format_func=lambda d: f"{format_date_it(d)} ({d})",
            key="bolle_tab1_date_val",
        )

    with col_top2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        qb1, qb2, qb3 = st.columns(3)
        with qb1:
            if st.button("📅 Oggi", use_container_width=True, key="b_q_tod"):
                st.session_state["_target_date_override"] = today_str
                st.rerun()
        with qb2:
            if st.button("📅 Domani", use_container_width=True, key="b_q_tom"):
                st.session_state["_target_date_override"] = tomorrow_str
                st.rerun()
        with qb3:
            if st.button("📅 Ultima", use_container_width=True, key="b_q_lat"):
                st.session_state["_target_date_override"] = all_dates[0]
                st.rerun()

    with col_top3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if has_perm("can_execute_runs"):
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

    if has_perm("can_edit_bolle"):
        tab_b_form, tab_b_list = st.tabs([
            "📝 Compilazione Singola Bolla",
            "📋 Elenco Bolle & Stampa Documenti",
        ])
    else:
        tab_b_form = None
        tab_b_list = st.container()

    # --------------------------------------------------------------------------
    # SOTTO-SCHEDA 1: COMPILAZIONE SINGOLA BOLLA (MODALITÀ STANDARD)
    # --------------------------------------------------------------------------
    if tab_b_form is not None:
        with tab_b_form:
            store_choices = [
                f"{r['store_id']} - {r['store_name']} ({r['brand']}) [{r['giro']}]"
                for _, r in df_stores_side.iterrows()
            ] if not df_stores_side.empty else []

            if "_next_store_override" in st.session_state:
                st.session_state["form_store_sel"] = st.session_state.pop("_next_store_override")

            target_dt_obj = parse_date_obj(target_date)
            if st.session_state.get("_prev_target_date_for_form") != target_date:
                st.session_state["_prev_target_date_for_form"] = target_date
                st.session_state["form_dt_cons"] = target_dt_obj

            col_t1, col_t2, col_t3 = st.columns([2.5, 1.2, 1.3])
            with col_t1:
                sel_store_str = st.selectbox(
                    "Punto Vendita (Store)",
                    store_choices,
                    key="form_store_sel",
                    help="Seleziona il punto vendita. Se per la data indicata esiste già una bolla registrata, verrà aperta automaticamente per la modifica rapida."
                )
                current_sid = sel_store_str.split(" - ")[0].strip() if sel_store_str else "3680"

            # Verifica flag sdoppiamento_b9 in anagrafica per consentire o bloccare DOPPIA
            is_sdoppia = False
            if not df_stores_side.empty:
                m_row = df_stores_side[df_stores_side["store_id"].astype(str) == current_sid]
                if not m_row.empty:
                    is_sdoppia = str(m_row.iloc[0].get("sdoppiamento_b9", "NO")).strip().upper() == "SI"

            tipo_options = ["STD", "DOPPIA"] if is_sdoppia else ["STD"]
            with col_t2:
                form_tipo_cons = st.selectbox(
                    "Tipologia Consegna",
                    tipo_options,
                    key="form_tipo_cons",
                    help="STD: consegna standard (/0). DOPPIA: sdoppiamento (/9 'B') attivo per i negozi abilitati in Anagrafica.",
                )

            with col_t3:
                form_data_cons = st.date_input(
                    "Data Consegna",
                    value=target_dt_obj,
                    format="DD/MM/YYYY",
                    key="form_dt_cons"
                )

            # Rilevamento automatico se la bolla esiste già
            df_existing = get_bolle(
                data_consegna=str(form_data_cons),
                id_store=current_sid,
                tipo_cons=form_tipo_cons
            )
            existing_bolla = df_existing.iloc[0].to_dict() if not df_existing.empty else None

            if existing_bolla:
                st.markdown(
                    f"""
                    <div style="background: rgba(30, 142, 62, 0.10); border-left: 4px solid #1e8e3e; padding: 9px 14px; border-radius: 6px; margin: 8px 0 14px 0;">
                        <div style="font-weight: 600; color: #137333;">🟢 Bolla #{existing_bolla['id']} Registrata</div>
                        <div style="font-size: 0.88rem; color: #202124;">
                            Bolla esistente per <b>{current_sid}</b> con consegna <b>{format_date_it(str(form_data_cons))}</b> ({form_tipo_cons}). 
                            I quantitativi e le informazioni registrate sono caricati nei campi sottostanti per la modifica immediata.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f"""
                    <div style="background: rgba(26, 115, 232, 0.08); border-left: 4px solid #1a73e8; padding: 9px 14px; border-radius: 6px; margin: 8px 0 14px 0;">
                        <div style="font-weight: 600; color: #1a73e8;">✨ Nuova Bolla in Compilazione</div>
                        <div style="font-size: 0.88rem; color: #202124;">
                            Nessuna bolla presente per <b>{current_sid}</b> con consegna <b>{format_date_it(str(form_data_cons))}</b> ({form_tipo_cons}). 
                            I parametri del vettore e mezzo sono precompilati dall'Anagrafica. Inserisci i colli o precompila dalla previsione.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # Cache key per inizializzazione e sincronizzazione campi form
            active_cache_key = f"{form_data_cons}_{current_sid}_{form_tipo_cons}_{existing_bolla['id'] if existing_bolla else 'new'}"
            if st.session_state.get("_last_active_bolla_key") != active_cache_key:
                st.session_state["_last_active_bolla_key"] = active_cache_key
                prof = get_store_delivery_profile(current_sid, form_tipo_cons)

                if existing_bolla:
                    st.session_state["form_pv"] = str(existing_bolla.get("punto_vendita") or prof.get("punto_vendita") or "ZARA")
                    st.session_state["form_vettore"] = str(existing_bolla.get("vettore") or prof.get("vettore") or "LACCHI SPA")
                    st.session_state["form_autista"] = str(existing_bolla.get("autista") or "")
                    st.session_state["form_mezzo"] = str(existing_bolla.get("tipo_mezzo") or prof.get("tipo_mezzo") or "")
                    st.session_state["form_indirizzo"] = str(existing_bolla.get("indirizzo_destino") or prof.get("indirizzo") or "")
                    st.session_state["form_c_abb"] = int(round(float(existing_bolla.get("colli_abbigl", 0) or 0)))
                    st.session_state["form_c_calz"] = int(round(float(existing_bolla.get("colli_calzat", 0) or 0)))
                    st.session_state["form_c_eco"] = int(round(float(existing_bolla.get("colli_ecom", 0) or 0)))
                    st.session_state["form_c_oth"] = int(round(float(existing_bolla.get("colli_others", 0) or 0)))
                    st.session_state["form_c_var"] = int(round(float(existing_bolla.get("colli_vario", 0) or 0)))
                    st.session_state["form_c_cont"] = int(round(float(existing_bolla.get("colli_cont", 0) or 0)))
                    st.session_state["form_c_mat"] = int(round(float(existing_bolla.get("colli_mat_vario", 0) or 0)))
                    st.session_state["form_c_dann"] = int(round(float(existing_bolla.get("colli_dann", 0) or 0)))
                    st.session_state["form_c_nonconf"] = int(round(float(existing_bolla.get("colli_non_conf", 0) or 0)))
                    st.session_state["form_stringa_custom"] = str(existing_bolla.get("stringa", "") or "")
                    st.session_state["form_anomalie"] = str(existing_bolla.get("anomalie_scarico", "") or "")
                else:
                    st.session_state["form_pv"] = str(prof.get("punto_vendita") or "ZARA")
                    st.session_state["form_vettore"] = str(prof.get("vettore") or "LACCHI SPA")
                    st.session_state["form_autista"] = str(prof.get("autista", "") or "")
                    st.session_state["form_mezzo"] = str(prof.get("tipo_mezzo") or ("FURGONE 8" if form_tipo_cons == "DOPPIA" else "MOTRICE 18 PLT"))
                    st.session_state["form_indirizzo"] = str(prof.get("indirizzo") or "")
                    st.session_state["form_c_abb"] = 0
                    st.session_state["form_c_calz"] = 0
                    st.session_state["form_c_eco"] = 0
                    st.session_state["form_c_oth"] = 0
                    st.session_state["form_c_var"] = 0
                    st.session_state["form_c_cont"] = 0
                    st.session_state["form_c_mat"] = 0
                    st.session_state["form_c_dann"] = 0
                    st.session_state["form_c_nonconf"] = 0
                    st.session_state["form_stringa_custom"] = ""
                    st.session_state["form_anomalie"] = ""

            # Testata Bolla (Senza autista/cell come da richiesta)
            col_v1, col_v2, col_v3, col_v4 = st.columns([1.2, 1.3, 1.5, 1.5])
            with col_v1:
                form_data_carico = st.date_input("Data Spedizione", value=date.today(), format="DD/MM/YYYY", key="form_dt_carico")
            with col_v2:
                form_pv = st.text_input("Insegna / Brand", key="form_pv")
            with col_v3:
                form_vettore = st.text_input("Vettore Assegnato", key="form_vettore")
            with col_v4:
                form_mezzo = st.text_input("Tipo Mezzo", key="form_mezzo")

            form_indirizzo = st.text_input("Indirizzo di Destino", key="form_indirizzo")

            # ------------------------------------------------------------------
            # CARD DATI PREVISIONALI (SEMPRE VISIBILE)
            # ------------------------------------------------------------------
            p_tot = int(round(float(existing_bolla.get("prev_totale", 0) or 0))) if existing_bolla else 0
            p_abb = int(round(float(existing_bolla.get("prev_abbigl", 0) or 0))) if existing_bolla else 0
            p_calz = int(round(float(existing_bolla.get("prev_calzat", 0) or 0))) if existing_bolla else 0
            p_eco = int(round(float(existing_bolla.get("prev_ecom", 0) or 0))) if existing_bolla else 0
            p_oth = int(round(float(existing_bolla.get("prev_others", 0) or 0))) if existing_bolla else 0

            if p_tot == 0:
                pl_data = get_store_latest_planned_data(current_sid)
                if pl_data.get("has_data"):
                    sdop_f = 0.3 if form_tipo_cons == "DOPPIA" else (0.7 if is_sdoppia else 1.0)
                    p_abb = int(round(float(pl_data.get("textile", 0) or 0) * sdop_f))
                    p_calz = int(round(float(pl_data.get("shoes", 0) or 0) * sdop_f))
                    p_eco = int(round(float(pl_data.get("ecom", 0) or 0) * sdop_f))
                    p_oth = int(round(float(pl_data.get("others", 0) or 0) * sdop_f))
                    p_tot = p_abb + p_calz + p_eco + p_oth

            st.markdown(f"""
            <div class="modern-card" style="padding: 12px 18px; margin-top: 10px; margin-bottom: 14px; border-left: 5px solid #1E3A8A; background-color: #F8FAFC;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px;">📊 DATI PREVISIONALI ATTESI (DALLA PREVISIONE ARRIVI)</span>
                    <span style="font-size: 13.5px; font-weight: 800; color: #1E3A8A;">TOTALE PREVISTO: {format_number_it(p_tot, 0)} COLLI</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 4px;">
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px; text-align: center;">
                        <div style="font-size: 10px; font-weight: 600; color: #64748B;">👗 TESSILE</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(p_abb, 0)}</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px; text-align: center;">
                        <div style="font-size: 10px; font-weight: 600; color: #64748B;">👟 SCARPE</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(p_calz, 0)}</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px; text-align: center;">
                        <div style="font-size: 10px; font-weight: 600; color: #64748B;">📦 E-COMMERCE</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(p_eco, 0)}</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px; text-align: center;">
                        <div style="font-size: 10px; font-weight: 600; color: #64748B;">📦 ALTRI</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(p_oth, 0)}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Quantità Colli Effettivi (Modificabili a mano)
            st.markdown("##### 📦 Conteggio Colli Effettivi Bolla")
            col_q1, col_q2, col_q3, col_q4, col_q5 = st.columns(5)
            with col_q1:
                c_abb = st.number_input("Abbigliamento", min_value=0, step=1, key="form_c_abb")
            with col_q2:
                c_calz = st.number_input("Calzature", min_value=0, step=1, key="form_c_calz")
            with col_q3:
                c_eco = st.number_input("E-Commerce", min_value=0, step=1, key="form_c_eco")
            with col_q4:
                c_oth = st.number_input("Altri Bultos", min_value=0, step=1, key="form_c_oth")
            with col_q5:
                c_var = st.number_input("Mat. Vario Piattaforma", min_value=0, step=1, key="form_c_var")

            tot_operativa_calc = int(c_abb + c_calz + c_eco + c_oth + c_var)
            delta_eff_prev = tot_operativa_calc - p_tot
            if delta_eff_prev == 0:
                st.success(f"🟢 **Totale Colli Bolla: {format_number_it(tot_operativa_calc, 0)} colli (CONFORME AL PREVISTO)**")
            elif delta_eff_prev > 0:
                st.warning(f"🟡 **Totale Colli Bolla: {format_number_it(tot_operativa_calc, 0)} colli (ECCEDENZA: +{delta_eff_prev} colli rispetto al previsto di {p_tot})**")
            else:
                st.error(f"🔴 **Totale Colli Bolla: {format_number_it(tot_operativa_calc, 0)} colli (MANCANZA: {delta_eff_prev} colli rispetto al previsto di {p_tot})**")

            # Intershops & Note
            with st.expander("🔄 Trasferimenti tra Negozi (Intershops / Stand / Ceste)", expanded=False):
                inter_rows_data = []
                existing_inter = []
                try:
                    if existing_bolla and existing_bolla.get("intershops_json"):
                        existing_inter = json.loads(existing_bolla["intershops_json"])
                except Exception:
                    existing_inter = []

                for row_i in range(3):
                    cur_item = existing_inter[row_i] if row_i < len(existing_inter) else {}
                    ci1, ci2, ci3 = st.columns([1, 1, 2])
                    with ci1:
                        m_val = st.text_input(f"Negozio Mittente #{row_i+1}", value=str(cur_item.get("mittente", "")), key=f"inter_m_{row_i}")
                    with ci2:
                        c_val = st.number_input(f"Colli #{row_i+1}", min_value=0, value=int(round(float(cur_item.get("colli", 0) or 0))), step=1, key=f"inter_c_{row_i}")
                    with ci3:
                        t_val = st.text_input(f"Tipologia #{row_i+1}", value=str(cur_item.get("tipo", "")), placeholder="es. MERCE, CESTE, STAND", key=f"inter_t_{row_i}")
                    if c_val > 0:
                        inter_rows_data.append({"mittente": m_val, "colli": int(c_val), "tipo": t_val})

            curr_note_val = str(existing_bolla.get("note") or existing_bolla.get("stringa") or "") if existing_bolla else ""
            form_note = st.text_area("📝 Note Generiche di Consegna / Banchina", value=curr_note_val, key="form_note_input", placeholder="Inserisci eventuali note operative, anomalie o indicazioni per la consegna...")

            # Pulsanti di Azione
            col_sv1, col_sv2, col_sv3 = st.columns([2, 2, 1.2])
            with col_sv1:
                btn_save_text = "💾 AGGIORNA BOLLA" if existing_bolla else "💾 SALVA BOLLA"
                save_clicked = st.button(btn_save_text, type="primary", use_container_width=True, key="btn_save_bolla")
            with col_sv2:
                btn_next_text = "💾 Aggiorna e Passa al Prossimo ➡️" if existing_bolla else "💾 Salva e Passa al Prossimo ➡️"
                save_next_clicked = st.button(btn_next_text, use_container_width=True, key="btn_save_next_bolla")
            with col_sv3:
                if existing_bolla:
                    with st.popover("🗑️ Elimina Bolla", use_container_width=True):
                        st.warning(f"Eliminare la bolla #{existing_bolla['id']} per {current_sid}?")
                        if st.button("Conferma Eliminazione", type="primary", use_container_width=True, key="btn_del_curr_bolla"):
                            delete_bolla(existing_bolla["id"])
                            st.session_state["flash_bolle_msg"] = f"🗑️ Bolla #{existing_bolla['id']} eliminata con successo."
                            st.rerun()

            if save_clicked or save_next_clicked:
                computed_stringa = format_intershops_string(inter_rows_data) if inter_rows_data else ""
                bolla_save_payload = {
                    "id": existing_bolla.get("id") if existing_bolla else None,
                    "data": str(form_data_carico),
                    "data_consegna": str(form_data_cons),
                    "id_store": current_sid,
                    "punto_vendita": form_pv,
                    "store_name": sel_store_str.split(" - ")[1].split(" (")[0] if " - " in sel_store_str else "",
                    "tipo_cons": form_tipo_cons,
                    "vettore": form_vettore,
                    "cell_autista": "",
                    "autista": "",
                    "tipo_mezzo": form_mezzo,
                    "indirizzo_destino": form_indirizzo,
                    "colli_abbigl": int(c_abb),
                    "colli_calzat": int(c_calz),
                    "colli_ecom": int(c_eco),
                    "colli_others": int(c_oth),
                    "colli_vario": int(c_var),
                    "colli_cont": 0,
                    "colli_mat_vario": 0,
                    "colli_dann": 0,
                    "colli_non_conf": 0,
                    "anomalie_scarico": "",
                    "note": form_note,
                    "prev_abbigl": p_abb,
                    "prev_calzat": p_calz,
                    "prev_ecom": p_eco,
                    "prev_others": p_oth,
                    "prev_totale": p_tot,
                    "intershops_list": inter_rows_data,
                    "stringa": computed_stringa,
                }
                new_id = save_or_update_bolla(bolla_save_payload)
                if save_next_clicked and store_choices:
                    try:
                        curr_idx = store_choices.index(sel_store_str)
                        if curr_idx + 1 < len(store_choices):
                            st.session_state["_next_store_override"] = store_choices[curr_idx + 1]
                    except Exception:
                        pass
                act_word = "aggiornata" if existing_bolla else "salvata"
                st.session_state["flash_bolle_msg"] = f"🎉 Bolla #{new_id} per Store **{current_sid}** {act_word} con successo!"
                st.rerun()

        # --------------------------------------------------------------------------
    # SOTTO-SCHEDA 2: ELENCO, FILTRI & STAMPA
    # --------------------------------------------------------------------------
    with tab_b_list:
        store_giro_map = {}
        all_giri_list = []
        if not df_stores_side.empty:
            store_giro_map = df_stores_side.set_index("store_id")["giro"].fillna("").to_dict()
            all_giri_list = sorted([g for g in df_stores_side["giro"].dropna().unique() if str(g).strip()])

        f_c1, f_c2, f_c3, f_c4 = st.columns([1.2, 1.4, 1.2, 1.8])
        with f_c1:
            f_giro = st.selectbox("Filtra Giro", ["TUTTI"] + all_giri_list, key="bolle_f_giro")
        with f_c2:
            f_carrier = st.selectbox("Filtra Vettore", ["TUTTI"] + get_all_carriers(), key="bolle_f_carrier")
        with f_c3:
            f_tipo = st.selectbox("Tipo Consegna", ["TUTTI", "STD", "DOPPIA"], key="bolle_f_tipo")
        with f_c4:
            f_search = st.text_input("🔍 Cerca Store ID o Nome", "", key="bolle_f_search")

        df_bolle = get_bolle(
            data=target_date,
            vettore=f_carrier if f_carrier != "TUTTI" else None,
            tipo_cons=f_tipo if f_tipo != "TUTTI" else None,
            search=f_search if f_search else None,
        )

        if not df_bolle.empty:
            df_bolle["giro"] = df_bolle["id_store"].astype(str).map(lambda s: store_giro_map.get(s, ""))
            if f_giro != "TUTTI":
                df_bolle = df_bolle[df_bolle["giro"] == f_giro].copy()

        # Metriche rapide sulla selezione
        tot_colli_b = int((
            df_bolle["colli_abbigl"] + df_bolle["colli_calzat"] +
            df_bolle["colli_ecom"] + df_bolle["colli_others"] + df_bolle["colli_vario"]
        ).sum()) if not df_bolle.empty else 0

        mk1, mk2, mk3, mk4, mk5 = st.columns(5)
        mk1.metric("Bolle Visualizzate", len(df_bolle))
        mk2.metric("Colli Totali", format_number_it(tot_colli_b, 0))
        mk3.metric("Abbigliamento", format_number_it(int(df_bolle["colli_abbigl"].sum()) if not df_bolle.empty else 0, 0))
        mk4.metric("Calzature", format_number_it(int(df_bolle["colli_calzat"].sum()) if not df_bolle.empty else 0, 0))
        mk5.metric("Altri + E-Com", format_number_it(int(df_bolle["colli_others"].sum() + df_bolle["colli_ecom"].sum()) if not df_bolle.empty else 0, 0))

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
            is_filt = (f_giro != "TUTTI" or f_tipo != "TUTTI" or f_carrier != "TUTTI" or bool(f_search))
            lbl_print = f"🖨️ Stampa Selezione ({len(df_bolle)})" if is_filt else f"🖨️ Stampa Tutte ({len(df_bolle)})"
            if st.button(lbl_print, use_container_width=True):
                if not df_bolle.empty:
                    st.session_state["print_html"] = render_bolla_printable_html(df_bolle.to_dict(orient="records"), title=f"Bolle Consegna - {format_date_it(target_date)}")
                    st.session_state["print_title"] = f"Bolle_{target_date}"
                else:
                    st.warning("Nessuna bolla da stampare.")
        with b_act4:
            if not df_bolle.empty:
                excel_bytes = export_bolle_excel(df_bolle, target_date)
                st.download_button(
                    "📥 Esporta Excel",
                    data=excel_bytes,
                    file_name=f"Riepilogo_Bolle_{target_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                st.button("📥 Esporta Excel", disabled=True, use_container_width=True)
        with b_act5:
            if has_perm("can_delete_bolle"):
                with st.popover("🗑️ Svota Bolle Data", use_container_width=True):
                    st.warning(f"Eliminare tutte le bolle del **{format_date_it(target_date)}**?")
                    if st.button("Conferma Eliminazione", type="primary", use_container_width=True, key="btn_del_bolle_dt"):
                        with st.spinner(f"🗑️ Eliminazione bolle del {format_date_it(target_date)} in corso..."):
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
            # Format quantities as clean integers
            for col_n in ["TOT_COLLI", "colli_abbigl", "colli_calzat", "colli_others", "colli_ecom", "colli_vario", "colli_cont", "colli_mat_vario", "colli_dann", "colli_non_conf"]:
                if col_n in df_b_disp.columns:
                    df_b_disp[col_n] = df_b_disp[col_n].fillna(0).round().astype(int)

            cols_map = {
                "giro": "Giro",
                "id_store": "Store ID",
                "punto_vendita": "Insegna",
                "store_name": "Punto Vendita",
                "tipo_cons": "Tipo",
                "TOT_COLLI": "Tot. Colli",
                "colli_abbigl": "Abbigliamento",
                "colli_calzat": "Calzature",
                "colli_others": "Altri",
                "colli_ecom": "E-Com",
                "vettore": "Vettore",
                "tipo_mezzo": "Mezzo",
                "stringa": "Intershops / Note"
            }
            cols_avail = [c for c in cols_map.keys() if c in df_b_disp.columns]
            df_show = df_b_disp[cols_avail].rename(columns=cols_map)
            st.dataframe(
                df_show,
                use_container_width=True,
                height=420,
                column_config={
                    "Tot. Colli": st.column_config.NumberColumn(format="%d"),
                    "Abbigliamento": st.column_config.NumberColumn(format="%d"),
                    "Calzature": st.column_config.NumberColumn(format="%d"),
                    "Altri": st.column_config.NumberColumn(format="%d"),
                    "E-Com": st.column_config.NumberColumn(format="%d"),
                }
            )

            # Tool di eliminazione rapida singola bolla
            if has_perm("can_delete_bolle"):
                with st.expander("🗑️ Elimina Singola Bolla da questa Data"):
                    ed_c1, ed_c2 = st.columns([3, 1])
                    with ed_c1:
                        bolla_choices = {
                            int(r["id"]): f"ID #{int(r['id'])} — Negozio {r.get('id_store', '')} ({r.get('punto_vendita', '')} - {r.get('tipo_cons', 'STD')}) — Tot: {int(round(r.get('TOT_COLLI', 0)))} colli"
                            for _, r in df_b_disp.iterrows() if "id" in r and pd.notna(r["id"])
                        }
                        selected_bolla_to_del = st.selectbox(
                            "Seleziona Bolla da Eliminare:",
                            options=list(bolla_choices.keys()),
                            format_func=lambda bid: bolla_choices.get(bid, str(bid)),
                            key="sb_del_single_bolla"
                        )
                    with ed_c2:
                        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                        if st.button("🗑️ Elimina Questa Bolla", type="primary", use_container_width=True, key="btn_del_single_bolla"):
                            if selected_bolla_to_del:
                                delete_bolla(selected_bolla_to_del)
                                st.success(f"Bolla #{selected_bolla_to_del} eliminata con successo.")
                                st.rerun()


    # ==============================================================================
    # PAGE 3: CONSUNTIVO & PLANNER INDITEX (CONFRONTO PREVISIONE VS BOLLE REALI)
    # ==============================================================================

# ==============================================================================
# PAGE: SPUNTA BANCHINA & CONTEGGIO MERCI (MOBILE TOUCHSCREEN)
# ==============================================================================
elif "Spunta Banchina" in menu:
    st.markdown('<div class="main-header">📱 Spunta Banchina & Conteggio Merci</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Interfaccia touch per smartphone & banchina: seleziona il punto vendita, confronta il dato previsionale e inserisci le quantità contate allo scarico.</div>', unsafe_allow_html=True)

    all_b_dates = get_bolle_dates()
    if not all_b_dates:
        st.info("ℹ️ Nessuna bolla di consegna registrata in archivio. Genera prima le bolle dalla Previsione Arrivi.")
    else:
        # 1. Filtri Rapidi di Testata Mobile
        c_mob1, c_mob2, c_mob3 = st.columns([1.5, 1.5, 1.2])
        with c_mob1:
            sel_spunta_dt = st.selectbox(
                "📅 Data di Consegna",
                all_b_dates,
                format_func=lambda d: f"{format_date_it(d)} ({d})",
                key="mob_spunta_date"
            )
        
        df_b_date = get_bolle(data_consegna=sel_spunta_dt)
        all_giri_mob = ["TUTTI"]
        if not df_b_date.empty and not df_stores_side.empty:
            s_map = df_stores_side.set_index("store_id")["giro"].dropna().to_dict()
            df_b_date["giro"] = df_b_date["id_store"].map(s_map).fillna("DA ASSEGNARE")
            g_uniq = sorted([g for g in df_b_date["giro"].unique() if str(g).strip()])
            all_giri_mob += g_uniq

        with c_mob2:
            sel_giro_mob = st.selectbox("🚛 Filtro Giro", all_giri_mob, key="mob_spunta_giro")

        if sel_giro_mob != "TUTTI":
            df_b_date = df_b_date[df_b_date["giro"] == sel_giro_mob]

        with c_mob3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            spuntati_cnt = int((df_b_date.get("spuntato", pd.Series(0, index=df_b_date.index)).fillna(0) == 1).sum()) if not df_b_date.empty else 0
            tot_b_cnt = len(df_b_date)
            st.caption(f"Avanzamento: **{spuntati_cnt} / {tot_b_cnt}** spuntati")

        # Quadratura Telemetrica Live Barra 0 vs Barra 9 (Previsione vs Spunta)
        df_b_quad = get_bolle(data_consegna=sel_spunta_dt)
        if not df_b_quad.empty:
            b0_sub = df_b_quad[df_b_quad["tipo_cons"] == "STD"]
            b9_sub = df_b_quad[df_b_quad["tipo_cons"] == "DOPPIA"]

            b0_eff = int(round(float(b0_sub["TOT_COLLI"].sum()))) if not b0_sub.empty else 0
            b0_prev = int(round(float(b0_sub["prev_totale"].sum()))) if not b0_sub.empty else 0
            b0_delta = b0_eff - b0_prev
            b0_sp_ok = int((b0_sub["spuntato"].fillna(0) == 1).sum()) if not b0_sub.empty else 0
            b0_n_tot = len(b0_sub)

            b9_eff = int(round(float(b9_sub["TOT_COLLI"].sum()))) if not b9_sub.empty else 0
            b9_prev = int(round(float(b9_sub["prev_totale"].sum()))) if not b9_sub.empty else 0
            b9_delta = b9_eff - b9_prev
            b9_sp_ok = int((b9_sub["spuntato"].fillna(0) == 1).sum()) if not b9_sub.empty else 0
            b9_n_tot = len(b9_sub)

            t_eff = b0_eff + b9_eff
            t_prev = b0_prev + b9_prev
            t_delta = t_eff - t_prev
            t_sp_ok = b0_sp_ok + b9_sp_ok
            t_n_tot = b0_n_tot + b9_n_tot

            b0_sign = "+" if b0_delta > 0 else ""
            b9_sign = "+" if b9_delta > 0 else ""
            t_sign = "+" if t_delta > 0 else ""
            b0_col = "#15803D" if b0_delta >= 0 else "#DC2626"
            b9_col = "#15803D" if b9_delta >= 0 else "#DC2626"
            t_col = "#15803D" if t_delta >= 0 else "#DC2626"

            st.markdown(f"""
            <div class="modern-card" style="padding: 12px 16px; margin-bottom: 14px; background: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                    <span style="font-size: 12px; font-weight: 800; color: #0F172A; text-transform: uppercase;">
                        📊 QUADRATURA LIVE SPUNTA — {format_date_it(sel_spunta_dt)}
                    </span>
                    <span style="font-size: 11px; font-weight: 700; color: #475569;">
                        Stato Conteggio: <strong style="color: #0284C7;">{t_sp_ok} / {t_n_tot} Negozi</strong>
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px;">
                    <div style="background: #F0FDF4; border: 1px solid #86EFAC; border-radius: 8px; padding: 8px 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 11px; font-weight: 800; color: #166534;">🚚 BARRA 0 (Standard)</span>
                            <span style="font-size: 10px; font-weight: 700; background: #DCFCE7; color: #15803D; padding: 1px 6px; border-radius: 8px;">{b0_sp_ok}/{b0_n_tot} ok</span>
                        </div>
                        <div style="font-size: 19px; font-weight: 800; color: #14532D; margin-top: 3px;">
                            {format_number_it(b0_eff, 0)} <span style="font-size: 11.5px; font-weight: 600;">colli</span>
                        </div>
                        <div style="font-size: 10.5px; color: #166534; margin-top: 2px; display: flex; justify-content: space-between;">
                            <span>Prev: <strong>{format_number_it(b0_prev, 0)}</strong></span>
                            <span style="font-weight: 700; color: {b0_col};">Delta: {b0_sign}{b0_delta}</span>
                        </div>
                    </div>

                    <div style="background: #FEF3C7; border: 1px solid #FCD34D; border-radius: 8px; padding: 8px 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 11px; font-weight: 800; color: #92400E;">🔁 BARRA 9 (2ª Uscita)</span>
                            <span style="font-size: 10px; font-weight: 700; background: #FDE68A; color: #B45309; padding: 1px 6px; border-radius: 8px;">{b9_sp_ok}/{b9_n_tot} ok</span>
                        </div>
                        <div style="font-size: 19px; font-weight: 800; color: #78350F; margin-top: 3px;">
                            {format_number_it(b9_eff, 0)} <span style="font-size: 11.5px; font-weight: 600;">colli</span>
                        </div>
                        <div style="font-size: 10.5px; color: #92400E; margin-top: 2px; display: flex; justify-content: space-between;">
                            <span>Prev: <strong>{format_number_it(b9_prev, 0)}</strong></span>
                            <span style="font-weight: 700; color: {b9_col};">Delta: {b9_sign}{b9_delta}</span>
                        </div>
                    </div>

                    <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 8px 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 11px; font-weight: 800; color: #1E293B;">📦 TOTALE CONTATI</span>
                            <span style="font-size: 10px; font-weight: 700; background: #E2E8F0; color: #475569; padding: 1px 6px; border-radius: 8px;">Banchina</span>
                        </div>
                        <div style="font-size: 19px; font-weight: 800; color: #0F172A; margin-top: 3px;">
                            {format_number_it(t_eff, 0)} <span style="font-size: 11.5px; font-weight: 600;">colli</span>
                        </div>
                        <div style="font-size: 10.5px; color: #475569; margin-top: 2px; display: flex; justify-content: space-between;">
                            <span>Prev: <strong>{format_number_it(t_prev, 0)}</strong></span>
                            <span style="font-weight: 800; color: {t_col};">Delta: {t_sign}{t_delta}</span>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        if df_b_date.empty:
            st.warning(f"Nessuna bolla trovata per la data {format_date_it(sel_spunta_dt)} nel giro selezionato.")
        else:
            # Opzioni di selezione negozio
            b_options = {}
            for _, r in df_b_date.iterrows():
                bid = int(r["id"])
                sid = str(r["id_store"])
                sname = str(r.get("store_name", sid))
                tipo = str(r.get("tipo_cons", "STD"))
                tot_c = int(round(float(r.get("TOT_COLLI", 0) or 0)))
                prev_c = int(round(float(r.get("prev_totale", 0) or 0)))
                is_sp = int(r.get("spuntato", 0) or 0) == 1
                giro_st = str(r.get("giro", ""))
                
                if is_sp:
                    tag = "🟢 [SPUNTATO]"
                else:
                    tag = "⏳ [DA CONTARE]"
                b_options[bid] = f"{tag} {sid} - {sname} ({tipo}) [{giro_st}] — Contati: {tot_c} | Prev: {prev_c}"

            if "_next_spunta_bid" in st.session_state and st.session_state["_next_spunta_bid"] in b_options:
                st.session_state["mob_selected_bid"] = st.session_state.pop("_next_spunta_bid")

            sel_bid = st.selectbox(
                "🏪 Seleziona Punto Vendita da Spuntare:",
                options=list(b_options.keys()),
                format_func=lambda bid: b_options[bid],
                key="mob_selected_bid"
            )

            b_curr = df_b_date[df_b_date["id"] == sel_bid].iloc[0].to_dict()
            curr_sid = str(b_curr.get("id_store", ""))
            curr_sname = str(b_curr.get("store_name", ""))
            curr_pv = str(b_curr.get("punto_vendita", ""))
            curr_tipo = str(b_curr.get("tipo_cons", "STD"))
            curr_mezzo = str(b_curr.get("tipo_mezzo", "—"))
            curr_vett = str(b_curr.get("vettore", "LACCHI SPA"))
            curr_ind = str(b_curr.get("indirizzo_destino", "—"))
            curr_giro = str(b_curr.get("giro", "—"))

            prev_tot_m = int(round(float(b_curr.get("prev_totale", 0) or 0)))
            prev_abb_m = int(round(float(b_curr.get("prev_abbigl", 0) or 0)))
            prev_calz_m = int(round(float(b_curr.get("prev_calzat", 0) or 0)))
            prev_eco_m = int(round(float(b_curr.get("prev_ecom", 0) or 0)))
            prev_oth_m = int(round(float(b_curr.get("prev_others", 0) or 0)))

            # Scheda Negozio Touch
            st.markdown(f"""
            <div class="modern-card" style="padding: 14px 18px; margin-top: 8px; margin-bottom: 12px; border-left: 5px solid #0284C7;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <span style="font-size: 18px; font-weight: 800; color: #0F172A;">Store {curr_sid}</span>
                        <span style="font-size: 15px; font-weight: 600; color: #334155; margin-left: 8px;">{curr_sname}</span>
                        <span style="background: #E0F2FE; color: #0369A1; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 9999px; margin-left: 8px;">{curr_pv}</span>
                        <span style="background: #FEF3C7; color: #B45309; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 9999px; margin-left: 4px;">{curr_tipo}</span>
                    </div>
                    <div style="font-size: 13px; font-weight: 700; color: #64748B;">
                        Giro: <strong style="color: #0F172A;">{curr_giro}</strong> | Mezzo: <strong style="color: #0F172A;">{curr_mezzo}</strong> | Vettore: <strong style="color: #0F172A;">{curr_vett}</strong>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Card Valori Previsionali Attesi
            st.markdown(f"""
            <div class="modern-card" style="padding: 12px 18px; margin-bottom: 14px; background-color: #F8FAFC; border: 1px solid #E2E8F0;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">📊 DATI PREVISIONALI ATTESI</span>
                    <span style="font-size: 14px; font-weight: 800; color: #1E3A8A;">TOTALE PREVISTO: {format_number_it(prev_tot_m, 0)} COLLI</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 4px;">
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 8px; text-align: center;">
                        <div style="font-size: 9.5px; font-weight: 700; color: #64748B;">👗 TESSILE</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(prev_abb_m, 0)}</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 8px; text-align: center;">
                        <div style="font-size: 9.5px; font-weight: 700; color: #64748B;">👟 SCARPE</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(prev_calz_m, 0)}</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 8px; text-align: center;">
                        <div style="font-size: 9.5px; font-weight: 700; color: #64748B;">📦 E-COM</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(prev_eco_m, 0)}</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 8px; text-align: center;">
                        <div style="font-size: 9.5px; font-weight: 700; color: #64748B;">📦 ALTRI</div>
                        <div style="font-size: 14px; font-weight: 800; color: #0F172A;">{format_number_it(prev_oth_m, 0)}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Conteggio Effettivo Touch
            st.markdown("##### ✍️ Conteggio Merce Banchina (Quantità Effettive)")
            c_m1, c_m2, c_m3 = st.columns(3)
            with c_m1:
                init_abb = int(round(float(b_curr.get("colli_abbigl") or 0)))
                m_abb = st.number_input("👗 Abbigliamento", min_value=0, value=init_abb, step=1, key=f"m_in_abb_{sel_bid}")
                init_var = int(round(float(b_curr.get("colli_vario") or 0)))
                m_var = st.number_input("📦 Mat. Vario", min_value=0, value=init_var, step=1, key=f"m_in_var_{sel_bid}")
            with c_m2:
                init_calz = int(round(float(b_curr.get("colli_calzat") or 0)))
                m_calz = st.number_input("👟 Calzature", min_value=0, value=init_calz, step=1, key=f"m_in_calz_{sel_bid}")
                init_eco = int(round(float(b_curr.get("colli_ecom") or 0)))
                m_eco = st.number_input("📦 E-Commerce", min_value=0, value=init_eco, step=1, key=f"m_in_eco_{sel_bid}")
            with c_m3:
                init_oth = int(round(float(b_curr.get("colli_others") or 0)))
                m_oth = st.number_input("📦 Altri Bultos", min_value=0, value=init_oth, step=1, key=f"m_in_oth_{sel_bid}")

            m_tot_calc = int(m_abb + m_calz + m_eco + m_oth + m_var)
            m_delta = m_tot_calc - prev_tot_m

            # Live Delta Banner
            if m_delta == 0:
                st.success(f"🟢 **CONFORME: {format_number_it(m_tot_calc, 0)} Colli Contati (Delta: 0 rispetto al previsto)**")
            elif m_delta > 0:
                st.warning(f"🟡 **ECCEDENZA RISCONTRATA: {format_number_it(m_tot_calc, 0)} Colli Contati (+{m_delta} colli in più rispetto al previsto di {prev_tot_m})**")
            else:
                st.error(f"🔴 **MANCANZA RISCONTRATA: {format_number_it(m_tot_calc, 0)} Colli Contati ({m_delta} colli rispetto al previsto di {prev_tot_m})**")

            # Campo Note Banchina
            m_note = st.text_input("📝 Note / Osservazioni Banchina", value=str(b_curr.get("note") or ""), placeholder="es. merce integra, 1 collo bagnato, etc.", key=f"m_note_{sel_bid}")

            # Pulsanti Touchscreen Grandi
            col_mb1, col_mb2 = st.columns([1.6, 1.4])
            with col_mb1:
                btn_m_save = st.button("💾 REGISTRA SPUNTA SU BOLLA", type="primary", use_container_width=True, key=f"btn_m_save_{sel_bid}")
            with col_mb2:
                btn_m_next = st.button("💾 Salva e Passa al Prossimo ➡️", use_container_width=True, key=f"btn_m_next_{sel_bid}")

            if btn_m_save or btn_m_next:
                b_curr["colli_abbigl"] = int(m_abb)
                b_curr["colli_calzat"] = int(m_calz)
                b_curr["colli_ecom"] = int(m_eco)
                b_curr["colli_others"] = int(m_oth)
                b_curr["colli_vario"] = int(m_var)
                b_curr["note"] = m_note
                b_curr["spuntato"] = 1
                b_curr["prev_abbigl"] = prev_abb_m
                b_curr["prev_calzat"] = prev_calz_m
                b_curr["prev_ecom"] = prev_eco_m
                b_curr["prev_others"] = prev_oth_m
                b_curr["prev_totale"] = prev_tot_m
                save_or_update_bolla(b_curr)

                if btn_m_next and b_options:
                    all_bids = list(b_options.keys())
                    try:
                        curr_i = all_bids.index(sel_bid)
                        if curr_i + 1 < len(all_bids):
                            st.session_state["_next_spunta_bid"] = all_bids[curr_i + 1]
                    except Exception:
                        pass

                st.session_state["flash_bolle_msg"] = f"🎉 Spunta registrata per Negozio **{curr_sid}** ({curr_sname})! Totale: **{m_tot_calc}** colli."
                st.rerun()


elif "Consuntivo & Planner" in menu:
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
            export_planner_roma(
                df_planner=df_planner_real,
                output_path=out_planner_path,
                template_path=PLANNER_TEMPLATE_FILE,
                delivery_date=sel_plan_date,
                df_stores=df_stores_side
            )
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
elif "Anagrafica Negozi" in menu:
    _inject_modern_css()
    st.markdown('<div class="main-header">🏢 Anagrafica Punti Vendita, Giri & Parco Mezzi</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Gestione integrata dei punti vendita, percorsi/giri, autisti e flotta veicoli con relative capienze operative.</div>', unsafe_allow_html=True)

    df_stores = get_stores_df()
    df_vehicles = get_vehicles_df()

    # Dynamic active vehicles list for selectboxes
    if not df_vehicles.empty and "cod_mezzo" in df_vehicles.columns:
        mezzi_list_full = df_vehicles[df_vehicles["attivo"].fillna("SI").str.upper() == "SI"]["cod_mezzo"].tolist()
        if not mezzi_list_full:
            mezzi_list_full = df_vehicles["cod_mezzo"].tolist()
    else:
        mezzi_list_full = ["BILICO 33", "BILICO x 3", "MOTRICE 18 PLT", "MOTRICE 14", "MOTRICE 14x3", "EUROCARGO 75", "FURGONE 8"]

    tab_negozi, tab_mezzi = st.tabs([
        "🏢 Punti Vendita & Giri di Consegna",
        "🚛 Anagrafica Parco Mezzi & Capienze"
    ])

    with tab_negozi:
        # --- 1. KPI TOP METRICS CARDS (NEGOZI) ---
        tot_st = len(df_stores)
        att_st = int((df_stores["attivo"].fillna("SI").str.upper() == "SI").sum()) if not df_stores.empty else 0
        inatt_st = tot_st - att_st
        giri_cnt = int(df_stores["giro"].dropna().nunique()) if not df_stores.empty else 0
        vett_cnt = int(df_stores["vettore"].dropna().nunique()) if not df_stores.empty else 0
        lav_cnt = int((df_stores["lavorazione"].fillna("NO").astype(str).str.upper() != "NO").sum()) if not df_stores.empty else 0
        scorp_cnt = int((df_stores["scorporo_profumi"].fillna("NO").astype(str).str.upper() == "SI").sum()) if not df_stores.empty else 0

        kpi_anag_html = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin-bottom: 20px;">
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🏢 Negozi Censiti</div>
                <div style="font-size: 22px; font-weight: 800; color: #0284C7; margin-top: 4px;">{tot_st}</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">{att_st} Operativi • <span style="color:#DC2626; font-weight:700;">{inatt_st} Standby</span></div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🚚 Giri Operativi</div>
                <div style="font-size: 22px; font-weight: 800; color: #0F172A; margin-top: 4px;">{giri_cnt} Giri</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Mappati per flotta standard e B9</div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🚛 Vettori Mappati</div>
                <div style="font-size: 22px; font-weight: 800; color: #10B981; margin-top: 4px;">{vett_cnt} Vettori</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Assegnati ai singoli giri</div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🏭 Lavorazioni Banchina</div>
                <div style="font-size: 22px; font-weight: 800; color: #6366F1; margin-top: 4px;">{lav_cnt} Negozi</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Stender 'a madonna' & Zara Home</div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🧴 Scorporo Profumi</div>
                <div style="font-size: 22px; font-weight: 800; color: #E11D48; margin-top: 4px;">{scorp_cnt} Negozi</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Deduzione capi piegati attiva</div>
            </div>
        </div>
        """
        st.markdown(kpi_anag_html, unsafe_allow_html=True)

        # --- 2. TOOL AGGIORNAMENTO MASSIVO PER GIRO ---
        with st.expander("⚡ Aggiornamento Massivo per Giro (Vettore & Tipo Mezzo)", expanded=False):
            st.caption("Assegna o modifica contemporaneamente Vettore e Tipo Mezzo per tutti i punti vendita del giro selezionato:")

            df_giro_sum = get_giro_summary()
            giri_avail = sorted([g for g in df_stores["giro"].dropna().unique().tolist() if str(g).strip() != ""], key=_giro_sort_key) if not df_stores.empty else []

            col_bm1, col_bm2, col_bm3, col_bm4, col_bm5 = st.columns([1.1, 1.8, 1.8, 1.8, 1.6])
            with col_bm1:
                sel_g = st.selectbox("Seleziona Giro", giri_avail, key="mass_sel_giro") if giri_avail else "ZA1"
                g_row = df_giro_sum[df_giro_sum["giro"] == sel_g].iloc[0] if not df_giro_sum.empty and not df_giro_sum[df_giro_sum["giro"] == sel_g].empty else {}
            with col_bm2:
                curr_g_vet = "" if str(g_row.get("vettore", "")) in ["Non Assegnato", "—", "None", "nan", None] else str(g_row.get("vettore", "LACCHI SPA"))
                g_vet = st.text_input("Vettore Assegnato", value=curr_g_vet or "LACCHI SPA", placeholder="Es. LACCHI SPA", key=f"mass_vet_{sel_g}")
            with col_bm3:
                curr_m = str(g_row.get("tipo_mezzo", "MOTRICE 18 PLT") or "MOTRICE 18 PLT").strip()
                idx_m = mezzi_list_full.index(curr_m) if curr_m in mezzi_list_full else 0
                g_mez = st.selectbox("Mezzo Standard (/0)", options=mezzi_list_full, index=idx_m, key=f"mass_mez_{sel_g}")
            with col_bm4:
                curr_md = str(g_row.get("tipo_mezzo_doppia", "FURGONE 8") or "FURGONE 8").strip()
                idx_md = mezzi_list_full.index(curr_md) if curr_md in mezzi_list_full else 0
                g_mez_d = st.selectbox("Mezzo Giri Doppi (/9)", options=mezzi_list_full, index=idx_md, key=f"mass_mez_d_{sel_g}")
            with col_bm5:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button(f"💾 APPLICA AL GIRO {sel_g}", type="primary", use_container_width=True, key=f"btn_apply_giro_{sel_g}"):
                    n_up = update_giro_driver(sel_g, autista="", cell_autista="", tipo_mezzo=g_mez, tipo_mezzo_doppia=g_mez_d, vettore=g_vet)
                    st.success(f"✅ Aggiornati tutti i **{n_up}** negozi del giro **{sel_g}** (Standard: {g_mez}, Doppia: {g_mez_d})!")
                    st.rerun()

            if not df_giro_sum.empty:
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                df_g_disp = df_giro_sum[["giro", "n_stores", "vettore", "tipo_mezzo", "tipo_mezzo_doppia", "elenco_negozi"]].copy()
                df_g_disp.columns = ["Giro", "N. Negozi", "Vettore Assegnato", "Mezzo Standard (/0)", "Mezzo Giri Doppi (/9)", "Negozi Mappati"]
                st.dataframe(df_g_disp, use_container_width=True, hide_index=True)

        FORMULA_OPTIONS = [
            "MC/1,9",
            "MC*1,5/1,8",
            "MC/1,5",
            "(MC*1,5/1,8)*0,7",
            "(MC/1,9)*0,7",
            "(MC/1,5 )* 0,7",
        ]

        # --- 3. ELENCO & CONFIGURAZIONE PUNTI VENDITA (UNIFICATO) ---
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">🏢 Elenco & Configurazione Punti Vendita</div>', unsafe_allow_html=True)
        st.caption("Visualizza l'elenco completo dei punti vendita e modifica direttamente i dati nelle celle della tabella. Clicca su **Salva Modifiche** per aggiornare:")

        cf1, cf2, cf3, cf4, cf5, cf6 = st.columns([1.5, 1.1, 1.1, 1.1, 1.1, 1.1])
        with cf1:
            f_search = st.text_input("🔍 Cerca Negozio (ID, Nome o Indirizzo)", "", key="anag_search", placeholder="Scrivi per filtrare...")
        with cf2:
            f_giro = st.selectbox("Filtra Giro", ["TUTTI"] + giri_avail, key="anag_f_giro")
        with cf3:
            all_brands = sorted([b for b in df_stores["brand"].dropna().unique().tolist() if str(b).strip()]) if not df_stores.empty else []
            f_brand = st.selectbox("Filtra Brand", ["TUTTI"] + all_brands, key="anag_f_brand")
        with cf4:
            f_lav = st.selectbox("Lavorazione", ["TUTTI", "SI TESSILE", "SI HOME", "NO"], key="anag_f_lav")
        with cf5:
            f_sdop = st.selectbox("Giri Doppi (/9)", ["TUTTI", "SOLO GIRI DOPPI (B /9)", "SOLO STANDARD (/0)"], key="anag_f_sdop")
        with cf6:
            f_att = st.selectbox("Stato Negozio", ["TUTTI", "SI (Operativo)", "NO (Standby)"], key="anag_f_att")

        df_filtered = df_stores.copy() if not df_stores.empty else pd.DataFrame()
        if not df_filtered.empty:
            if f_search:
                q = f_search.strip().lower()
                df_filtered = df_filtered[
                    df_filtered["store_id"].astype(str).str.lower().str.contains(q) |
                    df_filtered["store_name"].astype(str).str.lower().str.contains(q) |
                    df_filtered["indirizzo"].astype(str).str.lower().str.contains(q) |
                    df_filtered["cc"].astype(str).str.lower().str.contains(q)
                ]
            if f_giro != "TUTTI":
                df_filtered = df_filtered[df_filtered["giro"] == f_giro]
            if f_brand != "TUTTI":
                df_filtered = df_filtered[df_filtered["brand"] == f_brand]
            if f_lav != "TUTTI":
                df_filtered = df_filtered[df_filtered["lavorazione"].fillna("NO").str.upper() == f_lav]
            if f_sdop == "SOLO GIRI DOPPI (B /9)":
                df_filtered = df_filtered[df_filtered["store_id"].astype(str).str.endswith("B")]
            elif f_sdop == "SOLO STANDARD (/0)":
                df_filtered = df_filtered[~df_filtered["store_id"].astype(str).str.endswith("B")]
            if f_att == "SI (Operativo)":
                df_filtered = df_filtered[df_filtered["attivo"].fillna("SI").str.upper() == "SI"]
            elif f_att == "NO (Standby)":
                df_filtered = df_filtered[df_filtered["attivo"].fillna("SI").str.upper() == "NO"]

        col_save_s_top, col_cnt_s = st.columns([2.5, 3.5])
        with col_save_s_top:
            save_s = st.button("💾 SALVA MODIFICHE PUNTI VENDITA", type="primary", use_container_width=True, key="btn_save_stores_main")
        with col_cnt_s:
            st.markdown(f"<div style='margin-top:8px; font-size:13px; color:#64748B;'>Negozi visualizzati: <strong>{len(df_filtered)}</strong> / {len(df_stores)} ({att_st} operativi)</div>", unsafe_allow_html=True)

        cols_order = [
            "store_id", "store_name", "brand", "giro", "attivo", "vettore", "lavorazione",
            "scorporo_profumi", "formula", "tipo_mezzo",
            "sdoppiamento_b9",
            "indirizzo", "provincia", "cod_sga", "cc"
        ]
        df_grid_edit = df_filtered[[c for c in cols_order if c in df_filtered.columns]].copy() if not df_filtered.empty else pd.DataFrame(columns=cols_order)

        f_opts_grid = list(FORMULA_OPTIONS)
        for f_val in df_grid_edit["formula"].dropna().unique():
            if f_val and f_val not in f_opts_grid:
                f_opts_grid.append(str(f_val))

        edited_df = st.data_editor(
            df_grid_edit,
            column_config={
                "store_id": st.column_config.TextColumn("Store ID", disabled=True, width="small"),
                "store_name": st.column_config.TextColumn("Nome Negozio / Insegna", required=True, width="medium"),
                "brand": st.column_config.SelectboxColumn("Brand", options=["ZARA", "BERSHKA", "PULL&BEAR", "MASSIMO DUTTI", "OYSHO", "STRADIVARIUS", "ZARA HOME", "ALTRO"], required=True, width="small"),
                "giro": st.column_config.TextColumn("Giro", required=True, width="small"),
                "attivo": st.column_config.SelectboxColumn("Stato", options=["SI", "NO"], required=True, width="small"),
                "vettore": st.column_config.TextColumn("Vettore", width="medium"),
                "lavorazione": st.column_config.SelectboxColumn("Lavorazione Piattaforma", options=["NO", "SI TESSILE", "SI HOME"], required=True, width="medium"),
                "scorporo_profumi": st.column_config.SelectboxColumn("Scorporo Profumi", options=["NO", "SI"], required=True, width="small"),
                "formula": st.column_config.SelectboxColumn("Formula Pedane", options=f_opts_grid, required=True, width="medium"),
                "tipo_mezzo": st.column_config.SelectboxColumn("Tipo Mezzo", options=mezzi_list_full, width="medium"),
                "sdoppiamento_b9": st.column_config.SelectboxColumn("2ª Consegna (/9)", options=["NO", "SI"], required=True, width="small"),
                "indirizzo": st.column_config.TextColumn("Indirizzo Scarico", width="large"),
                "provincia": st.column_config.TextColumn("Prov.", width="small"),
                "cod_sga": st.column_config.NumberColumn("Cod. SGA", format="%d", width="small"),
                "cc": st.column_config.TextColumn("Centro Comm.", width="medium"),
            },
            use_container_width=True,
            height=520,
            key="anagrafica_editor_main",
        )

        if save_s:
            n_up = bulk_update_stores(edited_df)
            st.success(f"✅ Aggiornati con successo **{n_up}** punti vendita nel Database!")
            st.rerun()

        # SCHEDA DETTAGLIO / MODIFICA SINGOLO NEGOZIO
        with st.expander("🔍 Scheda Dettaglio / Modifica Singolo Negozio", expanded=False):
            st.caption("Seleziona qualsiasi negozio per visualizzarne la scheda completa, modificarne i parametri o scegliere la formula:")

            store_opts = [f"{r['store_id']} - {r['store_name']} ({r.get('brand', '')})" for _, r in df_stores.iterrows()] if not df_stores.empty else []
            sel_st_card = st.selectbox("Seleziona Punto Vendita da Modificare", store_opts, key="sel_st_card_edit")

            if sel_st_card:
                target_sid = sel_st_card.split(" - ")[0].strip()
                s_data = df_stores[df_stores["store_id"] == target_sid].iloc[0] if not df_stores[df_stores["store_id"] == target_sid].empty else None

                if s_data is not None:
                    ce1, ce2, ce3 = st.columns(3)
                    with ce1:
                        e_sn = st.text_input("Nome Negozio / Insegna", value=str(s_data.get("store_name", "")), key=f"e_sn_{target_sid}")
                        b_opts = ["ZARA", "BERSHKA", "PULL&BEAR", "MASSIMO DUTTI", "OYSHO", "STRADIVARIUS", "ZARA HOME", "ALTRO"]
                        curr_b = str(s_data.get("brand", "ZARA") or "ZARA").strip().upper()
                        idx_b = b_opts.index(curr_b) if curr_b in b_opts else 0
                        e_br = st.selectbox("Brand", b_opts, index=idx_b, key=f"e_br_{target_sid}")

                        att_opts = ["SI (Operativo)", "NO (Standby)"]
                        curr_att = "SI (Operativo)" if str(s_data.get("attivo", "SI")).strip().upper() == "SI" else "NO (Standby)"
                        e_att_sel = st.selectbox("Stato Negozio", att_opts, index=att_opts.index(curr_att), key=f"e_att_{target_sid}")
                        e_att_val = "SI" if "SI" in e_att_sel else "NO"

                        # FORMULA WITH PRESET OPTIONS
                        curr_form = str(s_data.get("formula", "MC/1,9") or "MC/1,9").strip()
                        f_opts = list(FORMULA_OPTIONS)
                        if curr_form and curr_form not in f_opts:
                            f_opts.append(curr_form)
                        idx_f = f_opts.index(curr_form) if curr_form in f_opts else 0
                        e_form = st.selectbox("Formula Calcolo Pedane", f_opts, index=idx_f, key=f"e_form_{target_sid}")

                    with ce2:
                        curr_g = str(s_data.get("giro", "ZA1") or "ZA1").strip()
                        e_g = st.text_input("Giro Assegnato", value=curr_g, key=f"e_g_{target_sid}").strip().upper()

                        curr_vett = str(s_data.get("vettore", "LACCHI SPA") or "LACCHI SPA").strip()
                        e_vett = st.text_input("Vettore Assegnato", value=curr_vett, key=f"e_vett_{target_sid}")

                        curr_m = str(s_data.get("tipo_mezzo", "MOTRICE 18 PLT") or "MOTRICE 18 PLT").strip()
                        idx_m = mezzi_list_full.index(curr_m) if curr_m in mezzi_list_full else 0
                        e_m = st.selectbox("Tipo Mezzo STD", options=mezzi_list_full, index=idx_m, key=f"e_m_{target_sid}")

                        lav_opts = ["NO", "SI TESSILE", "SI HOME"]
                        curr_lav = str(s_data.get("lavorazione", "NO") or "NO").strip().upper()
                        idx_lav = lav_opts.index(curr_lav) if curr_lav in lav_opts else 0
                        e_lav = st.selectbox("Lavorazione Piattaforma", lav_opts, index=idx_lav, key=f"e_lav_{target_sid}")

                    with ce3:
                        scorp_opts = ["NO", "SI"]
                        curr_scorp = str(s_data.get("scorporo_profumi", "NO") or "NO").strip().upper()
                        idx_scorp = scorp_opts.index(curr_scorp) if curr_scorp in scorp_opts else 0
                        e_scorp = st.selectbox("Scorporo Profumi", scorp_opts, index=idx_scorp, key=f"e_scorp_{target_sid}")

                        sdop_opts = ["NO", "SI"]
                        curr_sdop = str(s_data.get("sdoppiamento_b9", "NO") or "NO").strip().upper()
                        idx_sdop = sdop_opts.index(curr_sdop) if curr_sdop in sdop_opts else 0
                        e_sdop = st.selectbox("Sdoppiamento Barra 9 (/9)", sdop_opts, index=idx_sdop, key=f"e_sdop_{target_sid}")

                        curr_md = str(s_data.get("tipo_mezzo_doppia", "FURGONE 8") or "FURGONE 8").strip()
                        idx_md = mezzi_list_full.index(curr_md) if curr_md in mezzi_list_full else 0
                        e_md = st.selectbox("Mezzo /9", options=mezzi_list_full, index=idx_md, key=f"e_md_{target_sid}")

                        e_ind = st.text_input("Indirizzo Scarico", value=str(s_data.get("indirizzo", "") or ""), key=f"e_ind_{target_sid}")
                        e_cc = st.text_input("Centro Commerciale", value=str(s_data.get("cc", "") or ""), key=f"e_cc_{target_sid}")

                    if st.button(f"💾 SALVA MODIFICHE PER NEGOZIO {target_sid}", type="primary", use_container_width=True, key=f"btn_save_st_{target_sid}"):
                        update_store_record(target_sid, {
                            "store_name": e_sn.strip(),
                            "brand": e_br,
                            "punto_vendita": e_br,
                            "attivo": e_att_val,
                            "giro": e_g or "DA ASSEGNARE",
                            "vettore": e_vett.strip(),
                            "tipo_mezzo": e_m,
                            "lavorazione": e_lav,
                            "scorporo_profumi": e_scorp,
                            "sdoppiamento_b9": e_sdop,
                            "tipo_mezzo_doppia": e_md,
                            "formula": e_form.strip(),
                            "indirizzo": e_ind.strip(),
                            "cc": e_cc.strip(),
                        })
                        st.success(f"🎉 Negozio **{target_sid}** ({e_sn}) aggiornato con successo nel Database!")
                        st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        # --- 4. GESTIONE AGGIUNTA & ELIMINAZIONE NEGOZI ---
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">⚡ Operazioni Rapide Negozi</div>', unsafe_allow_html=True)
        col_st_act1, col_st_act2 = st.columns([1.5, 1.5])

        with col_st_act1:
            st.markdown("##### ➕ Inserisci Nuovo Negozio")
            with st.form("form_add_new_store", clear_on_submit=True):
                ns1, ns2 = st.columns(2)
                with ns1:
                    new_sid = st.text_input("Store ID (Numero Univoco)").strip()
                    new_sname = st.text_input("Nome Negozio").strip()
                    new_b = st.selectbox("Brand", ["ZARA", "BERSHKA", "PULL&BEAR", "MASSIMO DUTTI", "OYSHO", "STRADIVARIUS", "ZARA HOME", "ALTRO"])
                    new_g = st.text_input("Giro Assegnato", value="ZA1").strip().upper()
                with ns2:
                    new_vet = st.text_input("Vettore", value="LACCHI SPA").strip()
                    new_mez = st.selectbox("Mezzo STD", options=mezzi_list_full)
                    new_form = st.selectbox("Formula Pedane", FORMULA_OPTIONS)
                    new_att = st.selectbox("Stato Negozio", ["SI", "NO"])
                btn_create_st = st.form_submit_button("➕ REGISTRA NEGOZIO", type="primary", use_container_width=True)
                if btn_create_st:
                    if not new_sid or not new_sname:
                        st.error("Inserisci almeno Store ID e Nome Negozio.")
                    elif not df_stores.empty and new_sid in df_stores["store_id"].values:
                        st.error(f"Lo Store ID {new_sid} è già presente in anagrafica!")
                    else:
                        add_store_record({
                            "store_id": new_sid,
                            "store_name": new_sname,
                            "punto_vendita": new_b,
                            "brand": new_b,
                            "giro": new_g or "DA ASSEGNARE",
                            "vettore": new_vet,
                            "tipo_mezzo": new_mez,
                            "formula": new_form,
                            "lavorazione": "NO",
                            "scorporo_profumi": "NO",
                            "sdoppiamento_b9": "NO",
                            "attivo": new_att,
                        })
                        st.success(f"✅ Negozio **{new_sid}** ({new_sname}) registrato con successo!")
                        st.rerun()

        with col_st_act2:
            st.markdown("##### 🗑️ Elimina Punto Vendita dal Database")
            del_opts = [f"{r['store_id']} - {r['store_name']} ({r.get('brand', '')})" for _, r in df_stores.iterrows()] if not df_stores.empty else []
            sel_st_del = st.selectbox("Seleziona Negozio da Rimuovere", del_opts, key="sel_st_to_del_box")
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            if sel_st_del:
                del_id = sel_st_del.split(" - ")[0].strip()
                if st.button(f"🗑️ ELIMINA DEFINITIVAMENTE STORE {del_id}", type="primary", use_container_width=True, key="btn_confirm_del_st_direct"):
                    delete_store_record(del_id, blacklist=True)
                    st.success(f"✅ Negozio **{del_id}** rimosso definitivamente dall'archivio!")
                    st.rerun()

            st.markdown("---")
            excel_buf = io.BytesIO()
            with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                df_export = df_stores.drop(columns=[c for c in ["autista", "cell_autista", "autista_doppia"] if c in df_stores.columns])
                df_export.to_excel(writer, index=False, sheet_name="Anagrafica Negozi")
            excel_buf.seek(0)
            st.download_button(
                "📥 Esporta Anagrafica Completa in Excel",
                data=excel_buf.read(),
                file_name="anagrafica_negozi_zara.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="btn_export_anag_xlsx",
            )

        st.markdown('</div>', unsafe_allow_html=True)

    with tab_mezzi:
        # --- 1. KPI TOP METRICS CARDS (MEZZI) ---
        tot_m = len(df_vehicles)
        att_m = int((df_vehicles["attivo"].fillna("SI").str.upper() == "SI").sum()) if not df_vehicles.empty else 0
        tipi_m = int(df_vehicles["tipo_mezzo"].nunique()) if not df_vehicles.empty else 0
        max_cap = int(df_vehicles[df_vehicles["attivo"] == "SI"]["capienza_pedane"].max()) if not df_vehicles.empty else 0
        tot_cap = int(df_vehicles[df_vehicles["attivo"] == "SI"]["capienza_pedane"].sum()) if not df_vehicles.empty else 0

        kpi_mezzi_html = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px;">
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🚛 Mezzi Censiti</div>
                <div style="font-size: 22px; font-weight: 800; color: #0284C7; margin-top: 4px;">{tot_m} Veicoli</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">{att_m} Operativi • {tot_m - att_m} Non Attivi</div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">🏷️ Tipologie Mezzo</div>
                <div style="font-size: 22px; font-weight: 800; color: #0F172A; margin-top: 4px;">{tipi_m} Classi</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Bilico, Motrice, Eurocargo, Furgone</div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">📦 Capienza Massima Singola</div>
                <div style="font-size: 22px; font-weight: 800; color: #10B981; margin-top: 4px;">{max_cap} PLT</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Max carico veicolo singolo</div>
            </div>
            <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
                <div style="font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;">📊 Flotta Totale Operativa</div>
                <div style="font-size: 22px; font-weight: 800; color: #6366F1; margin-top: 4px;">{tot_cap} PLT</div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Capienza complessiva veicoli attivi</div>
            </div>
        </div>
        """
        st.markdown(kpi_mezzi_html, unsafe_allow_html=True)

        # --- 2. ELENCO & CONFIGURAZIONE PARCO MEZZI (UNIFICATO) ---
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">🚛 Parco Mezzi & Capienze Operative</div>', unsafe_allow_html=True)
        st.caption("Visualizza i veicoli della flotta e modifica direttamente tipologia, allestimento, capienza e stato operativo nelle celle. Clicca su **Salva Modifiche** per aggiornare:")

        col_save_v, col_cnt_v = st.columns([2.5, 3.5])
        with col_save_v:
            save_v = st.button("💾 SALVA MODIFICHE PARCO MEZZI", type="primary", use_container_width=True, key="btn_save_veh_main")
        with col_cnt_v:
            st.markdown(f"<div style='margin-top:8px; font-size:13px; color:#64748B;'>Veicoli registrati: <strong>{len(df_vehicles)}</strong> ({att_m} operativi) • Flotta totale: <strong>{tot_cap} PLT</strong></div>", unsafe_allow_html=True)

        edited_mezzi_df = st.data_editor(
            df_vehicles,
            column_config={
                "cod_mezzo": st.column_config.TextColumn("Codice Mezzo / Denominazione", disabled=True, width="medium"),
                "tipo_mezzo": st.column_config.SelectboxColumn("Tipologia", options=["BILICO", "MOTRICE", "EUROCARGO", "FURGONE", "ALTRO"], required=True, width="small"),
                "descrizione": st.column_config.TextColumn("Descrizione / Allestimento", width="large"),
                "capienza_pedane": st.column_config.NumberColumn("Capienza Pedane (PLT)", min_value=1, max_value=150, format="%d", required=True, width="small"),
                "attivo": st.column_config.SelectboxColumn("Stato", options=["SI", "NO"], required=True, width="small"),
                "note": st.column_config.TextColumn("Note Operative", width="medium"),
            },
            use_container_width=True,
            height=340,
            key="vehicles_editor_main",
        )

        if save_v:
            bulk_update_vehicles(edited_mezzi_df)
            st.success("✅ Parco Mezzi aggiornato con successo nel Database!")
            st.rerun()

        # SCHEDA MODIFICA / RINOMINA VEICOLO
        with st.expander("✏️ Rinomina Codice Mezzo / Dettaglio Singolo Veicolo", expanded=False):
            st.caption("Seleziona qualsiasi veicolo per modificarne la denominazione/codice identificativo. Se ridenomini il mezzo, l'anagrafica negozi aggiorna automaticamente i collegamenti:")

            veh_opts = df_vehicles["cod_mezzo"].tolist() if not df_vehicles.empty else []
            sel_veh_card = st.selectbox("Seleziona Veicolo da Modificare", veh_opts, key="sel_veh_card_edit")

            if sel_veh_card:
                v_match = df_vehicles[df_vehicles["cod_mezzo"] == sel_veh_card]
                if not v_match.empty:
                    v_row = v_match.iloc[0]
                    vm_c1, vm_c2, vm_c3 = st.columns(3)
                    with vm_c1:
                        e_v_cod = st.text_input("Codice Mezzo / Denominazione (Modificabile)", value=str(v_row.get("cod_mezzo", "")), key=f"v_c_cod_{sel_veh_card}").strip().upper()
                        t_opts = ["BILICO", "MOTRICE", "EUROCARGO", "FURGONE", "ALTRO"]
                        curr_t = str(v_row.get("tipo_mezzo", "MOTRICE") or "MOTRICE").strip().upper()
                        idx_t = t_opts.index(curr_t) if curr_t in t_opts else 1
                        e_v_tipo = st.selectbox("Tipologia Mezzo", t_opts, index=idx_t, key=f"v_c_tipo_{sel_veh_card}")

                    with vm_c2:
                        curr_cap_v = int(v_row.get("capienza_pedane", 18) or 18)
                        e_v_cap = st.number_input("Capienza Pedane (PLT)", min_value=1, max_value=150, value=curr_cap_v, step=1, key=f"v_c_cap_{sel_veh_card}")
                        att_v_opts = ["SI (Attivo)", "NO (Non Attivo)"]
                        curr_v_att = "SI (Attivo)" if str(v_row.get("attivo", "SI")).strip().upper() == "SI" else "NO (Non Attivo)"
                        e_v_att_sel = st.selectbox("Stato Operativo Veicolo", att_v_opts, index=att_v_opts.index(curr_v_att), key=f"v_c_att_{sel_veh_card}")
                        e_v_att = "SI" if "SI" in e_v_att_sel else "NO"

                    with vm_c3:
                        e_v_desc = st.text_input("Descrizione / Allestimento", value=str(v_row.get("descrizione", "") or ""), key=f"v_c_desc_{sel_veh_card}")
                        e_v_note = st.text_input("Note Operative", value=str(v_row.get("note", "") or ""), key=f"v_c_note_{sel_veh_card}")

                    if st.button(f"💾 SALVA MODIFICHE VEICOLO '{sel_veh_card}'", type="primary", use_container_width=True, key=f"btn_save_veh_card_{sel_veh_card}"):
                        if not e_v_cod:
                            st.error("Il codice del mezzo non può essere vuoto.")
                        else:
                            update_vehicle_record(sel_veh_card, {
                                "cod_mezzo": e_v_cod,
                                "tipo_mezzo": e_v_tipo,
                                "descrizione": e_v_desc,
                                "capienza_pedane": int(e_v_cap),
                                "attivo": e_v_att,
                                "note": e_v_note,
                            })
                            st.success(f"🎉 Veicolo **{e_v_cod}** salvato con successo nel Parco Mezzi!")
                            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        # --- 3. GESTIONE DIRETTA: AGGIUNGI & ELIMINA MEZZI (SEMPRE VISIBILE E IMMEDIATA) ---
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">⚡ Operazioni Rapide Parco Mezzi</div>', unsafe_allow_html=True)
        col_m_op1, col_m_op2 = st.columns([1.5, 1.5])

        with col_m_op1:
            st.markdown("##### ➕ Inserisci Nuovo Mezzo nel Parco")
            with st.form("form_add_new_vehicle", clear_on_submit=True):
                new_m_cod = st.text_input("Codice Mezzo (es. MOTRICE 20, BILICO 34)").strip().upper()
                vm1, vm2 = st.columns(2)
                with vm1:
                    new_m_tipo = st.selectbox("Tipologia", ["BILICO", "MOTRICE", "EUROCARGO", "FURGONE", "ALTRO"])
                    new_m_cap = st.number_input("Capienza Pedane (PLT)", min_value=1, max_value=150, value=18, step=1)
                with vm2:
                    new_m_att = st.selectbox("Stato Operativo", ["SI", "NO"])
                    new_m_desc = st.text_input("Descrizione / Allestimento").strip()
                new_m_note = st.text_input("Note Operative").strip()

                btn_add_veh_now = st.form_submit_button("➕ AGGIUNGI MEZZO AL PARCO", type="primary", use_container_width=True)
                if btn_add_veh_now:
                    if not new_m_cod:
                        st.error("Inserisci la denominazione del mezzo.")
                    elif not df_vehicles.empty and new_m_cod in df_vehicles["cod_mezzo"].values:
                        st.error(f"Il mezzo {new_m_cod} è già presente nel Parco Mezzi!")
                    else:
                        add_vehicle_record({
                            "cod_mezzo": new_m_cod,
                            "tipo_mezzo": new_m_tipo,
                            "descrizione": new_m_desc,
                            "capienza_pedane": int(new_m_cap),
                            "attivo": new_m_att,
                            "note": new_m_note,
                        })
                        st.success(f"✅ Mezzo **{new_m_cod}** ({new_m_cap} PLT) inserito con successo!")
                        st.rerun()

        with col_m_op2:
            st.markdown("##### 🗑️ Elimina Mezzo dal Parco")
            st.caption("Seleziona qualsiasi mezzo dalla lista (compresi quelli preimpostati che non usi) ed eliminalo con un clic:")
            m_del_options = df_vehicles["cod_mezzo"].tolist() if not df_vehicles.empty else []
            sel_v_to_delete = st.selectbox("Seleziona Veicolo da Eliminare", m_del_options, key="direct_del_veh_select")

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            if sel_v_to_delete:
                if st.button(f"🗑️ ELIMINA MEZZO '{sel_v_to_delete}' ORA", type="primary", use_container_width=True, key="btn_direct_delete_veh_action"):
                    delete_vehicle_record(sel_v_to_delete)
                    st.success(f"✅ Mezzo **{sel_v_to_delete}** eliminato definitivamente dal Parco Mezzi!")
                    st.rerun()

            st.markdown("---")
            excel_m_buf = io.BytesIO()
            with pd.ExcelWriter(excel_m_buf, engine="openpyxl") as writer:
                df_vehicles.to_excel(writer, index=False, sheet_name="Parco Mezzi")
            excel_m_buf.seek(0)
            st.download_button(
                "📥 Esporta Parco Mezzi in Excel",
                data=excel_m_buf.read(),
                file_name="parco_mezzi_zara.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="btn_export_veh_xlsx",
            )

        st.markdown('</div>', unsafe_allow_html=True)


# PAGE 5: STORICO, CANCELLAZIONE MASSIVA & BACKUP CLOUD
# ==============================================================================
elif menu.startswith("🗄️ 5.") or menu.startswith("⚙️ 5."):
    st.markdown('<div class="main-header">⚙️ Impostazioni, Invio Email, Cloud & Backup</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Configurazione server SMTP per invio email operative, sincronizzazione Google Sheets, archivio storico e backup database.</div>', unsafe_allow_html=True)

    tab_email, tab_cloud_gs, tab_hist, tab_backup = st.tabs([
        "✉️ Posta & Parametri Invio Email",
        "🟢 Cloud Google Sheets (Apps Script)",
        "📊 Archivio & Storico Elaborazioni",
        "💾 Backup File Database (.db)",
    ])

    with tab_email:
        st.markdown("#### ✉️ Configurazione Invio Email & Parametri SMTP")
        st.markdown(
            "Configura i parametri del server di posta in uscita (SMTP) e gli indirizzi standard dei destinatari "
            "per l'inoltro automatico dei file dell'operativa (Sintesi e Flussi SGA)."
        )

        cfg_now = get_email_config()

        if "flash_preset_msg" in st.session_state:
            st.success(st.session_state.pop("flash_preset_msg"))

        # Inizializza chiavi in session_state se non presenti
        if "cfg_in_smtp_host" not in st.session_state:
            st.session_state["cfg_in_smtp_host"] = cfg_now.get("smtp_host", "")
        if "cfg_in_smtp_port" not in st.session_state:
            st.session_state["cfg_in_smtp_port"] = int(cfg_now.get("smtp_port", 587))
        if "cfg_in_smtp_sec" not in st.session_state:
            st.session_state["cfg_in_smtp_sec"] = cfg_now.get("smtp_security", "STARTTLS")
        if "cfg_in_sender_name" not in st.session_state:
            st.session_state["cfg_in_sender_name"] = cfg_now.get("sender_name", "Logistica Zara Hub")
        if "cfg_in_smtp_user" not in st.session_state:
            st.session_state["cfg_in_smtp_user"] = cfg_now.get("smtp_user", "")
        if "cfg_in_smtp_pass" not in st.session_state:
            st.session_state["cfg_in_smtp_pass"] = cfg_now.get("smtp_password", "")
        if "cfg_in_def_to" not in st.session_state:
            st.session_state["cfg_in_def_to"] = cfg_now.get("default_to", "operativa@trasporti.it, traffico@trasporti.it")
        if "cfg_in_def_cc" not in st.session_state:
            st.session_state["cfg_in_def_cc"] = cfg_now.get("default_cc", "")
        if "cfg_in_subj_tmpl" not in st.session_state:
            st.session_state["cfg_in_subj_tmpl"] = cfg_now.get("subject_template", "[ZARA LOGISTICS] File Operativa & Flussi SGA - Spedizione del {date}")

        def apply_preset(host: str, port: int, sec: str, prov_name: str):
            st.session_state["cfg_in_smtp_host"] = host
            st.session_state["cfg_in_smtp_port"] = port
            st.session_state["cfg_in_smtp_sec"] = sec
            cfg_now["smtp_host"] = host
            cfg_now["smtp_port"] = port
            cfg_now["smtp_security"] = sec
            save_email_config(cfg_now)
            st.session_state["flash_preset_msg"] = f"✅ Preimpostazione **{prov_name}** applicata nei campi: Host = `{host}`, Porta = `{port}`, Sicurezza = `{sec}`"
            st.rerun()

        # Preset rapidi
        st.markdown("##### 🚀 Preimpostazioni Rapide Provider (Clicca per compilare al volo i campi)")
        pr1, pr2, pr3, pr4, pr5 = st.columns(5)
        with pr1:
            if st.button("🔴 Gmail (Google)", use_container_width=True, key="preset_gmail"):
                apply_preset("smtp.gmail.com", 587, "STARTTLS", "Google Gmail")
        with pr2:
            if st.button("🔵 Microsoft 365", use_container_width=True, key="preset_m365"):
                apply_preset("smtp.office365.com", 587, "STARTTLS", "Microsoft 365 / Outlook")
        with pr3:
            if st.button("🟡 Aruba Webmail", use_container_width=True, key="preset_aruba"):
                apply_preset("smtps.aruba.it", 465, "SSL", "Aruba Webmail")
        with pr4:
            if st.button("🏢 Server Lacchi", use_container_width=True, key="preset_lacchi"):
                apply_preset("mail.lacchi.it", 587, "STARTTLS", "Server Lacchi SpA")
        with pr5:
            if st.button("🔄 Pulisci Host", use_container_width=True, key="preset_reset"):
                apply_preset("", 587, "STARTTLS", "Vuoto (Personalizzato)")

        st.markdown("<hr style='margin: 12px 0; border: none; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)

        col_s1, col_s2, col_s3 = st.columns([2, 1, 1.2])
        with col_s1:
            cfg_host = st.text_input("Server SMTP (Host)", placeholder="es. smtp.gmail.com o smtp.office365.com", key="cfg_in_smtp_host")
        with col_s2:
            cfg_port = st.number_input("Porta SMTP", min_value=1, max_value=65535, step=1, key="cfg_in_smtp_port")
        with col_s3:
            sec_opts = ["STARTTLS", "SSL", "NESSUNA"]
            curr_sec = str(st.session_state.get("cfg_in_smtp_sec", "STARTTLS")).upper()
            curr_sec_idx = sec_opts.index(curr_sec) if curr_sec in sec_opts else 0
            cfg_sec = st.selectbox("Protocollo Sicurezza", sec_opts, index=curr_sec_idx, key="cfg_in_smtp_sec")

        col_u1, col_u2, col_u3 = st.columns([1.5, 1.5, 1.5])
        with col_u1:
            cfg_name = st.text_input("Nome Visualizzato Mittente", value=cfg_now.get("sender_name", "Logistica Zara Hub"), key="cfg_in_sender_name")
        with col_u2:
            cfg_user = st.text_input("Indirizzo Email / Utente Login", value=cfg_now.get("smtp_user", ""), placeholder="es. operativa@lacchi.it", key="cfg_in_smtp_user")
        with col_u3:
            cfg_pass = st.text_input("Password SMTP / Password per le App", value=cfg_now.get("smtp_password", ""), type="password", key="cfg_in_smtp_pass")

        with st.expander("ℹ️ Istruzioni e Guida per le Password App (Gmail / Outlook / Aruba)", expanded=False):
            st.markdown("""
            - **Google Gmail**: Se sul tuo account Google è attiva l'autenticazione a 2 fattori, Google non consente di usare la password principale. Vai su *Gestisci il tuo Account Google > Sicurezza > Password per le app*, genera una nuova password denominata "Logistica Zara" (stringa di 16 lettere) e incollala qui. Host: `smtp.gmail.com`, Porta: `587`, Sicurezza: `STARTTLS`.
            - **Microsoft 365 / Outlook**: Richiede analogamente una *Password per le app* o abilitazione SMTP AUTH nel tenant aziendale. Host: `smtp.office365.com`, Porta: `587`, Sicurezza: `STARTTLS`.
            - **Aruba**: Host: `smtps.aruba.it`, Porta: `465`, Sicurezza: `SSL` (oppure Porta: `587`, Sicurezza: `STARTTLS`).
            """)

        st.markdown("<hr style='margin: 16px 0; border: none; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)
        st.markdown("##### 👥 Indirizzi di Invio Standard & Modello Predefinito")
        st.caption("Questi indirizzi appariranno precompilati in automatico ogni volta che generi i file dell'operativa in 'Previsione Arrivi':")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            cfg_to = st.text_input(
                "Destinatari Principali (A / TO - separati da virgola)",
                value=cfg_now.get("default_to", "operativa@trasporti.it, traffico@trasporti.it"),
                placeholder="es. operativa@lacchi.it, traffico@lacchi.it",
                key="cfg_in_def_to"
            )
        with col_d2:
            cfg_cc = st.text_input(
                "Destinatari in Copia (CC - separati da virgola, opzionale)",
                value=cfg_now.get("default_cc", ""),
                placeholder="es. direzione@lacchi.it, logistica@lacchi.it",
                key="cfg_in_def_cc"
            )

        cfg_subj = st.text_input(
            "Modello Oggetto Email (supporta placeholder {date})",
            value=cfg_now.get("subject_template", "[ZARA LOGISTICS] File Operativa & Flussi SGA - Spedizione del {date}"),
            key="cfg_in_subj_tmpl"
        )

        with st.expander("🛡️ Come rendere le credenziali email permanenti al 100% su Streamlit Cloud (Secrets)", expanded=False):
            st.markdown(
                "I parametri salvati vengono memorizzati nel database, nel file locale protetto e sincronizzati sul tuo Google Sheets.<br>"
                "Tuttavia, poiché Streamlit Cloud ricrea i container Linux ad ogni nuovo aggiornamento del codice su GitHub, "
                "il metodo raccomandato e **definitivo** per non doverli mai più reinserire è salvarli nei **Secrets di Streamlit**:<br><br>"
                "1. In basso a destra dell'app, clicca su <strong>'Manage app'</strong>.<br>"
                "2. Clicca su <strong>'Settings'</strong> (o icona ⚙️ / ⋮) e seleziona la scheda <strong>'Secrets'</strong>.<br>"
                "3. Incolla questo blocco e premi <strong>Save</strong>:<br>",
                unsafe_allow_html=True
            )
            secrets_example = (
                "[smtp]\n"
                f'smtp_host = "{cfg_host or "smtp.gmail.com"}"\n'
                f'smtp_port = {int(cfg_port) if cfg_port else 587}\n'
                f'smtp_user = "{cfg_user or "tua_email@gmail.com"}"\n'
                f'smtp_password = "{cfg_pass or "tua_password_app_16_caratteri"}"\n'
                f'smtp_security = "{cfg_sec or "STARTTLS"}"\n'
                f'sender_name = "{cfg_name or "Logistica Zara Hub"}"\n'
                f'default_to = "{cfg_to or "operativa@trasporti.it, traffico@trasporti.it"}"\n'
                f'default_cc = "{cfg_cc or ""}"\n'
            )
            st.code(secrets_example, language="toml")

        st.markdown("<hr style='margin: 16px 0; border: none; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)

        # Test Connessione & Salvataggio
        col_act1, col_act2 = st.columns([1.5, 2])
        with col_act1:
            st.markdown("##### 💾 Salvataggio Configurazione")
            if st.button("💾 SALVA CONFIGURAZIONE EMAIL", type="primary", use_container_width=True, key="btn_save_email_cfg"):
                updated_cfg = {
                    "smtp_host": cfg_host.strip(),
                    "smtp_port": int(cfg_port),
                    "smtp_security": cfg_sec,
                    "sender_name": cfg_name.strip(),
                    "smtp_user": cfg_user.strip(),
                    "smtp_password": cfg_pass.strip(),
                    "default_to": cfg_to.strip(),
                    "default_cc": cfg_cc.strip(),
                    "subject_template": cfg_subj.strip(),
                    "body_template": cfg_now.get("body_template", "")
                }
                save_email_config(updated_cfg)
                st.success("✅ Configurazione email salvata nel database, nel file locale e sincronizzata su Google Sheets!")
                st.rerun()

        with col_act2:
            st.markdown("##### 🧪 Test Connessione & Invio Prova")
            col_t_in, col_t_btn = st.columns([2, 1.2])
            with col_t_in:
                test_addr = st.text_input("Invia email di prova a:", value=cfg_user if cfg_user else "", placeholder="indirizzo@dominio.it", key="cfg_test_email_addr")
            with col_t_btn:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                test_clicked = st.button("🧪 Invia Test Ora", use_container_width=True, key="btn_exec_test_email")

            if test_clicked:
                if not test_addr:
                    st.warning("Inserisci un indirizzo email a cui inviare la prova.")
                else:
                    curr_test_cfg = {
                        "smtp_host": cfg_host.strip(),
                        "smtp_port": int(cfg_port),
                        "smtp_security": cfg_sec,
                        "sender_name": cfg_name.strip(),
                        "smtp_user": cfg_user.strip(),
                        "smtp_password": cfg_pass.strip(),
                    }
                    with st.spinner(f"Tentativo di connessione a {cfg_host.strip()}:{cfg_port}..."):
                        ok_test, msg_test = send_test_email(test_addr, smtp_config=curr_test_cfg)
                        if ok_test:
                            st.success(f"🎉 **{msg_test}**")
                        else:
                            st.error(f"❌ **{msg_test}**")


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
                            with st.spinner(f"🗑️ Eliminazione di {len(selected_mass_ids)} elaborazioni in corso... Attendere prego"):
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
                        with st.spinner("⚠️ Svuotamento totale dello storico in corso... Attendere prego"):
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


# ==============================================================================
# BARRA DI NAVIGAZIONE MOBILE TOUCH FISSA IN BASSO (SMARTPHONE & TABLET)
# ==============================================================================
st.markdown('<div class="mobile-bottom-nav">', unsafe_allow_html=True)
mob_bot_cols = st.columns(len(MENU_OPTIONS))
for mb_idx, mb_opt in enumerate(MENU_OPTIONS):
    mb_short = mb_opt.split(". ")[-1] if ". " in mb_opt else mb_opt
    mb_icon = mb_opt.split(" ")[0] if " " in mb_opt else "📌"
    mb_is_act = (st.session_state.get("nav_menu") == mb_opt)
    with mob_bot_cols[mb_idx]:
        if st.button(f"{mb_icon} {mb_short}", key=f"mob_fixed_bot_{mb_idx}", type="primary" if mb_is_act else "secondary", use_container_width=True):
            st.session_state["nav_menu"] = mb_opt
            st.rerun()
st.markdown('</div>', unsafe_allow_html=True)
