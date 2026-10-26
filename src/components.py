"""
UI Components for Zara Logistics Automation Platform.
Renders Spunta Arrivi (per Negozio), Vista per Giro & Vettori, and
Platform Processing (Lavorazioni di Piattaforma) with full Dark Mode & Light Mode support.
"""

import re
import html
import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional
from src.utils import format_number_it


def _inject_modern_css():
    st.markdown("""
    <style>
        .modern-card {
            background-color: var(--secondary-background-color, #FFFFFF);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 22px;
            border: 1px solid rgba(128, 128, 128, 0.25);
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
            color: var(--text-color, #1E293B);
        }
        .modern-section-title {
            font-size: 17px;
            font-weight: 700;
            color: var(--text-color, #1F497D);
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .modern-tbl {
            width: 100%;
            border-collapse: collapse;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            margin-top: 6px;
        }
        .modern-tbl th {
            background-color: rgba(128, 128, 128, 0.14);
            color: var(--text-color, #475569);
            font-weight: 700;
            text-align: center;
            padding: 10px 12px;
            border-bottom: 2px solid rgba(128, 128, 128, 0.25);
            font-size: 12.5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .modern-tbl td {
            padding: 9px 12px;
            text-align: center;
            border-bottom: 1px solid rgba(128, 128, 128, 0.15);
            color: var(--text-color, #1E293B);
        }
        .modern-tbl tr:hover {
            background-color: rgba(128, 128, 128, 0.08);
        }
        .modern-tbl tr.row-b9 {
            background-color: rgba(245, 158, 11, 0.06);
        }
        .modern-tbl tr.row-b9:hover {
            background-color: rgba(245, 158, 11, 0.13);
        }
        .modern-tbl tr.section-divider td {
            background-color: rgba(245, 158, 11, 0.16);
            color: var(--text-color, #1E293B);
            font-weight: 700;
            font-size: 13px;
            text-align: left;
            padding: 8px 14px;
            letter-spacing: 0.4px;
            border-top: 2px solid rgba(245, 158, 11, 0.4);
            border-bottom: 1px solid rgba(245, 158, 11, 0.3);
        }
        .modern-tbl tr.total-row td {
            background-color: rgba(14, 165, 233, 0.14);
            font-weight: 800;
            font-size: 14.5px;
            border-top: 2px solid rgba(14, 165, 233, 0.45);
            border-bottom: 2px solid rgba(14, 165, 233, 0.45);
        }
        .text-strong {
            font-weight: 700;
            color: var(--text-color, #1E293B);
        }
        .text-accent-blue {
            font-weight: 700;
            color: #38BDF8;
        }
        .text-muted-custom {
            opacity: 0.65;
        }
        .badge-green {
            background-color: rgba(34, 197, 94, 0.18);
            color: #10B981;
            border: 1px solid rgba(34, 197, 94, 0.4);
            padding: 4px 10px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 13px;
            display: inline-block;
        }
        .badge-yellow {
            background-color: rgba(234, 179, 8, 0.18);
            color: #F59E0B;
            border: 1px solid rgba(234, 179, 8, 0.4);
            padding: 3px 9px;
            border-radius: 14px;
            font-weight: 700;
            font-size: 12.5px;
            display: inline-block;
        }
        .badge-red {
            background-color: rgba(239, 68, 68, 0.18);
            color: #EF4444;
            border: 1px solid rgba(239, 68, 68, 0.4);
            padding: 4px 10px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 13px;
            display: inline-block;
        }
        .badge-beta {
            background-color: rgba(225, 29, 72, 0.18);
            color: #F43F5E;
            border: 1px solid rgba(225, 29, 72, 0.45);
            padding: 5px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 14px;
            display: inline-block;
        }
        .badge-pill-blue {
            background-color: rgba(14, 165, 233, 0.18);
            color: #0284C7;
            border: 1px solid rgba(14, 165, 233, 0.4);
            padding: 3px 10px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 13px;
            display: inline-block;
        }
        .badge-giro {
            background-color: rgba(99, 102, 241, 0.16);
            color: #6366F1;
            border: 1px solid rgba(99, 102, 241, 0.35);
            padding: 3px 9px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 12.5px;
            display: inline-block;
        }
        .row-standby {
            background-color: rgba(239, 68, 68, 0.07) !important;
            color: #64748B !important;
        }
        .row-new-store {
            background-color: rgba(56, 189, 248, 0.09) !important;
            border-left: 4px solid #0284C7 !important;
        }
        .badge-standby {
            display: inline-block;
            padding: 2.5px 8px;
            border-radius: 6px;
            font-weight: 800;
            font-size: 11px;
            background: #FEE2E2;
            color: #991B1B;
            border: 1px solid #FCA5A5;
        }
        .badge-new-store {
            display: inline-block;
            padding: 2.5px 8px;
            border-radius: 6px;
            font-weight: 800;
            font-size: 11px;
            background: #E0F2FE;
            color: #0369A1;
            border: 1px solid #7DD3FC;
            box-shadow: 0 0 8px rgba(56, 189, 248, 0.25);
        }
        .badge-pill-gray {
            display: inline-block;
            padding: 2.5px 8px;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 11px;
            background-color: #E2E8F0;
            color: #64748B;
            border: 1px solid #CBD5E1;
        }
        .section-divider-standby {
            background: linear-gradient(90deg, #FEE2E2 0%, #FEF2F2 100%) !important;
            color: #991B1B !important;
            font-weight: 800 !important;
            font-size: 12px !important;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            text-align: left !important;
            padding: 9px 14px !important;
            border-top: 2px solid #F87171 !important;
            border-bottom: 2px solid #F87171 !important;
        }
        .section-divider-new {
            background: linear-gradient(90deg, #E0F2FE 0%, #F0F9FF 100%) !important;
            color: #0369A1 !important;
            font-weight: 800 !important;
            font-size: 12px !important;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            text-align: left !important;
            padding: 9px 14px !important;
            border-top: 2px solid #38BDF8 !important;
            border-bottom: 2px solid #38BDF8 !important;
        }
        .highlight-total-box {
            background-color: rgba(234, 179, 8, 0.2);
            border: 1.5px solid rgba(234, 179, 8, 0.55);
            border-radius: 8px;
            padding: 12px 20px;
            text-align: center;
        }
        .highlight-total-title {
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: block;
            font-weight: 700;
            color: #EAB308;
        }
        .highlight-total-val {
            font-size: 26px;
            font-weight: 900;
            color: var(--text-color, #1E293B);
        }
        .callout-box {
            margin-top: 15px;
            padding: 12px;
            background-color: rgba(128, 128, 128, 0.1);
            border-radius: 8px;
            border-left: 4px solid #38BDF8;
            font-size: 13px;
            color: var(--text-color, #475569);
        }
    </style>
    """, unsafe_allow_html=True)


def _store_sort_key(code_str: str):
    """Sorts numeric store codes in ascending numeric order, keeping suffix if any."""
    s = str(code_str).strip()
    digits = re.sub(r"\D", "", s)
    num = int(digits) if digits.isdigit() else 999999
    return (num, s)


def _giro_sort_key(giro_str: str):
    """Sorts ZA1, ZA2, ..., ZA20 in natural numeric order."""
    s = str(giro_str).strip().upper()
    m = re.search(r"(\d+)", s)
    num = int(m.group(1)) if m else 999
    return (num, s)


