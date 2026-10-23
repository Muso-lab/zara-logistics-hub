import pytest
from pathlib import Path
import pandas as pd
from src.parsers import parse_grupo_envio, parse_other_files, parse_esportazione
from src.db import init_db, seed_anagrafica_if_empty, get_stores_df
from src.engine import compute_analisi, compute_spunta_arrivi, compute_sga_flows, compute_planning_roma, evaluate_pedane
from src.pipeline import run_pipeline
from src.config import BASE_DIR

REF_DIR = BASE_DIR / "reference_data"

def test_evaluate_pedane():
    # Standard 1.9 m3 divisor
    assert evaluate_pedane(1.9, "MC/1,9") == 1
    assert evaluate_pedane(2.0, "MC/1,9") == 2
    assert evaluate_pedane(10.0, "MC/1,9") == 6
    # Bershka / Zara factor
    assert evaluate_pedane(10.0, "MC*1,5/1,8") == 9
    # Zara Home 1.5 m3
    assert evaluate_pedane(10.0, "MC/1,5") == 7
    # Barra 0 split
    assert evaluate_pedane(10.0, "(MC*1,5/1,8)*0,7") == 6
    assert evaluate_pedane(0, "MC/1,9") == 0

def test_parsers():
    df_tot = parse_grupo_envio(REF_DIR / "TOTAL.xls")
    assert not df_tot.empty
    assert len(df_tot) == 49
    assert abs(df_tot["bultos"].sum() - 8169.0) < 1e-2

    df_sho = parse_grupo_envio(REF_DIR / "SHOES.xls")
    assert not df_sho.empty
    assert abs(df_sho["bultos"].sum() - 749.0) < 1e-2

    df_tex = parse_grupo_envio(REF_DIR / "TEXILE.xls")
    assert not df_tex.empty
    assert abs(df_tex["bultos"].sum() - 7364.0) < 1e-2

    df_eco = parse_grupo_envio(REF_DIR / "ECOM.xls")
    assert not df_eco.empty
    assert abs(df_eco["bultos"].sum() - 68.0) < 1e-2

    df_oth_raw, df_oth_agg = parse_other_files(REF_DIR / "OTHER")
    assert not df_oth_raw.empty
    assert not df_oth_agg.empty
    assert abs(df_oth_agg["otros_enviado"].sum() - 296.0) < 1e-2

    df_esp = parse_esportazione(REF_DIR / "esportazione.xlsx")
    assert not df_esp.empty
    assert len(df_esp) == 55

def test_engine_calculations():
    init_db()
    seed_anagrafica_if_empty()
    df_stores = get_stores_df()

    df_tot = parse_grupo_envio(REF_DIR / "TOTAL.xls")
    df_sho = parse_grupo_envio(REF_DIR / "SHOES.xls")
    df_tex = parse_grupo_envio(REF_DIR / "TEXILE.xls")
    df_eco = parse_grupo_envio(REF_DIR / "ECOM.xls")
    _, df_oth_agg = parse_other_files(REF_DIR / "OTHER")
    df_esp = parse_esportazione(REF_DIR / "esportazione.xlsx")

    df_a = compute_analisi(df_stores, df_tot, df_sho, df_tex, df_eco, df_oth_agg)
    assert len(df_a) >= 50

    df_sp = compute_spunta_arrivi(df_a)
    assert len(df_sp) >= 94
    # Check Megalò stores
    row_3503 = df_sp[df_sp["store_code"] == "3503"].iloc[0]
    assert row_3503["giro"] == "ZA1"
    assert row_3503["pedane"] > 0

    df_sga0, df_sga9 = compute_sga_flows(df_sp, df_stores, "2026-10-22")
    assert len(df_sga0) > 0
    assert len(df_sga9) > 0
    # Every Andata has a matching Ritorno
    assert (df_sga0["flusso_tipo"] == "ANDATA").sum() == (df_sga0["flusso_tipo"] == "RITORNO").sum()
    assert (df_sga9["flusso_tipo"] == "ANDATA").sum() == (df_sga9["flusso_tipo"] == "RITORNO").sum()

