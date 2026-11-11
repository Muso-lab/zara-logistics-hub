"""
Interfacce Semplificate "Zero Distrazioni" per gli Operatori (Ufficio, Magazzino, Mobile Banchina).
Mantiene al 100% la compatibilità con la modalità Admin / Vista Classica Completa di backup.
"""
from __future__ import annotations

import html
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.bolle_manager import (
    add_colli_to_bolla_spuntata,
    add_intershop_to_bolla,
    clear_sigilli_by_date,
    compute_inditex_delivery_dates,
    confirm_bolla_spunta,
    export_bolle_excel,
    generate_bolle_from_forecast,
    get_bolla_by_id,
    get_bolle_by_date,
    get_bolle_dates,
    heal_shifted_bolle_dates,
    remove_intershop_from_bolla,
    render_bolla_printable_html,
)
from src.cloud_sync import get_extranet_credentials, set_extranet_credentials
from src.config import DATA_DIR, DB_PATH
from src.db import get_stores_df, load_run_data
from src.pipeline import run_pipeline
from src.scraper import InditexExtranetScraper
from src.utils import get_cycle_date_range, parse_date_obj


def _clean_str(val: Any) -> str:
    """Pulisce valori None, NaN, 'nan', 'null' restituendo stringa vuota."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", "nat"):
        return ""
    return s


def format_date_it(d_val: Any) -> str:
    if d_val is None or pd.isna(d_val) or str(d_val).strip() == "":
        return ""
    try:
        return parse_date_obj(d_val).strftime("%d/%m/%Y")
    except Exception:
        return str(d_val).strip()[:10]


def format_date_weekday_it(d_str: Any) -> str:
    days_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    try:
        dt = parse_date_obj(d_str)
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


def cleanup_legacy_wrong_bolle(db_path: Path = DB_PATH) -> None:
    """Corregge eventuali date traslate da UTC Google Sheets, rimuove record di test e pulisce 'nan'."""
    heal_shifted_bolle_dates(db_path=db_path)


def ensure_bolle_for_latest_run(runs_df: pd.DataFrame) -> bool:
    """
    Verifica le ultime Run e, se per le date di consegna (/0 STD o /9 DOPPIA)
    mancano bolle (o la generazione precedente era parziale/incompleta rispetto
    ai 49 negozi STD e 10 negozi DOPPIA dell'anagrafica), rigenera automaticamente
    i negozi mancanti senza sovrascrivere le spunte già effettuate (overwrite=False).
    """
    cleanup_legacy_wrong_bolle()
    if runs_df is None or runs_df.empty:
        return False
    generated_any = False
    try:
        for _, run_row in runs_df.head(3).iterrows():
            r_id = int(run_row["id"])
            r_cycle = str(run_row.get("cycle_type", "LUN-MER"))
            dt_base = parse_date_obj(run_row["run_date"], default=date.today())
            date_dop, date_std = compute_inditex_delivery_dates(dt_base, r_cycle)
            b_std = get_bolle_by_date(date_std)
            b_dop = get_bolle_by_date(date_dop)
            n_std = len(b_std[b_std["tipo_cons"].astype(str).str.upper() == "STD"]) if not b_std.empty and "tipo_cons" in b_std.columns else len(b_std)
            n_dop = len(b_dop[b_dop["tipo_cons"].astype(str).str.upper() == "DOPPIA"]) if not b_dop.empty and "tipo_cons" in b_dop.columns else len(b_dop)
            if n_std < 48 or n_dop < 10:
                res = generate_bolle_from_forecast(r_id, overwrite=False)
                if res.get("created", 0) > 0:
                    generated_any = True
    except Exception:
        pass
    return generated_any


def _format_store_display(
    s_code: str,
    b_row: Optional[Any] = None,
    stores_lookup: Optional[Dict[str, str]] = None,
) -> str:
    """
    Restituisce l'etichetta completa e ricercabile del negozio combinando Brand (punto_vendita)
    e Nome Negozio/Centro Commerciale (es. 'STRADIVARIUS ROM-EUROMA2', 'ZARA ROM-ROMA EST'),
    così l'operatore può cercare nell'Omnibox sia per codice (2917, 3534), sia per insegna
    (Stradivarius, Zara, Bershka, Pull&Bear, Oysho, Massimo Dutti, Zara Home), sia per località
    (Roma Est, Euroma, Ottaviano, Corso, ecc.).
    """
    code_clean = str(s_code or "").strip()
    brand = ""
    sname = ""
    if b_row is not None:
        brand = _clean_str(b_row.get("punto_vendita") or b_row.get("brand")).upper()
        sname = _clean_str(b_row.get("store_name"))
    if stores_lookup and code_clean in stores_lookup:
        l_val = _clean_str(stores_lookup[code_clean])
        if l_val:
            if not sname:
                sname = l_val
            elif not brand and l_val.upper() != sname.upper():
                return l_val
    if brand and sname:
        if brand.lower() not in sname.lower():
            return f"{brand} {sname}"
        return sname
    return sname or brand or f"Store {code_clean}"


def _build_unified_stores_lookup(
    df_stores_side: pd.DataFrame,
    df_b_date: pd.DataFrame,
) -> Tuple[List[str], Dict[str, str]]:
    """
    Unisce l'anagrafica completa (`stores`) e le `bolle` del giorno in un unico dizionario
    `{store_code: 'BRAND NOME_NEGOZIO'}` e nella lista ordinata di tutti i codici negozio.
    """
    lookup: Dict[str, str] = {}
    codes_set = set()

    if df_stores_side is not None and not df_stores_side.empty:
        sc_col = "store_id" if "store_id" in df_stores_side.columns else "id_store"
        if sc_col in df_stores_side.columns:
            for _, sr in df_stores_side.iterrows():
                sc = str(sr[sc_col]).strip()
                if not sc or sc.upper().endswith("B"):
                    continue
                att = _clean_str(sr.get("attivo", "SI")).upper()
                if att in ("NO", "0", "FALSE"):
                    continue
                codes_set.add(sc)
                br_str = _clean_str(sr.get("brand") or sr.get("punto_vendita")).upper()
                nm_str = _clean_str(sr.get("store_name"))
                if br_str and nm_str and br_str.lower() not in nm_str.lower():
                    lookup[sc] = f"{br_str} {nm_str}"
                elif nm_str or br_str:
                    lookup[sc] = nm_str or br_str

    if df_b_date is not None and not df_b_date.empty:
        for _, br in df_b_date.iterrows():
            sc = str(br.get("id_store", "")).strip()
            if not sc or sc.upper().endswith("B"):
                continue
            codes_set.add(sc)
            disp = _format_store_display(sc, br, lookup)
            if disp and (sc not in lookup or len(disp) > len(lookup[sc])):
                lookup[sc] = disp

    return sorted(list(codes_set)), lookup


def _resolve_omnibox_bid(
    raw_val: Any,
    omnibox_options: List[int],
    omnibox_labels: Dict[int, str],
    default_bid: int,
) -> int:
    """
    Risolve il valore restituito dall'Omnibox (`st.selectbox` con `accept_new_options=True`):
    - Se l'utente ha selezionato una voce dalla tendina, `raw_val` è l'ID intero `int` della bolla.
    - Se l'utente ha digitato un testo (es. '3534', 'roma est', 'stradivarius euroma') e premuto Invio
      sulla tastiera dello smartphone, `raw_val` è una stringa e viene risolta al primo negozio corrispondente.
    """
    if not omnibox_options:
        return default_bid
    if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
        iv = int(raw_val)
        if iv in omnibox_options:
            return iv
    if isinstance(raw_val, str):
        q = raw_val.strip().lower()
        if q:
            for bid in omnibox_options:
                lbl = omnibox_labels.get(bid, "")
                if lbl.lower() == q:
                    return bid
            for bid in omnibox_options:
                lbl = omnibox_labels.get(bid, "").lower()
                if f" {q} —" in lbl or lbl.startswith(f"{q} —"):
                    return bid
            tokens = [t for t in q.split() if t]
            if tokens:
                for bid in omnibox_options:
                    lbl = omnibox_labels.get(bid, "").lower()
                    if all(tok in lbl for tok in tokens):
                        return bid
    return default_bid if default_bid in omnibox_options else omnibox_options[0]


def _resolve_omnibox_store_code(
    raw_val: Any,
    mitt_opts: List[str],
    names_lookup: Dict[str, str],
) -> str:
    """Risolve il codice negozio mittente dall'Omnibox Trasferimenti anche se digitato a mano + Invio."""
    if not raw_val:
        return ""
    s_val = str(raw_val).strip()
    if s_val in mitt_opts:
        return s_val
    q = s_val.lower()
    if q.startswith("🔍"):
        return ""
    for code in mitt_opts:
        if not code:
            continue
        if code.lower() == q or q.startswith(f"{code.lower()} "):
            return code
    tokens = [t for t in q.split() if t]
    if tokens:
        for code in mitt_opts:
            if not code:
                continue
            full_lbl = f"{code} {names_lookup.get(code, '')}".lower()
            if all(tok in full_lbl for tok in tokens):
                return code
    return ""


def _inject_omnibox_autoselect_js() -> None:
    """
    Inietta CSS proporzionato per Mobile/Desktop (compatibile con Streamlit 1.54+ React Aria ComboBox
    e con BaseWeb) e listener JavaScript sul documento padre:
    - Sull'Omnibox Negozio rimuove qualsiasi blocco `readonly` su mobile, apre subito la tastiera virtuale
      al tocco, sposta il vecchio valore nel placeholder e svuota il campo di ricerca in un colpo solo
      (ripristinando automaticamente il negozio se si tocca fuori senza scegliere altro).
    - Sugli input numerici/testuali seleziona l'intera cifra/stringa al tocco per sovrascriverla subito.
    """
    st.markdown("""
    <style>
    /* Contenitore Selectbox / Omnibox per Streamlit 1.54+ (React Aria) e BaseWeb */
    div[data-testid="stSelectbox"] .react-aria-Group,
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 44px !important;
        height: auto !important;
        padding: 3px 10px !important;
        border-radius: 10px !important;
        border: 1.5px solid #CBD5E1 !important;
        background-color: #FFFFFF !important;
        align-items: center !important;
    }
    div[data-testid="stSelectbox"] .react-aria-Group[data-focus-within],
    div[data-testid="stSelectbox"] [data-baseweb="select"]:focus-within > div {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18) !important;
        background-color: #EFF6FF !important;
    }
    /* Input interno dell'Omnibox (React Aria input.react-aria-Input) */
    div[data-testid="stSelectbox"] input.react-aria-Input,
    div[data-testid="stSelectbox"] [data-baseweb="select"] input,
    div[data-testid="stSelectbox"] input {
        min-height: 28px !important;
        height: 28px !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        line-height: 1.3 !important;
        color: #0F172A !important;
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        text-align: left !important;
        padding: 2px 4px !important;
        margin: 0 !important;
        caret-color: #1D4ED8 !important;
        user-select: text !important;
        -webkit-user-select: text !important;
    }
    div[data-testid="stSelectbox"] input.react-aria-Input::placeholder,
    div[data-testid="stSelectbox"] input::placeholder {
        color: #64748B !important;
        font-weight: 600 !important;
        opacity: 0.85 !important;
    }
    /* Nasconde la voce fittizia 'Add: ...' generata da accept_new_options=True */
    [id$="-option-__creatable__"],
    [data-key="__creatable__"],
    div[data-testid="stSelectboxVirtualDropdown"] [id*="__creatable__"] {
        display: none !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        overflow: hidden !important;
    }
    /* Menu a tendina Omnibox leggibile e compatto */
    div[data-testid="stSelectboxVirtualDropdown"] [role="option"],
    ul[data-testid="stSelectboxVirtualDropdown"] li,
    div[data-baseweb="popover"] li {
        font-size: 13.5px !important;
        font-weight: 600 !important;
        line-height: 1.3 !important;
    }
    /* Input numerici e di testo proporzionati e mai tagliati */
    div[data-testid="stNumberInput"] [data-baseweb="input"],
    div[data-testid="stTextInput"] [data-baseweb="input"],
    div[data-testid="stTextInput"] [data-baseweb="base-input"] {
        min-height: 42px !important;
        height: 42px !important;
        border-radius: 10px !important;
        border: 1.5px solid #CBD5E1 !important;
        background-color: #FFFFFF !important;
        align-items: center !important;
    }
    div[data-testid="stNumberInput"] input[type="number"] {
        min-height: 38px !important;
        height: 38px !important;
        font-size: 16px !important;
        font-weight: 800 !important;
        line-height: 1.2 !important;
        padding: 2px 8px !important;
        border: none !important;
        text-align: center !important;
        background: transparent !important;
    }
    div[data-testid="stTextInput"] input[type="text"] {
        min-height: 38px !important;
        height: 38px !important;
        font-size: 14px !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
        padding: 4px 10px !important;
        border: none !important;
        text-align: left !important;
        background: transparent !important;
    }
    div[data-testid="stNumberInput"] button {
        min-width: 38px !important;
        min-height: 38px !important;
        height: 38px !important;
        font-size: 17px !important;
        font-weight: 800 !important;
        border: none !important;
        border-left: 1px solid #E2E8F0 !important;
        border-radius: 0 !important;
        padding: 0 !important;
    }
    label, [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span, [data-testid="stWidgetLabel"] label {
        font-size: 13.5px !important;
        font-weight: 700 !important;
        line-height: 1.3 !important;
        margin-bottom: 4px !important;
    }
    div[data-testid="stButton"] > button {
        min-height: 44px !important;
        font-size: 13.5px !important;
        font-weight: 700 !important;
        padding: 6px 12px !important;
        line-height: 1.25 !important;
        border-radius: 10px !important;
        white-space: normal !important;
        word-wrap: break-word !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.components.v1.html("""
    <script>
    (function() {
        try {
            const doc = (window.parent && window.parent.document) ? window.parent.document : document;
            const win = (window.parent) ? window.parent : window;

            const isOmniboxSelect = (sbContainer) => {
                if (!sbContainer) return false;
                const txt = (sbContainer.innerText || sbContainer.textContent || '').toLowerCase();
                if (txt.indexOf('omnibox') !== -1) return true;
                const inp = sbContainer.querySelector('input');
                if (inp) {
                    const al = (inp.getAttribute('aria-label') || '').toLowerCase();
                    if (al.indexOf('omnibox') !== -1) return true;
                }
                return false;
            };

            const unlockOmniboxInputs = () => {
                const boxes = doc.querySelectorAll('div[data-testid="stSelectbox"]');
                boxes.forEach((sb) => {
                    if (!isOmniboxSelect(sb)) return;
                    const inp = sb.querySelector('input');
                    if (inp) {
                        if (inp.hasAttribute('readonly') || inp.readOnly) {
                            inp.removeAttribute('readonly');
                            inp.readOnly = false;
                        }
                        if (inp.getAttribute('inputmode') !== 'search') {
                            inp.setAttribute('inputmode', 'search');
                        }
                        inp.setAttribute('autocomplete', 'off');
                        inp.setAttribute('autocorrect', 'off');
                        inp.setAttribute('autocapitalize', 'off');
                        inp.setAttribute('spellcheck', 'false');
                    }
                });
            };

            unlockOmniboxInputs();

            if (doc._zaraOmniboxV2Installed) return;
            doc._zaraOmniboxV2Installed = true;

            const obs = new MutationObserver(() => {
                unlockOmniboxInputs();
            });
            obs.observe(doc.body, { childList: true, subtree: true });

            const clearOmniboxForTyping = (inp) => {
                if (!inp) return;
                inp.removeAttribute('readonly');
                inp.readOnly = false;
                inp.setAttribute('inputmode', 'search');

                const curVal = inp.value || '';
                if (curVal && inp.dataset.zaraCleared !== '1') {
                    inp.placeholder = '🔍 Digita codice o nome (attuale: ' + curVal + ')';
                    inp.dataset.zaraCleared = '1';
                    try {
                        const tracker = inp._valueTracker;
                        if (tracker) {
                            tracker.setValue(curVal);
                        }
                        const setter = Object.getOwnPropertyDescriptor(
                            win.HTMLInputElement.prototype,
                            'value'
                        ).set;
                        if (setter) {
                            setter.call(inp, '');
                        } else {
                            inp.value = '';
                        }
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    } catch (err) {}
                }
                try {
                    inp.focus();
                } catch (err) {}
            };

            const selectAllRegularInput = (el) => {
                if (!el || el.tagName !== 'INPUT') return;
                setTimeout(() => {
                    try {
                        el.focus();
                        el.select();
                        if (el.value && el.setSelectionRange) {
                            el.setSelectionRange(0, el.value.length);
                        }
                    } catch (e) {}
                }, 10);
            };

            doc.addEventListener('pointerdown', (e) => {
                const t = e.target;
                if (!t || !t.closest) return;
                const sb = t.closest('div[data-testid="stSelectbox"]');
                if (sb && isOmniboxSelect(sb)) {
                    const inp = sb.querySelector('input');
                    if (inp) {
                        inp.removeAttribute('readonly');
                        inp.readOnly = false;
                        inp.setAttribute('inputmode', 'search');
                    }
                }
            }, true);

            doc.addEventListener('click', (e) => {
                const t = e.target;
                if (!t || !t.closest) return;
                const sb = t.closest('div[data-testid="stSelectbox"]');
                if (sb && isOmniboxSelect(sb)) {
                    const inp = sb.querySelector('input');
                    if (inp) {
                        clearOmniboxForTyping(inp);
                    }
                    return;
                }
                if (t.tagName === 'INPUT' && !sb) {
                    selectAllRegularInput(t);
                }
            }, true);

            doc.addEventListener('focusin', (e) => {
                const t = e.target;
                if (!t || t.tagName !== 'INPUT') return;
                const sb = t.closest && t.closest('div[data-testid="stSelectbox"]');
                if (sb) {
                    if (isOmniboxSelect(sb)) {
                        clearOmniboxForTyping(t);
                    }
                } else {
                    selectAllRegularInput(t);
                }
            }, true);

            doc.addEventListener('focusout', (e) => {
                const t = e.target;
                if (t && t.tagName === 'INPUT' && t.dataset) {
                    t.dataset.zaraCleared = '0';
                }
            }, true);
        } catch (err) {}
    })();
    </script>
    """, height=0, width=0)


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
    1) Selezione Date & Ciclo (con anteprima chiara delle date di consegna /0 e /9)
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
                border: 2px solid #3B82F6; border-radius: 12px; padding: 14px 20px; margin-bottom: 16px;">
        <div style="font-size: 18px; font-weight: 800; color: #1E3A8A;">
            💼 CREAZIONE NUOVI GIRI OPERATIVI (MODALITÀ RAPIDA UFFICIO)
        </div>
        <div style="font-size: 13px; color: #1E40AF; margin-top: 3px;">
            <strong>1.</strong> Controlla le date &bull; <strong>2.</strong> Inserisci eventuali profumi &bull; <strong>3.</strong> Premi il tastone per creare i giri e caricare gli XML sul Cloud.
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
                    "LUN-MER (Consegna Mercoledì /0 e Giovedì /9)",
                    "GIOV-DOM (Consegna Sabato /0 e Domenica /9)",
                ],
                index=default_cycle_idx,
                horizontal=True,
                key="uff_simp_cycle_choice",
            )
            cycle_type = "LUN-MER" if "LUN-MER" in cycle_choice else "GIOV-DOM"

        date_b9_preview, date_b0_preview = compute_inditex_delivery_dates(run_date, cycle_type)
        st.markdown(f"""
        <div style="background: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 8px; padding: 8px 14px; margin: 6px 0 10px 0; font-size: 13px; color: #14532D;">
            🗓️ <strong>Date di Consegna Bolle &amp; Flussi SGA/XML che verranno generate:</strong>
            &nbsp;&bull;&nbsp; 🚚 <strong>Barra 0 (/0 STD): {format_date_weekday_it(str(date_b0_preview))}</strong>
            &nbsp;&bull;&nbsp; 🔁 <strong>Barra 9 (/9 DOPPIA): {format_date_weekday_it(str(date_b9_preview))}</strong>
        </div>
        """, unsafe_allow_html=True)

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
                    padding: 16px 20px; margin: 10px 0 14px 0;">
            <div style="font-size: 15px; font-weight: 800; color: #38BDF8;">
                🚀 AVVIO OPERATIVA IN CORSO — ATTENDERE PREGO (5%)
            </div>
            <div style="font-size: 13px; color: #F8FAFC; margin-top: 4px;">
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
                        padding: 16px 20px; margin: 10px 0 14px 0;">
                <div style="font-size: 15px; font-weight: 800; color: #38BDF8;">
                    🔄 ELABORAZIONE IN CORSO ({pct}%)
                </div>
                <div style="font-size: 13px; color: #F8FAFC; margin-top: 4px;">
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
    1) Seleziona la Data di Consegna (con indicazione chiara Mercoledì/Sabato /0 vs Giovedì/Domenica /9)
    2) Seleziona Giro / Negozi + eventuale Sigillo temporaneo di sessione (non residente!)
    3) TASTONE STAMPA BOLLE (senza fogli bianchi tra una bolla e l'altra)
    """
    if "flash_bolle_msg" in st.session_state:
        st.success(f"🎉 **{st.session_state.pop('flash_bolle_msg')}**")

    _inject_omnibox_autoselect_js()

    # Assicura automaticamente che le bolle dell'ultima previsione siano state create e pulisce date anomale
    ensure_bolle_for_latest_run(runs_side)

    st.markdown("""
    <div style="background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
                border: 2px solid #10B981; border-radius: 12px; padding: 14px 20px; margin-bottom: 16px;">
        <div style="font-size: 18px; font-weight: 800; color: #065F46;">
            🖨️ STAMPA BOLLE DI CONSEGNA (MODALITÀ RAPIDA MAGAZZINO)
        </div>
        <div style="font-size: 13px; color: #047857; margin-top: 3px;">
            <strong>1.</strong> Scegli la data operativa &bull; <strong>2.</strong> Scegli il giro o i negozi &bull; <strong>3.</strong> Premi <strong>STAMPA BOLLE</strong>.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Info rapida sulle date ufficiali dell'ultima operativa
    latest_std_str = None
    latest_dop_str = None
    if not runs_side.empty:
        try:
            lr = runs_side.iloc[0]
            lr_dt = parse_date_obj(lr["run_date"])
            lr_cyc = str(lr.get("cycle_type", "LUN-MER"))
            d_dop_o, d_std_o = compute_inditex_delivery_dates(lr_dt, lr_cyc)
            latest_std_str = str(d_std_o)
            latest_dop_str = str(d_dop_o)
        except Exception:
            pass

    today_str = str(date.today())
    tomorrow_str = str(date.today() + timedelta(days=1))
    all_dates = get_bolle_dates(120)
    if not all_dates:
        all_dates = [latest_std_str or tomorrow_str, today_str]

    # Etichette descrittive per ogni data disponibile (mostra /0 STD vs /9 DOPPIA e numero bolle)
    date_label_map: Dict[str, str] = {}
    for d_item in all_dates:
        try:
            dt_o = datetime.strptime(d_item[:10], "%Y-%m-%d").date()
            wd = dt_o.weekday()
            if wd in (2, 5):
                tag_d = "🚚 Consegna /0 STD"
            elif wd in (3, 6):
                tag_d = "🔁 Consegna /9 DOPPIA"
            else:
                tag_d = "📦 Consegna"
        except Exception:
            tag_d = "📦 Consegna"
        date_label_map[d_item] = f"📅 {format_date_weekday_it(d_item)} — {tag_d}"

    # Scelta predefinita intelligente: privilegia la data /0 STD dell'ultima run (Mercoledì o Sabato), o oggi/domani
    if "mag_simp_date" not in st.session_state or st.session_state["mag_simp_date"] not in all_dates:
        if today_str in all_dates:
            st.session_state["mag_simp_date"] = today_str
        elif tomorrow_str in all_dates:
            st.session_state["mag_simp_date"] = tomorrow_str
        elif latest_std_str and latest_std_str in all_dates:
            st.session_state["mag_simp_date"] = latest_std_str
        else:
            st.session_state["mag_simp_date"] = all_dates[0]

    # --- STEP 1: SELEZIONE DATA DI CONSEGNA ---
    with st.container(border=True):
        st.markdown("#### 📅 1. Seleziona la Data di Consegna")
        if latest_std_str and latest_dop_str:
            c_info_run, c_btn_b0, c_btn_b9 = st.columns([2.2, 1.2, 1.2])
            with c_info_run:
                st.caption(
                    f"🗓️ **Ultima Operativa attiva:**\n"
                    f"• **/0 STD:** {format_date_weekday_it(latest_std_str)}\n"
                    f"• **/9 DOPPIA:** {format_date_weekday_it(latest_dop_str)}"
                )
            with c_btn_b0:
                if st.button(
                    f"🚚 Vai a /0 ({format_date_it(latest_std_str)})",
                    use_container_width=True,
                    type="primary" if st.session_state["mag_simp_date"] == latest_std_str else "secondary",
                    key="mag_btn_go_std",
                ):
                    if latest_std_str not in all_dates:
                        all_dates.insert(0, latest_std_str)
                    st.session_state["mag_simp_date"] = latest_std_str
                    st.rerun()
            with c_btn_b9:
                if st.button(
                    f"🔁 Vai a /9 ({format_date_it(latest_dop_str)})",
                    use_container_width=True,
                    type="primary" if st.session_state["mag_simp_date"] == latest_dop_str else "secondary",
                    key="mag_btn_go_dop",
                ):
                    if latest_dop_str not in all_dates:
                        all_dates.insert(0, latest_dop_str)
                    st.session_state["mag_simp_date"] = latest_dop_str
                    st.rerun()

        c_d_sel, c_b1, c_b2 = st.columns([3.0, 1.0, 1.0])
        with c_d_sel:
            target_date = st.selectbox(
                "Data di Consegna",
                options=all_dates,
                index=all_dates.index(st.session_state["mag_simp_date"]),
                format_func=lambda d: date_label_map.get(d, f"📅 {format_date_weekday_it(d)}"),
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
                if latest_std_str:
                    st.session_state["mag_simp_date"] = latest_std_str
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

    # --- STEP 2: SELEZIONA GIRO, NEGOZI & SIGILLO TEMPORANEO ---
    with st.container(border=True):
        st.markdown("#### 🏪 2. Seleziona Giro, Negozi e Sigillo (Opzionale)")
        all_giri = sorted([g for g in df_bolle["giro"].unique() if str(g).strip()])
        c_f_giro, c_f_tipo, c_f_sig = st.columns([1.3, 1.5, 1.4])
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
        with c_f_sig:
            # Chiave dinamica per data + giro: si azzera automaticamente cambiando giro o data (NON residente!)
            sigillo_session_val = st.text_input(
                "🔒 Sigillo per questa stampa (Opzionale)",
                value="",
                placeholder="Vuoto = nessun sigillo in stampa",
                key=f"mag_sigillo_temp_{target_date}_{sel_giro}",
                help="Il sigillo inserito qui vale SOLO per questa stampa e si azzera automaticamente cambiando giro o data.",
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
            "🏪 Seleziona Negozi specifici (Digita codice o nome • Lascia vuoto per stampare TUTTI i negozi del filtro)",
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

    if st.button(
        f"🖨️ STAMPA BOLLE SELEZIONATE ({n_bolle} BOLLE — {tot_colli_print} COLLI)",
        type="primary",
        use_container_width=True,
        disabled=(n_bolle == 0),
        key="mag_simp_big_print_btn",
    ):
        recs = [get_bolla_by_id(int(r["id"])) for _, r in df_to_print.iterrows()]
        recs = [r for r in recs if r]
        html_out = render_bolla_printable_html(
            recs,
            auto_print=True,
            override_sigillo=sigillo_session_val.strip(),
        )
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
            html_out = render_bolla_printable_html(
                recs,
                auto_print=True,
                override_sigillo=sigillo_session_val.strip(),
            ) + f"\n<!-- print_ts: {datetime.now().isoformat()} -->"
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
            html_out = render_bolla_printable_html(
                recs,
                auto_print=True,
                override_sigillo=sigillo_session_val.strip(),
            ) + f"\n<!-- print_ts: {datetime.now().isoformat()} -->"
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
        st.success("✅ **Finestra di stampa inviata al browser!** (1 bolla per foglio A4, senza pagine bianche intermedie)")
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
                "Trasferimenti": df_to_print["stringa"].fillna("") if "stringa" in df_to_print.columns else "",
                "Vettore": df_to_print["vettore"] if "vettore" in df_to_print.columns else "",
                "Spunta": df_to_print["spuntato"].map(lambda s: "🟢 Spuntato" if int(s or 0) == 1 else "⏳ Da contare"),
            })
            st.dataframe(disp_df, use_container_width=True, hide_index=True)


# ==============================================================================
# HELPER UI MOBILE: GESTIONE TRASFERIMENTI (INTERSHOPS)
# ==============================================================================
def _render_mobile_intershops_section(
    bolla_id: int,
    store_id: str,
    store_name: str,
    all_store_codes: List[str],
    key_prefix: str = "mob_inter",
    store_names_map: Optional[Dict[str, str]] = None,
):
    """Box compatto mobile per vedere, aggiungere o rimuovere Trasferimenti tra Negozi (Intershops)."""
    b_fresh = get_bolla_by_id(int(bolla_id)) or {}
    inter_list: List[Dict[str, Any]] = []
    try:
        if b_fresh.get("intershops_json"):
            parsed = json.loads(b_fresh["intershops_json"])
            if isinstance(parsed, list):
                inter_list = [x for x in parsed if isinstance(x, dict) and float(x.get("colli", 0) or 0) > 0]
    except Exception:
        inter_list = []

    names_lookup = store_names_map or {}

    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:13.5px; font-weight:800; color:#0369A1; margin-bottom:6px;'>"
            f"🔄 Trasferimenti tra Negozi (Intershops) — Store {html.escape(str(store_id))}</div>",
            unsafe_allow_html=True,
        )

        if inter_list:
            for idx_i, item in enumerate(inter_list):
                c_txt, c_del = st.columns([3.5, 1])
                with c_txt:
                    m_s = _clean_str(item.get("mittente")) or "N/D"
                    c_s = int(float(item.get("colli", 0) or 0))
                    t_s = _clean_str(item.get("tipo")) or "MERCE"
                    st.markdown(
                        f"<div style='font-size:13px; background:#F0F9FF; border:1px solid #BAE6FD; "
                        f"border-radius:8px; padding:6px 10px; margin-bottom:4px;'>"
                        f"📦 <strong>{c_s} colli {html.escape(t_s)}</strong> da Negozio <strong>{html.escape(m_s)}</strong></div>",
                        unsafe_allow_html=True,
                    )
                with c_del:
                    if st.button("🗑️", key=f"{key_prefix}_del_{bolla_id}_{idx_i}", use_container_width=True, help="Rimuovi trasferimento"):
                        remove_intershop_from_bolla(int(bolla_id), idx_i)
                        st.session_state["flash_bolle_msg"] = f"Trasferimento rimosso da Store {store_id}."
                        st.rerun()
        else:
            st.caption("Nessun trasferimento registrato per questo negozio.")

        mitt_opts = [""] + [s for s in all_store_codes if s != str(store_id)]

        def _fmt_mitt(code_val: str) -> str:
            if not code_val:
                return "🔍 Digita codice (es. 3534) o nome negozio mittente..."
            nm = names_lookup.get(str(code_val), "")
            return f"{code_val} — {nm}" if nm else f"Store {code_val}"

        mitt_sb_key = f"{key_prefix}_mitt_sb_{bolla_id}"
        if mitt_sb_key in st.session_state:
            st.session_state[mitt_sb_key] = _resolve_omnibox_store_code(
                st.session_state[mitt_sb_key],
                mitt_opts,
                names_lookup,
            )

        mitt_sel_raw = st.selectbox(
            "🔍 Negozio Mittente (Omnibox)",
            options=mitt_opts,
            format_func=_fmt_mitt,
            accept_new_options=True,
            filter_mode="fuzzy",
            key=mitt_sb_key,
        )
        mitt_sel = _resolve_omnibox_store_code(mitt_sel_raw, mitt_opts, names_lookup)

        c_m2, c_m3 = st.columns([1.0, 1.3])
        with c_m2:
            tr_colli = st.number_input(
                "N° Colli",
                min_value=1,
                max_value=200,
                value=1,
                step=1,
                key=f"{key_prefix}_colli_{bolla_id}",
            )
        with c_m3:
            tr_tipo = st.selectbox(
                "Tipologia",
                options=["MERCE", "CESTE", "STAND", "BUSTE", "SCATOLE", "VARIO"],
                key=f"{key_prefix}_tipo_{bolla_id}",
            )

        if st.button(
            f"➕ AGGIUNGI TRASFERIMENTO ({int(tr_colli)}C {tr_tipo})",
            type="secondary",
            use_container_width=True,
            key=f"{key_prefix}_add_btn_{bolla_id}",
        ):
            res_tr = add_intershop_to_bolla(
                bolla_id=int(bolla_id),
                mittente=mitt_sel.strip(),
                colli=int(tr_colli),
                tipo=tr_tipo,
            )
            if res_tr.get("status") == "ok":
                st.session_state["flash_bolle_msg"] = (
                    f"Trasferimento aggiunto a Store {store_id}: {res_tr['stringa']}"
                )
                st.rerun()
            else:
                st.error(res_tr.get("message", "Errore salvataggio trasferimento."))


# ==============================================================================
# 3. MODALITÀ MOBILE BANCHINA SEMPLIFICATA (2 TASTI + OMNIBOX + TRASFERIMENTI)
# ==============================================================================
def render_mobile_two_buttons_view(
    runs_side: pd.DataFrame,
    df_stores_side: pd.DataFrame,
    allow_classic_toggle: bool = False,
):
    """
    Interfaccia Smartphone / Palmare:
    - Font e box proporzionati per schermi mobile (nessun testo gigante che sborda)
    - Nessun filtro sui giri (rimosso come richiesto)
    - Selezione negozio tramite OMNIBOX ricercabile con apertura tastiera garantita e svuotamento rapido al tocco
    - Insegna completa (es. STRADIVARIUS ROM-EUROMA2, ZARA ROM-ROMA EST) sincronizzata tra Anagrafica e Bolle
    - TASTO 1: 📋 SPUNTA NEGOZIO (1-Tap Conforme, conteggio manuale + Trasferimenti)
    - TASTO 2: ➕ AGGIUNGI COLLI & TRASFERIMENTI (sia per negozi già spuntati sia per negozi NON spuntati!)
    """
    if "flash_bolle_msg" in st.session_state:
        st.success(f"🎉 **{st.session_state.pop('flash_bolle_msg')}**")

    ensure_bolle_for_latest_run(runs_side)
    _inject_omnibox_autoselect_js()

    if allow_classic_toggle:
        c_title_m, c_tog_m = st.columns([2.8, 1.2])
        with c_title_m:
            st.markdown("#### 📱 Spunta Banchina Mobile")
        with c_tog_m:
            if st.button("🔧 Vista Completa", use_container_width=True, key="btn_mob_to_classic"):
                st.session_state["mob_use_classic_spunta"] = True
                st.rerun()

    today_str = str(date.today())
    tomorrow_str = str(date.today() + timedelta(days=1))
    all_dates = get_bolle_dates(120)
    if not all_dates:
        all_dates = [tomorrow_str, today_str]

    # Calcola date /0 STD e /9 DOPPIA dell'ultima Run per i pulsanti rapidi e per il default intelligente
    latest_std_str = None
    latest_dop_str = None
    if not runs_side.empty:
        try:
            lr = runs_side.iloc[0]
            dt_b = parse_date_obj(lr["run_date"], default=date.today())
            d_dop, d_std = compute_inditex_delivery_dates(dt_b, str(lr.get("cycle_type", "LUN-MER")))
            latest_std_str = str(d_std)
            latest_dop_str = str(d_dop)
        except Exception:
            pass

    if "mob2_date" not in st.session_state or st.session_state["mob2_date"] not in all_dates:
        if today_str in all_dates:
            st.session_state["mob2_date"] = today_str
        elif tomorrow_str in all_dates:
            st.session_state["mob2_date"] = tomorrow_str
        elif latest_std_str and latest_std_str in all_dates:
            st.session_state["mob2_date"] = latest_std_str
        else:
            st.session_state["mob2_date"] = all_dates[0]

    def _fmt_mob_date(d_iso: str) -> str:
        df_tmp = get_bolle_by_date(d_iso)
        if df_tmp.empty:
            return format_date_weekday_it(d_iso)
        types = {str(x).upper() for x in df_tmp["tipo_cons"].dropna().unique()}
        if types == {"STD"}:
            tag = "🚚 /0 STD"
        elif types == {"DOPPIA"}:
            tag = "🔁 /9 DOPPIA"
        else:
            tag = "/0 + /9"
        return f"{format_date_weekday_it(d_iso)} ({tag} • {len(df_tmp)} neg.)"

    # Selezione Data Consegna (senza filtro Giri come richiesto)
    mob_date = st.selectbox(
        "📅 Data di Consegna",
        options=all_dates,
        index=all_dates.index(st.session_state["mob2_date"]),
        format_func=_fmt_mob_date,
        key="mob2_date_sb",
    )
    if mob_date != st.session_state["mob2_date"]:
        st.session_state["mob2_date"] = mob_date
        st.rerun()

    if latest_std_str and latest_dop_str and latest_std_str in all_dates and latest_dop_str in all_dates:
        c_qd1, c_qd2 = st.columns(2)
        with c_qd1:
            if st.button(
                f"🚚 /0 STD: {format_date_weekday_it(latest_std_str)}",
                type="primary" if mob_date == latest_std_str else "secondary",
                use_container_width=True,
                key="mob2_quick_b0_dt",
            ):
                st.session_state["mob2_date"] = latest_std_str
                st.rerun()
        with c_qd2:
            if st.button(
                f"🔁 /9 DOPPIA: {format_date_weekday_it(latest_dop_str)}",
                type="primary" if mob_date == latest_dop_str else "secondary",
                use_container_width=True,
                key="mob2_quick_b9_dt",
            ):
                st.session_state["mob2_date"] = latest_dop_str
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

    df_b_date = df_b_date.copy()
    df_b_date["spuntato"] = pd.to_numeric(df_b_date.get("spuntato", 0), errors="coerce").fillna(0).astype(int)
    df_b_date = df_b_date.sort_values(by=["id_store", "tipo_cons"]).reset_index(drop=True)

    tot_stores = len(df_b_date)
    spuntati_df = df_b_date[df_b_date["spuntato"] == 1].reset_index(drop=True)
    da_spuntare_df = df_b_date[df_b_date["spuntato"] == 0].reset_index(drop=True)
    n_spuntati = len(spuntati_df)
    n_da_spuntare = len(da_spuntare_df)

    all_store_codes_list, store_names_lookup = _build_unified_stores_lookup(df_stores_side, df_b_date)

    # Barra stato avanzamento compatta
    pct_done = int(round((n_spuntati / tot_stores) * 100)) if tot_stores > 0 else 0
    st.markdown(f"""
    <div style="background: #0F172A; color: #FFFFFF; border-radius: 8px; padding: 6px 12px; margin-bottom: 10px;
                display: flex; align-items: center; justify-content: space-between; font-size: 12px; font-weight: 700;">
        <span>📊 Spuntati: <strong style="color: #34D399;">{n_spuntati}/{tot_stores}</strong> ({pct_done}%)</span>
        <span style="color: #FBBF24;">⏳ Da contare: {n_da_spuntare}</span>
    </div>
    """, unsafe_allow_html=True)

    # ==========================================================================
    # I DUE TASTI MOBILE (SCELTA OPERAZIONE)
    # ==========================================================================
    if "mob2_mode" not in st.session_state:
        st.session_state["mob2_mode"] = "spunta"

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
            f"➕ 2. AGGIUNGI COLLI / TRASF. ({tot_stores})",
            type="primary" if is_add_mode else "secondary",
            use_container_width=True,
            key="mob2_big_btn_aggiungi",
        ):
            st.session_state["mob2_mode"] = "aggiungi"
            st.rerun()

    # ==========================================================================
    # MODALITÀ 1: 📋 SPUNTA NEGOZIO (CON OMNIBOX)
    # ==========================================================================
    if st.session_state["mob2_mode"] == "spunta":
        show_all = st.checkbox(
            f"Mostra nell'Omnibox anche i negozi già spuntati ({tot_stores} totali)",
            value=(n_da_spuntare == 0),
            key="mob2_show_all_chk",
        )
        working_df = df_b_date if (show_all or n_da_spuntare == 0) else da_spuntare_df

        if working_df.empty:
            st.success("🎉 Tutti i negozi sono stati spuntati!")
            return

        # Costruzione mappa Omnibox con Insegna + Nome Negozio completo (es. 2917 — STRADIVARIUS ROM-EUROMA2)
        omnibox_options: List[int] = []
        omnibox_labels: Dict[int, str] = {}
        for _, r in working_df.iterrows():
            b_id_val = int(r["id"])
            s_code = str(r["id_store"]).strip()
            s_disp = _format_store_display(s_code, r, store_names_lookup)
            t_tag = "/9 DOPPIA" if str(r.get("tipo_cons", "")).upper() == "DOPPIA" else "/0 STD"
            st_icon = "🟢" if int(r.get("spuntato", 0)) == 1 else "⏳"
            p_tot_r = sum(
                int(round(float(r.get(k, 0) or 0)))
                for k in ["prev_abbigl", "prev_calzat", "prev_ecom", "prev_others"]
            )
            if p_tot_r == 0:
                p_tot_r = sum(
                    int(round(float(r.get(k, 0) or 0)))
                    for k in ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario"]
                )
            omnibox_options.append(b_id_val)
            omnibox_labels[b_id_val] = f"{st_icon} {s_code} — {s_disp} ({t_tag} • {p_tot_r} colli)"

        if "mob2_selected_bid" not in st.session_state or st.session_state["mob2_selected_bid"] not in omnibox_options:
            st.session_state["mob2_selected_bid"] = omnibox_options[0]

        curr_bid = int(st.session_state["mob2_selected_bid"])

        if "mob2_omnibox_spunta" in st.session_state:
            resolved_sp = _resolve_omnibox_bid(
                st.session_state["mob2_omnibox_spunta"],
                omnibox_options,
                omnibox_labels,
                curr_bid,
            )
            curr_bid = resolved_sp
            st.session_state["mob2_selected_bid"] = curr_bid
            st.session_state["mob2_omnibox_spunta"] = curr_bid

        curr_pos = omnibox_options.index(curr_bid)

        # OMNIBOX + frecce compatte (accept_new_options=True sblocca sempre la tastiera su mobile anche con <= 10 negozi)
        selected_raw = st.selectbox(
            "🔍 Omnibox Negozio (tocca il box e digita codice es. 3534, insegna o centro es. Roma Est / Stradivarius)",
            options=omnibox_options,
            index=curr_pos,
            format_func=lambda bid_k: omnibox_labels.get(bid_k, str(bid_k)),
            accept_new_options=True,
            filter_mode="fuzzy",
            key="mob2_omnibox_spunta",
        )
        selected_bid = _resolve_omnibox_bid(selected_raw, omnibox_options, omnibox_labels, curr_bid)
        if selected_bid != curr_bid:
            st.session_state["mob2_selected_bid"] = selected_bid
            st.session_state["mob2_omnibox_spunta"] = selected_bid
            st.rerun()

        c_nav_prev, c_nav_info, c_nav_next = st.columns([1, 1.8, 1])
        with c_nav_prev:
            if st.button("◀️ Prec.", use_container_width=True, disabled=(curr_pos <= 0), key="mob2_prev_btn"):
                prev_bid = omnibox_options[curr_pos - 1]
                st.session_state["mob2_selected_bid"] = prev_bid
                st.session_state["mob2_omnibox_spunta"] = prev_bid
                st.rerun()
        with c_nav_info:
            st.markdown(
                f"<div style='text-align:center; font-size:12px; color:#475569; padding-top:8px;'>"
                f"Negozio <strong>{curr_pos + 1}</strong> di <strong>{len(omnibox_options)}</strong></div>",
                unsafe_allow_html=True,
            )
        with c_nav_next:
            if st.button("Succ. ▶️", use_container_width=True, disabled=(curr_pos >= len(omnibox_options) - 1), key="mob2_next_btn"):
                next_bid = omnibox_options[curr_pos + 1]
                st.session_state["mob2_selected_bid"] = next_bid
                st.session_state["mob2_omnibox_spunta"] = next_bid
                st.rerun()

        b_row = working_df[working_df["id"] == selected_bid].iloc[0]
        bid = int(b_row["id"])
        sid = str(b_row["id_store"]).strip()
        sname = _format_store_display(sid, b_row, store_names_lookup)
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

        # Card negozio con font ben proporzionati che non sbordano
        st.markdown(f"""
        <div style="background: {badge_bg}; color: white; border-radius: 10px; padding: 10px 14px; margin: 6px 0 10px 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; font-weight: 700;">
                <span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 99px;">{tipo_lbl}</span>
                <span>{badge_status}</span>
            </div>
            <div style="font-size: 15.5px; font-weight: 800; margin-top: 5px; line-height: 1.25; word-break: break-word;">
                🏪 {sid} — {html.escape(sname)}
            </div>
            <div style="font-size: 12.5px; color: #DBEAFE; margin-top: 4px; line-height: 1.35;">
                📦 Previsti: <strong style="color: #FDE047; font-size: 13.5px;">{prev_tot} colli</strong>
                (Abb: {prev_abb} | Calz: {prev_cal} | Ecom: {prev_eco} | Altri: {prev_oth})
            </div>
        </div>
        """, unsafe_allow_html=True)

        # TASTO 1-TAP: CONFORME AL PREVISTO (SALVA SUBITO!)
        if st.button(
            f"⚡ CONFORME AL PREVISTO ({prev_tot} COLLI) — SALVA 1-TAP",
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
            st.markdown("<div style='font-size:13px; font-weight:700; margin-bottom:6px;'>✏️ Quantità effettive contate:</div>", unsafe_allow_html=True)
            c_i1, c_i2 = st.columns(2)
            with c_i1:
                in_abb = st.number_input(f"👗 Abbigl. (Prev: {prev_abb})", min_value=0, value=cur_abb, step=1, key=f"m2_abb_{bid}")
                in_eco = st.number_input(f"📦 E-Com (Prev: {prev_eco})", min_value=0, value=cur_eco, step=1, key=f"m2_eco_{bid}")
            with c_i2:
                in_cal = st.number_input(f"👟 Calzat. (Prev: {prev_cal})", min_value=0, value=cur_cal, step=1, key=f"m2_cal_{bid}")
                in_oth = st.number_input(f"📦 Altri (Prev: {prev_oth})", min_value=0, value=cur_oth, step=1, key=f"m2_oth_{bid}")
            in_var = st.number_input(f"📦 Mat. Vario (Prev: {prev_var})", min_value=0, value=cur_var, step=1, key=f"m2_var_{bid}")
            in_note = st.text_input(
                "📝 Note Banchina (opzionale)",
                value=_clean_str(b_row.get("note")),
                placeholder="Inserisci eventuale nota...",
                key=f"m2_note_{bid}",
            )

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
                    note=_clean_str(in_note),
                )
                if res_sp["status"] == "ok":
                    st.session_state["flash_bolle_msg"] = (
                        f"Spunta salvata per Store {sid} ({sname}): {res_sp['total_colli']} colli!"
                    )
                    st.session_state["_scroll_to_top"] = True
                    st.rerun()

        # SEZIONE TRASFERIMENTI (INTERSHOPS) DIRETTAMENTE NELLA SCHEDA DEL NEGOZIO
        _render_mobile_intershops_section(
            bolla_id=bid,
            store_id=sid,
            store_name=sname,
            all_store_codes=all_store_codes_list,
            key_prefix="mob_sp_tr",
            store_names_map=store_names_lookup,
        )

    # ==========================================================================
    # MODALITÀ 2: ➕ AGGIUNGI COLLI & TRASFERIMENTI (TUTTI I NEGOZI: SPUNTATI E NON!)
    # ==========================================================================
    else:
        with st.container(border=True):
            st.markdown("##### ➕ Aggiungi Colli o Trasferimenti (Negozi Spuntati `🟢` e Da Spuntare `⏳`)")

            all_store_opts: Dict[int, str] = {}
            for _, s_r in df_b_date.iterrows():
                s_bid = int(s_r["id"])
                s_id = str(s_r["id_store"]).strip()
                s_nm = _format_store_display(s_id, s_r, store_names_lookup)
                s_tc = "/9 DOPPIA" if str(s_r.get("tipo_cons", "")).upper() == "DOPPIA" else "/0 STD"
                is_sp = int(s_r.get("spuntato", 0)) == 1
                icon_sp = "🟢 Spuntato" if is_sp else "⏳ Da spuntare"
                s_tot = sum(
                    int(round(float(s_r.get(k, 0) or 0)))
                    for k in ["colli_abbigl", "colli_calzat", "colli_ecom", "colli_others", "colli_vario"]
                )
                all_store_opts[s_bid] = f"{s_id} — {s_nm} ({s_tc} • {icon_sp} • Attuali: {s_tot} colli)"

            add_opt_keys = list(all_store_opts.keys())
            default_add_bid = add_opt_keys[0]
            if "mob2_add_store_omnibox" in st.session_state:
                default_add_bid = _resolve_omnibox_bid(
                    st.session_state["mob2_add_store_omnibox"],
                    add_opt_keys,
                    all_store_opts,
                    default_add_bid,
                )
                st.session_state["mob2_add_store_omnibox"] = default_add_bid

            target_raw = st.selectbox(
                "🔍 1️⃣ Omnibox Negozio (tocca il box e digita codice es. 3534, insegna o centro es. Roma Est / Stradivarius)",
                options=add_opt_keys,
                format_func=lambda k: all_store_opts.get(k, str(k)),
                accept_new_options=True,
                filter_mode="fuzzy",
                key="mob2_add_store_omnibox",
            )
            target_bid = _resolve_omnibox_bid(target_raw, add_opt_keys, all_store_opts, default_add_bid)

            sel_row = df_b_date[df_b_date["id"] == target_bid].iloc[0]
            sel_sid = str(sel_row["id_store"]).strip()
            sel_sname = _format_store_display(sel_sid, sel_row, store_names_lookup)
            sel_is_spuntato = int(sel_row.get("spuntato", 0)) == 1

            if "mob2_add_qty" not in st.session_state:
                st.session_state["mob2_add_qty"] = 1

            st.markdown("<div style='font-size:13px; font-weight:700; margin:6px 0 4px 0;'>2️⃣ Quantità colli da aggiungere:</div>", unsafe_allow_html=True)
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
                    "🔢 Colli da aggiungere",
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

            if not sel_is_spuntato:
                mark_as_spuntato = st.checkbox(
                    "Segna il negozio come Spuntato (🟢) dopo l'aggiunta",
                    value=True,
                    key=f"mob2_mark_sp_{target_bid}",
                )
            else:
                mark_as_spuntato = True

            reason_note = st.text_input(
                "📝 Nota opzionale (es. fine scarico, bancale extra)",
                placeholder="Opzionale...",
                key="mob2_add_reason",
            )

            if st.button(
                f"✅ AGGIUNGI +{int(qty_to_add)} COLLI A STORE {sel_sid}",
                type="primary",
                use_container_width=True,
                key="mob2_confirm_add_btn",
            ):
                res_add = add_colli_to_bolla_spuntata(
                    bolla_id=int(target_bid),
                    colli_to_add=int(qty_to_add),
                    category=cat_choice,
                    note_reason=_clean_str(reason_note),
                    mark_spuntato=bool(mark_as_spuntato),
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

        # SEZIONE TRASFERIMENTI (INTERSHOPS) ANCHE NEL TASTO 2
        _render_mobile_intershops_section(
            bolla_id=int(target_bid),
            store_id=sel_sid,
            store_name=sel_sname,
            all_store_codes=all_store_codes_list,
            key_prefix="mob_add_tr",
            store_names_map=store_names_lookup,
        )
