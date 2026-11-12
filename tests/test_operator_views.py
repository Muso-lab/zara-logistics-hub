"""
Test di simulazione end-to-end dei flussi Operatore (Ufficio, Magazzino, Mobile Banchina a 2 Tasti)
e verifica integrità backup + modalità Admin + migliorie mobile/magazzino/date/stampa.
"""
import py_compile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.bolle_manager import (
    add_colli_to_bolla_spuntata,
    add_intershop_to_bolla,
    clear_sigilli_by_date,
    compute_inditex_delivery_dates,
    confirm_bolla_spunta,
    export_bolle_excel,
    get_bolla_by_id,
    get_bolle_by_date,
    init_bolle_tables,
    remove_intershop_from_bolla,
    render_bolla_printable_html,
    save_or_update_bolla,
)
from src.engine import compute_sga_flows
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
    Simula l'Operatore Banchina Mobile con i 2 soli tasti + Omnibox + Aggiunta a non spuntati + Trasferimenti:
    1) 📋 SPUNTA NEGOZIO (1-Tap Conforme al previsto oppure inserimento manuale + trasferimenti)
    2) ➕ AGGIUNGI COLLI / TRASF. (Aggiunta colli sia a negozio già spuntato sia a negozio NON spuntato + trasferimenti)
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

    # --- TASTO 2: AGGIUNGI COLLI A NEGOZIO NON ANCORA SPUNTATO (Store 3591, lasciandolo da spuntare) ---
    res_add_uncounted = add_colli_to_bolla_spuntata(
        bolla_id=b2_id,
        colli_to_add=3,
        category="colli_ecom",
        note_reason="Extra ecom su bancale",
        mark_spuntato=False,
        db_path=db_path,
    )
    assert res_add_uncounted["status"] == "ok"
    assert res_add_uncounted["new_category_total"] == 7  # 4 + 3
    assert res_add_uncounted["spuntato"] == 0

    # --- TASTO 2: AGGIUNGI COLLI A NEGOZIO GIÀ SPUNTATO (Store 3680) ---
    res_add = add_colli_to_bolla_spuntata(
        bolla_id=b1_id,
        colli_to_add=5,
        category="colli_abbigl",
        note_reason="Trovati fine scarico",
        mark_spuntato=True,
        db_path=db_path,
    )
    assert res_add["status"] == "ok"
    assert res_add["new_category_total"] == 45  # 40 + 5
    assert res_add["new_total_colli"] == 62     # 57 + 5

    b1_final = get_bolla_by_id(b1_id, db_path=db_path)
    assert int(b1_final["spuntato"]) == 1
    assert "+5 Abbigliamento (Trovati fine scarico)" in b1_final["note"]

    # --- TRASFERIMENTI (INTERSHOPS) DIRETTAMENTE DA MOBILE ---
    res_tr1 = add_intershop_to_bolla(
        bolla_id=b1_id,
        mittente="3591 - ZARA EUROMA2",
        colli=4,
        tipo="MERCE",
        db_path=db_path,
    )
    assert res_tr1["status"] == "ok"
    assert len(res_tr1["intershops_list"]) == 1
    assert res_tr1["intershops_list"][0]["colli"] == 4

    res_tr2 = add_intershop_to_bolla(
        bolla_id=b1_id,
        mittente="157 - ZARA PORTA DI ROMA",
        colli=2,
        tipo="STAND",
        db_path=db_path,
    )
    assert res_tr2["status"] == "ok"
    assert len(res_tr2["intershops_list"]) == 2

    res_rem = remove_intershop_from_bolla(bolla_id=b1_id, index=0, db_path=db_path)
    assert res_rem["status"] == "ok"
    assert len(res_rem["intershops_list"]) == 1
    assert res_rem["intershops_list"][0]["tipo"] == "STAND"