def render_spunta_arrivi_modern(df_spunta: pd.DataFrame, df_stores: Optional[pd.DataFrame] = None):
    """
    Renders the Spunta Arrivi table showing ONLY store rows, sorted by store code
    (numeric ascending) with:
    - Active standard stores (numeric order)
    - Active Barra 9 ('B') stores
    - Inactive stores (Stato NO / Standby) placed at the bottom and highlighted in red/amber (pedane = 0)
    - New stores unmapped in anagrafica placed at the bottom and highlighted in cyan/glow
    displaying all store columns except 'totale_pedane', in a modern graphical card.
    """
    _inject_modern_css()

    if df_spunta is None or df_spunta.empty:
        st.info("ℹ️ Nessun dato di spunta disponibile.")
        return

    df = df_spunta.copy()
    if "is_store" in df.columns:
        df = df[df["is_store"] == True].copy()
    if "store_code" in df.columns:
        df = df[
            ~df["store_code"].astype(str).str.strip().str.upper().isin(["", "NEGOZIO", "STORE ID", "EXTRA", "NONE"])
        ].copy()

    if df.empty:
        st.info("ℹ️ Nessun punto vendita presente nella spunta.")
        return

    # Enrich store active / new metadata if df_stores available
    map_attivo = {}
    known_sids = set()
    if df_stores is not None and not df_stores.empty:
        sid_c = "store_id" if "store_id" in df_stores.columns else "store_code"
        if sid_c in df_stores.columns:
            known_sids = {str(x).strip() for x in df_stores[sid_c].dropna()}
            if "attivo" in df_stores.columns:
                map_attivo = df_stores.set_index(sid_c)["attivo"].fillna("SI").astype(str).str.upper().to_dict()

    # Ensure clean types
    for col in ["textile_attesi", "other_attesi", "shoes_attesi", "ecom_attesi", "pedane", "is_barra9"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round().astype(int)
        else:
            df[col] = 0
    df["mc"] = pd.to_numeric(df.get("mc", 0.0), errors="coerce").fillna(0.0).round(2)

    # Determine is_active, is_new, is_b
    def _is_store_active(r) -> bool:
        sc = str(r.get("store_code", "")).strip()
        base_sc = sc[:-1] if sc.endswith("B") else sc
        if "attivo" in r and str(r.get("attivo", "SI")).strip().upper() == "NO":
            return False
        if "is_active" in r and r.get("is_active") is False:
            return False
        if map_attivo:
            st_att = map_attivo.get(sc, map_attivo.get(base_sc, "SI"))
            if st_att == "NO":
                return False
        return True

    def _is_store_new(r) -> bool:
        if "is_new" in r and r.get("is_new") is True:
            return True
        sc = str(r.get("store_code", "")).strip()
        base_sc = sc[:-1] if sc.endswith("B") else sc
        if known_sids:
            return (sc not in known_sids and base_sc not in known_sids)
        return False

    df["_is_active"] = df.apply(_is_store_active, axis=1)
    df["_is_new"] = df.apply(_is_store_new, axis=1)
    df["_is_b"] = (df["is_barra9"] == 1) | df["store_code"].astype(str).str.strip().str.upper().str.endswith("B")
    df["_sort_num"] = df["store_code"].apply(lambda x: _store_sort_key(x)[0])
    df["_sort_str"] = df["store_code"].astype(str).str.strip()

    row_idx_col = "row_idx" if "row_idx" in df.columns else "_sort_str"

    # 4 Groups:
    # 1. Active Standard Stores
    df_std = df[df["_is_active"] & ~df["_is_b"] & ~df["_is_new"]].sort_values(by=["_sort_num", row_idx_col], ascending=[True, True])
    # 2. Active Barra 9 Stores
    df_b9 = df[df["_is_active"] & df["_is_b"] & ~df["_is_new"]].sort_values(by=["_sort_num", row_idx_col], ascending=[True, True])
    # 3. Inactive / Standby Stores
    df_inactive = df[~df["_is_active"]].sort_values(by=["_sort_num", row_idx_col], ascending=[True, True])
    # 4. New Stores Unmapped
    df_new = df[df["_is_active"] & df["_is_new"]].sort_values(by=["_sort_num", row_idx_col], ascending=[True, True])

    rows_html = []

    def _build_row(r: pd.Series, row_type: str = "std") -> str:
        scode = html.escape(str(r.get("store_code", "")).strip())
        sname = html.escape(str(r.get("store_name", "")).replace("\n", " ").strip())
        brand = html.escape(str(r.get("punto_vendita", "") or r.get("brand", "")).strip())
        giro = html.escape(str(r.get("giro", "")).strip())
        mc_val = float(r.get("mc", 0.0))
        tex_val = int(r.get("textile_attesi", 0))
        oth_val = int(r.get("other_attesi", 0))
        sho_val = int(r.get("shoes_attesi", 0))
        eco_val = int(r.get("ecom_attesi", 0))
        tot_colli_row = tex_val + oth_val + sho_val + eco_val
        ped_val = int(r.get("pedane", 0))

        if row_type == "standby":
            tr_class = ' class="row-standby"'
            code_badge = f'<span class="badge-standby">⛔ {scode}</span>'
            giro_badge = f'<span class="badge-giro" style="opacity: 0.6;">{giro}</span>' if giro else "—"
            ped_badge = '<span class="badge-pill-gray">0 plt (Escluso)</span>'
        elif row_type == "new":
            tr_class = ' class="row-new-store"'
            code_badge = f'<span class="badge-new-store">✨ {scode} (NUOVO)</span>'
            giro_badge = f'<span class="badge-giro" style="background:#E0F2FE; color:#0369A1; border:1px solid #38BDF8;">{giro or "DA ASSEGNARE"}</span>'
            ped_badge = f'<span class="badge-pill-blue" style="box-shadow: 0 0 6px rgba(56,189,248,0.4);">{ped_val} plt</span>' if ped_val > 0 else '<span class="text-muted-custom">0</span>'
        elif row_type == "b9":
            tr_class = ' class="row-b9"'
            code_badge = f'<span class="badge-yellow">{scode}</span>'
            giro_badge = f'<span class="badge-giro">{giro}</span>' if giro else "—"
            ped_badge = f'<span class="badge-pill-blue">{ped_val} plt</span>' if ped_val > 0 else '<span class="text-muted-custom">0</span>'
        else:
            tr_class = ""
            code_badge = f'<span class="text-strong">{scode}</span>'
            giro_badge = f'<span class="badge-giro">{giro}</span>' if giro else "—"
            ped_badge = f'<span class="badge-pill-blue">{ped_val} plt</span>' if ped_val > 0 else '<span class="text-muted-custom">0</span>'

        def _fmt_int(v: int, is_b_row: bool) -> str:
            if is_b_row and v == 0:
                return '<span class="text-muted-custom">—</span>'
            if v == 0:
                return '<span class="text-muted-custom">0</span>'
            return f"<strong>{format_number_it(v, 0)}</strong>"

        is_b_flag = (row_type == "b9")
        return (
            f"<tr{tr_class}>"
            f'<td style="text-align: left;">{code_badge}</td>'
            f'<td style="text-align: left; font-weight: 600;">{sname}</td>'
            f'<td style="text-align: left;">{brand}</td>'
            f"<td>{giro_badge}</td>"
            f'<td class="text-strong">{format_number_it(mc_val, 2)}</td>'
            f"<td>{_fmt_int(tex_val, is_b_flag)}</td>"
            f"<td>{_fmt_int(oth_val, is_b_flag)}</td>"
            f"<td>{_fmt_int(sho_val, is_b_flag)}</td>"
            f"<td>{_fmt_int(eco_val, is_b_flag)}</td>"
            f"<td>{_fmt_int(tot_colli_row, is_b_flag)}</td>"
            f"<td>{ped_badge}</td>"
            f"</tr>"
        )

    # 1. Standard active stores
    for _, r in df_std.iterrows():
        rows_html.append(_build_row(r, row_type="std"))

    # 2. Barra 9 active stores
    if not df_b9.empty:
        rows_html.append(
            '<tr class="section-divider">'
            '<td colspan="11">🚚 NEGOZI SDOPPIAMENTO BARRA 9 ("B" — Quota Volume 30%)</td>'
            "</tr>"
        )
        for _, r in df_b9.iterrows():
            rows_html.append(_build_row(r, row_type="b9"))

    # 3. Inactive / Standby stores
    if not df_inactive.empty:
        rows_html.append(
            '<tr class="section-divider-standby">'
            '<td colspan="11">⛔ NEGOZI NON OPERATIVI / STANDBY (STATO: NO — ESCLUSI DAL TRASPORTO / RISTRUTTURAZIONE)</td>'
            "</tr>"
        )
        for _, r in df_inactive.iterrows():
            rows_html.append(_build_row(r, row_type="standby"))

    # 4. New stores unmapped
    if not df_new.empty:
        rows_html.append(
            '<tr class="section-divider-new">'
            '<td colspan="11">✨ NUOVI PUNTI VENDITA NON CENSITI (DA ASSEGNARE A GIRO IN ANAGRAFICA)</td>'
            "</tr>"
        )
        for _, r in df_new.iterrows():
            rows_html.append(_build_row(r, row_type="new"))

    # Totals row: transported volumes and pedane (exclude inactive stores from pedane!)
    df_transported = df[df["_is_active"]].copy()
    tot_mc = float(df_transported["mc"].sum())
    tot_tex = int(df_transported["textile_attesi"].sum())
    tot_oth = int(df_transported["other_attesi"].sum())
    tot_sho = int(df_transported["shoes_attesi"].sum())
    tot_eco = int(df_transported["ecom_attesi"].sum())
    tot_colli = tot_tex + tot_oth + tot_sho + tot_eco
    tot_ped = int(df_transported["pedane"].sum())

    inact_cnt = len(df_inactive)
    inact_note = f" <span style='font-size:11px; font-weight:normal; opacity:0.85;'>({inact_cnt} PV in standby esclusi)</span>" if inact_cnt > 0 else ""

    rows_html.append(
        '<tr class="total-row">'
        f'<td colspan="4" style="text-align: left;">📊 TOTALE TRASPORTO OPERATIVO{inact_note}</td>'
        f"<td>{format_number_it(tot_mc, 2)} m³</td>"
        f"<td>{format_number_it(tot_tex, 0)}</td>"
        f"<td>{format_number_it(tot_oth, 0)}</td>"
        f"<td>{format_number_it(tot_sho, 0)}</td>"
        f"<td>{format_number_it(tot_eco, 0)}</td>"
        f"<td>{format_number_it(tot_colli, 0)}</td>"
        f'<td><span class="badge-beta">{format_number_it(tot_ped, 0)} plt</span></td>'
        "</tr>"
    )

    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="modern-section-title">📋 Elenco Punti Vendita — Spunta Arrivi (Ordine Numerico con Negozi "B" in Coda)</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Visualizzazione ordinata per codice negozio con volumi (MC), colli attesi per categoria (Tessile, Other, Calzature, E-Com) e pedane singolo punto vendita. I flussi Barra 9 ('B') sono raggruppati in fondo."
    )

    table_html = (
        '<div style="overflow-x: auto; max-height: 680px; overflow-y: auto;">'
        '<table class="modern-tbl">'
        "<thead><tr>"
        '<th style="text-align: left;">Negozio</th>'
        '<th style="text-align: left;">Centro / Località</th>'
        '<th style="text-align: left;">Punto Vendita</th>'
        "<th>Giro</th>"
        "<th>MC (m³)</th>"
        "<th>Textile Attesi</th>"
        "<th>Other Attesi</th>"
        "<th>Shoes Attesi</th>"
        "<th>E-Com Attesi</th>"
        "<th>Tot. Colli</th>"
        "<th>Pedane PV</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def parse_vehicle_capacity(tipo_mezzo: str, vehicles_df: Optional[pd.DataFrame] = None) -> int:
    """
    Parses theoretical pallet capacity from vehicle type string.
    Checks dynamic vehicles registry first, then falls back to regex patterns.
    """
    if not tipo_mezzo or not isinstance(tipo_mezzo, str):
        return 0
    s = str(tipo_mezzo).strip().upper()
    if not s or s in ("NONE", "NAN", "—", "-"):
        return 0

    if vehicles_df is None:
        try:
            from src.db import get_vehicles_df
            vehicles_df = get_vehicles_df()
        except Exception:
            vehicles_df = None

    if vehicles_df is not None and not vehicles_df.empty and "cod_mezzo" in vehicles_df.columns:
        match_v = vehicles_df[vehicles_df["cod_mezzo"].astype(str).str.strip().str.upper() == s]
        if not match_v.empty:
            cap = int(match_v.iloc[0].get("capienza_pedane", 0))
            if cap > 0:
                return cap

    import re
    # Multiplier pattern like "14x3" or "14 * 3"
    m_mult = re.search(r"(\d+)\s*[xX*]\s*(\d+)", s)
    if m_mult:
        return int(m_mult.group(1)) * int(m_mult.group(2))

    # Multiplier pattern like "BILICO x 3" or "BILICO * 3"
    m_bil_mult = re.search(r"BILICO\s*[xX*]\s*(\d+)", s)
    if m_bil_mult:
        return 33 * int(m_bil_mult.group(1))

    # Explicit pallet number
    m_num = re.search(r"\b(33|18|14|12|10|8|6)\b", s)
    if m_num:
        return int(m_num.group(1))

    # Keyword defaults
    if "BILICO" in s:
        return 33
    if "MOTRICE" in s:
        return 18
    if "EUROCARGO" in s:
        return 14
    if "FURG" in s:
        return 8

    digits = re.findall(r"\d+", s)
    if digits and int(digits[0]) <= 40:
        return int(digits[0])
    return 0


def suggest_support_vehicle(pedane_tot: int, capienza: int, vehicles_df: Optional[pd.DataFrame] = None) -> Dict[str, str]:
    """
    Determines if a support vehicle (or primary vehicle) is needed for the giro
    and proposes the ideal vehicle type to cover the service, dynamically consulting
    the Anagrafica Mezzi fleet registry.
    """
    if vehicles_df is None:
        try:
            from src.db import get_vehicles_df
            vehicles_df = get_vehicles_df()
        except Exception:
            vehicles_df = None

    v_active = []
    if vehicles_df is not None and not vehicles_df.empty and "cod_mezzo" in vehicles_df.columns:
        f_df = vehicles_df[vehicles_df["attivo"].fillna("SI").astype(str).str.upper() == "SI"].copy()
        f_df["capienza_pedane"] = pd.to_numeric(f_df["capienza_pedane"], errors="coerce").fillna(18).astype(int)
        v_active = f_df.sort_values(by="capienza_pedane", ascending=True)[["cod_mezzo", "capienza_pedane"]].to_dict("records")

    if not v_active:
        v_active = [
            {"cod_mezzo": "FURGONE 8", "capienza_pedane": 8},
            {"cod_mezzo": "EUROCARGO 75", "capienza_pedane": 14},
            {"cod_mezzo": "MOTRICE 18 PLT", "capienza_pedane": 18},
            {"cod_mezzo": "BILICO 33", "capienza_pedane": 33},
        ]

    def _pick_best(need_plt: int) -> str:
        for v in v_active:
            if v["capienza_pedane"] >= need_plt:
                return str(v["cod_mezzo"])
        largest = v_active[-1]
        mult = (need_plt + largest["capienza_pedane"] - 1) // largest["capienza_pedane"]
        return f"{largest['cod_mezzo']} x {mult} ({mult * largest['capienza_pedane']} PLT)"

    if capienza == 0:
        if pedane_tot <= 0:
            return {"status": "none", "badge": "—", "note": ""}
        best = _pick_best(pedane_tot)
        return {"status": "unassigned", "badge": best, "note": f"Consigliato per {pedane_tot} PLT"}

    delta = pedane_tot - capienza
    if delta <= 0:
        return {"status": "ok", "badge": "Mezzo Idoneo", "note": "Copertura 100%"}

    best = _pick_best(delta)
    return {"status": "overload", "badge": best, "note": f"Copre esubero +{delta} PLT"}


def render_riepilogo_giri_modern(
    df_spunta: pd.DataFrame,
    df_stores: Optional[pd.DataFrame] = None,
    special_breakdowns: Optional[Dict[str, Any]] = None
):
    """
    Renders the 'Vista per Giro' showing carrier/driver data, vehicle type,
    stores in the route, total MC, total Colli, 'Impronta a Terra (Pedane)'
    (which considers the dynamic platform processing development: stander + bancali),
    theoretical vehicle capacity, and load saturation percentage.
    """
    _inject_modern_css()

    if df_spunta is None or df_spunta.empty:
        st.info("ℹ️ Nessun dato disponibile per il riepilogo per giro.")
        return

    df = df_spunta.copy()
    if "is_store" in df.columns:
        df = df[df["is_store"] == True].copy()
    if "store_code" in df.columns:
        df = df[
            ~df["store_code"].astype(str).str.strip().str.upper().isin(["", "NEGOZIO", "STORE ID", "EXTRA", "NONE"])
        ].copy()

    if df.empty:
        st.info("ℹ️ Nessun giro disponibile.")
        return

    for col in ["textile_attesi", "other_attesi", "shoes_attesi", "ecom_attesi", "pedane", "is_barra9"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round().astype(int)
        else:
            df[col] = 0
    df["mc"] = pd.to_numeric(df.get("mc", 0.0), errors="coerce").fillna(0.0).round(2)

    # Enrich carrier/driver/vehicle info from df_stores if available
    store_meta = {}
    if df_stores is not None and not df_stores.empty and "store_id" in df_stores.columns:
        for _, sr in df_stores.iterrows():
            store_meta[str(sr["store_id"]).strip()] = sr.to_dict()

    # Extract special stores for platform processing
    special_stores = (special_breakdowns.get("special_stores") or {}) if isinstance(special_breakdowns, dict) else {}

    # Group by giro
    giri_names = sorted(
        [g for g in df["giro"].dropna().astype(str).str.strip().unique() if g],
        key=_giro_sort_key,
    )

    std_giri_rows = []
    b9_giri_rows = []

    for g_name in giri_names:
        grp = df[df["giro"].astype(str).str.strip() == g_name]
        is_b9_giro = bool((grp["is_barra9"] == 1).all() or grp["store_code"].astype(str).str.endswith("B").all())

        # Determine Vettore / Autista / Tipo Mezzo / Cod. Mezzo from spunta or stores master
        vett_list = [str(v).strip() for v in grp.get("vettore_autista", []) if str(v).strip() and str(v).strip().upper() != "NONE"]
        mezzo_list = [str(v).strip() for v in grp.get("tipo_mezzo", []) if str(v).strip() and str(v).strip().upper() != "NONE"]
        cod_m_list = [str(v).strip() for v in grp.get("cod_mezzo", []) if str(v).strip() and str(v).strip().upper() != "NONE"]

        vettore_str = vett_list[0] if vett_list else ""
        mezzo_str = mezzo_list[0] if mezzo_list else ""
        cod_mezzo_str = cod_m_list[0] if cod_m_list else ""

        # Check Anagrafica Negozi for updated driver/carrier/vehicle if missing
        autista_anag = ""
        for sc in grp["store_code"].astype(str).str.strip():
            base_sc = sc[:-1] if sc.endswith("B") else sc
            m = store_meta.get(sc) or store_meta.get(base_sc) or {}
            if is_b9_giro and m.get("autista_doppia"):
                autista_anag = str(m.get("autista_doppia")).strip()
                if not mezzo_str and m.get("tipo_mezzo_doppia"):
                    mezzo_str = str(m.get("tipo_mezzo_doppia")).strip()
                break
            elif m.get("autista"):
                autista_anag = str(m.get("autista")).strip()
                if not mezzo_str and m.get("tipo_mezzo"):
                    mezzo_str = str(m.get("tipo_mezzo")).strip()
                break

        vettore_display = vettore_str or autista_anag or "Da Assegnare"
        if autista_anag and vettore_str and autista_anag.upper() not in vettore_str.upper():
            vettore_display = f"{vettore_str} ({autista_anag})"

        # Store list summary & Pedane calculation with platform footprint development
        seen_s = []
        g_pedane_tot = 0
        platform_notes = []

        for _, sr in grp.iterrows():
            sc = str(sr["store_code"]).strip()
            pv = str(sr.get("punto_vendita") or sr.get("brand") or "").strip()
            raw_ped = int(round(float(sr.get("pedane", 0) or 0)))

            # Check store active status (Standby / Restructuring check)
            is_st_active = True
            if "attivo" in sr and str(sr.get("attivo", "SI")).strip().upper() == "NO":
                is_st_active = False
            elif "is_active" in sr and sr.get("is_active") is False:
                is_st_active = False
            elif sc in store_meta and str(store_meta[sc].get("attivo", "SI")).strip().upper() == "NO":
                is_st_active = False

            if not is_st_active:
                # Excluded from transported volume / truck load!
                store_badge = f"<span style='text-decoration: line-through; opacity: 0.65;'>{sc}</span> <span class='badge-standby' style='font-size:9.5px; padding:1px 5px;'>STANDBY (0 plt)</span>"
                lbl = f"{store_badge} ({pv})" if pv else store_badge
                if lbl not in seen_s:
                    seen_s.append(lbl)
                continue

            # Check if this store has active platform processing
            sp_info = special_stores.get(sc) if not is_b9_giro else None
            if sp_info and isinstance(sp_info, dict):
                # Platform store footprint: bancali + (stander * 2)
                banc_tot = int(sp_info.get("bancali", 0))
                stdr = int(sp_info.get("stander", 0))
                # 2 stander = 4 pedane "a madonna" -> 1 stander = 2 pedane eq.
                stdr_eq = int(sp_info.get("stander_pedane_eq", stdr * 2))
                impronta = int(sp_info.get("impronta_a_terra", banc_tot + stdr_eq))
                g_pedane_tot += impronta
                platform_notes.append(f"{sc}: {impronta} PLT ({banc_tot} plt + {stdr} stdr)")
                store_badge = f"<strong>{sc}</strong> <span class='badge-pill-blue' style='font-size:10.5px;'>🏭 {banc_tot} PLT + {stdr} STD</span>"
            else:
                g_pedane_tot += raw_ped
                store_badge = sc

            lbl = f"{store_badge} ({pv})" if pv else store_badge
            if lbl not in seen_s:
                seen_s.append(lbl)

        stores_summary = ", ".join(seen_s)
        g_mc = round(float(grp["mc"].sum()), 2)
        g_colli = int((grp["textile_attesi"] + grp["other_attesi"] + grp["shoes_attesi"] + grp["ecom_attesi"]).sum())

        capienza = parse_vehicle_capacity(mezzo_str)
        carico_pct = round((g_pedane_tot / capienza) * 100) if capienza > 0 else 0

        info = {
            "giro": g_name,
            "is_b9": is_b9_giro,
            "vettore": vettore_display,
            "tipo_mezzo": mezzo_str or "—",
            "cod_mezzo": cod_mezzo_str or "—",
            "n_stores": len(seen_s),
            "stores_summary": stores_summary,
            "mc": g_mc,
            "colli": g_colli,
            "pedane_totale_giro": g_pedane_tot,
            "capienza": capienza,
            "carico_pct": carico_pct,
            "platform_notes": platform_notes,
        }
        if is_b9_giro:
            b9_giri_rows.append(info)
        else:
            std_giri_rows.append(info)

    all_giri = std_giri_rows + b9_giri_rows
    tot_mc_all = sum(g["mc"] for g in all_giri)
    tot_colli_all = sum(g["colli"] for g in all_giri)
    tot_ped_all = sum(g["pedane_totale_giro"] for g in all_giri)
    tot_cap_all = sum(g["capienza"] for g in all_giri if g["capienza"] > 0)
    sat_media = round((tot_ped_all / tot_cap_all) * 100) if tot_cap_all > 0 else 0

    # Quick KPI summary metrics
    kpi_html = f"""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 20px;">
        <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
            <div style="font-size: 11.5px; font-weight: 700; color: #64748B; text-transform: uppercase;">🚛 Giri Pianificati</div>
            <div style="font-size: 22px; font-weight: 800; color: #0284C7; margin-top: 4px;">{len(all_giri)} Giri</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 2px;">{len(std_giri_rows)} Standard • {len(b9_giri_rows)} Barra 9</div>
        </div>
        <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
            <div style="font-size: 11.5px; font-weight: 700; color: #64748B; text-transform: uppercase;">📦 Volume & Colli</div>
            <div style="font-size: 22px; font-weight: 800; color: #0F172A; margin-top: 4px;">{format_number_it(tot_colli_all, 0)} colli</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 2px;">{format_number_it(tot_mc_all, 2)} m³ complessivi</div>
        </div>
        <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
            <div style="font-size: 11.5px; font-weight: 700; color: #64748B; text-transform: uppercase;">📐 Impronta a Terra</div>
            <div style="font-size: 22px; font-weight: 800; color: #E11D48; margin-top: 4px;">{format_number_it(tot_ped_all, 0)} pedane</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 2px;">Con sviluppo stander 'a madonna'</div>
        </div>
        <div class="modern-card" style="padding: 14px 18px; margin-bottom: 0;">
            <div style="font-size: 11.5px; font-weight: 700; color: #64748B; text-transform: uppercase;">🚚 Capienza & Saturazione</div>
            <div style="font-size: 22px; font-weight: 800; color: #10B981; margin-top: 4px;">{sat_media}% carico</div>
            <div style="font-size: 12px; color: #64748B; margin-top: 2px;">{tot_ped_all} su {tot_cap_all} PLT disponibili</div>
        </div>
    </div>
    """
    st.markdown(kpi_html, unsafe_allow_html=True)

    def _render_giro_tr(g: Dict[str, Any]) -> str:
        tr_cls = ' class="row-b9"' if g["is_b9"] else ""
        g_badge = f'<span class="badge-yellow">{html.escape(g["giro"])}</span>' if g["is_b9"] else f'<span class="badge-giro">{html.escape(g["giro"])}</span>'
        colli_html = f'<strong>{format_number_it(g["colli"], 0)}</strong>' if g["colli"] > 0 else '<span class="text-muted-custom">—</span>'

        # Platform footprint details
        if g["platform_notes"]:
            sub_notes = "<br>".join([f"<span style='color: #0284C7; font-size: 11px;'>🏭 {html.escape(n)}</span>" for n in g["platform_notes"]])
            pedane_cell = f'<strong style="color: #0284C7; font-size: 14px;">{format_number_it(g["pedane_totale_giro"], 0)} PLT</strong><br>{sub_notes}'
        else:
            pedane_cell = f'<span class="badge-beta">{format_number_it(g["pedane_totale_giro"], 0)} pedane</span>'

        # Capienza display
        cap_val = g["capienza"]
        if cap_val > 0:
            cap_html = f'<strong style="font-size: 13.5px;">{cap_val} PLT</strong>'
            pct = g["carico_pct"]
            delta = g["pedane_totale_giro"] - cap_val
            if pct <= 90:
                sat_html = f'<span class="badge-green">🟢 {pct}% ({g["pedane_totale_giro"]}/{cap_val})</span>'
            elif pct <= 100:
                sat_html = f'<span class="badge-giro">🔵 {pct}% ({g["pedane_totale_giro"]}/{cap_val}) — Pieno</span>'
            else:
                sat_html = f'<span class="badge-yellow">⚠️ {pct}% ({g["pedane_totale_giro"]}/{cap_val}) — +{delta} PLT</span>'
        else:
            cap_html = '<span class="text-muted-custom">—</span>'
            sat_html = '<span class="text-muted-custom">—</span>'

        # Proposta mezzo di supporto
        supp = suggest_support_vehicle(g["pedane_totale_giro"], cap_val)
        st_supp = supp["status"]
        if st_supp == "ok":
            supp_html = '<span class="badge-green" style="font-size: 11.5px;">✔ Mezzo Idoneo</span>'
        elif st_supp == "overload":
            supp_html = f'<span class="badge-yellow" style="font-size: 11.5px; font-weight: 700;">➕ {html.escape(supp["badge"])}</span><div style="font-size: 10.5px; color: #D97706; margin-top: 2px;">{html.escape(supp["note"])}</div>'
        elif st_supp == "unassigned":
            supp_html = f'<span class="badge-pill-blue" style="font-size: 11.5px; font-weight: 700;">🚚 {html.escape(supp["badge"])}</span><div style="font-size: 10.5px; color: #0284C7; margin-top: 2px;">{html.escape(supp["note"])}</div>'
        else:
            supp_html = '<span class="text-muted-custom">—</span>'

        return (
            f"<tr{tr_cls}>"
            f"<td>{g_badge}</td>"
            f'<td style="text-align: left; font-weight: 700;">{html.escape(g["vettore"])}</td>'
            f'<td><span class="badge-pill-blue">{html.escape(g["tipo_mezzo"])}</span></td>'
            f"<td>{html.escape(g['cod_mezzo'])}</td>"
            f'<td style="text-align: left; font-size: 13px;">{g["stores_summary"]}</td>'
            f'<td class="text-strong">{format_number_it(g["mc"], 2)} m³</td>'
            f"<td>{colli_html}</td>"
            f"<td>{pedane_cell}</td>"
            f"<td>{cap_html}</td>"
            f"<td>{sat_html}</td>"
            f"<td>{supp_html}</td>"
            f"</tr>"
        )

    rows_html = [_render_giro_tr(g) for g in std_giri_rows]
    if b9_giri_rows:
        rows_html.append(
            '<tr class="section-divider">'
            '<td colspan="11">🚚 GIRI SDOPPIAMENTO BARRA 9 ("B" — Seconde Uscite / Furgoni & Bilici Dedicati)</td>'
            "</tr>"
        )
        rows_html.extend(_render_giro_tr(g) for g in b9_giri_rows)

    sat_tot_badge = f'<span class="badge-green">🟢 {sat_media}% ({tot_ped_all}/{tot_cap_all})</span>' if sat_media <= 100 else f'<span class="badge-yellow">⚠️ {sat_media}% ({tot_ped_all}/{tot_cap_all})</span>'

    rows_html.append(
        '<tr class="total-row">'
        '<td colspan="5" style="text-align: left;">📊 TOTALE SPAZIO COMPLESSIVO TUTTI I GIRI</td>'
        f"<td>{format_number_it(tot_mc_all, 2)} m³</td>"
        f"<td>{format_number_it(tot_colli_all, 0)}</td>"
        f'<td><strong style="color: #E11D48; font-size: 14.5px;">{format_number_it(tot_ped_all, 0)} PLT</strong></td>'
        f"<td><strong>{tot_cap_all} PLT</strong></td>"
        f"<td>{sat_tot_badge}</td>"
        f"<td>—</td>"
        "</tr>"
    )

    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="modern-section-title">🚛 Vista per Giro — Vettori, Mezzi, Impronta a Terra & Supporto Consigliato</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Confronto tra l'impronta a terra complessiva per giro (incluso sviluppo lavorazione banchina: stander 'a madonna' + bancali) e la capienza teorica del mezzo assegnato in anagrafica, con proposta automatica del mezzo di supporto idoneo a coprire eventuali esuberi."
    )

    table_html = (
        '<div style="overflow-x: auto;">'
        '<table class="modern-tbl">'
        "<thead><tr>"
        "<th>Giro</th>"
        '<th style="text-align: left;">Vettore / Autista</th>'
        "<th>Tipo Mezzo</th>"
        "<th>Cod. Mezzo</th>"
        '<th style="text-align: left;">Punti Vendita nel Giro</th>'
        "<th>Volume (MC)</th>"
        "<th>Colli</th>"
        "<th>Impronta a Terra (PLT)</th>"
        "<th>Capienza Mezzo</th>"
        "<th>Saturazione Carico</th>"
        "<th>Supporto Consigliato</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_lavorazioni_piattaforma(sb: Optional[Dict[str, Any]], key_prefix: str = "plt"):
    """
    Renders the complete Lavorazioni di Piattaforma section
    with adaptive Dark & Light mode styling using Streamlit CSS variables.
    """
    if not sb or not isinstance(sb, dict):
        st.info("ℹ️ Nessun dato disponibile per le lavorazioni di piattaforma in questa elaborazione.")
        return

    spec = sb.get("special_stores", {})
    zh = sb.get("zara_home", {})
    tot_pezzi = sb.get("totale_pezzi_lavorati", 0)
    checks = sb.get("check_totals", {})

    _inject_modern_css()

    # -------------------------------------------------------------
    # 1. QUADRATURA TOTALI TEORICI VS SPUNTA
    # -------------------------------------------------------------
    tot_colli_teo = checks.get("totali_teorici_colli", 0)
    chk_colli = checks.get("check_colli", 0)
    diff_colli = checks.get("diff_colli", chk_colli - tot_colli_teo)

    tot_mc_teo = checks.get("totali_teorici_mc", 0.0)
    chk_mc = checks.get("check_mc", 0.0)
    diff_mc = checks.get("diff_mc", chk_mc - tot_mc_teo)

    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown('<div class="modern-section-title">⚖️ 1. Quadratura Totali (File TOTAL vs Somma Voci & Spunta Arrivi)</div>', unsafe_allow_html=True)
    st.caption("Verifica di quadratura tra i valori complessivi Inditex e la somma analitica delle singole voci (Tessile, Scarpe, E-Com).")

    colli_ok = abs(diff_colli) < 1.0
    colli_badge = '<span class="badge-green">✔ Quadrato Perfetto</span>' if colli_ok else f'<span class="badge-yellow">Delta {diff_colli:+,.0f} colli</span>'
    mc_status_class = "badge-green" if abs(diff_mc) < 0.1 else "badge-yellow"
    mc_badge = f'<span class="{mc_status_class}">{diff_mc:+,.2f} m³ (Arrotondamenti)</span>'

    html_checks = (
        '<table class="modern-tbl">'
        '<thead><tr>'
        '<th style="text-align: left; width: 34%;">Grandezza</th>'
        '<th style="width: 22%;">File Generale TOTAL</th>'
        '<th style="width: 22%;">Somma Voci / Spunta</th>'
        '<th style="width: 22%;">Stato Quadratura</th>'
        '</tr></thead>'
        '<tbody>'
        '<tr>'
        '<td style="text-align: left; font-weight: 600;">📦 TOTALE COLLI</td>'
        f'<td class="text-strong">{format_number_it(tot_colli_teo, 0)}</td>'
        f'<td class="text-strong">{format_number_it(chk_colli, 0)}</td>'
        f'<td>{colli_badge}</td>'
        '</tr><tr>'
        '<td style="text-align: left; font-weight: 600;">📐 TOTALI VOLUME (MC)</td>'
        f'<td class="text-strong">{format_number_it(tot_mc_teo, 2)} m³</td>'
        f'<td class="text-strong">{format_number_it(chk_mc, 2)} m³</td>'
        f'<td>{mc_badge}</td>'
        '</tr></tbody>'
        '</table>'
    )
    st.markdown(html_checks, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 2. DETTAGLIO PEZZI APPESI / STESI & CORREZIONE PROFUMI
    # -------------------------------------------------------------
    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown('<div class="modern-section-title">👕 2. Dettaglio Pezzi Appesi / Stesi & Correzione Profumi</div>', unsafe_allow_html=True)
    st.caption("Pezzi calcolati al netto dei profumi dedicati per la corretta determinazione degli stander e dei bancali stesi (dinamico da Anagrafica Negozi).")

    pezzi_rows_html = []
    if spec:
        for sid, sdata in spec.items():
            lbl = sdata.get("label", sid)
            sname = sdata.get("store_name", f"Store {sid}")
            tot_p = sdata.get("totale_pezzi", 0)
            app = sdata.get("appesi", 0)
            ste = sdata.get("stesi", 0)
            corr_p = sdata.get("correzione_profumi", 0)
            pezzi_rows_html.append(
                f'<tr>'
                f'<td style="text-align: left; font-weight: 600;">{html.escape(str(lbl))} - {html.escape(sname)}</td>'
                f'<td class="text-strong">{format_number_it(tot_p, 0)}</td>'
                f'<td><span class="badge-pill-blue">{format_number_it(app, 0)}</span></td>'
                f'<td style="font-weight: 600;">{format_number_it(ste, 0)}</td>'
                f'<td class="text-muted-custom">{format_number_it(corr_p, 0)}</td>'
                f'</tr>'
            )
    else:
        pezzi_rows_html.append('<tr><td colspan="5" class="text-muted-custom">Nessun negozio con lavorazione tessile attiva.</td></tr>')

    html_pezzi = (
        '<table class="modern-tbl">'
        '<thead><tr>'
        '<th style="text-align: left; width: 28%;">Punto Vendita</th>'
        '<th style="width: 18%;">Totale Pezzi</th>'
        '<th style="width: 18%;">Appesi</th>'
        '<th style="width: 18%;">Stesi (Netto)</th>'
        '<th style="width: 18%;">Corr. Profumi</th>'
        '</tr></thead>'
        f'<tbody>{"".join(pezzi_rows_html)}</tbody>'
        '</table>'
    )
    st.markdown(html_pezzi, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 3. RIPARTIZIONE ZARA HOME & 4. SVILUPPO STANDER / BANCALI
    # -------------------------------------------------------------
    c_zh, c_sv = st.columns([1, 1.25])

    with c_zh:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">🏠 3. Zara Home (Split 50/50)</div>', unsafe_allow_html=True)
        st.caption("Suddivisione 50% Barra 0 (/0) e 50% Barra 8 (/8)")

        zh_rows_html = []
        if zh:
            for sid, zdata in zh.items():
                sname = zdata.get("store_name", f"Store {sid}")
                tot_paq = zdata.get("totale_paqueteria", 0)
                q0 = zdata.get("quota_barra0", 0)
                q8 = zdata.get("quota_barra8", 0)
                zh_rows_html.append(
                    f'<tr>'
                    f'<td style="text-align: left; font-weight: 600;">{html.escape(str(sid))} - {html.escape(sname)}</td>'
                    f'<td class="text-strong">{format_number_it(tot_paq, 0)}</td>'
                    f'<td>{format_number_it(q0, 0)}</td>'
                    f'<td>{format_number_it(q8, 0)}</td>'
                    f'</tr>'
                )
        else:
            zh_rows_html.append('<tr><td colspan="4" class="text-muted-custom">Nessun negozio Zara Home configurato.</td></tr>')

        html_zh = (
            '<table class="modern-tbl">'
            '<thead><tr>'
            '<th style="text-align: left; width: 35%;">Negozio</th>'
            '<th style="width: 25%;">Totale</th>'
            '<th style="width: 20%;">/0</th>'
            '<th style="width: 20%;">/8</th>'
            '</tr></thead>'
            f'<tbody>{"".join(zh_rows_html)}</tbody>'
            '</table>'
            '<div style="margin-top: 18px;">'
            '<div class="highlight-total-box">'
            '<span class="highlight-total-title">TOTALE PEZZI COMPLESSIVI LAVORATI</span>'
            f'<span class="highlight-total-val">{format_number_it(tot_pezzi, 0)} pezzi</span>'
            '</div></div>'
        )
        st.markdown(html_zh, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_sv:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">👗 4. Sviluppo Stander, Bancali & Impronta a Terra</div>', unsafe_allow_html=True)
        st.caption("Fattori di carico: 200 pz/stander, 300 pz/bancale steso (store 3680 fattore 65% Barra 0). Regola 2 stander = 4 pedane 'a madonna'.")

        sv_rows_html = []
        if spec:
            for sid, sdata in spec.items():
                lbl = sdata.get("label", sid)
                stdr = sdata.get("stander", 0)
                stdr_eq = sdata.get("stander_pedane_eq", stdr * 2)
                banc_tot = sdata.get("bancali", 0)
                banc_stesi = sdata.get("bancali_stesi", banc_tot)
                banc_extra = sdata.get("bancali_extra", 0)
                sint = sdata.get("sintesi", f"{banc_tot} bancali + {stdr} stander")
                impr = sdata.get("impronta_a_terra", banc_tot + stdr_eq)
                teor = sdata.get("pedane_senza_lavorazione", 0)
                diff = impr - teor if teor > 0 else 0
                diff_tag = f'<span class="badge-yellow" style="font-size:11px; margin-left:4px;">+{diff} PLT</span>' if diff > 0 else ""

                banc_detail = f"{banc_tot}"
                if banc_extra > 0:
                    banc_detail += f" <span style='font-size:11px; color:#64748B;'>({banc_stesi}+{banc_extra})</span>"

                sv_rows_html.append(
                    f'<tr>'
                    f'<td style="text-align: left; font-weight: 600;">{html.escape(str(lbl))}</td>'
                    f'<td class="text-strong">{stdr} <span style="font-size: 11px; color: #64748B;">({stdr_eq} PLT eq.)</span></td>'
                    f'<td class="text-strong">{banc_detail}</td>'
                    f'<td><span class="badge-beta">{html.escape(sint)}</span></td>'
                    f'<td><strong style="color: #0284C7; font-size: 14.5px;">{impr} PLT</strong> {diff_tag}</td>'
                    f'</tr>'
                )
        else:
            sv_rows_html.append('<tr><td colspan="5" class="text-muted-custom">Nessun negozio con lavorazione tessile attiva.</td></tr>')

        html_sv = (
            '<table class="modern-tbl">'
            '<thead><tr>'
            '<th style="text-align: left; width: 22%;">Negozio</th>'
            '<th style="width: 20%;">Stander</th>'
            '<th style="width: 18%;">Bancali</th>'
            '<th style="width: 25%;">Allestimento</th>'
            '<th style="width: 15%;">Impronta</th>'
            '</tr></thead>'
            f'<tbody>{"".join(sv_rows_html)}</tbody>'
            '</table>'
            '<div class="callout-box" style="margin-top: 14px;">'
            "💡 <strong>Regola di Carico Mezzi Piattaforma:</strong> 2 stander occupano lo spazio di 4 bancali disposti trasversalmente ('a madonna'), ovvero <strong>1 stander = 2 pedane equivalenti a terra</strong>. Nelle viste per giro e saturazione mezzi, l'ingombro reale considera l'impronta a terra complessiva (bancali effettivi + stander convertiti)."
            '</div>'
        )
        st.markdown(html_sv, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_anagrafica_negozi_modern(df_stores: pd.DataFrame):
    """
    Renders the Anagrafica Punti Vendita table with the exact modern aesthetic of Spunta Arrivi & Giri:
    - Consistent typography, headers, hover effects, and cards
    - Colored badges for Status, Brand, Giro, Lavorazione, Scorporo Profumi, and Sdoppiamento
    - Non-active / Standby stores placed at the bottom with a distinct section divider
    """
    _inject_modern_css()

    if df_stores is None or df_stores.empty:
        st.info("ℹ️ Nessun punto vendita presente in anagrafica.")
        return

    df = df_stores.copy()

    # Split active vs standby
    df["_attivo_upper"] = df["attivo"].fillna("SI").astype(str).str.strip().str.upper()
    df_active = df[df["_attivo_upper"] != "NO"].copy()
    df_standby = df[df["_attivo_upper"] == "NO"].copy()

    # Sort active by giro and store_id
    if not df_active.empty:
        df_active["_giro_sort"] = df_active["giro"].apply(_giro_sort_key)
        df_active["_store_sort"] = df_active["store_id"].apply(_store_sort_key)
        df_active = df_active.sort_values(by=["_giro_sort", "_store_sort"]).drop(columns=["_giro_sort", "_store_sort"])

    if not df_standby.empty:
        df_standby["_store_sort"] = df_standby["store_id"].apply(_store_sort_key)
        df_standby = df_standby.sort_values(by=["_store_sort"]).drop(columns=["_store_sort"])

    def _render_store_row(r, is_standby: bool = False) -> str:
        sid = html.escape(str(r.get("store_id", "")))
        sname = html.escape(str(r.get("store_name", "")))
        brand = html.escape(str(r.get("brand", "") or r.get("punto_vendita", "")))
        giro = html.escape(str(r.get("giro", "") or "—"))
        mezzo = html.escape(str(r.get("tipo_mezzo", "") or "—"))
        aut = html.escape(str(r.get("autista", "") or "—"))
        cell = str(r.get("cell_autista", "") or "").strip()
        lav = str(r.get("lavorazione", "NO") or "NO").strip().upper()
        scorp = str(r.get("scorporo_profumi", "NO") or "NO").strip().upper()
        sdop = str(r.get("sdoppiamento_b9", "NO") or "NO").strip().upper()
        mezzo_d = html.escape(str(r.get("tipo_mezzo_doppia", "") or "—"))
        form = html.escape(str(r.get("formula", "") or "MC/1,9"))
        ind = html.escape(str(r.get("indirizzo", "") or ""))
        cc = html.escape(str(r.get("cc", "") or ""))

        aut_cell = f"{aut}<br><span style='font-size:11px; opacity:0.75;'>📞 {html.escape(cell)}</span>" if cell and aut != "—" else aut

        brand_badge = f'<span class="badge-pill-blue" style="font-size:11px; padding:2px 7px;">{brand}</span>' if brand else ""
        giro_badge = f'<span class="badge-giro">{giro}</span>' if giro != "—" else '<span class="text-muted-custom">—</span>'
        mezzo_badge = f'<span class="text-strong" style="font-size:12.5px;">{mezzo}</span>' if mezzo != "—" else '<span class="text-muted-custom">—</span>'

        if is_standby:
            status_badge = '<span class="badge-standby">STANDBY</span>'
            row_cls = "row-standby"
        else:
            status_badge = '<span class="badge-green">OPERATIVO</span>'
            row_cls = ""

        # Lavorazione badge
        if lav == "SI TESSILE":
            lav_badge = '<span class="badge-yellow" style="font-size:11px;">👗 SI TESSILE</span>'
        elif lav == "SI HOME":
            lav_badge = '<span class="badge-yellow" style="font-size:11px;">🏠 SI HOME</span>'
        else:
            lav_badge = '<span class="badge-pill-gray" style="font-size:11px;">NO</span>'

        # Scorporo Profumi badge
        if scorp == "SI":
            scorp_badge = '<span class="badge-beta" style="font-size:11px; padding:2px 7px;">🧴 SI</span>'
        else:
            scorp_badge = '<span class="badge-pill-gray" style="font-size:11px;">NO</span>'

        # Sdoppiamento Barra 9 badge
        if sdop == "SI":
            sdop_badge = f'<span class="badge-yellow" style="font-size:11px;">⚡ SI</span><br><span style="font-size:10.5px; opacity:0.8;">{mezzo_d}</span>'
        else:
            sdop_badge = '<span class="badge-pill-gray" style="font-size:11px;">NO</span>'

        loc_str = []
        if ind:
            loc_str.append(ind)
        if cc and cc != "FUORI POLO / DA ASSEGNARE":
            loc_str.append(f"<em>({cc})</em>")
        loc_html = "<br>".join(loc_str) if loc_str else "<span class='text-muted-custom'>—</span>"

        return (
            f'<tr class="{row_cls}">'
            f'<td style="text-align: left;">'
            f'<span class="text-strong" style="font-size: 14.5px;">{sid}</span>'
            f'<span style="font-size: 13px; font-weight: 600; margin-left: 6px;">{sname}</span>'
            f'<div style="margin-top: 3px;">{brand_badge}</div>'
            f'</td>'
            f'<td>{giro_badge}</td>'
            f'<td>{status_badge}</td>'
            f'<td style="text-align: left;">{mezzo_badge}</td>'
            f'<td style="text-align: left; font-size: 12.5px;">{aut_cell}</td>'
            f'<td>{lav_badge}</td>'
            f'<td>{scorp_badge}</td>'
            f'<td>{sdop_badge}</td>'
            f'<td style="font-family: monospace; font-size: 12px; font-weight: 600; color: #0284C7;">{form}</td>'
            f'<td style="text-align: left; font-size: 11.5px; max-width: 200px; color: #64748B;">{loc_html}</td>'
            f'</tr>'
        )

    rows_html = []
    # 1. Active stores
    for _, r in df_active.iterrows():
        rows_html.append(_render_store_row(r, is_standby=False))

    # 2. Standby stores (bottom section)
    if not df_standby.empty:
        rows_html.append(
            '<tr class="section-divider-standby">'
            f'<td colspan="10">⏸️ PUNTI VENDITA NON ATTIVI (STANDBY / RISTRUTTURAZIONE) — {len(df_standby)} Negozi (Esclusi dal carico e dai volumi trasportati)</td>'
            '</tr>'
        )
        for _, r in df_standby.iterrows():
            rows_html.append(_render_store_row(r, is_standby=True))

    tot_active = len(df_active)
    tot_standby = len(df_standby)
    tot_all = tot_active + tot_standby

    table_html = (
        '<div class="modern-card">'
        '<div class="modern-section-title">'
        '<span>🏢 Elenco Ufficiale Punti Vendita & Configurazione Operativa</span>'
        f'<span style="font-size: 12px; font-weight: 500; opacity: 0.7; margin-left: auto;">Totale: <strong>{tot_all}</strong> negozi ({tot_active} attivi, {tot_standby} standby)</span>'
        '</div>'
        '<div style="overflow-x: auto; width: 100%;">'
        '<table class="modern-tbl">'
        '<thead><tr>'
        '<th style="text-align: left; min-width: 210px;">Negozio & Insegna</th>'
        '<th style="min-width: 80px;">Giro</th>'
        '<th style="min-width: 95px;">Stato</th>'
        '<th style="text-align: left; min-width: 130px;">Mezzo STD</th>'
        '<th style="text-align: left; min-width: 140px;">Autista & Cellulare</th>'
        '<th style="min-width: 110px;">Lavorazione</th>'
        '<th style="min-width: 90px;">Profumi</th>'
        '<th style="min-width: 90px;">Sdopp. /9</th>'
        '<th style="min-width: 90px;">Formula</th>'
        '<th style="text-align: left; min-width: 180px;">Indirizzo & CC</th>'
        '</tr></thead>'
        '<tbody>'
        + "".join(rows_html) +
        '</tbody>'
        '</table>'
        '</div>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


def render_parco_mezzi_modern(df_vehicles: pd.DataFrame):
    """
    Renders the Fleet Registry (Parco Mezzi) table with the exact modern aesthetic of Spunta Arrivi & Giri:
    - Consistent typography, badges for vehicle classes, capacity, and status
    """
    _inject_modern_css()

    if df_vehicles is None or df_vehicles.empty:
        st.info("ℹ️ Nessun veicolo presente nel Parco Mezzi.")
        return

    df = df_vehicles.copy()
    if "capienza_pedane" in df.columns:
        df["capienza_pedane"] = pd.to_numeric(df["capienza_pedane"], errors="coerce").fillna(0).astype(int)
        df = df.sort_values(by=["capienza_pedane", "cod_mezzo"], ascending=[True, True])

    rows_html = []
    tot_active = 0
    tot_cap = 0

    for _, r in df.iterrows():
        cod = html.escape(str(r.get("cod_mezzo", "")))
        tipo = html.escape(str(r.get("tipo_mezzo", "MOTRICE")).upper())
        desc = html.escape(str(r.get("descrizione", "") or "—"))
        cap = int(r.get("capienza_pedane", 0))
        att = str(r.get("attivo", "SI")).strip().upper()
        note = html.escape(str(r.get("note", "") or "—"))

        is_att = (att == "SI")
        if is_att:
            tot_active += 1
            tot_cap += cap
            status_badge = '<span class="badge-green">ATTIVO</span>'
            row_cls = ""
        else:
            status_badge = '<span class="badge-standby">NON ATTIVO</span>'
            row_cls = "row-standby"

        # Capienza badge styling
        if cap >= 33:
            cap_badge = f'<span class="badge-green" style="font-size: 14px; font-weight: 800; padding: 4px 12px;">{cap} PLT</span>'
        elif cap >= 18:
            cap_badge = f'<span class="badge-pill-blue" style="font-size: 14px; font-weight: 800; padding: 4px 12px;">{cap} PLT</span>'
        elif cap >= 14:
            cap_badge = f'<span class="badge-giro" style="font-size: 14px; font-weight: 800; padding: 4px 12px;">{cap} PLT</span>'
        else:
            cap_badge = f'<span class="badge-pill-gray" style="font-size: 14px; font-weight: 800; padding: 4px 12px;">{cap} PLT</span>'

        tipo_badge = f'<span class="badge-pill-blue" style="font-size: 11px; padding: 2px 8px;">{tipo}</span>'

        rows_html.append(
            f'<tr class="{row_cls}">'
            f'<td style="text-align: left;"><span class="text-strong" style="font-size: 14px;">🚛 {cod}</span></td>'
            f'<td>{tipo_badge}</td>'
            f'<td style="text-align: left; font-size: 13px;">{desc}</td>'
            f'<td>{cap_badge}</td>'
            f'<td>{status_badge}</td>'
            f'<td style="text-align: left; font-size: 12px; color: #64748B;">{note}</td>'
            f'</tr>'
        )

    table_html = (
        '<div class="modern-card">'
        '<div class="modern-section-title">'
        '<span>🚛 Anagrafica Ufficiale Parco Mezzi & Capienze Operative</span>'
        f'<span style="font-size: 12px; font-weight: 500; opacity: 0.7; margin-left: auto;">Veicoli Attivi: <strong>{tot_active}</strong> / {len(df)} • Flotta Totale: <strong>{tot_cap} PLT</strong></span>'
        '</div>'
        '<div style="overflow-x: auto; width: 100%;">'
        '<table class="modern-tbl">'
        '<thead><tr>'
        '<th style="text-align: left; min-width: 170px;">Codice Mezzo / Denominazione</th>'
        '<th style="min-width: 100px;">Tipologia</th>'
        '<th style="text-align: left; min-width: 220px;">Descrizione / Allestimento</th>'
        '<th style="min-width: 120px;">Capienza (PLT)</th>'
        '<th style="min-width: 100px;">Stato</th>'
        '<th style="text-align: left; min-width: 180px;">Note Operative</th>'
        '</tr></thead>'
        '<tbody>'
        + "".join(rows_html) +
        '</tbody>'
        '</table>'
        '</div>'
        '<div class="callout-box" style="margin-top: 14px;">'
        '💡 <strong>Algoritmo Proposta Mezzi di Supporto:</strong> I veicoli attivi sopra elencati alimentano automaticamente l\'assegnazione nei giri standard (/0) e sdoppiati (/9), e definiscono la proposta automatica del veicolo di rinforzo idoneo in caso di sovraccarico del giro.'
        '</div>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)
