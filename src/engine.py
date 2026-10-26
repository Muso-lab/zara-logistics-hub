import json
import math
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from src.config import (
    PESO_SPECIFICO_COLLO_KG,
    VOLUME_DIVISORE_COLLI_BARRA9,
    VOLUME_DIVISORE_PEDANA,
    PERCENTUALE_BARRA0_SPLIT,
    PERCENTUALE_BARRA9_SPLIT,
    MAGAZZINO_CARICO_DEFAULT,
    COD_MITTENTE_DEFAULT,
    DATA_DIR
)


def evaluate_pedane(mc: float, formula_str: str = "") -> int:
    """
    Evaluates store-specific pedane formula.
    Supported formats from anagrafica:
    - 'MC/1,9'
    - 'MC*1,5/1,8'
    - 'MC/1,5'
    - '(MC*1,5/1,8)*0,7'
    - Custom arithmetic expressions using MC
    Note: since `mc` passed to this function is already scaled by the row factor
    (e.g. 0.7 on Barra 0 or 0.3 on Barra 9), any redundant `*0.7` in formula_str
    is stripped to avoid multiplying by 0.7 twice.
    """
    if mc <= 0:
        return 0
    if not formula_str or pd.isna(formula_str):
        return math.ceil(mc / VOLUME_DIVISORE_PEDANA)
    
    clean_f = str(formula_str).upper().replace(" ", "").replace(",", ".")
    # Replace variable MC with numeric value
    expr = clean_f.replace("MC", f"({mc})")
    # Verify allowed arithmetic characters only
    if not re.match(r"^[0-9\.\+\-\*\/\(\)]+$", expr):
        return math.ceil(mc / VOLUME_DIVISORE_PEDANA)
    try:
        val = eval(expr, {"__builtins__": None}, {})
        return math.ceil(val - 1e-9)
    except:
        return math.ceil(mc / VOLUME_DIVISORE_PEDANA)


def compute_analisi(
    df_stores: pd.DataFrame,
    df_total: pd.DataFrame,
    df_shoes: pd.DataFrame,
    df_texile: pd.DataFrame,
    df_ecom: pd.DataFrame,
    df_other_agg: pd.DataFrame
) -> pd.DataFrame:
    """
    Computes the central ANALISI table:
    For each store in df_stores:
      - textile colli = max(0, texile.bultos - other.otros_enviado)
      - others colli = other.otros_enviado
      - shoes colli = shoes.bultos
      - ecom colli = ecom.bultos
      - volumes and weights
    """
    def _to_map(df, default_col="store_id"):
        if df is None or df.empty:
            return {}
        col = default_col if default_col in df.columns else ("store_id" if "store_id" in df.columns else ("store_code" if "store_code" in df.columns else None))
        if not col:
            return {}
        return {str(k).strip(): v for k, v in df.set_index(col).to_dict(orient="index").items()}

    map_total = _to_map(df_total, "store_id")
    map_shoes = _to_map(df_shoes, "store_id")
    map_texile = _to_map(df_texile, "store_id")
    map_ecom = _to_map(df_ecom, "store_id")
    map_other = _to_map(df_other_agg, "store_code")

    results = []
    # Process distinct stores (excluding 'B' suffix stores from master for base analisi)
    base_stores = df_stores[~df_stores["store_id"].str.endswith("B")].copy()

    for _, srow in base_stores.iterrows():
        sid = str(srow["store_id"]).strip()
        brand = str(srow.get("punto_vendita", "") or srow.get("brand", ""))
        sname = str(srow.get("store_name", ""))
        giro = str(srow.get("giro", ""))

        tex_data = map_texile.get(sid, {})
        sho_data = map_shoes.get(sid, {})
        eco_data = map_ecom.get(sid, {})
        oth_data = map_other.get(sid, {})

        # Textile total bultos
        crts_textile_total = int(round(float(tex_data.get("bultos", 0.0))))
        vol_textile = round(float(tex_data.get("volumen", 0.0)), 2)
        weight_textile = int(round(float(tex_data.get("peso", 0.0))))

        # Others bultos
        planned_others = int(round(float(oth_data.get("otros_enviado", 0.0))))

        # Planned textile = Textile total - Others
        if crts_textile_total > 0:
            planned_textile = max(0, crts_textile_total - planned_others)
        else:
            planned_textile = 0

        # Shoes
        planned_shoes = int(round(float(sho_data.get("bultos", 0.0))))
        vol_shoes = round(float(sho_data.get("volumen", 0.0)), 2)
        weight_shoes = int(round(float(sho_data.get("peso", 0.0))))

        # Ecom
        planned_ecom = int(round(float(eco_data.get("bultos", 0.0))))
        vol_ecom = round(float(eco_data.get("volumen", 0.0)), 2)
        weight_ecom = int(round(float(eco_data.get("peso", 0.0))))

        # Totals
        total_vol = round(vol_textile + vol_shoes + vol_ecom, 2)
        total_weight = int(weight_textile + weight_shoes + weight_ecom)
        total_planned_crts = int(planned_textile + planned_others + planned_shoes + planned_ecom)

        # Fallback to TOTAL file if sub-category files didn't include this store
        tot_d = map_total.get(sid, {})
        if total_planned_crts == 0 and (float(tot_d.get("bultos", 0.0)) > 0 or float(tot_d.get("volumen", 0.0)) > 0):
            planned_textile = int(round(float(tot_d.get("bultos", 0.0))))
            crts_textile_total = planned_textile
            vol_textile = round(float(tot_d.get("volumen", 0.0)), 2)
            weight_textile = int(round(float(tot_d.get("peso", 0.0))))
            total_vol = vol_textile
            total_weight = weight_textile
            total_planned_crts = planned_textile

        results.append({
            "store_id": sid,
            "brand": brand,
            "store_name": sname,
            "giro": giro,
            "crts_textile_total": crts_textile_total,
            "planned_others": planned_others,
            "planned_textile": planned_textile,
            "vol_textile": vol_textile,
            "weight_textile": weight_textile,
            "planned_shoes": planned_shoes,
            "vol_shoes": vol_shoes,
            "weight_shoes": weight_shoes,
            "planned_ecom": planned_ecom,
            "vol_ecom": vol_ecom,
            "weight_ecom": weight_ecom,
            "total_vol": total_vol,
            "total_weight": total_weight,
            "total_planned_crts": total_planned_crts
        })

    return pd.DataFrame(results)


