from pathlib import Path
from typing import Optional, Union
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
from datetime import datetime

from src.config import (
    PLANNER_TEMPLATE_FILE,
    OUTPUT_DIR
)


def export_sga_file(df_flows: pd.DataFrame, output_path: Union[str, Path]):
    """
    Exports SGA flows (Barra 0 or Barra 9) to an Excel file matching TMS requirements:
    Columns: GIRO, DATA_CARICO, COD_MITTENTE, MAGAZZINO_CARICO, DATA_SCARICO, COD_DESTINATARIO, MAGAZZINO_SCARICO, PESO, VOLUME, COLLI
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cols_order = [
        "GIRO", "DATA_CARICO", "COD_MITTENTE", "MAGAZZINO_CARICO",
        "DATA_SCARICO", "COD_DESTINATARIO", "MAGAZZINO_SCARICO",
        "PESO", "VOLUME", "COLLI"
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SGA_DEF"

    # Header style
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    for col_idx, col_name in enumerate(cols_order, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    for r_idx, (_, row) in enumerate(df_flows.iterrows(), start=2):
        is_ritorno = (row.get("flusso_tipo") == "RITORNO")
        for c_idx, col_name in enumerate(cols_order, start=1):
            val = row.get(col_name, "")
            # If retorno and numeric columns are 0, TMS prefers empty or 0
            if is_ritorno and col_name in ("PESO", "VOLUME", "COLLI"):
                val = ""
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.border = thin_border
            if col_name in ("PESO", "VOLUME", "COLLI") and val != "":
                cell.number_format = "#,##0.00" if col_name == "VOLUME" else "#,##0"

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    wb.save(output_path)


def export_zara_spunta(
    df_spunta: pd.DataFrame,
    output_path: Union[str, Path],
    special_breakdowns: Optional[Dict[str, Any]] = None
):
    """
    Exports the complete SPUNTA ARRIVI sheet as ZARA.xlsx,
    including the bottom section for Platform Processing (Lavorazioni di Piattaforma).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SPUNTA ARRIVI "

    headers = [
        "NEGOZIO", "STORE", "PUNTO VENDITA", "MC", "TEXTILE ATTESI", "",
        "OTHER ATTESI", "", "SHOES ATTESI", "", "ECOM ATTESI", "",
        "PEDANE", "TOTALE PEDANE", "VETTORE AUTISTA", "TIPO MEZZO", "TARGA", "COD.MEZZO", "SUPPORTO"
    ]

    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h if h else None)
        if h:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )
    section_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
    section_font = Font(name="Calibri", size=10, bold=True, color="000000")

    for _, r in df_spunta.iterrows():
        ridx = int(r["row_idx"])
        is_store = bool(r["is_store"])

        if not is_store:
            # Header line
            ws.cell(row=ridx, column=1, value=r["store_code"]).font = section_font
            ws.cell(row=ridx, column=2, value=r["store_name"]).font = section_font
            ws.cell(row=ridx, column=3, value=r["punto_vendita"]).font = section_font
            for c in range(1, 20):
                ws.cell(row=ridx, column=c).fill = section_fill
            continue

        ws.cell(row=ridx, column=1, value=r["store_code"]).border = thin_border
        ws.cell(row=ridx, column=2, value=r["store_name"]).border = thin_border
        ws.cell(row=ridx, column=3, value=r["punto_vendita"]).border = thin_border
        
        c_mc = ws.cell(row=ridx, column=4, value=round(float(r["mc"]), 2) if r["mc"] > 0 else "")
        c_mc.border = thin_border
        c_mc.number_format = "0.00"

        c_tex = ws.cell(row=ridx, column=5, value=int(r["textile_attesi"]) if r["textile_attesi"] > 0 else "")
        c_tex.border = thin_border

        c_oth = ws.cell(row=ridx, column=7, value=int(r["other_attesi"]) if r["other_attesi"] > 0 else "")
        c_oth.border = thin_border

        c_sho = ws.cell(row=ridx, column=9, value=int(r["shoes_attesi"]) if r["shoes_attesi"] > 0 else "")
        c_sho.border = thin_border

        c_eco = ws.cell(row=ridx, column=11, value=int(r["ecom_attesi"]) if r["ecom_attesi"] > 0 else "")
        c_eco.border = thin_border

        c_ped = ws.cell(row=ridx, column=13, value=int(r["pedane"]) if r["pedane"] > 0 else "")
        c_ped.border = thin_border

        tot_p = r.get("totale_pedane", 0.0)
        c_totp = ws.cell(row=ridx, column=14, value=int(tot_p) if tot_p > 0 else "")
        c_totp.border = thin_border

        ws.cell(row=ridx, column=15, value=r["vettore_autista"]).border = thin_border
        ws.cell(row=ridx, column=16, value=r["tipo_mezzo"]).border = thin_border
        ws.cell(row=ridx, column=17, value=r["targa"]).border = thin_border
        ws.cell(row=ridx, column=18, value=r["cod_mezzo"]).border = thin_border
        ws.cell(row=ridx, column=19, value=r["supporto"]).border = thin_border

        # Giro in col 26 (Z)
        ws.cell(row=ridx, column=26, value=r["giro"])

    # Write Bottom Section: Lavorazioni di Piattaforma (Rows 96-113, dynamically adjusted)
    if special_breakdowns:
        bold_font = Font(name="Calibri", size=10, bold=True)
        title_fill = PatternFill(start_color="B8CCE4", end_color="B8CCE4", fill_type="solid")
        
        checks = special_breakdowns.get("check_totals", {})
        spec = special_breakdowns.get("special_stores", {})
        zh = special_breakdowns.get("zara_home", {})

        max_spunta_row = int(df_spunta["row_idx"].max()) if not df_spunta.empty and "row_idx" in df_spunta.columns else 75
        base_offset = max(0, (max_spunta_row + 3) - 96)

        # Row 96: Header
        c96 = ws.cell(row=96 + base_offset, column=1, value="TOTALI ")
        c96.font = bold_font
        c96.fill = title_fill
        ws.cell(row=96 + base_offset, column=3, value="CHECK").font = bold_font
        ws.cell(row=96 + base_offset, column=4, value="CHECK").font = bold_font

        # Row 97: Totali Teorici vs Check Spunta Colli
        ws.cell(row=97 + base_offset, column=1, value="TOTALI TEORICI").font = bold_font
        ws.cell(row=97 + base_offset, column=2, value=int(checks.get("totali_teorici_colli", 0)))
        ws.cell(row=97 + base_offset, column=3, value=int(checks.get("check_colli", 0)))

        # Row 98: Totali MC
        ws.cell(row=98 + base_offset, column=1, value="TOTALI MC").font = bold_font
        c_tmc1 = ws.cell(row=98 + base_offset, column=2, value=round(float(checks.get("totali_teorici_mc", 0.0)), 2))
        c_tmc1.number_format = "0.00"
        c_tmc2 = ws.cell(row=98 + base_offset, column=3, value=round(float(checks.get("check_mc", 0.0)), 2))
        c_tmc2.number_format = "0.00"

        # Row 99: Headers for Pezzi Appesi / Stesi
        ws.cell(row=99 + base_offset, column=2, value="TOTALI").font = bold_font
        ws.cell(row=99 + base_offset, column=3, value="APPESI").font = bold_font
        ws.cell(row=99 + base_offset, column=4, value="STESI").font = bold_font
        ws.cell(row=99 + base_offset, column=13, value="CORREZIONE PROFUM").font = bold_font

        # Rows 100-102: Stores 3680, 9226, 3591
        s_config = [
            (100, "3680", " PEZZI 3680"),
            (101, "9226", " PEZZI 9226"),
            (102, "3591", "PEZZI 3591")
        ]
        for r_row, sid, lbl in s_config:
            s_data = spec.get(sid, {})
            ws.cell(row=r_row + base_offset, column=1, value=lbl).font = bold_font
            ws.cell(row=r_row + base_offset, column=2, value=int(s_data.get("totale_pezzi", 0)))
            ws.cell(row=r_row + base_offset, column=3, value=int(s_data.get("appesi", 0)))
            ws.cell(row=r_row + base_offset, column=4, value=int(s_data.get("stesi", 0)))
            ws.cell(row=r_row + base_offset, column=13, value=int(s_data.get("correzione_profumi", 0)))

        # Row 105: Zara Home Headers
        c105 = ws.cell(row=105 + base_offset, column=1, value="ZARA HOME")
        c105.font = bold_font
        c105.fill = title_fill
        ws.cell(row=105 + base_offset, column=3, value="/0").font = bold_font
        ws.cell(row=105 + base_offset, column=4, value="/8").font = bold_font

        # Row 106-107: Zara Home Stores 1984, 1971
        zh_config = [
            (106, "1984"),
            (107, "1971")
        ]
        for r_row, sid in zh_config:
            z_data = zh.get(sid, {})
            ws.cell(row=r_row + base_offset, column=1, value=int(sid))
            ws.cell(row=r_row + base_offset, column=2, value=int(z_data.get("totale_paqueteria", 0)))
            ws.cell(row=r_row + base_offset, column=3, value=round(float(z_data.get("quota_barra0", 0.0)), 1))
            ws.cell(row=r_row + base_offset, column=4, value=round(float(z_data.get("quota_barra8", 0.0)), 1))

        # Row 108: Totale Pezzi
        ws.cell(row=108 + base_offset, column=1, value="TOTALE PEZZI").font = bold_font
        ws.cell(row=108 + base_offset, column=2, value=int(special_breakdowns.get("totale_pezzi_lavorati", 0))).font = bold_font

        # Row 110: Sviluppo Stander e Bancali
        c110 = ws.cell(row=110 + base_offset, column=1, value="SVILUPPO")
        c110.font = bold_font
        c110.fill = title_fill
        ws.cell(row=110 + base_offset, column=2, value="STANDER").font = bold_font
        ws.cell(row=110 + base_offset, column=3, value="PLT").font = bold_font
        ws.cell(row=110 + base_offset, column=4, value="BETA").font = bold_font

        # Rows 111-113: Sviluppo Stores
        sv_config = [
            (111, "3680", "3680 /0"),
            (112, "9226", "9226"),
            (113, "3591", "3591")
        ]
        for r_row, sid, lbl in sv_config:
            s_data = spec.get(sid, {})
            ws.cell(row=r_row + base_offset, column=1, value=lbl).font = bold_font
            ws.cell(row=r_row + base_offset, column=2, value=int(s_data.get("stander", 0)))
            ws.cell(row=r_row + base_offset, column=3, value=int(s_data.get("bancali", 0)))
            ws.cell(row=r_row + base_offset, column=5, value=s_data.get("sintesi", "")).font = bold_font

    # Column widths
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 15
    ws.column_dimensions["G"].width = 15
    ws.column_dimensions["I"].width = 15
    ws.column_dimensions["K"].width = 15
    ws.column_dimensions["M"].width = 10
    ws.column_dimensions["N"].width = 15
    ws.column_dimensions["O"].width = 20
    ws.column_dimensions["P"].width = 14
    ws.column_dimensions["Q"].width = 12

    wb.save(output_path)


