"""
UI Components for Zara Logistics Automation Platform.
Renders Platform Processing (Lavorazioni di Piattaforma) with full Dark Mode & Light Mode support.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional
from src.utils import format_number_it


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
            font-size: 14.5px;
            margin-top: 6px;
        }
        .modern-tbl th {
            background-color: rgba(128, 128, 128, 0.12);
            color: var(--text-color, #475569);
            font-weight: 700;
            text-align: center;
            padding: 10px 14px;
            border-bottom: 2px solid rgba(128, 128, 128, 0.25);
            font-size: 13.5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .modern-tbl td {
            padding: 10px 14px;
            text-align: center;
            border-bottom: 1px solid rgba(128, 128, 128, 0.15);
            color: var(--text-color, #1E293B);
        }
        .modern-tbl tr:hover {
            background-color: rgba(128, 128, 128, 0.08);
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
            opacity: 0.7;
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
            padding: 4px 10px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 13px;
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
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 13px;
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
                <td style="text-align: left; font-weight: 600;">📦 TOTALI COLLI (BULTOS)</td>
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