def test_simulazione_operatore_magazzino_stampa_bolle_sigillo_e_pagine(tmp_path):
    """
    Simula l'Operatore Magazzino:
    1) Verifica che il sigillo NON sia residente (override_sigillo="" di default)
    2) Verifica che in stampa non ci siano fogli bianchi tra una bolla e l'altra (CSS @media print)
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
            "sigillo": "VECCHIO-SIGILLO-RESIDENTE",
        },
        db_path=db_path,
    )
    save_or_update_bolla(
        {
            "data": "2026-11-14",
            "data_consegna": "2026-11-14",
            "id_store": "3591",
            "store_name": "ZARA EUROMA2",
            "tipo_cons": "STD",
            "colli_abbigl": 20,
            "colli_calzat": 5,
            "colli_ecom": 2,
            "colli_others": 1,
            "carrier_name": "LACCHI",
        },
        db_path=db_path,
    )

    df_b0 = get_bolle_by_date("2026-11-14", db_path=db_path)
    assert len(df_b0) == 2
    records = [get_bolla_by_id(int(r["id"]), db_path=db_path) for _, r in df_b0.iterrows()]

    # 1) Stampa con override_sigillo="" (nessun sigillo inserito nella sessione corrente) -> il vecchio sigillo NON compare
    html_no_seal = render_bolla_printable_html(records, auto_print=True, override_sigillo="")
    assert "VECCHIO-SIGILLO-RESIDENTE" not in html_no_seal
    assert "window.print()" in html_no_seal
    # Verifica CSS anti-fogli-bianchi
    assert "min-height: 0 !important" in html_no_seal
    assert ".bolla-sheet:last-of-type" in html_no_seal

    # 2) Stampa con sigillo temporaneo di giro -> compare il sigillo inserito
    html_with_seal = render_bolla_printable_html(records, auto_print=False, override_sigillo="SIG-NUOVO-999")
    assert "SIG-NUOVO-999" in html_with_seal

    # 3) Pulizia sigilli su DB
    cleared = clear_sigilli_by_date("2026-11-14", db_path=db_path)
    assert cleared == 2


def test_verifica_date_consegna_inditex_sabato_non_venerdi():
    """
    Verifica che l'operativa GIOV-DOM lanciata di Giovedì (es. 2026-10-22) o Venerdì (2026-10-23)
    produca SEMPRE Sabato (2026-10-24) per /0 STD e Domenica (2026-10-25) per /9 DOPPIA,
    e MAI Venerdì (2026-10-23).
    """
    # Giovedì 22 Ottobre 2026 con ciclo GIOV-DOM (compute_inditex_delivery_dates ritorna (date_b9, date_b0))
    dt_b9, dt_b0 = compute_inditex_delivery_dates(date(2026, 10, 22), "GIOV-DOM")
    assert dt_b0 == date(2026, 10, 24), "Barra 0 (/0 STD) di GIOV-DOM deve essere Sabato, non Venerdì!"
    assert dt_b9 == date(2026, 10, 25), "Barra 9 (/9 DOPPIA) di GIOV-DOM deve essere Domenica, non Sabato!"

    # Anche compute_sga_flows deve usare Sabato 24/10/2026 e Domenica 25/10/2026
    df_spunta = pd.DataFrame([
        {
            "row_idx": 1,
            "is_store": True,
            "store_code": "3503",
            "store_name": "ROMA VIA CONDOTTI",
            "punto_vendita": "ZARA",
            "brand": "ZARA",
            "mc": 4.5,
            "textile_attesi": 100,
            "other_attesi": 20,
            "shoes_attesi": 15,
            "ecom_attesi": 5,
            "pedane": 6,
            "totale_pedane": 6,
            "vettore_autista": "MARIO ROSSI",
            "tipo_mezzo": "EUROCARGO 75",
            "targa": "AA123BB",
            "cod_mezzo": "EC75",
            "supporto": "",
            "giro": "ZA1",
            "is_barra9": 0,
            "attivo": "SI",
        },
        {
            "row_idx": 2,
            "is_store": True,
            "store_code": "1984B",
            "store_name": "ROMA COLA DI RIENZO",
            "punto_vendita": "ZARA HOME",
            "brand": "ZARA HOME",
            "mc": 3.0,
            "textile_attesi": 0,
            "other_attesi": 0,
            "shoes_attesi": 0,
            "ecom_attesi": 0,
            "pedane": 4,
            "totale_pedane": 4,
            "vettore_autista": "LUIGI BIANCHI",
            "tipo_mezzo": "MOTRICE 18 PLT",
            "targa": "CC456DD",
            "cod_mezzo": "MOT18",
            "supporto": "",
            "giro": "ZA15",
            "is_barra9": 1,
            "attivo": "SI",
        },
    ])
    df_stores = pd.DataFrame([
        {"store_id": "3503", "cod_sga": 3503, "giro": "ZA1", "attivo": "SI"},
        {"store_id": "1984", "cod_sga": 1984, "giro": "ZA15", "attivo": "SI"},
    ])
    df_sga0, df_sga9 = compute_sga_flows(df_spunta, df_stores, "2026-10-22", cycle_type="GIOV-DOM")
    assert df_sga0.iloc[0]["DATA_CARICO"] == "24/10/2026"
    assert df_sga9.iloc[0]["DATA_CARICO"] == "25/10/2026"


def test_formatting_helpers():
    assert format_date_it("2026-11-11") == "11/11/2026"
    assert "11/11/2026" in format_date_weekday_it("2026-11-11")
    assert format_number_it(1234.56, 0) == "1.235"
    assert format_number_it(27.9, 1) == "27,9"


def test_iso_utc_date_parsing_and_heal_shifted_bolle_dates(tmp_path):
    """
    Verifica che i timestamp UTC provenienti da Google Sheets (es. '2026-11-06T23:00:00.000Z',
    che corrisponde a Sabato 07/11/2026 00:00 in Europe/Rome) vengano convertiti a 2026-11-07
    e che heal_shifted_bolle_dates riallinei Venerdì 06/11 -> Sabato 07/11 (/0 STD) e
    Sabato 07/11 -> Domenica 08/11 (/9 DOPPIA) preservando le spunte e ripulendo i 'nan'.
    """
    from src.utils import parse_date_obj
    from src.bolle_manager import heal_shifted_bolle_dates
    from src.operator_views import _clean_str

    assert parse_date_obj("2026-11-06T23:00:00.000Z") == date(2026, 11, 7)
    assert parse_date_obj("2026-11-07T23:00:00.000Z") == date(2026, 11, 8)
    assert parse_date_obj("2026-07-10T22:00:00.000Z") == date(2026, 7, 11)
    assert _clean_str(float("nan")) == ""
    assert _clean_str("nan") == ""
    assert _clean_str("NaN") == ""
    assert _clean_str(None) == ""
    assert _clean_str("Nota valida") == "Nota valida"

    db_path = tmp_path / "test_heal_dates.db"
    init_bolle_tables(db_path=db_path)

    # Inseriamo una bolla STD scalata a Venerdì 2026-11-06 con note='nan'
    save_or_update_bolla(
        {
            "data": "2026-11-06",
            "data_consegna": "2026-11-06",
            "id_store": "10265",
            "store_name": "PES-VITTORIO E",
            "tipo_cons": "STD",
            "prev_abbigl": 40,
            "prev_calzat": 1,
            "colli_abbigl": 40,
            "colli_calzat": 1,
            "note": "nan",
            "spuntato": 0,
        },
        db_path=db_path,
    )
    # Inseriamo una bolla DOPPIA scalata a Sabato 2026-11-07 già spuntata (spuntato=1)
    save_or_update_bolla(
        {
            "data": "2026-11-07",
            "data_consegna": "2026-11-07",
            "id_store": "14010",
            "store_name": "ROM-OTTAVIANO",
            "tipo_cons": "DOPPIA",
            "prev_abbigl": 50,
            "colli_abbigl": 50,
            "note": "nan",
            "spuntato": 1,
        },
        db_path=db_path,
    )

    res_heal = heal_shifted_bolle_dates(db_path=db_path)
    assert res_heal >= 2

    df_fri = get_bolle_by_date("2026-11-06", db_path=db_path)
    df_sat = get_bolle_by_date("2026-11-07", db_path=db_path)
    df_sun = get_bolle_by_date("2026-11-08", db_path=db_path)

    assert df_fri.empty, "Venerdì 06/11 non deve più avere bolle!"
    assert len(df_sat) == 1 and df_sat.iloc[0]["id_store"] == "10265" and df_sat.iloc[0]["tipo_cons"] == "STD"
    assert df_sat.iloc[0]["note"] == ""
    assert len(df_sun) == 1 and df_sun.iloc[0]["id_store"] == "14010" and df_sun.iloc[0]["tipo_cons"] == "DOPPIA"
    assert int(df_sun.iloc[0]["spuntato"]) == 1
    assert df_sun.iloc[0]["note"] == ""


def test_mobile_omnibox_store_completeness_and_resolution():
    """
    Verifica:
    1) Che l'etichetta Omnibox includa sempre sia l'Insegna (es. STRADIVARIUS, ZARA, BERSHKA, PULL&BEAR)
       sia il Centro/Località (es. ROM-EUROMA2, ROM-ROMA EST) unificando Anagrafica (`stores`) e `bolle`.
    2) Che la risoluzione Omnibox (`_resolve_omnibox_bid` e `_resolve_omnibox_store_code`) trovi
       istantaneamente 'roma est', 'stradivarius euroma', '2917', '3534', ecc.
    """
    from src.operator_views import (
        _format_store_display,
        _build_unified_stores_lookup,
        _resolve_omnibox_bid,
        _resolve_omnibox_store_code,
    )

    df_stores = pd.DataFrame([
        {"store_id": "2917", "brand": "STRADIVARIUS", "store_name": "ROM-EUROMA2", "attivo": "SI"},
        {"store_id": "3534", "brand": "ZARA", "store_name": "ROM-ROMA EST", "attivo": "SI"},
        {"store_id": "2898", "brand": "STRADIVARIUS", "store_name": "ROM-ROMA EST", "attivo": "SI"},
        {"store_id": "5306", "brand": "PULL&BEAR", "store_name": "ROM-ROMA EST", "attivo": "SI"},
        {"store_id": "8364", "brand": "BERSHKA", "store_name": "ROM-ROMA EST", "attivo": "SI"},
    ])
    df_bolle = pd.DataFrame([
        {"id": 101, "id_store": "2917", "punto_vendita": "STRADIVARIUS", "store_name": "ROM-EUROMA2", "tipo_cons": "STD"},
        {"id": 102, "id_store": "3534", "punto_vendita": "ZARA", "store_name": "ROM-ROMA EST", "tipo_cons": "STD"},
    ])

    codes, lookup = _build_unified_stores_lookup(df_stores, df_bolle)
    assert "2917" in codes and "3534" in codes and "2898" in codes and "5306" in codes and "8364" in codes
    assert lookup["2917"] == "STRADIVARIUS ROM-EUROMA2"
    assert lookup["3534"] == "ZARA ROM-ROMA EST"
    assert _format_store_display("2917", df_bolle.iloc[0], lookup) == "STRADIVARIUS ROM-EUROMA2"

    opts = [101, 102]
    labels = {
        101: "⏳ 2917 — STRADIVARIUS ROM-EUROMA2 (/0 STD • 159 colli)",
        102: "⏳ 3534 — ZARA ROM-ROMA EST (/0 STD • 267 colli)",
    }
    assert _resolve_omnibox_bid(102, opts, labels, 101) == 102
    assert _resolve_omnibox_bid("stradivarius euroma", opts, labels, 102) == 101
    assert _resolve_omnibox_bid("roma est", opts, labels, 101) == 102
    assert _resolve_omnibox_bid("2917", opts, labels, 102) == 101
    assert _resolve_omnibox_bid("3534", opts, labels, 101) == 102

    mitt_opts = [""] + codes
    assert _resolve_omnibox_store_code("stradivarius euroma", mitt_opts, lookup) == "2917"
    assert _resolve_omnibox_store_code("zara roma est", mitt_opts, lookup) == "3534"
    assert _resolve_omnibox_store_code("5306", mitt_opts, lookup) == "5306"


def test_mobile_intershop_material_description(tmp_path):
    """
    Verifica che nella sezione Trasferimenti da Mobile sia possibile aggiungere
    la descrizione del materiale da trasferire e che compaia sia nella stringa
    sia nella stampa della bolla.
    """
    db_path = tmp_path / "test_inter_desc.db"
    init_bolle_tables(db_path=db_path)

    bid = save_or_update_bolla(
        {
            "data": "2026-11-14",
            "data_consegna": "2026-11-14",
            "id_store": "3534",
            "punto_vendita": "ZARA",
            "store_name": "ROM-ROMA EST",
            "tipo_cons": "STD",
            "colli_abbigl": 100,
        },
        db_path=db_path,
        sync_cloud=False,
    )

    res = add_intershop_to_bolla(
        bolla_id=bid,
        mittente="3680",
        colli=3,
        tipo="VARIO",
        descrizione="Manichini vetrina e grucce",
        db_path=db_path,
    )
    assert res["status"] == "ok"
    assert "3C VARIO (Manichini vetrina e grucce) da 3680" in res["stringa"]
    assert res["intershops_list"][0]["descrizione"] == "Manichini vetrina e grucce"

    bolla_rec = get_bolla_by_id(bid, db_path=db_path)
    html_out = render_bolla_printable_html([bolla_rec], auto_print=False)
    assert "VARIO — Manichini vetrina e grucce" in html_out
    assert "3680" in html_out


def test_split_bolla_for_printing_in_n_vans():
    """
    Verifica la divisione di una bolla in 2, 3 o 4 furgoni in fase di stampa:
    1) Ripartizione equa automatica: il totale colli e ogni singola categoria quadrano al 100%.
    2) Ripartizione personalizzata per totale furgone e per categoria: l'ultimo furgone
       assorbe automaticamente il saldo per differenza senza mai perdere o inventare colli.
    3) Personalizzazione Autista, Sigillo e Furgone destinatario dei Trasferimenti (Intershops).
    """
    from src.bolle_manager import SPLIT_CAT_KEYS, split_bolla_for_printing

    base_bolla = {
        "id": 846,
        "data": "2026-11-11",
        "data_consegna": "2026-11-11",
        "id_store": "3534",
        "punto_vendita": "ZARA",
        "store_name": "ROM-ROMA EST",
        "tipo_cons": "STD",
        "colli_abbigl": 200,
        "colli_calzat": 35,
        "colli_ecom": 20,
        "colli_others": 10,
        "colli_vario": 2,
        "intershops_json": '[{"mittente": "3680", "colli": 4, "tipo": "STAND", "descrizione": "Manichini"}]',
        "stringa": "4C STAND (Manichini) da 3680",
    }
    orig_total = 200 + 35 + 20 + 10 + 2  # 267 colli

    # 1. Divisione equa su 2, 3 e 4 furgoni
    for n_v in (2, 3, 4):
        parts = split_bolla_for_printing(base_bolla, n_parts=n_v)
        assert len(parts) == n_v
        assert sum(int(p["TOT_COLLI"]) for p in parts) == orig_total
        for ck in SPLIT_CAT_KEYS:
            assert sum(int(p[ck]) for p in parts) == base_bolla[ck]

    # 2. Divisione su 3 furgoni con totale personalizzato sui primi 2 e saldo automatico sul 3°
    #    + Autista/Sigillo dedicati e Trasferimenti sul Furgone 2
    custom_3 = [
        {"target_total": 100, "autista": "ROSSI MARIO", "sigillo": "SIG-F1"},
        {"target_total": 90, "autista": "BIANCHI LUIGI", "sigillo": "SIG-F2"},
        {"autista": "VERDI PAOLO", "sigillo": "SIG-F3"},
    ]
    parts_3 = split_bolla_for_printing(
        base_bolla,
        n_parts=3,
        custom_parts=custom_3,
        intershops_part_idx=2,
    )
    assert [int(p["TOT_COLLI"]) for p in parts_3] == [100, 90, 77]
    assert sum(int(p["TOT_COLLI"]) for p in parts_3) == orig_total
    for ck in SPLIT_CAT_KEYS:
        assert sum(int(p[ck]) for p in parts_3) == base_bolla[ck]

    # Verifica che i trasferimenti siano SOLO sul Furgone 2 e non duplicati su 1 e 3
    assert parts_3[0]["intershops_json"] == "[]"
    assert "3680" in parts_3[1]["intershops_json"]
    assert parts_3[2]["intershops_json"] == "[]"

    # Verifica HTML stampabile
    html_split = render_bolla_printable_html(parts_3, auto_print=False, override_sigillo="")
    assert "00846/1" in html_split
    assert "00846/2" in html_split
    assert "00846/3" in html_split
    assert "FURGONE 1 DI 3" in html_split
    assert "FURGONE 2 DI 3" in html_split
    assert "FURGONE 3 DI 3" in html_split
    assert "SIG-F1" in html_split and "SIG-F2" in html_split and "SIG-F3" in html_split
    assert "ROSSI MARIO" in html_split and "BIANCHI LUIGI" in html_split and "VERDI PAOLO" in html_split



