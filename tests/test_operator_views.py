"""
Test di simulazione end-to-end dei flussi Operatore (Ufficio, Magazzino, Mobile Banchina a 2 Tasti)
e verifica integrità backup + modalità Admin.
"""
import py_compile
from pathlib import Path

import pandas as pd
import pytest

from src.bolle_manager import (
    add_colli_to_bolla_spuntata,
    confirm_bolla_spunta,
    export_bolle_excel,
    get_bolla_by_id,
    get_bolle_by_date,
    init_bolle_tables,
    render_bolla_printable_html,
    save_or_update_bolla,
)
from src.operator_views import (
    ensure_bolle_for_latest_run,
    format_date_it,
    format_date_weekday_it,
    format_number_it,
)


def test_backup_and_syntax_integrity():
    """Verifica che il file di backup app_backup_full.py esista e che app.py + operator_views.py compilino senza errori."""
    root = Path(__file__).resolve().parent.parent
    backup_file = root / "app_backup_full.py"
    app_file = root / "app.py"
    op_views_file = root / "src" / "operator_views.py"

    assert backup_file.exists(), "Il file di backup app_backup_full.py deve esistere"
    assert backup_file.stat().st_size > 250_000, "Il backup app_backup_full.py deve essere completo"

    py_compile.compile(str(app_file), doraise=True)
    py_compile.compile(str(backup_file), doraise=True)
    py_compile.compile(str(op_views_file), doraise=True)


def test_simulazione_operatore_mobile_due_tasti(tmp_path):
    """
    Simula l'Operatore Banchina Mobile con i 2 soli tasti:
    1) 📋 SPUNTA NEGOZIO (1-Tap Conforme al previsto oppure inserimento manuale)
    2) ➕ AGGIUNGI COLLI (Aggiunta rapida +1 / +5 a negozio già spuntato)
    """
    db_path = tmp_path / "test_mobile_op.db"
    init_bolle_tables(db_path=db_path)

    # Inserimento di 2 negozi da spuntare per la data odierna
    b1_id = save_or_update_bolla(
        {
            "data": "2026-11-11",
            "data_consegna": "2026-11-11",
            "id_store": "3680",
            "store_name": "ZARA ROMA CORSO",
            "tipo_cons": "STD",
            "prev_abbigl": 40,
            "prev_calzat": 10,
            "prev_ecom": 5,
            "prev_others": 2,
            "prev_vario": 0,
            "colli_abbigl": 40,
            "colli_calzat": 10,
            "colli_ecom": 5,
            "colli_others": 2,
            "colli_vario": 0,
            "spuntato": 0,
        },
        db_path=db_path,
    )
    b2_id = save_or_update_bolla(
        {
            "data": "2026-11-11",
            "data_consegna": "2026-11-11",
            "id_store": "3591",
            "store_name": "ZARA EUROMA2",
            "tipo_cons": "STD",
            "prev_abbigl": 30,
            "prev_calzat": 8,
            "prev_ecom": 4,
            "prev_others": 0,
            "prev_vario": 0,
            "colli_abbigl": 30,
            "colli_calzat": 8,
            "colli_ecom": 4,
            "colli_others": 0,
            "colli_vario": 0,
            "spuntato": 0,
        },
        db_path=db_path,
    )

    # --- TASTO 1: SPUNTA NEGOZIO (Scenario A: 1-Tap Conforme al previsto per Store 3680) ---
    res_1tap = confirm_bolla_spunta(b1_id, use_expected=True, db_path=db_path)
    assert res_1tap["status"] == "ok"
    assert res_1tap["spuntato"] == 1
    assert res_1tap["total_colli"] == 57  # 40 + 10 + 5 + 2

    b1_after = get_bolla_by_id(b1_id, db_path=db_path)
    assert int(b1_after["spuntato"]) == 1

    # --- TASTO 1: SPUNTA NEGOZIO (Scenario B: Spunta con modifica manuale per Store 3591) ---
    res_man = confirm_bolla_spunta(
        b2_id,
        use_expected=False,
        colli_abbigl=28,
        colli_calzat=8,
        colli_ecom=4,
        colli_others=1,
        colli_vario=0,
        note="Mancano 2 tessile, +1 other",
        db_path=db_path,
    )
    assert res_man["status"] == "ok"
    assert res_man["total_colli"] == 41

    # --- TASTO 2: AGGIUNGI COLLI A NEGOZIO GIÀ SPUNTATO (Store 3680) ---
    res_add = add_colli_to_bolla_spuntata(
        bolla_id=b1_id,
        colli_to_add=5,
        category="colli_abbigl",
        note_reason="Trovati fine scarico",
        db_path=db_path,
    )
    assert res_add["status"] == "ok"
    assert res_add["new_category_total"] == 45  # 40 + 5
    assert res_add["new_total_colli"] == 62     # 57 + 5

    b1_final = get_bolla_by_id(b1_id, db_path=db_path)
    assert int(b1_final["spuntato"]) == 1
    assert "+5 Abbigliamento (Trovati fine scarico)" in b1_final["note"]


def test_simulazione_operatore_magazzino_stampa_bolle(tmp_path):
    """
    Simula l'Operatore Magazzino:
    1) Seleziona la Data di Consegna
    2) Filtra per Giro / Negozi
    3) Stampa le bolle selezionate (HTML con auto_print) e scarica l'Excel
    """
    db_path = tmp_path / "test_mag_op.db"
    init_bolle_tables(db_path=db_path)

    save_or_update_bolla(
        {
            "data": "2026-11-14",
            "data_consegna": "2026-11-14",
            "id_store": "3680",
            "store_name": "ZARA ROMA CORSO",
            "tipo_cons": "STD",
            "colli_abbigl": 50,
            "colli_calzat": 12,
            "colli_ecom": 6,
            "colli_others": 3,
            "carrier_name": "LACCHI",
        },
        db_path=db_path,
    )
    save_or_update_bolla(
        {
            "data": "2026-11-15",
            "data_consegna": "2026-11-15",
            "id_store": "3680B",
            "store_name": "ZARA ROMA CORSO",
            "tipo_cons": "DOPPIA",
            "colli_abbigl": 20,
            "colli_calzat": 5,
            "colli_ecom": 2,
            "colli_others": 1,
            "carrier_name": "LACCHI",
        },
        db_path=db_path,
    )

    df_b0 = get_bolle_by_date("2026-11-14", db_path=db_path)
    assert len(df_b0) == 1
    rec = get_bolla_by_id(int(df_b0.iloc[0]["id"]), db_path=db_path)
    html_print = render_bolla_printable_html([rec], auto_print=True)
    assert "window.print()" in html_print
    assert "ZARA ROMA CORSO" in html_print

    df_b0["giro"] = "ZA1"
    excel_bytes = export_bolle_excel(df_b0, "2026-11-14")
    assert len(excel_bytes) > 1000


def test_formatting_helpers():
    assert format_date_it("2026-11-11") == "11/11/2026"
    assert "11/11/2026" in format_date_weekday_it("2026-11-11")
    assert format_number_it(1234.56, 0) == "1.235"
    assert format_number_it(27.9, 1) == "27,9"
