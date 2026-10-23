import os
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from datetime import datetime
import pandas as pd

from src.config import (
    OUTPUT_DIR,
    DEFAULT_NETWORK_OUTPUT_DIR
)
from src.db import (
    init_db,
    seed_anagrafica_if_empty,
    get_stores_df,
    create_run,
    update_run_totals,
    get_connection
)
from src.parsers import (
    parse_grupo_envio,
    parse_other_files,
    parse_esportazione
)
from src.engine import (
    compute_analisi,
    compute_spunta_arrivi,
    compute_sga_flows,
    compute_planning_roma,
    compute_special_breakdowns
)
from src.exporters import (
    export_zara_spunta,
    export_sga_file,
    export_planner_roma
)


def run_pipeline(
    total_source: Any,
    shoes_source: Any,
    texile_source: Any,
    ecom_source: Any,
    other_source: Any,
    esportazione_source: Any,
    run_date: Optional[str] = None,
    cycle_type: str = "GIOV-DOM",
    notes: str = "",
    perfume_corrections: Optional[Dict[str, float]] = None,
    save_to_network: bool = False
) -> Dict[str, Any]:
    """
    Executes the entire logistics pipeline:
    1. Initializes DB & loads store master
    2. Parses all input sources (files, paths, or text)
    3. Runs calculations (ANALISI, Spunta Arrivi, SGA Flows Barra 0/9, Planning Roma, Breakdowns)
    4. Persists complete run history into SQLite
    5. Exports output Excel files
    6. Returns all computed DataFrames, KPIs, and generated file paths
    """
    init_db()
    seed_anagrafica_if_empty()
    df_stores = get_stores_df()

    if not run_date:
        run_date = datetime.now().strftime("%Y-%m-%d")

    # 1. Parse Inputs
    df_tot = parse_grupo_envio(total_source)
    df_sho = parse_grupo_envio(shoes_source)
    df_tex = parse_grupo_envio(texile_source)
    df_eco = parse_grupo_envio(ecom_source)
    df_oth_raw, df_oth_agg = parse_other_files(other_source)
    df_esp = parse_esportazione(esportazione_source)

    # Auto-detect unknown stores in incoming files and onboard them automatically
    existing_store_ids = set(df_stores["store_id"].astype(str).str.strip().tolist()) if not df_stores.empty else set()
    existing_base_ids = {sid[:-1] if sid.endswith("B") else sid for sid in existing_store_ids}

    new_stores_alert = []
    seen_new = set()

    for df_source, cat_name in [(df_tot, "TOTAL"), (df_sho, "SHOES"), (df_tex, "TEXILE"), (df_eco, "ECOM")]:
        if not df_source.empty and "store_id" in df_source.columns:
            for _, r in df_source.iterrows():
                sid = str(r["store_id"]).strip()
                if sid and sid not in existing_base_ids and sid not in seen_new:
                    seen_new.add(sid)
                    raw_tienda = str(r.get("raw_tienda", "")).strip()
                    store_name = raw_tienda if raw_tienda else f"Store {sid}"
                    # Heuristic brand detection from raw_tienda
                    raw_upper = raw_tienda.upper()
                    if "BERSHKA" in raw_upper or "BSK" in raw_upper:
                        brand = "BERSHKA"
                    elif "PULL" in raw_upper:
                        brand = "PULL&BEAR"
                    elif "STRADIVARIUS" in raw_upper or "STR" in raw_upper:
                        brand = "STRADIVARIUS"
                    elif "OYSHO" in raw_upper:
                        brand = "OYSHO"
                    elif "DUTTI" in raw_upper or "MD" in raw_upper:
                        brand = "MASSIMO DUTTI"
                    elif "HOME" in raw_upper:
                        brand = "ZARA HOME"
                    else:
                        brand = "ZARA"

                    new_record = {
                        "store_id": sid,
                        "store_name": store_name,
                        "punto_vendita": brand,
                        "brand": brand,
                        "giro": "DA ASSEGNARE",
                        "cod_sga": int(sid) if sid.isdigit() else None,
                        "cc": "FUORI POLO / DA ASSEGNARE",
                        "attivo": "SI",
                        "barra": "BARRA 0",
                        "stender": "NO",
                        "formula": "MC/1,9",
                        "lavorazione": "NO",
                        "sdoppiamento_b9": "NO"
                    }
                    from src.db import add_store_record
                    add_store_record(new_record)
                    new_stores_alert.append({
                        "store_id": sid,
                        "store_name": store_name,
                        "brand": brand,
                        "giro": "DA ASSEGNARE",
                        "file_source": cat_name,
                        "bultos": float(r.get("bultos", 0.0)),
                        "volumen": float(r.get("volumen", 0.0))
                    })

    if new_stores_alert:
        # Refresh df_stores so all calculations include the new store
        df_stores = get_stores_df()

    # 2. Compute Core Engine
    df_analisi = compute_analisi(df_stores, df_tot, df_sho, df_tex, df_eco, df_oth_agg)
    df_spunta = compute_spunta_arrivi(df_analisi, df_stores=df_stores)
    df_sga0, df_sga9 = compute_sga_flows(df_spunta, df_stores, run_date)
    df_planner = compute_planning_roma(df_analisi, df_esp, df_stores=df_stores)
    special_breakdowns = compute_special_breakdowns(
        df_spunta=df_spunta,
        df_total=df_tot,
        df_shoes=df_sho,
        df_texile=df_tex,
        df_ecom=df_eco,
        perfume_corrections_override=perfume_corrections,
        df_stores=df_stores
    )

    # 3. Compute Totals
    tot_bultos = float(df_tot["bultos"].sum()) if not df_tot.empty else float(df_tex["bultos"].sum() + df_sho["bultos"].sum() + df_eco["bultos"].sum())
    tot_vol = float(df_tot["volumen"].sum()) if not df_tot.empty else float(df_analisi["total_vol"].sum())
    tot_peso = float(df_tot["peso"].sum()) if not df_tot.empty else float(df_analisi["total_weight"].sum())
    tot_pedane = int(df_spunta[df_spunta["is_store"]]["pedane"].sum())

    # 4. Save to Database (Complete Historicity)
    run_id = create_run(run_date=run_date, cycle_type=cycle_type, notes=notes)
    update_run_totals(run_id, tot_bultos, tot_vol, tot_peso, tot_pedane)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Save Raw Forecast Items
        for cat, df_cat in [("TOTAL", df_tot), ("SHOES", df_sho), ("TEXILE", df_tex), ("ECOM", df_eco)]:
            if not df_cat.empty:
                for _, r in df_cat.iterrows():
                    cursor.execute("""
                    INSERT INTO forecast_raw (run_id, file_category, store_code, raw_tienda, p_colgada, paqueteria, peso, volumen, bultos)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (run_id, cat, str(r["store_id"]), str(r.get("raw_tienda", "")), float(r["p_colgada"]), float(r["paqueteria"]), float(r["peso"]), float(r["volumen"]), float(r["bultos"])))

        # Save Other Items
        if not df_oth_raw.empty:
            for _, r in df_oth_raw.iterrows():
                cursor.execute("""
                INSERT INTO other_items (run_id, file_name, raw_tienda, store_code, confirm, bultos, otros_bultos_enviado)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (run_id, str(r.get("file_name", "")), str(r.get("raw_tienda", "")), str(r["store_code"]), str(r.get("confirm", "")), float(r.get("bultos", 0)), float(r.get("otros_bultos_enviado", 0))))

        # Save Actual Deliveries
        if not df_esp.empty:
            for _, r in df_esp.iterrows():
                cursor.execute("""
                INSERT INTO actual_deliveries (run_id, store_code, tipo_cons, tot_abbigl, tot_calzat, tot_ecom, tot_others, tot_vario, tot_cont, colli_mat_vario, stringa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (run_id, str(r["ID_STORE"]), str(r["TIPO_CONS"]), float(r["TOT_ABBIGL"]), float(r["TOT_CALZAT"]), float(r["TOT_ECOM"]), float(r["TOT_OTHERS"]), float(r["TOT_VARIO"]), float(r["TOT_CONT"]), float(r["colli_mat_vario"]), str(r["stringa"])))

        # Save Planning Results
        for _, r in df_planner.iterrows():
            cursor.execute("""
            INSERT INTO planning_results (run_id, store_code, brand, store_name, giro, planned_textile, received_textile, planned_others, received_others, vol_textile, weight_textile, planned_shoes, received_shoes, vol_shoes, weight_shoes, planned_ecom, received_ecom, vol_ecom, weight_ecom, total_vol, total_weight, total_planned_crts, total_received_crts, intershops)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, str(r["store_code"]), str(r["brand"]), str(r["store_name"]), str(r.get("route_id", "")), float(r["planned_textile"]), float(r["received_textile"]), float(r["planned_others"]), float(r["received_others"]), float(r["vol_textile"]), float(r["weight_textile"]), float(r["planned_shoes"]), float(r["received_shoes"]), float(r["vol_shoes"]), float(r["weight_shoes"]), float(r["planned_ecom"]), float(r["received_ecom"]), float(r["vol_ecom"]), float(r["weight_ecom"]), float(r["total_vol"]), float(r["total_weight"]), float(r["total_planned_crts"]), float(r["total_received_crts"]), str(r.get("intershops", ""))))

        # Save Spunta Arrivi
        for _, r in df_spunta.iterrows():
            cursor.execute("""
            INSERT INTO spunta_arrivi (run_id, row_idx, store_code, store_name, punto_vendita, brand, mc, textile_attesi, other_attesi, shoes_attesi, ecom_attesi, pedane, totale_pedane, vettore_autista, tipo_mezzo, targa, cod_mezzo, supporto, giro, is_barra9)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, int(r["row_idx"]), str(r["store_code"]), str(r["store_name"]), str(r["punto_vendita"]), str(r["brand"]), float(r["mc"]), float(r["textile_attesi"]), float(r["other_attesi"]), float(r["shoes_attesi"]), float(r["ecom_attesi"]), int(r["pedane"]), float(r["totale_pedane"]), str(r["vettore_autista"]), str(r["tipo_mezzo"]), str(r["targa"]), str(r["cod_mezzo"]), str(r["supporto"]), str(r["giro"]), int(r["is_barra9"])))

        # Save SGA Flows
        for _, r in pd.concat([df_sga0, df_sga9], ignore_index=True).iterrows():
            cursor.execute("""
            INSERT INTO sga_flows (run_id, barra, flusso_tipo, giro, data_carico, cod_mittente, magazzino_carico, data_scarico, cod_destinatario, magazzino_scarico, peso, volume, colli, store_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, int(r["barra"]), str(r["flusso_tipo"]), str(r["GIRO"]), str(r["DATA_CARICO"]), int(r["COD_MITTENTE"]), str(r["MAGAZZINO_CARICO"]), str(r["DATA_SCARICO"]), int(r["COD_DESTINATARIO"]), str(r["MAGAZZINO_SCARICO"]), float(r["PESO"]), float(r["VOLUME"]), float(r["COLLI"]), str(r["store_code"])))

        conn.commit()

    from src.cloud_sync import auto_sync_tables
    auto_sync_tables(["runs", "planning_results", "spunta_arrivi", "stores"])

    # 5. Export Files
    out_dir = OUTPUT_DIR / f"run_{run_id}_{run_date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    path_zara = out_dir / "ZARA.xlsx"
    path_sga0 = out_dir / "barrazero_Sga.xlsx"
    path_sga9 = out_dir / "barranove_Sga.xlsx"
    date_formatted = datetime.strptime(run_date[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    path_planner = out_dir / f"PLANNER ROMA _{date_formatted}.xlsx"

    export_zara_spunta(df_spunta, path_zara, special_breakdowns=special_breakdowns)
    export_sga_file(df_sga0, path_sga0)
    export_sga_file(df_sga9, path_sga9)
    export_planner_roma(df_planner, path_planner)

    exported_files = {
        "zara": path_zara,
        "sga0": path_sga0,
        "sga9": path_sga9,
        "planner": path_planner
    }

    if save_to_network and DEFAULT_NETWORK_OUTPUT_DIR.exists():
        try:
            import shutil
            shutil.copy2(path_zara, DEFAULT_NETWORK_OUTPUT_DIR / "ZARA.xlsx")
            shutil.copy2(path_sga0, DEFAULT_NETWORK_OUTPUT_DIR / "barrazero_Sga.xlsx")
            shutil.copy2(path_sga9, DEFAULT_NETWORK_OUTPUT_DIR / "barranove_Sga.xlsx")
            shutil.copy2(path_planner, DEFAULT_NETWORK_OUTPUT_DIR / f"PLANNER ROMA _{date_formatted}.xlsx")
        except Exception as e:
            print(f"Warning: could not copy to network directory: {e}")

    return {
        "run_id": run_id,
        "run_date": run_date,
        "cycle_type": cycle_type,
        "totals": {
            "total_bultos": tot_bultos,
            "total_volume": tot_vol,
            "total_weight": tot_peso,
            "total_pedane": tot_pedane
        },
        "df_analisi": df_analisi,
        "df_spunta": df_spunta,
        "df_sga0": df_sga0,
        "df_sga9": df_sga9,
        "df_planner": df_planner,
        "special_breakdowns": special_breakdowns,
        "exported_files": exported_files,
        "new_stores_alert": new_stores_alert
    }