def test_full_pipeline():
    res = run_pipeline(
        total_source=REF_DIR / "TOTAL.xls",
        shoes_source=REF_DIR / "SHOES.xls",
        texile_source=REF_DIR / "TEXILE.xls",
        ecom_source=REF_DIR / "ECOM.xls",
        other_source=REF_DIR / "OTHER",
        esportazione_source=REF_DIR / "esportazione.xlsx",
        run_date="2026-10-22",
        cycle_type="GIOV-DOM"
    )
    assert res["run_id"] > 0
    assert res["totals"]["total_bultos"] == 8169.0
    for name, p in res["exported_files"].items():
        assert p.exists()
        assert p.stat().st_size > 0

    # Test special breakdowns
    sb = res["special_breakdowns"]
    assert "stander_summary" in sb
    assert isinstance(sb["stander_summary"], pd.DataFrame)
    assert len(sb["stander_summary"]) == 3
    assert "zh_summary" in sb
    assert isinstance(sb["zh_summary"], pd.DataFrame)
    assert len(sb["zh_summary"]) == 2
    assert sb["totale_pezzi_lavorati"] > 0


def test_utils_localization_and_cycles():
    from src.utils import get_cycle_date_range, format_number_it
    from datetime import date

    # Test Thursday 22 Oct 2026
    ref_thursday = date(2026, 10, 22)

    # LUN-MER cycle
    desde_lm, hasta_lm = get_cycle_date_range("LUN-MER", ref_thursday)
    assert desde_lm == date(2026, 10, 19)  # Monday
    assert hasta_lm == date(2026, 10, 21)  # Wednesday

    # GIOV-DOM cycle
    desde_gd, hasta_gd = get_cycle_date_range("GIOV-DOM", ref_thursday)
    assert desde_gd == date(2026, 10, 22)  # Thursday
    assert hasta_gd == date(2026, 10, 25)  # Sunday

    # Number formatting IT
    assert format_number_it(10080, 0) == "10.080"
    assert format_number_it(1041.5, 2) == "1.041,50"
    assert format_number_it(0, 0) == "0"


def test_store_options_and_auto_onboarding():
    from src.db import add_store_record, update_store_record, delete_store_record, get_stores_df
    
    # 1. Test add_store_record
    test_store = {
        "store_id": "9998",
        "store_name": "TEST STORE 9998",
        "punto_vendita": "ZARA",
        "brand": "ZARA",
        "giro": "ZA99",
        "cod_sga": 9998,
        "cc": "TEST CC",
        "attivo": "SI",
        "lavorazione": "SI TESSILE",
        "sdoppiamento_b9": "SI",
        "formula": "MC/1,9"
    }
    add_store_record(test_store)
    df_s = get_stores_df()
    row = df_s[df_s["store_id"] == "9998"].iloc[0]
    assert row["lavorazione"] == "SI TESSILE"
    assert row["sdoppiamento_b9"] == "SI"
    assert row["giro"] == "ZA99"

    # 2. Test update_store_record
    update_store_record("9998", {"lavorazione": "SI HOME", "sdoppiamento_b9": "NO", "giro": "ZA1"})
    df_s2 = get_stores_df()
    row2 = df_s2[df_s2["store_id"] == "9998"].iloc[0]
    assert row2["lavorazione"] == "SI HOME"
    assert row2["sdoppiamento_b9"] == "NO"
    assert row2["giro"] == "ZA1"

    # Clean up test store
    delete_store_record("9998")

    # 3. Test auto-onboarding in run_pipeline with mock new store in total
    delete_store_record("9999")  # ensure clean start
    try:
        df_tot = parse_grupo_envio(REF_DIR / "TOTAL.xls").copy()
        # Add a mock row for unknown store 9999
        mock_row = pd.DataFrame([{
            "store_id": "9999",
            "raw_tienda": "9999-NAP-CENTRO",
            "p_colgada": 10.0,
            "paqueteria": 20.0,
            "peso": 300.0,
            "volumen": 5.0,
            "bultos": 30.0
        }])
        df_tot_extended = pd.concat([df_tot, mock_row], ignore_index=True)

        res = run_pipeline(
            total_source=df_tot_extended,
            shoes_source=REF_DIR / "SHOES.xls",
            texile_source=REF_DIR / "TEXILE.xls",
            ecom_source=REF_DIR / "ECOM.xls",
            other_source=REF_DIR / "OTHER",
            esportazione_source=None,
            run_date="2026-10-22",
            cycle_type="GIOV-DOM"
        )

        # Verify alert was generated
        assert "new_stores_alert" in res
        alerts = res["new_stores_alert"]
        assert any(a["store_id"] == "9999" for a in alerts)

        # Verify store was onboarded to database
        df_s3 = get_stores_df()
        assert "9999" in df_s3["store_id"].values
        s9999 = df_s3[df_s3["store_id"] == "9999"].iloc[0]
        assert s9999["giro"] == "DA ASSEGNARE"
        assert s9999["attivo"] == "SI"

        # Verify spunta arrivi includes 9999 under DA ASSEGNARE
        df_sp = res["df_spunta"]
        sp_9999 = df_sp[df_sp["store_code"] == "9999"]
        assert not sp_9999.empty
        assert sp_9999.iloc[0]["giro"] == "DA ASSEGNARE"
    finally:
        # Clean up test store 9999
        delete_store_record("9999")


