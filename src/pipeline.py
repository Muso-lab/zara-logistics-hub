from pathlib import Path
from typing import Dict, Any, Optional, Union
import pandas as pd
from datetime import datetime

from src.config import (
    OUTPUT_DIR,
    DEFAULT_NETWORK_OUTPUT_DIR
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
    export_planner_roma,
    export_sintesi_operativa
)
from src.mailer import build_operativa_zip


def run_pipeline(
    total_source: Any,
    shoes_source: Any,
    texile_source: Any,
    ecom_source: Any,
    other_source: Any,
    esportazione_source: Any,
    run_date: Optional[str] = None,
    cycle_type: str = "LUN-MER",
    notes: str = "",
    save_to_network: bool = False,
    perfume_corrections_override: Optional[Dict[str, float]] = None,
    perfume_corrections: Optional[Dict[str, float]] = None,
    db_path: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Executes the entire logistics forecast and processing pipeline.
    """
    if run_date is None:
        run_date = datetime.now().strftime("%Y-%m-%d")

    if perfume_corrections_override is None and perfume_corrections is not None:
        perfume_corrections_override = perfume_corrections

    # 1. Parse Input Files
    df_tot = parse_grupo_envio(total_source)
    df_sho = parse_grupo_envio(shoes_source)
    df_tex = parse_grupo_envio(texile_source)
    df_eco = parse_grupo_envio(ecom_source)
    oth_res = parse_other_files(other_source)
    if isinstance(oth_res, tuple):
        df_oth_raw, df_oth = oth_res
    else:
        df_oth = oth_res
    df_esp = parse_esportazione(esportazione_source)

    # 2. Load Master Stores Data
    from src.db import get_stores_df
    try:
        from src.cloud_sync import auto_sync_tables
    except ImportError:
        def auto_sync_tables(*args, **kwargs): pass

    df_stores = get_stores_df(db_path=db_path)

    # Detect any new stores present in df_tot/df_sho/df_oth but missing from df_stores
    known_store_ids = set()
    if not df_stores.empty:
        sid_col = "store_id" if "store_id" in df_stores.columns else "store_code"
        known_store_ids = set(df_stores[sid_col].dropna().astype(str).str.strip())

    found_store_ids = set()
    for df_src in [df_tot, df_sho, df_tex, df_eco]:
        if not df_src.empty and "store_id" in df_src.columns:
            found_store_ids.update(df_src["store_id"].dropna().astype(str).str.strip())
    if not df_oth.empty and "store_id" in df_oth.columns:
        found_store_ids.update(df_oth["store_id"].dropna().astype(str).str.strip())

    new_stores_alert = []
    from src.db import get_deleted_store_ids
    deleted_store_ids = get_deleted_store_ids(db_path=db_path)
    unregistered = [
        s for s in sorted(found_store_ids)
        if s and s not in known_store_ids and s not in deleted_store_ids and not s.endswith("B")
    ]
    if unregistered:
        from src.db import add_store_record
        for sid in unregistered:
            # Determine brand and name from sources if available
            s_name = f"STORE {sid}"
            s_brand = "ZARA"
            s_bultos = 0
            s_vol = 0.0

            # Inspect df_tot
            if not df_tot.empty and "store_id" in df_tot.columns:
                m_row = df_tot[df_tot["store_id"].astype(str).str.strip() == sid]
                if not m_row.empty:
                    s_bultos += float(m_row.iloc[0].get("total_bultos", 0.0) or 0.0)
                    s_vol += float(m_row.iloc[0].get("total_volumen", 0.0) or 0.0)
                    if "brand" in m_row.columns and pd.notna(m_row.iloc[0]["brand"]):
                        s_brand = str(m_row.iloc[0]["brand"]).strip()
                    if "store_name" in m_row.columns and pd.notna(m_row.iloc[0]["store_name"]):
                        s_name = str(m_row.iloc[0]["store_name"]).strip()

            add_store_record({
                "store_id": sid,
                "store_name": s_name,
                "punto_vendita": s_brand,
                "brand": s_brand,
                "giro": "DA ASSEGNARE",
                "attivo": "SI",
                "formula": "MC/1,9",
                "tipo_mezzo": "BILICO",
                "lavorazione": "NO",
                "scorporo_profumi": "NO",
                "sdoppiamento_b9": "NO",
                "note": "Inserito automaticamente da file inditex - nuovo punto vendita"
            }, db_path=db_path)

            new_stores_alert.append({
                "store_id": sid,
                "store_name": s_name,
                "brand": s_brand,
                "bultos": s_bultos,
                "volumen": s_vol
            })

        # Reload updated stores table
        df_stores = get_stores_df(db_path=db_path)

    # 3. Compute Engines
    df_analisi = compute_analisi(df_stores, df_tot, df_sho, df_tex, df_eco, df_oth)
    df_spunta = compute_spunta_arrivi(df_analisi, df_stores=df_stores)
    from src.bolle_manager import get_actuals_for_planner
    try:
        df_actuals = get_actuals_for_planner(run_date, db_path=db_path)
    except Exception:
        df_actuals = pd.DataFrame()
    df_planner = compute_planning_roma(df_analisi, df_actuals, df_stores=df_stores)
    df_sga0, df_sga9 = compute_sga_flows(df_spunta, df_stores, run_date)
    special_breakdowns = compute_special_breakdowns(
        df_spunta, df_tot, df_sho, df_texile=df_tex, df_ecom=df_eco,
        perfume_corrections_override=perfume_corrections_override,
        df_stores=df_stores
    )

    # Calculate Totals
    # Note: Non-active stores (standby) are excluded from actual transported pedane
    tot_bultos = float(df_tot["bultos"].sum()) if not df_tot.empty else (float(df_analisi["total_planned_crts"].sum()) if not df_analisi.empty else 0.0)
    tot_vol = float(df_tot["volumen"].sum()) if not df_tot.empty else (float(df_analisi["total_vol"].sum()) if not df_analisi.empty else 0.0)
    tot_peso = float(df_tot["peso"].sum()) if not df_tot.empty else (float(df_analisi["total_weight"].sum()) if not df_analisi.empty and "total_weight" in df_analisi.columns else 0.0)
    active_spunta = df_spunta[df_spunta["is_store"] == True] if not df_spunta.empty else pd.DataFrame()
    tot_pedane = float(active_spunta["pedane"].sum()) if not active_spunta.empty else 0.0

    # 4. Save to Database
    from src.db import get_connection
    conn = get_connection(db_path=db_path)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO runs (run_date, cycle_type, total_bultos, total_volume, total_weight, total_pedane, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (run_date, cycle_type, tot_bultos, tot_vol, tot_peso, tot_pedane, notes))
    run_id = cursor.lastrowid

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

    # Insert SGA Flows
    for _, r in pd.concat([df_sga0, df_sga9], ignore_index=True).iterrows():
        cursor.execute("""
        INSERT INTO sga_flows (run_id, barra, flusso_tipo, giro, data_carico, cod_mittente, magazzino_carico, data_scarico, cod_destinatario, magazzino_scarico, peso, volume, colli, store_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id, int(r["barra"]), str(r["flusso_tipo"]), str(r["GIRO"]),
            str(r["DATA_CARICO"]), int(r["COD_MITTENTE"]), str(r["MAGAZZINO_CARICO"]),
            str(r["DATA_SCARICO"]), int(r["COD_DESTINATARIO"]), str(r["MAGAZZINO_SCARICO"]),
            float(r["PESO"]), float(r["VOLUME"]), float(r["COLLI"]), str(r["store_code"])
        ))

    # Save raw forecast items for reloading
    for cat_name, df_src in [("TOTAL", df_tot), ("SHOES", df_sho), ("TEXILE", df_tex), ("ECOM", df_eco)]:
        if df_src is not None and not df_src.empty:
            for _, r in df_src.iterrows():
                cursor.execute("""
                INSERT INTO forecast_raw (run_id, file_category, store_code, raw_tienda, p_colgada, paqueteria, peso, volumen, bultos)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, cat_name, str(r.get("store_id", "")), str(r.get("tienda", "")),
                    float(r.get("p_colgada", 0.0) or 0.0), float(r.get("paqueteria", 0.0) or 0.0),
                    float(r.get("peso", 0.0) or 0.0), float(r.get("volumen", 0.0) or 0.0),
                    float(r.get("bultos", 0.0) or 0.0)
                ))

    # Save other shipments items
    if 'df_oth_raw' in locals() and df_oth_raw is not None and not df_oth_raw.empty:
        for _, r in df_oth_raw.iterrows():
            cursor.execute("""
            INSERT INTO other_items (run_id, file_name, raw_tienda, store_code, confirm, bultos, otros_bultos_enviado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id, str(r.get("file_name", "")), str(r.get("raw_tienda", "")),
                str(r.get("store_code", "")), str(r.get("confirm", "")),
                float(r.get("bultos", 0.0) or 0.0), float(r.get("otros_bultos_enviado", 0.0) or 0.0)
            ))

    conn.commit()
    conn.close()

    # Sync immediately to Google Sheets to persist across container restarts
    try:
        from src.cloud_sync import push_tables_to_cloud
        push_tables_to_cloud(["runs", "planning_results", "spunta_arrivi", "stores", "sga_flows", "forecast_raw"], timeout=20)
    except Exception as e:
        print(f"Warning: Cloud sync skipped or failed: {e}")

    # Auto-generate delivery bolle (/0 and /9) pre-filled with forecast quantities
    try:
        from src.bolle_manager import generate_bolle_from_forecast
        c_b_cnt, s_b_cnt = generate_bolle_from_forecast(run_id, overwrite=False)
        print(f"Auto-generated {c_b_cnt} bolle for run {run_id} ({s_b_cnt} existing)")
    except Exception as e:
        print(f"Warning: Auto bolle generation skipped: {e}")

    # 5. Export Files
    out_dir = OUTPUT_DIR / f"run_{run_id}_{run_date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    path_sintesi = out_dir / "Sintesi_Operativa.xlsx"
    path_zara = out_dir / "ZARA.xlsx"
    path_sga0 = out_dir / "barrazero_Sga.xlsx"
    path_sga9 = out_dir / "barranove_Sga.xlsx"
    date_formatted = datetime.strptime(run_date[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    path_planner = out_dir / f"PLANNER ROMA _{date_formatted}.xlsx"

    export_sintesi_operativa(df_spunta, special_breakdowns, df_stores, path_sintesi, run_date=run_date)
    export_zara_spunta(df_spunta, path_zara, special_breakdowns=special_breakdowns)
    export_sga_file(df_sga0, path_sga0)
    export_sga_file(df_sga9, path_sga9)
    export_planner_roma(df_planner, path_planner)

    path_zip = out_dir / f"File_Operativa_{run_id}_{date_formatted}.zip"
    build_operativa_zip({
        "Sintesi_Operativa.xlsx": path_sintesi,
        "barrazero_Sga.xlsx": path_sga0,
        "barranove_Sga.xlsx": path_sga9,
        "barrazero_Sga.csv": path_sga0.with_suffix(".csv"),
        "barranove_Sga.csv": path_sga9.with_suffix(".csv"),
    }, path_zip)

    exported_files = {
        "sintesi": path_sintesi,
        "sga0": path_sga0,
        "sga9": path_sga9,
        "sga0_csv": path_sga0.with_suffix(".csv"),
        "sga9_csv": path_sga9.with_suffix(".csv"),
        "operativa_zip": path_zip,
        "zara": path_zara,
        "planner": path_planner
    }

    if save_to_network and DEFAULT_NETWORK_OUTPUT_DIR.exists():
        try:
            import shutil
            shutil.copy2(path_sintesi, DEFAULT_NETWORK_OUTPUT_DIR / "Sintesi_Operativa.xlsx")
            shutil.copy2(path_zara, DEFAULT_NETWORK_OUTPUT_DIR / "ZARA.xlsx")
            shutil.copy2(path_sga0, DEFAULT_NETWORK_OUTPUT_DIR / "barrazero_Sga.xlsx")
            shutil.copy2(path_sga9, DEFAULT_NETWORK_OUTPUT_DIR / "barranove_Sga.xlsx")
            shutil.copy2(path_planner, DEFAULT_NETWORK_OUTPUT_DIR / f"PLANNER ROMA _{date_formatted}.xlsx")
        except Exception as e:
            print(f"Warning: could not copy to network directory: {e}")

    res = {
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

    import pickle
    try:
        with open(out_dir / "run_cache.pkl", "wb") as f_c:
            pickle.dump(res, f_c)
    except Exception:
        pass

    return res
