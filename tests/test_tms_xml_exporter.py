"""
Unit tests for TMS XML Exporter (TrasportoEntrataOrdini_1_00).
Verifies XML generation against desktop sample specifications for Consegna and Ritiro
distinguishing Barra 0 (B0) and Barra 9 (B9) across all 4 file types.
"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET
import pytest
import zipfile

from src.tms_xml_exporter import (
    build_tms_order_xml,
    parse_store_address,
    format_store_ragione_sociale,
    get_stores_lookup,
    generate_tms_xml_files,
    create_tms_xml_zip_bytes,
    generate_unique_id_flusso,
    LACCHI_HUB,
)


def test_parse_store_address():
    # Megalo
    addr1 = "LOCALITA S. FILOMENA -  66100 - Chieti - MEGALO'"
    res1 = parse_store_address(addr1, "CHIETI")
    assert res1["cap"] == "66100"
    assert res1["provincia"] == "CH"
    assert "Filomena" in res1["indirizzo"]
    assert "Chieti" in res1["localita"]

    # Roma Est
    addr2 = "VIA COLLATINA KM 12 - 800 - 00155 - Roma - CC Roma EST"
    res2 = parse_store_address(addr2, "ROMA")
    assert res2["cap"] == "00155"
    assert res2["provincia"] == "RM"
    assert "Collatina" in res2["indirizzo"]


def test_format_store_ragione_sociale():
    rs = format_store_ragione_sociale("STRADIVARIUS", "CHIETI-MEGALO", "16647")
    assert rs == "Stradivarius Megalo - 16647"


def test_build_consegna_xml_structure_b0_and_b9():
    st_info = {
        "store_id": "1984",
        "brand": "ZARA HOME",
        "store_name": "ROM-COLA RIENZO",
        "cod_sga": 314,
        "giro": "ZA1",
        "ragione_sociale": "ZARA HOME Cola di Rienzo - 1984",
        "indirizzo": "Via Cola Di Rienzo 225/229",
        "cap": "00192",
        "localita": "Roma Cola di Rienzo",
        "provincia": "RM",
        "nazione": "IT",
    }
    # Test Barra 0
    xml_b0 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info=st_info,
        giro="ZA1",
        stop_sequence=1,
        peso_kg=1020.0,
        colli=68,
        volume_mc=7.2,
        is_ritiro=False,
        barra=0,
        tipo_specifica="B0",
        elemento_id="20261129120000",
        id_flusso="20261129120000",
    )
    root0 = ET.fromstring(xml_b0)
    assert root0.tag == "TrasportoEntrataOrdini_1_00"
    assert root0.find("IdFlusso").text == "20261129120000"
    ord0 = root0.find("Ordini/Ordine")
    assert ord0.find("TipoSpecifica").text == "B0"
    assert ord0.find("CarichiScarichi/CaricoScarico/CaricoMittenteCodice").text == "1"
    assert ord0.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioCodice").text == "314"
    assert ord0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um1Valore").text == "1020.000"

    # Test Barra 9
    xml_b9 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info=st_info,
        giro="ZA1",
        stop_sequence=1,
        peso_kg=1020.0,
        colli=68,
        volume_mc=7.2,
        is_ritiro=False,
        barra=9,
        tipo_specifica="B9",
        elemento_id="20261129120000",
        id_flusso="20261129120000",
    )
    root9 = ET.fromstring(xml_b9)
    ord9 = root9.find("Ordini/Ordine")
    assert ord9.find("TipoSpecifica").text == "B9"


def test_build_ritiro_xml_structure_b0_and_b9():
    st_info = {
        "store_id": "1984",
        "brand": "ZARA HOME",
        "store_name": "ROM-COLA RIENZO",
        "cod_sga": 314,
        "giro": "ZA1",
        "ragione_sociale": "ZARA HOME Cola di Rienzo - 1984",
        "indirizzo": "Via Cola Di Rienzo 225/229",
        "cap": "00192",
        "localita": "Roma Cola di Rienzo",
        "provincia": "RM",
        "nazione": "IT",
    }
    # Ritiro Barra 0
    xml_r0 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info=st_info,
        giro="ZA1",
        stop_sequence=1,
        peso_kg=0.0,
        colli=0,
        volume_mc=0.0,
        is_ritiro=True,
        barra=0,
        tipo_specifica="B0",
        elemento_id="20261129120000R",
        id_flusso="20261129120000",
    )
    root_r0 = ET.fromstring(xml_r0)
    ord_r0 = root_r0.find("Ordini/Ordine")
    assert ord_r0.find("TipoSpecifica").text == "B0"
    assert ord_r0.find("ElementoId").text == "20261129120000R"
    assert ord_r0.find("OrdineRiferimento").text == "ZA1-1R"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/CaricoMittenteCodice").text == "314"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioCodice").text == "1"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um1Valore").text == "0.000"

    # Ritiro Barra 9
    xml_r9 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info=st_info,
        giro="ZA1",
        stop_sequence=1,
        peso_kg=0.0,
        colli=0,
        volume_mc=0.0,
        is_ritiro=True,
        barra=9,
        tipo_specifica="B9",
        elemento_id="20261129120000R",
        id_flusso="20261129120000",
    )
    root_r9 = ET.fromstring(xml_r9)
    ord_r9 = root_r9.find("Ordini/Ordine")
    assert ord_r9.find("TipoSpecifica").text == "B9"


def test_generate_tms_xml_files_and_zip_4_types(tmp_path):
    records = [
        # Store 16647 (Barra 0)
        {
            "store_id": "16647",
            "giro": "ZA1",
            "delivery_date": "2026-10-28",
            "colli": 50,
            "volume_mc": 5.0,
            "peso_kg": 750.0,
            "barra": 0,
            "tipo_specifica": "B0",
        },
        # Store 1984 (Barra 9)
        {
            "store_id": "1984",
            "giro": "ZA1",
            "delivery_date": "2026-10-29",
            "colli": 30,
            "volume_mc": 3.0,
            "peso_kg": 450.0,
            "barra": 9,
            "tipo_specifica": "B9",
        }
    ]
    xml_files, zip_path = generate_tms_xml_files(records, output_dir=tmp_path)
    # 2 records, each creates 1 CONSEGNA and 1 RITIRO = 4 XMLs
    assert len(xml_files) == 4
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 4
        assert any("16647_ZA1_16647_B0_CONSEGNA.xml" in n or "16647_B0_CONSEGNA.xml" in n for n in namelist)
        assert any("16647_B0_RITIRO.xml" in n for n in namelist)
        assert any("1984_B9_CONSEGNA.xml" in n for n in namelist)
        assert any("1984_B9_RITIRO.xml" in n for n in namelist)


def test_create_tms_xml_zip_bytes_4_files():
    # 1 store having both B0 and B9 delivers 4 files total
    records = [
        {
            "store_id": "1984",
            "giro": "ZA1",
            "delivery_date": "2026-10-28",
            "colli": 50,
            "volume_mc": 5.0,
            "peso_kg": 750.0,
            "barra": 0,
            "tipo_specifica": "B0",
        },
        {
            "store_id": "1984",
            "giro": "ZA1",
            "delivery_date": "2026-10-29",
            "colli": 40,
            "volume_mc": 4.0,
            "peso_kg": 600.0,
            "barra": 9,
            "tipo_specifica": "B9",
        }
    ]
    raw_zip = create_tms_xml_zip_bytes(records)
    assert len(raw_zip) > 0
    import io
    with zipfile.ZipFile(io.BytesIO(raw_zip), "r") as zf:
        namelist = zf.namelist()
        # Exactly the 4 files requested by user:
        # 1. consegna_BARRA0
        # 2. ritiro_BARRA0
        # 3. consegna_BARRA9
        # 4. ritiro_BARRA9
        assert len(namelist) == 4
        assert any("1984_B0_CONSEGNA.xml" in n for n in namelist)
        assert any("1984_B0_RITIRO.xml" in n for n in namelist)
        assert any("1984_B9_CONSEGNA.xml" in n for n in namelist)
        assert any("1984_B9_RITIRO.xml" in n for n in namelist)


def test_unique_numeric_id_flusso():
    ids = [generate_unique_id_flusso() for _ in range(50)]
    assert len(set(ids)) == 50
    for uid in ids:
        assert uid.isdigit()
        assert len(uid) >= 14

    records = [
        {"store_id": "16647", "giro": "ZA1", "delivery_date": "2026-10-28", "colli": 10, "barra": 0},
        {"store_id": "16351", "giro": "ZA1", "delivery_date": "2026-10-28", "colli": 20, "barra": 9},
    ]
    raw_zip = create_tms_xml_zip_bytes(records)
    import io
    with zipfile.ZipFile(io.BytesIO(raw_zip), "r") as zf:
        id_flusso_values = []
        for name in zf.namelist():
            xml_content = zf.read(name).decode("utf-8")
            root = ET.fromstring(xml_content)
            id_f = root.find("IdFlusso").text
            assert id_f.isdigit()
            id_flusso_values.append(id_f)
        assert len(set(id_flusso_values)) == 4


def test_definitive_xml_structure_exact_match():
    """
    Verifica che il builder XML generi file perfettamente conformi ai tracciati
    definitivi inviati dall'utente (3680_B0_CONSEGNA, 3680_B0_RITIRO, 3680B_B9_CONSEGNA, 3680B_B9_RITIRO),
    inclusi i tag informativi anagrafici auto-chiudenti (<RagioneSociale/>, etc.)
    e i campi valorizzati attesi dal TMS BeOne.
    """
    # 1. Consegna B0
    xml_c0 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info={"cod_sga": 319, "store_id": "3680", "giro": "ZA4"},
        giro="ZA4",
        stop_sequence=4,
        peso_kg=2970.0,
        colli=198,
        volume_mc=14.33,
        is_ritiro=False,
        barra=0,
        tipo_specifica="B0",
        id_flusso="20261029121022",
        elemento_id="20261029121022",
    )
    root_c0 = ET.fromstring(xml_c0)
    assert root_c0.tag == "TrasportoEntrataOrdini_1_00"
    assert root_c0.find("IdFlusso").text == "20261029121022"
    ord_c0 = root_c0.find("Ordini/Ordine")
    assert ord_c0.find("TipoSpecifica").text == "B0"
    assert ord_c0.find("OrdineRiferimento").text == "ZA4-4"
    assert ord_c0.find("CarichiScarichi/CaricoScarico/CaricoMittenteCodice").text == "1"
    assert ord_c0.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioCodice").text == "319"
    assert ord_c0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um1Valore").text == "2970.000"
    assert ord_c0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um2Valore").text == "198"
    assert ord_c0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um3Valore").text == "14.330"
    # Tag anagrafici vuoti
    assert ord_c0.find("CarichiScarichi/CaricoScarico/CaricoMittenteInformazioniAnagrafiche/RagioneSociale").text is None
    assert ord_c0.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioInformazioniAnagrafiche/RagioneSociale").text is None

    # 2. Ritiro B0
    xml_r0 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info={"cod_sga": 319, "store_id": "3680", "giro": "ZA4"},
        giro="ZA4",
        stop_sequence=4,
        peso_kg=0.0,
        colli=0,
        volume_mc=0.0,
        is_ritiro=True,
        barra=0,
        tipo_specifica="B0",
        id_flusso="20261029121023",
        elemento_id="20261029121023R",
    )
    root_r0 = ET.fromstring(xml_r0)
    ord_r0 = root_r0.find("Ordini/Ordine")
    assert ord_r0.find("TipoSpecifica").text == "B0"
    assert ord_r0.find("ElementoId").text == "20261029121023R"
    assert ord_r0.find("OrdineRiferimento").text == "ZA4-4R"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/CaricoMittenteCodice").text == "319"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioCodice").text == "1"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um1Valore").text == "0.000"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um2Valore").text == "0"
    assert ord_r0.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um3Valore").text == "0.000"

    # 3. Consegna B9
    xml_c9 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info={"cod_sga": 319, "store_id": "3680B", "giro": "ZA15"},
        giro="ZA15",
        stop_sequence=2,
        peso_kg=1001.087,
        colli=67,
        volume_mc=6.14,
        is_ritiro=False,
        barra=9,
        tipo_specifica="B9",
        id_flusso="20261029121056",
        elemento_id="20261029121056",
    )
    root_c9 = ET.fromstring(xml_c9)
    ord_c9 = root_c9.find("Ordini/Ordine")
    assert ord_c9.find("TipoSpecifica").text == "B9"
    assert ord_c9.find("OrdineRiferimento").text == "ZA15-2"
    assert ord_c9.find("CarichiScarichi/CaricoScarico/CaricoMittenteCodice").text == "1"
    assert ord_c9.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioCodice").text == "319"
    assert ord_c9.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um1Valore").text == "1001.087"
    assert ord_c9.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um2Valore").text == "67"
    assert ord_c9.find("CarichiScarichi/CaricoScarico/Merci/Merce/Um3Valore").text == "6.140"

    # 4. Ritiro B9
    xml_r9 = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info={"cod_sga": 319, "store_id": "3680B", "giro": "ZA15"},
        giro="ZA15",
        stop_sequence=2,
        peso_kg=0.0,
        colli=0,
        volume_mc=0.0,
        is_ritiro=True,
        barra=9,
        tipo_specifica="B9",
        id_flusso="20261029121057",
        elemento_id="20261029121057R",
    )
    root_r9 = ET.fromstring(xml_r9)
    ord_r9 = root_r9.find("Ordini/Ordine")
    assert ord_r9.find("TipoSpecifica").text == "B9"
    assert ord_r9.find("ElementoId").text == "20261029121057R"
    assert ord_r9.find("OrdineRiferimento").text == "ZA15-2R"
    assert ord_r9.find("CarichiScarichi/CaricoScarico/CaricoMittenteCodice").text == "319"
    assert ord_r9.find("CarichiScarichi/CaricoScarico/ScaricoDestinatarioCodice").text == "1"


def test_pull_and_bear_xml_escape_and_validation():
    """
    Test that store 5405 (PULL&BEAR MAC-ADRIATICO) or any brand/address with '&'
    properly escapes '&' to '&amp;' so XML parsers do not fail with
    'EntityRef: expecting ;'.
    """
    st_5405 = {
        "store_id": "5405",
        "brand": "PULL&BEAR",
        "store_name": "MAC-ADRIATICO",
        "cod_sga": 282,
        "giro": "ZA2",
        "ragione_sociale": "Pull&Bear Adriatico - 5405",
        "indirizzo": "Via S. Costantino & Figli - 98",
        "cap": "62012",
        "localita": "Civ. M. CUORE ADRIATICO",
        "provincia": "MC",
        "nazione": "IT",
    }
    xml_consegna = build_tms_order_xml(
        delivery_date="2026-10-27",
        store_info=st_5405,
        giro="ZA2",
        stop_sequence=1,
        peso_kg=150.0,
        colli=10,
        volume_mc=1.05,
        is_ritiro=False,
        barra=0,
        tipo_specifica="B0",
    )
    # Must parse successfully with ElementTree without raising XML parse errors
    root = ET.fromstring(xml_consegna)
    assert root.tag == "TrasportoEntrataOrdini_1_00"


def test_exact_116_files_no_duplicate_or_numeric_suffix(tmp_path):
    """
    Test standard cycle: 48 B0 stores + 10 B9 stores = 58 stores.
    Must generate exactly 116 files:
      - 48 Consegne B0
      - 48 Ritiri B0
      - 10 Consegne B9
      - 10 Ritiri B9
    Filenames must NEVER contain stop_sequence or numeric suffixes like _1_ or _2_.
    Calling generate_tms_xml_files twice on the same directory MUST NOT create 232 files.
    """
    records = []
    # 48 stores Barra 0
    for i in range(1, 49):
        records.append({
            "store_id": f"100{i:02d}",
            "giro": f"ZA{(i % 8) + 1}",
            "delivery_date": "2026-10-28",
            "colli": 50 + i,
            "volume_mc": 5.0,
            "peso_kg": 750.0,
            "barra": 0,
            "tipo_specifica": "B0",
        })
    # 10 stores Barra 9
    for i in range(1, 11):
        records.append({
            "store_id": f"200{i:02d}",
            "giro": f"ZA{(i % 4) + 1}",
            "delivery_date": "2026-10-29",
            "colli": 30 + i,
            "volume_mc": 3.0,
            "peso_kg": 450.0,
            "barra": 9,
            "tipo_specifica": "B9",
        })

    assert len(records) == 58

    # Prima generazione
    files1, zip_path1 = generate_tms_xml_files(records, output_dir=tmp_path)
    assert len(files1) == 116
    assert zip_path1.exists()

    xml_files_in_dir = list(tmp_path.glob("*.xml"))
    assert len(xml_files_in_dir) == 116

    b0_c = [f for f in xml_files_in_dir if "_B0_CONSEGNA.xml" in f.name]
    b0_r = [f for f in xml_files_in_dir if "_B0_RITIRO.xml" in f.name]
    b9_c = [f for f in xml_files_in_dir if "_B9_CONSEGNA.xml" in f.name]
    b9_r = [f for f in xml_files_in_dir if "_B9_RITIRO.xml" in f.name]

    assert len(b0_c) == 48
    assert len(b0_r) == 48
    assert len(b9_c) == 10
    assert len(b9_r) == 10

    # Verifica assenza assoluta di suffissi numerici intermedi come _1_ o _2_
    for f in xml_files_in_dir:
        stem = f.stem
        # Non deve contenere _B0_1_ o _B0_2_ o simili
        assert not re.search(r"_(B0|B9)_\d+_(CONSEGNA|RITIRO)", stem), f"File has unexpected numeric suffix: {f.name}"
        # Deve terminare rigorosamente con _B0_CONSEGNA, _B0_RITIRO, _B9_CONSEGNA, _B9_RITIRO
        assert stem.endswith(("_B0_CONSEGNA", "_B0_RITIRO", "_B9_CONSEGNA", "_B9_RITIRO")), f"Invalid name ending: {f.name}"

    # SECONDA GENERAZIONE SULLA STESSA CARTELLA (simulazione refresh / rerun Streamlit)
    files2, zip_path2 = generate_tms_xml_files(records, output_dir=tmp_path)
    xml_files_after_rerun = list(tmp_path.glob("*.xml"))
    # NON deve raddoppiare a 232! Deve rimanere esattamente a 116 file puliti
    assert len(xml_files_after_rerun) == 116
    assert len(files2) == 116

    # Verifica contenuto archivio ZIP
    with zipfile.ZipFile(zip_path2, "r") as zf:
        zip_names = zf.namelist()
        assert len(zip_names) == 116
        for name in zip_names:
            assert not re.search(r"_(B0|B9)_\d+_(CONSEGNA|RITIRO)", name), f"ZIP entry has numeric suffix: {name}"

    # Verifica anche la generazione diretta in memoria tramite create_tms_xml_zip_bytes
    zip_bytes = create_tms_xml_zip_bytes(records)
    import io
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf_mem:
        mem_names = zf_mem.namelist()
        assert len(mem_names) == 116