def test_delete_run():
    from src.db import create_run, delete_run, get_all_runs
    r_id = create_run(run_date="2026-10-22", cycle_type="LUN-MER", notes="Test Delete")
    assert r_id > 0
    runs_before = get_all_runs()
    assert r_id in runs_before["id"].values

    delete_run(r_id)
    runs_after = get_all_runs()
    assert r_id not in runs_after["id"].values


def test_bulk_delete_runs():
    from src.db import create_run, delete_runs, get_all_runs
    r1 = create_run(run_date="2026-10-22", cycle_type="LUN-MER", notes="Test Bulk 1")
    r2 = create_run(run_date="2026-10-22", cycle_type="LUN-MER", notes="Test Bulk 2")
    r3 = create_run(run_date="2026-10-22", cycle_type="LUN-MER", notes="Test Bulk 3")

    runs = get_all_runs()
    all_ids = runs["id"].values
    assert r1 in all_ids and r2 in all_ids and r3 in all_ids

    # Delete 2 of them
    deleted_cnt = delete_runs([r1, r2])
    assert deleted_cnt == 2

    runs_mid = get_all_runs()
    mid_ids = runs_mid["id"].values
    assert r1 not in mid_ids and r2 not in mid_ids
    assert r3 in mid_ids

    # Delete the remaining one
    delete_runs([r3])
    runs_end = get_all_runs()
    assert r3 not in runs_end["id"].values


def test_sdoppiamento_volume_split():
    from src.engine import compute_spunta_arrivi, compute_planning_roma
    # Mock single store with 100 colli, 10 mc
    df_analisi = pd.DataFrame([{
        "store_id": "5349",
        "store_name": "ROM-EUROMA2 APT0",
        "brand": "PULL&BEAR",
        "total_vol": 10.0,
        "planned_textile": 70.0,
        "planned_others": 30.0,
        "planned_shoes": 0.0,
        "planned_ecom": 0.0,
        "total_planned_crts": 100.0,
        "giro": "ZA16"
    }])

    # 1. Store with sdoppiamento = 'SI'
    df_stores_si = pd.DataFrame([{
        "store_id": "5349",
        "sdoppiamento_b9": "SI",
        "formula": "MC/1,9"
    }])
    df_sp_si = compute_spunta_arrivi(df_analisi, df_stores=df_stores_si)
    b0_row = df_sp_si[(df_sp_si["store_code"] == "5349") & (df_sp_si["is_barra9"] == 0)].iloc[0]
    b9_row = df_sp_si[(df_sp_si["store_code"] == "5349B") & (df_sp_si["is_barra9"] == 1)].iloc[0]

    assert abs(b0_row["mc"] - 7.0) < 1e-2  # 70% of 10.0
    assert abs(b9_row["mc"] - 3.0) < 1e-2  # 30% of 10.0
    assert b0_row["textile_attesi"] == 70  # 100% of colli remain on Barra 0 in Spunta Arrivi

    # 2. Planning Roma split check
    df_actuals_empty = pd.DataFrame(columns=["ID_STORE", "tipo_cons", "TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM", "TOT_OTHERS"])
    df_plan = compute_planning_roma(df_analisi, df_actuals_empty, df_stores=df_stores_si)
    p_std = df_plan[df_plan["store_code"] == "5349"].iloc[0]
    p_b9 = df_plan[df_plan["store_code"] == "5349B"].iloc[0]

    assert abs(p_std["total_planned_crts"] - 70.0) < 1e-1  # 70%
    assert abs(p_b9["total_planned_crts"] - 30.0) < 1e-1   # 30%