def export_planner_roma(
    df_planner: pd.DataFrame,
    output_path: Union[str, Path],
    template_path: Optional[Path] = None
):
    """
    Fills Planning ITX_RM template with calculated columns F to S and V,
    saving to PLANNER ROMA _<date>.xlsx.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if template_path is None or not Path(template_path).exists():
        template_path = PLANNER_TEMPLATE_FILE

    wb = openpyxl.load_workbook(template_path)
    ws = wb["Planning Roma"]

    map_p = df_planner.set_index("row_idx").to_dict(orient="index")

    for r_idx in range(7, 74):
        p_row = map_p.get(r_idx, {})
        if not p_row:
            continue

        pl_text = p_row.get("planned_textile", 0.0)
        rec_text = p_row.get("received_textile", 0.0)
        pl_oth = p_row.get("planned_others", 0.0)
        rec_oth = p_row.get("received_others", 0.0)
        vol_text = p_row.get("vol_textile", 0.0)
        wt_text = p_row.get("weight_textile", 0.0)

        pl_sho = p_row.get("planned_shoes", 0.0)
        rec_sho = p_row.get("received_shoes", 0.0)
        vol_sho = p_row.get("vol_shoes", 0.0)
        wt_sho = p_row.get("weight_shoes", 0.0)

        pl_eco = p_row.get("planned_ecom", 0.0)
        rec_eco = p_row.get("received_ecom", 0.0)
        vol_eco = p_row.get("vol_ecom", 0.0)
        wt_eco = p_row.get("weight_ecom", 0.0)

        intershops = p_row.get("intershops", "")

        # Write Col F (6) to Col S (19)
        ws.cell(row=r_idx, column=6, value=pl_text if pl_text > 0 else None)
        ws.cell(row=r_idx, column=7, value=rec_text if rec_text > 0 else None)
        ws.cell(row=r_idx, column=8, value=pl_oth if pl_oth > 0 else None)
        ws.cell(row=r_idx, column=9, value=rec_oth if rec_oth > 0 else None)
        ws.cell(row=r_idx, column=10, value=vol_text if vol_text > 0 else None)
        ws.cell(row=r_idx, column=11, value=wt_text if wt_text > 0 else None)

        ws.cell(row=r_idx, column=12, value=pl_sho if pl_sho > 0 else None)
        ws.cell(row=r_idx, column=13, value=rec_sho if rec_sho > 0 else None)
        ws.cell(row=r_idx, column=14, value=vol_sho if vol_sho > 0 else None)
        ws.cell(row=r_idx, column=15, value=wt_sho if wt_sho > 0 else None)

        ws.cell(row=r_idx, column=16, value=pl_eco if pl_eco > 0 else None)
        ws.cell(row=r_idx, column=17, value=rec_eco if rec_eco > 0 else None)
        ws.cell(row=r_idx, column=18, value=vol_eco if vol_eco > 0 else None)
        ws.cell(row=r_idx, column=19, value=wt_eco if wt_eco > 0 else None)

        # Col V (22): Intershops
        ws.cell(row=r_idx, column=22, value=intershops if intershops else None)

    wb.save(output_path)