def compute_spunta_arrivi(
    df_analisi: pd.DataFrame,
    df_stores: Optional[pd.DataFrame] = None,
    template_path: Optional[Path] = None
) -> pd.DataFrame:
    """
    Builds the SPUNTA ARRIVI table using the layout defined in spunta_template.json.
    Computes MC, Pedane (using store-specific formula), Totali Pedane per giro,
    and values for both Barra 0 and Barra 9 rows.
    """
    if template_path is None:
        template_path = DATA_DIR / "spunta_template.json"

    with open(template_path, "r", encoding="utf-8") as f:
        tpl_rows = json.load(f)

    map_a = {}
    if df_analisi is not None and not df_analisi.empty:
        sid_col = "store_id" if "store_id" in df_analisi.columns else ("store_code" if "store_code" in df_analisi.columns else None)
        if sid_col:
            for _, r in df_analisi.iterrows():
                k = str(r[sid_col]).strip()
                bk = k[:-1] if k.endswith("B") else k
                map_a[bk] = r.to_dict()
                if k != bk:
                    map_a[k] = r.to_dict()

    map_formula = {}
    map_sdoppia = {}
    map_attivo = {}
    map_giro = {}
    map_vett = {}
    map_mezzo = {}
    known_store_ids = set()
    if df_stores is not None and not df_stores.empty:
        sid_col = "store_id" if "store_id" in df_stores.columns else ("store_code" if "store_code" in df_stores.columns else None)
        if sid_col:
            known_store_ids = {str(x).strip() for x in df_stores[sid_col].dropna()}
            if "formula" in df_stores.columns:
                map_formula = df_stores.set_index(sid_col)["formula"].dropna().to_dict()
            if "sdoppiamento_b9" in df_stores.columns:
                map_sdoppia = df_stores.set_index(sid_col)["sdoppiamento_b9"].fillna("NO").astype(str).str.upper().to_dict()
            if "attivo" in df_stores.columns:
                map_attivo = df_stores.set_index(sid_col)["attivo"].fillna("SI").astype(str).str.upper().to_dict()
            if "giro" in df_stores.columns:
                map_giro = df_stores.set_index(sid_col)["giro"].dropna().to_dict()
            if "vettore" in df_stores.columns:
                map_vett = df_stores.set_index(sid_col)["vettore"].dropna().to_dict()
            if "tipo_mezzo" in df_stores.columns:
                map_mezzo = df_stores.set_index(sid_col)["tipo_mezzo"].dropna().to_dict()
    else:
        try:
            from src.db import get_stores_df
            sdf = get_stores_df()
            if not sdf.empty:
                known_store_ids = {str(x).strip() for x in sdf["store_id"].dropna()}
                map_sdoppia = sdf.set_index("store_id")["sdoppiamento_b9"].fillna("NO").astype(str).str.upper().to_dict()
                map_attivo = sdf.set_index("store_id")["attivo"].fillna("SI").astype(str).str.upper().to_dict()
                map_giro = sdf.set_index("store_id")["giro"].dropna().to_dict()
                map_vett = sdf.set_index("store_id")["vettore"].dropna().to_dict()
                map_mezzo = sdf.set_index("store_id")["tipo_mezzo"].dropna().to_dict()
        except:
            pass

    spunta_records = []
    for row in tpl_rows:
        ridx = row["row_idx"]
        is_store = row["is_store"]
        sid = row["store_id"]
        is_b9 = row.get("is_barra9", 0)
        factor = row.get("factor", 1.0)

        colli_factor = row.get("colli_factor", 1.0)
        if ridx in [68, 69, 70]:
            factor = 1.0 / 3.0
            colli_factor = 1.0 / 3.0

        if not is_store:
            # Section Header row
            spunta_records.append({
                "row_idx": ridx,
                "is_store": False,
                "store_code": sid,
                "store_name": row["store_name"],
                "punto_vendita": row["brand"],
                "brand": row["brand"],
                "mc": 0.0,
                "textile_attesi": 0,
                "other_attesi": 0,
                "shoes_attesi": 0,
                "ecom_attesi": 0,
                "pedane": 0,
                "totale_pedane": 0,
                "vettore_autista": "",
                "tipo_mezzo": "",
                "targa": "",
                "cod_mezzo": "",
                "supporto": "",
                "giro": row["giro"],
                "is_barra9": is_b9
            })
            continue

        # Dynamic sdoppiamento check from store master data
        # Note: in Spunta Arrivi, Barra 0 splits MC by 0.7 (and Barra 9 by 0.3),
        # while physical Colli (textile, other, shoes, ecom) remain 100% on Barra 0!
        base_sid = sid[:-1] if sid.endswith("B") else sid
        if ridx in [68, 69, 70]:
            factor = 1.0 / 3.0
            colli_factor = 1.0 / 3.0
        elif base_sid in map_sdoppia:
            is_sdop = (map_sdoppia[base_sid] == "SI")
            if is_b9:
                factor = 0.3 if is_sdop else 0.0
                colli_factor = 0.0
            else:
                factor = 0.7 if is_sdop else 1.0
                colli_factor = 1.0

        a_data = map_a.get(base_sid, {})

        tot_vol = float(a_data.get("total_vol", 0.0))
        # Volume rounded to 2 decimal places
        mc = round(tot_vol * factor, 2)

        if is_b9:
            # Barra 9 rows: colli are not in textile/shoes, they are calculated by volume
            textile_attesi = 0
            other_attesi = 0
            shoes_attesi = 0
            ecom_attesi = 0
        elif ridx in [68, 69, 70]:
            # Castel Giubileo (15733) 3 uscite: split integer colli across the 3 rows without decimals
            u_idx = ridx - 68  # 0, 1, 2
            def _split3(v: float) -> int:
                iv = int(round(float(v)))
                return (iv // 3) + (1 if (iv % 3) > u_idx else 0)
            textile_attesi = _split3(a_data.get("planned_textile", 0.0))
            other_attesi = _split3(a_data.get("planned_others", 0.0))
            shoes_attesi = _split3(a_data.get("planned_shoes", 0.0))
            ecom_attesi = _split3(a_data.get("planned_ecom", 0.0))
        else:
            textile_attesi = int(round(float(a_data.get("planned_textile", 0.0)) * colli_factor))
            other_attesi = int(round(float(a_data.get("planned_others", 0.0)) * colli_factor))
            shoes_attesi = int(round(float(a_data.get("planned_shoes", 0.0)) * colli_factor))
            ecom_attesi = int(round(float(a_data.get("planned_ecom", 0.0)) * colli_factor))

        # Pedane calculation using store-specific formula if available
        # On Barra 9 ('B') rows, original template uses MC*1,5/1,8 (i.e. MC/1.2)
        if is_b9:
            store_formula = map_formula.get(sid, "MC*1,5/1,8")
        else:
            store_formula = map_formula.get(sid, map_formula.get(base_sid, ""))
            if factor < 1.0 and store_formula:
                # Since mc is already scaled by 0.7, strip redundant *0,7 from formula string
                store_formula = re.sub(r"\*\s*0[.,]7\b", "", str(store_formula))
        calc_pedane = int(evaluate_pedane(mc, store_formula))

        # Check store active status (Stato SI / NO)
        st_attivo = map_attivo.get(sid, map_attivo.get(base_sid, "SI"))
        is_active = (st_attivo == "SI")
        is_new = (base_sid not in known_store_ids and sid not in known_store_ids)

        # Non-active stores (standby / restructuring) are excluded from transported pedane!
        pedane = calc_pedane if is_active else 0

        spunta_records.append({
            "row_idx": ridx,
            "is_store": True,
            "store_code": sid,
            "store_name": row["store_name"],
            "punto_vendita": row["brand"],
            "brand": row["brand"],
            "mc": mc,
            "textile_attesi": textile_attesi,
            "other_attesi": other_attesi,
            "shoes_attesi": shoes_attesi,
            "ecom_attesi": ecom_attesi,
            "pedane": pedane,
            "pedane_teoriche": calc_pedane,
            "totale_pedane": 0,  # Will compute below per group
            "vettore_autista": map_vett.get(sid, row["vettore_autista"]),
            "tipo_mezzo": map_mezzo.get(sid, row["tipo_mezzo"]),
            "targa": row["targa"],
            "cod_mezzo": row["cod_mezzo"],
            "supporto": row["supporto"],
            "giro": map_giro.get(sid, row["giro"]),
            "is_barra9": is_b9,
            "attivo": st_attivo,
            "is_active": is_active,
            "is_new": is_new,
        })

    df_sp = pd.DataFrame(spunta_records)

    # Detect unmapped stores from df_analisi with volume or colli
    tpl_sids = {str(r["store_id"]).strip() for r in tpl_rows if r.get("is_store")}
    tpl_base_sids = {s[:-1] if s.endswith("B") else s for s in tpl_sids}

    unmapped = []
    for _, a_row in df_analisi.iterrows():
        sid = str(a_row["store_id"]).strip()
        if sid not in tpl_base_sids and (float(a_row.get("total_planned_crts", 0)) > 0 or float(a_row.get("total_vol", 0)) > 0):
            unmapped.append(a_row)

    if unmapped:
        max_ridx = max((int(r["row_idx"]) for r in tpl_rows), default=75) + 1
        # Add Section Header
        spunta_records.append({
            "row_idx": max_ridx,
            "is_store": False,
            "store_code": "EXTRA",
            "store_name": "SPEDIZIONI DA ASSEGNARE / FUORI POLO",
            "punto_vendita": "FUORI POLO",
            "brand": "DA ASSEGNARE",
            "mc": 0.0,
            "textile_attesi": 0,
            "other_attesi": 0,
            "shoes_attesi": 0,
            "ecom_attesi": 0,
            "pedane": 0,
            "totale_pedane": 0,
            "vettore_autista": "",
            "tipo_mezzo": "",
            "targa": "",
            "cod_mezzo": "",
            "supporto": "",
            "giro": "DA ASSEGNARE",
            "is_barra9": 0
        })
        for u in unmapped:
            max_ridx += 1
            u_sid = str(u["store_id"]).strip()
            u_mc = round(float(u.get("total_vol", 0.0)), 2)
            u_form = map_formula.get(u_sid, "MC/1,9")
            u_calc_ped = int(evaluate_pedane(u_mc, u_form))
            u_attivo = map_attivo.get(u_sid, "SI")
            u_is_active = (u_attivo == "SI")
            u_ped = u_calc_ped if u_is_active else 0
            u_giro = str(u.get("giro", "DA ASSEGNARE")) if u.get("giro") else "DA ASSEGNARE"
            spunta_records.append({
                "row_idx": max_ridx,
                "is_store": True,
                "store_code": u_sid,
                "store_name": str(u.get("store_name", u_sid)),
                "punto_vendita": str(u.get("brand", "DA ASSEGNARE")),
                "brand": str(u.get("brand", "DA ASSEGNARE")),
                "mc": u_mc,
                "textile_attesi": int(round(float(u.get("planned_textile", 0.0)))),
                "other_attesi": int(round(float(u.get("planned_others", 0.0)))),
                "shoes_attesi": int(round(float(u.get("planned_shoes", 0.0)))),
                "ecom_attesi": int(round(float(u.get("planned_ecom", 0.0)))),
                "pedane": u_ped,
                "pedane_teoriche": u_calc_ped,
                "totale_pedane": 0,
                "vettore_autista": "",
                "tipo_mezzo": "",
                "targa": "",
                "cod_mezzo": "",
                "supporto": "",
                "giro": u_giro,
                "is_barra9": 0,
                "attivo": u_attivo,
                "is_active": u_is_active,
                "is_new": True,
            })

        df_sp = pd.DataFrame(spunta_records)

    # Compute totale_pedane per giro group
    # Group contiguous blocks of same giro
    for giro_name, grp in df_sp[df_sp["is_store"]].groupby("giro", sort=False):
        sum_ped = int(grp["pedane"].sum())
        first_idx = grp.index[0]
        df_sp.loc[first_idx, "totale_pedane"] = sum_ped

    return df_sp


def compute_sga_flows(
    df_spunta: pd.DataFrame,
    df_stores: pd.DataFrame,
    run_date: str
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generates Andata & Ritorno flows for:
    - Barra 0 (saved to barrazero_Sga.xlsx)
    - Barra 9 (saved to barranove_Sga.xlsx)
    """
    # Parse run_date
    try:
        dt = datetime.strptime(run_date[:10], "%Y-%m-%d")
    except:
        dt = datetime.now()

    # Data Carico / Scarico: formato rigido gg/mm/aaaa (DD/MM/YYYY)
    # Barra 0: NOW() + 1
    # Barra 9: NOW() + 2
    dt_b0 = (dt + timedelta(days=1)).strftime("%d/%m/%Y")
    dt_b9 = (dt + timedelta(days=2)).strftime("%d/%m/%Y")

    def _is_unassigned_giro(val: Any) -> bool:
        if pd.isna(val) or val is None:
            return True
        g = str(val).strip().upper()
        if not g or g in ("DA ASSEGNARE", "NON ASSEGNATO", "NON DEFINITO", "NONE", "NAN", "-"):
            return True
        if g.startswith("DA ASS") or g.startswith("NON ASS"):
            return True
        return False

    map_codsga = {}
    if df_stores is not None and not df_stores.empty:
        sid_col = "store_id" if "store_id" in df_stores.columns else ("store_code" if "store_code" in df_stores.columns else None)
        if sid_col and "cod_sga" in df_stores.columns:
            map_codsga = df_stores.set_index(sid_col)["cod_sga"].dropna().to_dict()

    # 1. Barra 0 Flows
    b0_stores = df_spunta[(df_spunta["is_store"]) & (df_spunta["is_barra9"] == 0)].copy()
    if "attivo" in b0_stores.columns:
        b0_stores = b0_stores[b0_stores["attivo"].fillna("SI").astype(str).str.upper() == "SI"].copy()
    elif "is_active" in b0_stores.columns:
        b0_stores = b0_stores[b0_stores["is_active"] == True].copy()
    b0_flows = []

    for _, r in b0_stores.iterrows():
        sid = str(r["store_code"]).strip()
        giro = str(r["giro"]).strip()
        if _is_unassigned_giro(giro) or _is_unassigned_giro(sid):
            continue
        cod_sga = map_codsga.get(sid, None)
        if pd.isna(cod_sga) or cod_sga is None:
            # Fallback
            cod_sga = int(sid) if sid.isdigit() else 0
        else:
            cod_sga = int(cod_sga)

        mc = float(r["mc"])
        colli = float(r["textile_attesi"] + r["other_attesi"] + r["shoes_attesi"] + r["ecom_attesi"])
        peso = colli * PESO_SPECIFICO_COLLO_KG

        if colli > 0:
            # ANDATA
            b0_flows.append({
                "GIRO": giro,
                "DATA_CARICO": dt_b0,
                "COD_MITTENTE": COD_MITTENTE_DEFAULT,
                "MAGAZZINO_CARICO": MAGAZZINO_CARICO_DEFAULT,
                "DATA_SCARICO": dt_b0,
                "COD_DESTINATARIO": cod_sga,
                "MAGAZZINO_SCARICO": giro,
                "PESO": peso,
                "VOLUME": mc,
                "COLLI": colli,
                "store_code": sid,
                "barra": 0,
                "flusso_tipo": "ANDATA"
            })
            # RITORNO
            b0_flows.append({
                "GIRO": giro,
                "DATA_CARICO": dt_b0,
                "COD_MITTENTE": cod_sga,
                "MAGAZZINO_CARICO": giro,
                "DATA_SCARICO": dt_b0,
                "COD_DESTINATARIO": COD_MITTENTE_DEFAULT,
                "MAGAZZINO_SCARICO": MAGAZZINO_CARICO_DEFAULT,
                "PESO": 0.0,
                "VOLUME": 0.0,
                "COLLI": 0.0,
                "store_code": sid,
                "barra": 0,
                "flusso_tipo": "RITORNO"
            })

    # 2. Barra 9 Flows
    b9_stores = df_spunta[(df_spunta["is_store"]) & (df_spunta["is_barra9"] == 1)].copy()
    if "attivo" in b9_stores.columns:
        b9_stores = b9_stores[b9_stores["attivo"].fillna("SI").astype(str).str.upper() == "SI"].copy()
    elif "is_active" in b9_stores.columns:
        b9_stores = b9_stores[b9_stores["is_active"] == True].copy()
    b9_flows = []

    for _, r in b9_stores.iterrows():
        sid = str(r["store_code"]).strip()
        giro = str(r["giro"]).strip()
        if _is_unassigned_giro(giro) or _is_unassigned_giro(sid):
            continue
        cod_sga = map_codsga.get(sid, None)
        if pd.isna(cod_sga) or cod_sga is None:
            base_sid = sid[:-1] if sid.endswith("B") else sid
            cod_sga = map_codsga.get(base_sid, 0)
        cod_sga = int(cod_sga) if cod_sga else 0

        mc = float(r["mc"])
        colli = mc / VOLUME_DIVISORE_COLLI_BARRA9 if mc > 0 else 0.0
        peso = colli * PESO_SPECIFICO_COLLO_KG

        if colli > 0:
            # ANDATA
            b9_flows.append({
                "GIRO": giro,
                "DATA_CARICO": dt_b9,
                "COD_MITTENTE": COD_MITTENTE_DEFAULT,
                "MAGAZZINO_CARICO": MAGAZZINO_CARICO_DEFAULT,
                "DATA_SCARICO": dt_b9,
                "COD_DESTINATARIO": cod_sga,
                "MAGAZZINO_SCARICO": giro,
                "PESO": peso,
                "VOLUME": mc,
                "COLLI": colli,
                "store_code": sid,
                "barra": 9,
                "flusso_tipo": "ANDATA"
            })
            # RITORNO
            b9_flows.append({
                "GIRO": giro,
                "DATA_CARICO": dt_b9,
                "COD_MITTENTE": cod_sga,
                "MAGAZZINO_CARICO": giro,
                "DATA_SCARICO": dt_b9,
                "COD_DESTINATARIO": COD_MITTENTE_DEFAULT,
                "MAGAZZINO_SCARICO": MAGAZZINO_CARICO_DEFAULT,
                "PESO": 0.0,
                "VOLUME": 0.0,
                "COLLI": 0.0,
                "store_code": sid,
                "barra": 9,
                "flusso_tipo": "RITORNO"
            })

    return pd.DataFrame(b0_flows), pd.DataFrame(b9_flows)


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if pd.isna(val) or val is None or str(val).strip() == "":
            return default
        return float(val)
    except:
        return default


def compute_planning_roma(
    df_analisi: pd.DataFrame,
    df_actuals: pd.DataFrame,
    template_path: Optional[Path] = None,
    df_stores: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Fills the Planning Roma table comparing Planned vs Received across all categories.
    Handles df_analisi indexed by either 'store_id' or 'store_code' gracefully.
    Avoids double-counting shoes on Zara stores with dedicated SHOES rows and
    properly segments STD vs DOPPIA (/9) actuals.
    """
    if template_path is None:
        template_path = DATA_DIR / "planner_template.json"

    with open(template_path, "r", encoding="utf-8") as f:
        tpl_rows = json.load(f)

    # Stores that have dedicated SHOES rows in the planner template
    stores_with_shoes_row = {
        str(r["store_code"]).strip()
        for r in tpl_rows
        if "SHOES" in str(r.get("brand", "")).upper()
    }

    # Stores that have a Barra 9 row in the planner template
    tpl_b9_stores = {
        str(r["store_code"])[:-1].strip()
        for r in tpl_rows
        if str(r.get("store_code", "")).endswith("B")
    }

    # Dynamic sdoppiamento status from df_stores or database
    map_sdoppia = {}
    if df_stores is not None and not df_stores.empty:
        sid_col = "store_id" if "store_id" in df_stores.columns else ("store_code" if "store_code" in df_stores.columns else None)
        if sid_col and "sdoppiamento_b9" in df_stores.columns:
            map_sdoppia = df_stores.set_index(sid_col)["sdoppiamento_b9"].fillna("NO").astype(str).str.upper().to_dict()
    else:
        try:
            from src.db import get_stores_df
            sdf = get_stores_df()
            if not sdf.empty:
                map_sdoppia = sdf.set_index("store_id")["sdoppiamento_b9"].fillna("NO").astype(str).str.upper().to_dict()
        except:
            pass

    # Rows 47 (3680 Zara secondary), 51 (9226 Zara secondary), 56 (3591 Zara secondary)
    # in Inditex template are reserved empty placeholder rows that must not duplicate store numbers
    placeholder_row_indices = {47, 51, 56}

    # Build planned map flexibly (handles store_id, store_code, id_store)
    # Also indexes by (base_sid, is_shoes) to support DataFrames having separate brand rows (like planning_results)
    map_a = {}
    map_a_brand = {}
    if df_analisi is not None and not df_analisi.empty:
        sid_col = None
        for cand in ["store_id", "store_code", "id_store", "ID_STORE"]:
            if cand in df_analisi.columns:
                sid_col = cand
                break
        if sid_col is not None:
            has_brand = "brand" in df_analisi.columns
            for _, r in df_analisi.iterrows():
                sid_raw = str(r[sid_col]).strip()
                base_sid = sid_raw[:-1] if sid_raw.endswith("B") else sid_raw
                r_dict = r.to_dict()

                if has_brand:
                    is_sho = "SHOES" in str(r.get("brand", "")).upper()
                    if (base_sid, is_sho) not in map_a_brand:
                        map_a_brand[(base_sid, is_sho)] = r_dict
                    if (sid_raw, is_sho) not in map_a_brand:
                        map_a_brand[(sid_raw, is_sho)] = r_dict

                if base_sid not in map_a:
                    map_a[base_sid] = r_dict.copy()
                else:
                    # Update fields non-destructively so textile or shoes aren't overwritten with 0
                    for num_col in ["planned_textile", "vol_textile", "weight_textile",
                                    "planned_shoes", "vol_shoes", "weight_shoes",
                                    "planned_others", "planned_ecom", "vol_ecom", "weight_ecom",
                                    "total_vol", "total_weight", "total_planned_crts"]:
                        if _safe_float(r_dict.get(num_col, 0)) > 0 and _safe_float(map_a[base_sid].get(num_col, 0)) == 0:
                            map_a[base_sid][num_col] = r_dict[num_col]

    # Build actuals map: segmented into STD, DOPPIA, and TOT
    map_act_std = {}
    map_act_doppia = {}
    map_act_tot = {}
    if df_actuals is not None and not df_actuals.empty:
        act_col = None
        for cand in ["ID_STORE", "id_store", "store_id", "store_code"]:
            if cand in df_actuals.columns:
                act_col = cand
                break
        if act_col is not None:
            has_tipo_cons = "tipo_cons" in df_actuals.columns
            if has_tipo_cons:
                for (sid, tcons), grp in df_actuals.groupby([act_col, df_actuals["tipo_cons"].fillna("STD").astype(str).str.upper()]):
                    sid_str = str(sid).strip()
                    base_sid = sid_str[:-1] if sid_str.endswith("B") else sid_str
                    c_abb = _safe_float(grp["TOT_ABBIGL"].sum()) if "TOT_ABBIGL" in grp.columns else (_safe_float(grp["colli_abbigl"].sum()) if "colli_abbigl" in grp.columns else 0.0)
                    c_calz = _safe_float(grp["TOT_CALZAT"].sum()) if "TOT_CALZAT" in grp.columns else (_safe_float(grp["colli_calzat"].sum()) if "colli_calzat" in grp.columns else 0.0)
                    c_eco = _safe_float(grp["TOT_ECOM"].sum()) if "TOT_ECOM" in grp.columns else (_safe_float(grp["colli_ecom"].sum()) if "colli_ecom" in grp.columns else 0.0)
                    c_oth = _safe_float(grp["TOT_OTHERS"].sum()) if "TOT_OTHERS" in grp.columns else (_safe_float(grp["colli_others"].sum()) if "colli_others" in grp.columns else 0.0)
                    str_list = [str(s) for s in grp["stringa"].dropna() if str(s).strip()] if "stringa" in grp.columns else []
                    d_info = {
                        "tot_abbigl": c_abb,
                        "tot_calzat": c_calz,
                        "tot_ecom": c_eco,
                        "tot_others": c_oth,
                        "stringa": " ".join(str_list)
                    }
                    if tcons == "DOPPIA":
                        map_act_doppia[base_sid] = d_info
                    else:
                        map_act_std[base_sid] = d_info

            for sid, grp in df_actuals.groupby(act_col):
                sid_str = str(sid).strip()
                base_sid = sid_str[:-1] if sid_str.endswith("B") else sid_str
                c_abb = _safe_float(grp["TOT_ABBIGL"].sum()) if "TOT_ABBIGL" in grp.columns else (_safe_float(grp["colli_abbigl"].sum()) if "colli_abbigl" in grp.columns else 0.0)
                c_calz = _safe_float(grp["TOT_CALZAT"].sum()) if "TOT_CALZAT" in grp.columns else (_safe_float(grp["colli_calzat"].sum()) if "colli_calzat" in grp.columns else 0.0)
                c_eco = _safe_float(grp["TOT_ECOM"].sum()) if "TOT_ECOM" in grp.columns else (_safe_float(grp["colli_ecom"].sum()) if "colli_ecom" in grp.columns else 0.0)
                c_oth = _safe_float(grp["TOT_OTHERS"].sum()) if "TOT_OTHERS" in grp.columns else (_safe_float(grp["colli_others"].sum()) if "colli_others" in grp.columns else 0.0)
                str_list = [str(s) for s in grp["stringa"].dropna() if str(s).strip()] if "stringa" in grp.columns else []
                map_act_tot[base_sid] = {
                    "tot_abbigl": c_abb,
                    "tot_calzat": c_calz,
                    "tot_ecom": c_eco,
                    "tot_others": c_oth,
                    "stringa": " ".join(str_list)
                }

            if not has_tipo_cons:
                map_act_std = map_act_tot

    records = []
    for row in tpl_rows:
        ridx = row["row_idx"]
        route_id = row["route_id"]
        store_code = row["store_code"]
        brand_raw = row["brand"]
        store_name = row["store_name"]
        delivery_day = row["delivery_day"]

        # Base store lookup
        base_sid = store_code[:-1] if store_code.endswith("B") else store_code
        is_shoes_row = "SHOES" in brand_raw.upper()
        is_home_app_row = "HOME APP" in brand_raw.upper()
        is_b9_row = store_code.endswith("B")
        is_placeholder = ridx in placeholder_row_indices

        # Lookup in map_a_brand first if present, otherwise fallback to store-level map_a
        lookup_sid = store_code if is_b9_row else base_sid
        a_data = map_a_brand.get((lookup_sid, is_shoes_row))
        if not a_data and is_b9_row:
            a_data = map_a_brand.get((base_sid, is_shoes_row))
        if not a_data:
            a_data = map_a.get(lookup_sid, map_a.get(base_sid, {}))

        # Initialize quantities
        pl_text = 0.0
        rec_text = 0.0
        pl_oth = 0.0
        rec_oth = 0.0
        vol_text = 0.0
        wt_text = 0.0

        pl_sho = 0.0
        rec_sho = 0.0
        vol_sho = 0.0
        wt_sho = 0.0

        pl_eco = 0.0
        rec_eco = 0.0
        vol_eco = 0.0
        wt_eco = 0.0

        intershops = map_act_tot.get(base_sid, {}).get("stringa", "")

        if is_placeholder:
            # Secondary reserved lines in template (empty by default)
            pass

        elif is_shoes_row:
            # Dedicated shoes row (e.g. ZARA SHOES)
            pl_sho = int(round(_safe_float(a_data.get("planned_shoes", 0.0))))
            act_s = map_act_std.get(base_sid, {}) if base_sid in tpl_b9_stores else map_act_tot.get(base_sid, {})
            rec_sho = int(round(_safe_float(act_s.get("tot_calzat", 0.0))))
            vol_sho = round(_safe_float(a_data.get("vol_shoes", 0.0)), 2)
            wt_sho = int(round(_safe_float(a_data.get("weight_shoes", 0.0))))

        elif is_home_app_row:
            # Zara Home Appesi (special display row)
            pass

        elif is_b9_row:
            # Barra 9 row (e.g. 5349B, 6525B, 3680B, 3503B)
            is_sdop = map_sdoppia.get(base_sid, "SI" if base_sid in tpl_b9_stores else "NO") == "SI"
            if is_sdop:
                already_split = str(a_data.get("store_code", "")).endswith("B")
                b9_mult = 1.0 if already_split else PERCENTUALE_BARRA9_SPLIT

                pl_text = int(round(_safe_float(a_data.get("planned_textile", 0.0)) * b9_mult))
                if base_sid not in stores_with_shoes_row:
                    pl_sho = int(round(_safe_float(a_data.get("planned_shoes", 0.0)) * b9_mult))
                pl_oth = int(round(_safe_float(a_data.get("planned_others", 0.0)) * b9_mult))
                if pl_oth == 0:
                    pl_oth = int(round(_safe_float(map_a.get(base_sid, {}).get("planned_others", 0.0)) * PERCENTUALE_BARRA9_SPLIT))
                pl_eco = int(round(_safe_float(a_data.get("planned_ecom", 0.0)) * b9_mult))
                if pl_eco == 0:
                    pl_eco = int(round(_safe_float(map_a.get(base_sid, {}).get("planned_ecom", 0.0)) * PERCENTUALE_BARRA9_SPLIT))

                act_d = map_act_doppia.get(base_sid, {})
                rec_text = int(round(_safe_float(act_d.get("tot_abbigl", 0.0))))
                if base_sid not in stores_with_shoes_row:
                    rec_sho = int(round(_safe_float(act_d.get("tot_calzat", 0.0))))
                rec_oth = int(round(_safe_float(act_d.get("tot_others", 0.0))))
                rec_eco = int(round(_safe_float(act_d.get("tot_ecom", 0.0))))
            else:
                pl_text = 0
                pl_sho = 0
                pl_oth = 0
                pl_eco = 0
                rec_text = 0
                rec_sho = 0
                rec_oth = 0
                rec_eco = 0

        else:
            # Standard store row
            is_sdop = map_sdoppia.get(base_sid, "SI" if base_sid in tpl_b9_stores else "NO") == "SI"
            # If store has active sdoppiamento and is in tpl_b9_stores or has a DOPPIA delivery
            if is_sdop and (base_sid in tpl_b9_stores or base_sid in map_act_doppia):
                act_row = map_act_std.get(base_sid, {})
                tot_t = int(round(_safe_float(a_data.get("planned_textile", 0.0))))
                tot_o = int(round(_safe_float(a_data.get("planned_others", 0.0))))
                tot_e = int(round(_safe_float(a_data.get("planned_ecom", 0.0))))
                pl_text = tot_t - int(round(tot_t * PERCENTUALE_BARRA9_SPLIT))
                pl_oth = tot_o - int(round(tot_o * PERCENTUALE_BARRA9_SPLIT))
                pl_eco = tot_e - int(round(tot_e * PERCENTUALE_BARRA9_SPLIT))
            else:
                act_row = map_act_tot.get(base_sid, {})
                pl_text = int(round(_safe_float(a_data.get("planned_textile", 0.0))))
                pl_oth = int(round(_safe_float(a_data.get("planned_others", 0.0))))
                pl_eco = int(round(_safe_float(a_data.get("planned_ecom", 0.0))))

            rec_text = int(round(_safe_float(act_row.get("tot_abbigl", 0.0))))
            rec_oth = int(round(_safe_float(act_row.get("tot_others", 0.0))))
            rec_eco = int(round(_safe_float(act_row.get("tot_ecom", 0.0))))

            vol_text = round(_safe_float(a_data.get("vol_textile", 0.0)), 2)
            wt_text = int(round(_safe_float(a_data.get("weight_textile", 0.0))))
            vol_eco = round(_safe_float(a_data.get("vol_ecom", 0.0)), 2)
            wt_eco = int(round(_safe_float(a_data.get("weight_ecom", 0.0))))

            # Shoes handling: only if store does NOT have a dedicated SHOES row
            if base_sid in stores_with_shoes_row:
                pl_sho = 0
                rec_sho = 0
                vol_sho = 0.0
                wt_sho = 0
            else:
                tot_s = int(round(_safe_float(a_data.get("planned_shoes", 0.0))))
                if is_sdop and (base_sid in tpl_b9_stores or base_sid in map_act_doppia):
                    pl_sho = tot_s - int(round(tot_s * PERCENTUALE_BARRA9_SPLIT))
                else:
                    pl_sho = tot_s
                rec_sho = int(round(_safe_float(act_row.get("tot_calzat", 0.0))))
                vol_sho = round(_safe_float(a_data.get("vol_shoes", 0.0)), 2)
                wt_sho = int(round(_safe_float(a_data.get("weight_shoes", 0.0))))

        tot_vol = round(vol_text + vol_sho + vol_eco, 2)
        tot_wt = int(round(wt_text + wt_sho + wt_eco))
        tot_pl_crts = int(round(pl_text + pl_oth + pl_sho + pl_eco))
        tot_rec_crts = int(round(rec_text + rec_oth + rec_sho + rec_eco))

        records.append({
            "row_idx": ridx,
            "route_id": route_id,
            "store_code": store_code,
            "brand": brand_raw,
            "store_name": store_name,
            "delivery_day": delivery_day,
            "planned_textile": pl_text,
            "received_textile": rec_text,
            "planned_others": pl_oth,
            "received_others": rec_oth,
            "vol_textile": vol_text,
            "weight_textile": wt_text,
            "planned_shoes": pl_sho,
            "received_shoes": rec_sho,
            "vol_shoes": vol_sho,
            "weight_shoes": wt_sho,
            "planned_ecom": pl_eco,
            "received_ecom": rec_eco,
            "vol_ecom": vol_eco,
            "weight_ecom": wt_eco,
            "total_vol": tot_vol,
            "total_weight": tot_wt,
            "total_planned_crts": tot_pl_crts,
            "total_received_crts": tot_rec_crts,
            "intershops": intershops
        })

    # For any store that had DOPPIA actuals but wasn't in template as a B row, append it cleanly
    existing_b_codes = {str(r["store_code"]).strip() for r in records}
    max_idx = max((int(r["row_idx"]) for r in records), default=75)
    for b_sid, d_info in map_act_doppia.items():
        b_code = f"{b_sid}B"
        if b_code not in existing_b_codes:
            max_idx += 1
            meta = {}
            if df_stores is not None and not df_stores.empty:
                sid_col = "store_id" if "store_id" in df_stores.columns else "store_code"
                m_sub = df_stores[df_stores[sid_col].astype(str).str.strip() == b_sid]
                if not m_sub.empty:
                    meta = m_sub.iloc[0].to_dict()
            pv_name = meta.get("brand") or meta.get("punto_vendita") or "INDITEX"
            st_name = (meta.get("store_name") or b_sid) + " APT9"
            rec_t = int(round(_safe_float(d_info.get("tot_abbigl", 0.0))))
            rec_s = int(round(_safe_float(d_info.get("tot_calzat", 0.0))))
            rec_e = int(round(_safe_float(d_info.get("tot_ecom", 0.0))))
            rec_o = int(round(_safe_float(d_info.get("tot_others", 0.0))))
            tot_rec = int(rec_t + rec_s + rec_e + rec_o)

            # Planned 30% from base store forecast
            a_d = map_a.get(b_sid, {})
            pl_t = int(round(_safe_float(a_d.get("planned_textile", 0.0)) * PERCENTUALE_BARRA9_SPLIT))
            pl_s = int(round(_safe_float(a_d.get("planned_shoes", 0.0)) * PERCENTUALE_BARRA9_SPLIT))
            pl_e = int(round(_safe_float(a_d.get("planned_ecom", 0.0)) * PERCENTUALE_BARRA9_SPLIT))
            pl_o = int(round(_safe_float(a_d.get("planned_others", 0.0)) * PERCENTUALE_BARRA9_SPLIT))
            tot_pl = int(pl_t + pl_s + pl_e + pl_o)

            records.append({
                "row_idx": max_idx,
                "route_id": 1,
                "store_code": b_code,
                "brand": pv_name,
                "store_name": st_name,
                "delivery_day": "MERCOLEDI / GIOVEDI",
                "planned_textile": pl_t,
                "received_textile": rec_t,
                "planned_others": pl_o,
                "received_others": rec_o,
                "vol_textile": 0.0,
                "weight_textile": 0,
                "planned_shoes": pl_s,
                "received_shoes": rec_s,
                "vol_shoes": 0.0,
                "weight_shoes": 0,
                "planned_ecom": pl_e,
                "received_ecom": rec_e,
                "vol_ecom": 0.0,
                "weight_ecom": 0,
                "total_vol": 0.0,
                "total_weight": 0,
                "total_planned_crts": tot_pl,
                "total_received_crts": tot_rec,
                "intershops": d_info.get("stringa", "")
            })

    return pd.DataFrame(records)


def compute_special_breakdowns(
    df_spunta: pd.DataFrame,
    df_total: pd.DataFrame,
    df_shoes: pd.DataFrame,
    df_texile: Optional[pd.DataFrame] = None,
    df_ecom: Optional[pd.DataFrame] = None,
    perfume_corrections_override: Optional[Dict[str, float]] = None,
    df_stores: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Computes special operational breakdowns:
    - Perfume corrections & Stesi/Appesi for textile stores (currently 3680, 9226, 3591)
    - Stander and bancali calculations
    - Zara Home 50/50 split for home stores (currently 1984 and 1971)
    - Check totals for theoretical vs actual spunta
    """
    map_tot = df_total.set_index("store_id").to_dict(orient="index") if not df_total.empty else {}
    map_sho = df_shoes.set_index("store_id").to_dict(orient="index") if not df_shoes.empty else {}

    # Default perfume corrections (subtracted from stesi)
    perfume_corrections = {
        "3680": 1085.0,
        "9226": 1791.0,
        "3591": 1030.0
    }

    store_names = {
        "3680": "C.C. Porta di Roma",
        "9226": "Via del Corso (P.zza Bocconi)",
        "3591": "C.C. Euroma2"
    }
    zh_names = {
        "1984": "ROMA COLA DI RIENZO",
        "1971": "ROMA PORTA DI ROMA"
    }

    tessile_ids = []
    home_ids = []
    if df_stores is not None and not df_stores.empty:
        if "lavorazione" in df_stores.columns:
            tessile_ids = [
                str(s).strip() for s in df_stores[df_stores["lavorazione"] == "SI TESSILE"]["store_id"].dropna()
                if not str(s).strip().endswith("B")
            ]
            home_ids = [
                str(s).strip() for s in df_stores[df_stores["lavorazione"] == "SI HOME"]["store_id"].dropna()
                if not str(s).strip().endswith("B")
            ]
        if "scorporo_profumi" in df_stores.columns:
            for _, s_row in df_stores.iterrows():
                sid_s = str(s_row["store_id"]).strip()
                if str(s_row.get("scorporo_profumi", "NO")).strip().upper() == "SI":
                    perfume_corrections[sid_s] = 0.0
                    if sid_s not in tessile_ids:
                        tessile_ids.append(sid_s)
                else:
                    perfume_corrections[sid_s] = 0.0
        for _, s_row in df_stores.iterrows():
            sid_s = str(s_row["store_id"]).strip()
            sname = str(s_row.get("store_name", "")).strip()
            if sname:
                store_names[sid_s] = sname
                zh_names[sid_s] = sname

    if perfume_corrections_override:
        perfume_corrections.update(perfume_corrections_override)

    if not tessile_ids:
        tessile_ids = ["3680", "9226", "3591"]
    if not home_ids:
        home_ids = ["1984", "1971"]

    if map_tot:
        tessile_ids = [s for s in tessile_ids if not str(s).endswith("B") and s in map_tot]
        home_ids = [s for s in home_ids if not str(s).endswith("B") and s in map_tot]

    special_stores = {}
    stander_rows = []

    for sid in tessile_ids:
        tot_d = map_tot.get(sid, {})
        sho_d = map_sho.get(sid, {})
        tot_colgada = float(tot_d.get("p_colgada", 0.0))
        sho_colgada = float(sho_d.get("p_colgada", 0.0))
        tot_paq = float(tot_d.get("paqueteria", 0.0))
        sho_paq = float(sho_d.get("paqueteria", 0.0))

        appesi = int(round(max(0.0, tot_colgada - sho_colgada)))
        corr = int(round(perfume_corrections.get(sid, 0.0)))
        stesi = int(round(max(0.0, tot_paq - sho_paq - corr)))
        tot_pezzi = int(appesi + stesi)

        # Stander & Bancali Stesi: store 3680 has factor 0.65 (Barra 0)
        # Other stores factor 1.0 (unless configured)
        b0_factor = 0.65 if sid == "3680" else 1.0
        label_negozio = "3680 /0" if sid == "3680" else sid

        stander = int(math.floor(appesi * b0_factor / 200.0)) if appesi > 0 else 0
        bancali_stesi = int(math.floor(stesi * b0_factor / 15.0 / 20.0)) if stesi > 0 else 0

        # Calcolo bancali per colli non-tessile (calzature / accessori / e-com)
        # Nello sviluppo banchina reale, i colli non appesi viaggiano su bancali (~18 colli/bancale)
        sp_row = None
        pedane_senza_lav = 0
        if df_spunta is not None and not df_spunta.empty and "store_code" in df_spunta.columns:
            m = df_spunta[df_spunta["store_code"].astype(str).str.strip() == sid]
            if not m.empty:
                sp_row = m.iloc[0]
                pedane_senza_lav = int(round(pd.to_numeric(sp_row.get("pedane", 0), errors="coerce") or 0))

        bancali_extra = 0
        if sp_row is not None:
            shoes_c = float(pd.to_numeric(sp_row.get("shoes_attesi", 0), errors="coerce") or 0)
            other_c = float(pd.to_numeric(sp_row.get("other_attesi", 0), errors="coerce") or 0)
            ecom_c = float(pd.to_numeric(sp_row.get("ecom_attesi", 0), errors="coerce") or 0)
            non_tex_colli = (shoes_c + other_c + ecom_c) * b0_factor
            bancali_extra = int(round(non_tex_colli / 18.0)) if non_tex_colli > 0 else 0
        elif sid in map_sho:
            sho_bultos = float(map_sho[sid].get("bultos", 0.0)) * b0_factor
            bancali_extra = int(round(sho_bultos / 18.0)) if sho_bultos > 0 else 0

        bancali_totali = bancali_stesi + bancali_extra
        # Regola di carico: 2 stender occupano lo spazio di 4 bancali "a madonna" (1 stender = 2 pedane eq.)
        stander_pedane_eq = stander * 2
        impronta_a_terra = bancali_totali + stander_pedane_eq
        sintesi = f"{bancali_totali} bancali + {stander} stender"
        s_name = store_names.get(sid, f"Store {sid}")

        special_stores[sid] = {
            "label": label_negozio,
            "store_name": s_name,
            "appesi": appesi,
            "stesi": stesi,
            "totale_pezzi": tot_pezzi,
            "correzione_profumi": corr,
            "stender": stander,
            "stander": stander,
            "bancali_stesi": bancali_stesi,
            "bancali_extra": bancali_extra,
            "bancali": bancali_totali,
            "stender_pedane_eq": stander_pedane_eq,
            "stander_pedane_eq": stander_pedane_eq,
            "impronta_a_terra": impronta_a_terra,
            "pedane_senza_lavorazione": pedane_senza_lav,
            "delta_pedane": impronta_a_terra - pedane_senza_lav if pedane_senza_lav > 0 else 0,
            "sintesi": sintesi
        }

        stander_rows.append({
            "Negozio": label_negozio,
            "Punto Vendita": s_name,
            "Totale Pezzi": tot_pezzi,
            "Appesi": appesi,
            "Stesi (Netto)": stesi,
            "Correzione Profumi": corr,
            "Stender": stander,
            "Stander": stander,
            "Stender Eq. (PLT)": stander_pedane_eq,
            "Stander Eq. (PLT)": stander_pedane_eq,
            "Bancali Stesi": bancali_stesi,
            "Bancali Scarpe/Altri": bancali_extra,
            "Bancali (PLT)": bancali_totali,
            "Sintesi Allestimento": sintesi,
            "Impronta a Terra (PLT)": impronta_a_terra,
            "Teorico Senza Lav.": pedane_senza_lav,
        })

    df_stander = pd.DataFrame(stander_rows)

    # Zara Home 50/50 split
    zh_stores = {}
    zh_rows = []

    for sid in home_ids:
        tot_d = map_tot.get(sid, {})
        paq = int(round(float(tot_d.get("paqueteria", 0.0))))
        quota_0 = int(round(paq / 2.0))
        quota_8 = int(paq - quota_0)
        s_name = zh_names.get(sid, f"Store {sid}")
        zh_stores[sid] = {
            "store_name": s_name,
            "totale_paqueteria": paq,
            "quota_barra0": quota_0,
            "quota_barra8": quota_8
        }
        zh_rows.append({
            "Store ID": sid,
            "Punto Vendita": s_name,
            "Totale Pezzi (Paqueteria)": paq,
            "Quota Barra 0 (/0)": quota_0,
            "Quota Barra 8 (/8)": quota_8
        })

    df_zh = pd.DataFrame(zh_rows)

    # Platform Totals & Checks
    tot_pezzi_lavorati = int(sum(s["totale_pezzi"] for s in special_stores.values()) + sum(z["totale_paqueteria"] for z in zh_stores.values()))

    tot_teorici_colli = float(df_total["bultos"].sum()) if not df_total.empty else 0.0
    tot_teorici_mc = float(df_total["volumen"].sum()) if not df_total.empty else 0.0
    tot_teorici_peso = float(df_total["peso"].sum()) if not df_total.empty else 0.0

    # Sum of categories (SHOES + TEXILE + ECOM)
    sum_voci_colli = 0.0
    sum_voci_mc = 0.0
    if df_texile is not None and not df_texile.empty:
        sum_voci_colli += float(df_texile["bultos"].sum())
        sum_voci_mc += float(df_texile["volumen"].sum())
    if not df_shoes.empty:
        sum_voci_colli += float(df_shoes["bultos"].sum())
        sum_voci_mc += float(df_shoes["volumen"].sum())
    if df_ecom is not None and not df_ecom.empty:
        sum_voci_colli += float(df_ecom["bultos"].sum())
        sum_voci_mc += float(df_ecom["volumen"].sum())

    # Sum of spunta (stores only)
    spunta_stores = df_spunta[df_spunta["is_store"] == True] if "is_store" in df_spunta.columns else df_spunta
    check_colli = float(spunta_stores["textile_attesi"].sum() + spunta_stores["other_attesi"].sum() + spunta_stores["shoes_attesi"].sum() + spunta_stores["ecom_attesi"].sum()) if not spunta_stores.empty else 0.0
    check_mc = float(spunta_stores["mc"].sum()) if not spunta_stores.empty else 0.0

    return {
        "special_stores": special_stores,
        "zara_home": zh_stores,
        "stender_summary": df_stander,
        "stander_summary": df_stander,
        "zh_summary": df_zh,
        "totale_pezzi_lavorati": tot_pezzi_lavorati,
        "perfume_corrections": perfume_corrections,
        "check_totals": {
            "totali_teorici_colli": tot_teorici_colli,
            "check_colli": check_colli,
            "diff_colli": check_colli - tot_teorici_colli,
            "totali_teorici_mc": tot_teorici_mc,
            "check_mc": check_mc,
            "diff_mc": check_mc - tot_teorici_mc,
            "tot_teorici_peso": tot_teorici_peso,
            "sum_voci_colli": sum_voci_colli,
            "sum_voci_mc": sum_voci_mc,
            "diff_voci_colli": sum_voci_colli - tot_teorici_colli if sum_voci_colli > 0 else 0.0,
            "diff_voci_mc": sum_voci_mc - tot_teorici_mc if sum_voci_mc > 0 else 0.0,
        }
    }