def test_classify_uploaded_files():
    import zipfile
    import io
    from src.parsers import classify_uploaded_files, NamedBytesIO

    # Test with direct NamedBytesIO files from reference_data
    files = []
    for fname in ["TOTAL.xls", "SHOES.xls", "TEXILE.xls", "ECOM.xls"]:
        p = REF_DIR / fname
        files.append(NamedBytesIO(p.read_bytes(), fname))
    other_dir = REF_DIR / "OTHER"
    for p in other_dir.glob("*.xls"):
        files.append(NamedBytesIO(p.read_bytes(), p.name))

    classified = classify_uploaded_files(files)
    assert classified["total"] is not None
    assert classified["shoes"] is not None
    assert classified["texile"] is not None
    assert classified["ecom"] is not None
    assert len(classified["other"]) > 0

    # Test with a ZIP archive containing the files
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for fname in ["TOTAL.xls", "SHOES.xls"]:
            zf.writestr(fname, (REF_DIR / fname).read_bytes())
        for p in list(other_dir.glob("*.xls"))[:2]:
            zf.writestr(f"OTHER/{p.name}", p.read_bytes())

    zip_file = NamedBytesIO(zip_buf.getvalue(), "pacchetto_arrivi.zip")
    classified_zip = classify_uploaded_files([zip_file])
    assert classified_zip["total"] is not None
    assert classified_zip["shoes"] is not None
    assert len(classified_zip["other"]) == 2


def test_vehicle_capacity_parsing():
    from src.components import parse_vehicle_capacity

    assert parse_vehicle_capacity("BILICO 33") == 33
    assert parse_vehicle_capacity("BILICO") == 33
    assert parse_vehicle_capacity("BILICO x 3") == 99
    assert parse_vehicle_capacity("MOTRICE 14x3") == 42
    assert parse_vehicle_capacity("MOTRICE 18 PLT") == 18
    assert parse_vehicle_capacity("MOTRICE 18") == 18
    assert parse_vehicle_capacity("MOTRICE EE 18") == 18
    assert parse_vehicle_capacity("MOTRICE 14") == 14
    assert parse_vehicle_capacity("MOTRICE EE 14") == 14
    assert parse_vehicle_capacity("EUROCARGO 75") == 14
    assert parse_vehicle_capacity("FURGONE 8") == 8
    assert parse_vehicle_capacity("FURG") == 8
    assert parse_vehicle_capacity("FURGONE") == 8
    assert parse_vehicle_capacity("") == 0
    assert parse_vehicle_capacity("Da Assegnare") == 0


def test_platform_footprint_calculation_9226():
    from src.engine import compute_special_breakdowns
    import pandas as pd

    # Mock inputs matching run 91 operational reality for 9226
    df_tot = pd.DataFrame([
        {"store_id": "9226", "p_colgada": 3288.0, "paqueteria": 5383.0, "bultos": 272.0, "volumen": 29.83, "peso": 2500.0}
    ])
    df_sho = pd.DataFrame([
        {"store_id": "9226", "p_colgada": 736.0, "paqueteria": 39.0, "bultos": 48.0, "volumen": 4.72, "peso": 500.0}
    ])
    df_sp = pd.DataFrame([
        {"store_code": "9226", "brand": "ZARA", "mc": 29.84, "textile_attesi": 202, "other_attesi": 22, "shoes_attesi": 48, "ecom_attesi": 0, "pedane": 25, "is_store": True}
    ])
    df_stores = pd.DataFrame([
        {"store_id": "9226", "store_name": "ROM-P BOCCONI", "lavorazione": "SI TESSILE", "scorporo_profumi": "SI", "pezzi_profumi": 1791.0}
    ])

    sb = compute_special_breakdowns(
        df_spunta=df_sp,
        df_total=df_tot,
        df_shoes=df_sho,
        df_stores=df_stores
    )

    s9226 = sb["special_stores"]["9226"]
    assert s9226["stander"] == 12
    assert s9226["bancali_stesi"] == 11
    assert s9226["bancali_extra"] == 4  # 70 non-textile colli / 18 = 4 bancali
    assert s9226["bancali"] == 15      # 11 stesi + 4 extra = 15 bancali
    assert s9226["stander_pedane_eq"] == 24  # 12 stander * 2 ("a madonna") = 24 pedane equivalenti
    assert s9226["impronta_a_terra"] == 39   # 15 bancali + 24 stander eq = 39 pedane totali
    assert s9226["pedane_senza_lavorazione"] == 25
    assert s9226["sintesi"] == "15 bancali + 12 stander"





