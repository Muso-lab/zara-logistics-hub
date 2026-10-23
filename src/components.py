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


def render_spunta_arrivi_modern(df_spunta: pd.DataFrame):
    """
    Renders the Spunta Arrivi table showing ONLY store rows, sorted by store code
    (numeric ascending) with all 'B' (Barra 9) stores placed at the bottom,
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

    # Ensure clean types
    for col in ["textile_attesi", "other_attesi", "shoes_attesi", "ecom_attesi", "pedane", "is_barra9"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round().astype(int)
        else:
            df[col] = 0
    df["mc"] = pd.to_numeric(df.get("mc", 0.0), errors="coerce").fillna(0.0).round(2)

    # Identify 'B' stores (either is_barra9 == 1 or store_code ends with 'B')
    df["_is_b"] = (df["is_barra9"] == 1) | df["store_code"].astype(str).str.strip().str.upper().str.endswith("B")
    df["_sort_num"] = df["store_code"].apply(lambda x: _store_sort_key(x)[0])
    df["_sort_str"] = df["store_code"].astype(str).str.strip()

    # Sort: first non-B stores in numeric order (preserving row_idx for 15733 3 uscite), then B stores at the bottom
    row_idx_col = "row_idx" if "row_idx" in df.columns else "_sort_str"
    df_std = df[~df["_is_b"]].sort_values(by=["_sort_num", row_idx_col], ascending=[True, True])
    df_b9 = df[df["_is_b"]].sort_values(by=["_sort_num", row_idx_col], ascending=[True, True])

    # Build HTML rows
    rows_html = []

    def _build_row(r: pd.Series, is_b: bool) -> str:
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

        tr_class = ' class="row-b9"' if is_b else ""
        code_badge = f'<span class="badge-yellow">{scode}</span>' if is_b else f'<span class="text-strong">{scode}</span>'
        giro_badge = f'<span class="badge-giro">{giro}</span>' if giro else "—"
        ped_badge = f'<span class="badge-pill-blue">{ped_val} plt</span>' if ped_val > 0 else '<span class="text-muted-custom">0</span>'

        def _fmt_int(v: int, is_b_row: bool) -> str:
            if is_b_row and v == 0:
                return '<span class="text-muted-custom">—</span>'
            if v == 0:
                return '<span class="text-muted-custom">0</span>'
            return f"<strong>{format_number_it(v, 0)}</strong>"

        return (
            f"<tr{tr_class}>"
            f'<td style="text-align: left;">{code_badge}</td>'
            f'<td style="text-align: left; font-weight: 600;">{sname}</td>'
            f'<td style="text-align: left;">{brand}</td>'
            f"<td>{giro_badge}</td>"
            f'<td class="text-strong">{format_number_it(mc_val, 2)}</td>'
            f"<td>{_fmt_int(tex_val, is_b)}</td>"
            f"<td>{_fmt_int(oth_val, is_b)}</td>"
            f"<td>{_fmt_int(sho_val, is_b)}</td>"
            f"<td>{_fmt_int(eco_val, is_b)}</td>"
            f"<td>{_fmt_int(tot_colli_row, is_b)}</td>"
            f"<td>{ped_badge}</td>"
            f"</tr>"
        )

    for _, r in df_std.iterrows():
        rows_html.append(_build_row(r, is_b=False))

    if not df_b9.empty:
        rows_html.append(
            '<tr class="section-divider">'
            '<td colspan="11">🚚 NEGOZI SDOPPIAMENTO BARRA 9 ("B" — Quota Volume 30%)</td>'
            "</tr>"
        )
        for _, r in df_b9.iterrows():
            rows_html.append(_build_row(r, is_b=True))

    # Totals row
    tot_mc = float(df["mc"].sum())
    tot_tex = int(df["textile_attesi"].sum())
    tot_oth = int(df["other_attesi"].sum())
    tot_sho = int(df["shoes_attesi"].sum())
    tot_eco = int(df["ecom_attesi"].sum())
    tot_colli = tot_tex + tot_oth + tot_sho + tot_eco
    tot_ped = int(df["pedane"].sum())

    rows_html.append(
        '<tr class="total-row">'
        '<td colspan="4" style="text-align: left;">📊 TOTALE GENERALE SPUNTA ARRIVI</td>'
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


def render_riepilogo_giri_modern(df_spunta: pd.DataFrame, df_stores: Optional[pd.DataFrame] = None):
    """
    Renders the 'Vista per Giro' showing carrier/driver data, vehicle type,
    stores in the route, total MC, total Colli, and 'Pedane Totale Giro'
    computed by summing the planned pedane of each store in the route.
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

        # Check Anagrafica Negozi for updated driver/carrier if missing
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

        # Store list summary (deduplicated for 15733 3 uscite)
        seen_s = []
        for _, sr in grp.iterrows():
            sc = str(sr["store_code"]).strip()
            pv = str(sr.get("punto_vendita") or sr.get("brand") or "").strip()
            lbl = f"{sc} ({pv})" if pv else sc
            if lbl not in seen_s:
                seen_s.append(lbl)
        stores_summary = ", ".join(seen_s)

        g_mc = round(float(grp["mc"].sum()), 2)
        g_colli = int((grp["textile_attesi"] + grp["other_attesi"] + grp["shoes_attesi"] + grp["ecom_attesi"]).sum())
        g_pedane_tot = int(grp["pedane"].sum())

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
        }
        if is_b9_giro:
            b9_giri_rows.append(info)
        else:
            std_giri_rows.append(info)

    def _render_giro_tr(g: Dict[str, Any]) -> str:
        tr_cls = ' class="row-b9"' if g["is_b9"] else ""
        g_badge = f'<span class="badge-yellow">{html.escape(g["giro"])}</span>' if g["is_b9"] else f'<span class="badge-giro">{html.escape(g["giro"])}</span>'
        colli_html = f'<strong>{format_number_it(g["colli"], 0)}</strong>' if g["colli"] > 0 else '<span class="text-muted-custom">—</span>'
        return (
            f"<tr{tr_cls}>"
            f"<td>{g_badge}</td>"
            f'<td style="text-align: left; font-weight: 700;">{html.escape(g["vettore"])}</td>'
            f'<td><span class="badge-pill-blue">{html.escape(g["tipo_mezzo"])}</span></td>'
            f"<td>{html.escape(g['cod_mezzo'])}</td>"
            f'<td style="text-align: left; font-size: 13px;">{html.escape(g["stores_summary"])}</td>'
            f'<td class="text-strong">{format_number_it(g["mc"], 2)} m³</td>'
            f"<td>{colli_html}</td>"
            f'<td><span class="badge-beta">{format_number_it(g["pedane_totale_giro"], 0)} pedane</span></td>'
            f"</tr>"
        )

    rows_html = [_render_giro_tr(g) for g in std_giri_rows]
    if b9_giri_rows:
        rows_html.append(
            '<tr class="section-divider">'
            '<td colspan="8">🚚 GIRI SDOPPIAMENTO BARRA 9 ("B" — Seconde Uscite / Furgoni & Bilici Dedicati)</td>'
            "</tr>"
        )
        rows_html.extend(_render_giro_tr(g) for g in b9_giri_rows)

    all_giri = std_giri_rows + b9_giri_rows
    tot_mc_all = sum(g["mc"] for g in all_giri)
    tot_colli_all = sum(g["colli"] for g in all_giri)
    tot_ped_all = sum(g["pedane_totale_giro"] for g in all_giri)

    rows_html.append(
        '<tr class="total-row">'
        '<td colspan="5" style="text-align: left;">📊 TOTALE SPAZIO COMPLESSIVO TUTTI I GIRI</td>'
        f"<td>{format_number_it(tot_mc_all, 2)} m³</td>"
        f"<td>{format_number_it(tot_colli_all, 0)}</td>"
        f'<td><span class="badge-beta">{format_number_it(tot_ped_all, 0)} pedane</span></td>'
        "</tr>"
    )

    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="modern-section-title">🚛 Riepilogo per Giro — Vettori, Mezzi & Pedane Totale Giro</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Spazio totale richiesto per ciascun giro ('Pedane Totale Giro') calcolato sommando le pedane previste dei singoli punti vendita assegnati al giro, con indicazione di Vettore/Autista e Tipo Mezzo."
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
        "<th>Volume Giro (MC)</th>"
        "<th>Colli Giro</th>"
        "<th>Pedane Totale Giro</th>"
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

    html_checks = f"""
    <table class="modern-tbl">
        <thead>
            <tr>
                <th style="text-align: left; width: 34%;">Grandezza</th>
                <th style="width: 22%;">File Generale TOTAL</th>
                <th style="width: 22%;">Somma Voci / Spunta</th>
                <th style="width: 22%;">Stato Quadratura</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="text-align: left; font-weight: 600;">📦 TOTALE COLLI</td>
                <td class="text-strong">{format_number_it(tot_colli_teo, 0)}</td>
                <td class="text-strong">{format_number_it(chk_colli, 0)}</td>
                <td>{colli_badge}</td>
            </tr>
            <tr>
                <td style="text-align: left; font-weight: 600;">📐 TOTALI VOLUME (MC)</td>
                <td class="text-strong">{format_number_it(tot_mc_teo, 2)} m³</td>
                <td class="text-strong">{format_number_it(chk_mc, 2)} m³</td>
                <td>{mc_badge}</td>
            </tr>
        </tbody>
    </table>
    """
    st.markdown(html_checks, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 2. DETTAGLIO PEZZI APPESI / STESI & CORREZIONE PROFUMI
    # -------------------------------------------------------------
    s3680 = spec.get("3680", {})
    s9226 = spec.get("9226", {})
    s3591 = spec.get("3591", {})

    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown('<div class="modern-section-title">👕 2. Dettaglio Pezzi Appesi / Stesi & Correzione Profumi</div>', unsafe_allow_html=True)
    st.caption("Pezzi calcolati al netto dei profumi dedicati per la corretta determinazione degli stander e dei bancali stesi.")

    html_pezzi = f"""
    <table class="modern-tbl">
        <thead>
            <tr>
                <th style="text-align: left; width: 28%;">Punto Vendita</th>
                <th style="width: 18%;">Totale Pezzi</th>
                <th style="width: 18%;">Appesi</th>
                <th style="width: 18%;">Stesi (Netto)</th>
                <th style="width: 18%;">Corr. Profumi</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="text-align: left; font-weight: 600;">3680 - Porta di Roma</td>
                <td class="text-strong">{format_number_it(s3680.get('totale_pezzi', 0), 0)}</td>
                <td><span class="badge-pill-blue">{format_number_it(s3680.get('appesi', 0), 0)}</span></td>
                <td style="font-weight: 600;">{format_number_it(s3680.get('stesi', 0), 0)}</td>
                <td class="text-muted-custom">{format_number_it(s3680.get('correzione_profumi', 0), 0)}</td>
            </tr>
            <tr>
                <td style="text-align: left; font-weight: 600;">9226 - Via del Corso</td>
                <td class="text-strong">{format_number_it(s9226.get('totale_pezzi', 0), 0)}</td>
                <td><span class="badge-pill-blue">{format_number_it(s9226.get('appesi', 0), 0)}</span></td>
                <td style="font-weight: 600;">{format_number_it(s9226.get('stesi', 0), 0)}</td>
                <td class="text-muted-custom">{format_number_it(s9226.get('correzione_profumi', 0), 0)}</td>
            </tr>
            <tr>
                <td style="text-align: left; font-weight: 600;">3591 - Euroma2</td>
                <td class="text-strong">{format_number_it(s3591.get('totale_pezzi', 0), 0)}</td>
                <td><span class="badge-pill-blue">{format_number_it(s3591.get('appesi', 0), 0)}</span></td>
                <td style="font-weight: 600;">{format_number_it(s3591.get('stesi', 0), 0)}</td>
                <td class="text-muted-custom">{format_number_it(s3591.get('correzione_profumi', 0), 0)}</td>
            </tr>
        </tbody>
    </table>
    """
    st.markdown(html_pezzi, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------
    # 3. RIPARTIZIONE ZARA HOME & 4. SVILUPPO STANDER / BANCALI
    # -------------------------------------------------------------
    c_zh, c_sv = st.columns([1, 1])

    zh1984 = zh.get("1984", {})
    zh1971 = zh.get("1971", {})

    with c_zh:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">🏠 3. Zara Home (Split 50/50)</div>', unsafe_allow_html=True)
        st.caption("Suddivisione 50% Barra 0 (/0) e 50% Barra 8 (/8)")

        html_zh = f"""
        <table class="modern-tbl">
            <thead>
                <tr>
                    <th style="text-align: left; width: 35%;">Negozio</th>
                    <th style="width: 25%;">Totale</th>
                    <th style="width: 20%;">/0</th>
                    <th style="width: 20%;">/8</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="text-align: left; font-weight: 600;">1984 Cola di Rienzo</td>
                    <td class="text-strong">{format_number_it(zh1984.get('totale_paqueteria', 0), 0)}</td>
                    <td>{format_number_it(zh1984.get('quota_barra0', 0), 0)}</td>
                    <td>{format_number_it(zh1984.get('quota_barra8', 0), 0)}</td>
                </tr>
                <tr>
                    <td style="text-align: left; font-weight: 600;">1971 Porta di Roma</td>
                    <td class="text-strong">{format_number_it(zh1971.get('totale_paqueteria', 0), 0)}</td>
                    <td>{format_number_it(zh1971.get('quota_barra0', 0), 0)}</td>
                    <td>{format_number_it(zh1971.get('quota_barra8', 0), 0)}</td>
                </tr>
            </tbody>
        </table>
        <div style="margin-top: 18px;">
            <div class="highlight-total-box">
                <span class="highlight-total-title">TOTALE PEZZI COMPLESSIVI LAVORATI</span>
                <span class="highlight-total-val">{format_number_it(tot_pezzi, 0)} pezzi</span>
            </div>
        </div>
        """
        st.markdown(html_zh, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_sv:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)
        st.markdown('<div class="modern-section-title">👗 4. Sviluppo Stander e Bancali (PLT)</div>', unsafe_allow_html=True)
        st.caption("Fattori di carico: 200 pz/stander, 300 pz/bancale (store 3680 fattore 65% Barra 0)")

        html_sv = f"""
        <table class="modern-tbl">
            <thead>
                <tr>
                    <th style="text-align: left; width: 28%;">Sviluppo</th>
                    <th style="width: 18%;">Stander</th>
                    <th style="width: 18%;">PLT</th>
                    <th style="width: 36%;">Allestimento (BETA)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="text-align: left; font-weight: 600;">3680 /0</td>
                    <td class="text-strong">{s3680.get('stander', 0)}</td>
                    <td class="text-strong">{s3680.get('bancali', 0)}</td>
                    <td><span class="badge-beta">{s3680.get('sintesi', '')}</span></td>
                </tr>
                <tr>
                    <td style="text-align: left; font-weight: 600;">9226</td>
                    <td class="text-strong">{s9226.get('stander', 0)}</td>
                    <td class="text-strong">{s9226.get('bancali', 0)}</td>
                    <td><span class="badge-beta">{s9226.get('sintesi', '')}</span></td>
                </tr>
                <tr>
                    <td style="text-align: left; font-weight: 600;">3591</td>
                    <td class="text-strong">{s3591.get('stander', 0)}</td>
                    <td class="text-strong">{s3591.get('bancali', 0)}</td>
                    <td><span class="badge-beta">{s3591.get('sintesi', '')}</span></td>
                </tr>
            </tbody>
        </table>
        <div class="callout-box">
            💡 <strong>Riepilogo Hub:</strong> I conteggi di stander e bancali determinano la corretta allocazione fisica a banchina per le partenze mattutine.
        </div>
        """
        st.markdown(html_sv, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
