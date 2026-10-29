"""
Unit tests for TMS XML Exporter (TrasportoEntrataOrdini_1_00).
Verifies XML generation against desktop sample specifications for Consegna and Ritiro.
"""

from pathlib import Path
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


def test_build_consegna_xml_structure():
    st_info = {
        "store_id": "16647",
        "brand": "STRADIVARIUS",
        "store_name": "CHIETI-MEGALO",
        "cod_sga": 298,
        "giro": "ZA1",
        "ragione_sociale": "Stradivarius Megalo - 16647",
        "indirizzo": "Località santa Filomena",
        "cap": "66100",
        "localita": "Chieti Megalò",
        "provincia": "CH",
        "nazione": "IT",
    }
    xml_str = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info=st_info,
        giro="ZA1",
        stop_sequence=1,
        peso_kg=1020.0,
        colli=68,
        volume_mc=7.2,
        is_ritiro=False,
        elemento_id="20261129120000",
        id_flusso="20261129120000",
    )
    root = ET.fromstring(xml_str)
    assert root.tag == "TrasportoEntrataOrdini_1_00"
    assert root.find("IdFlusso").text == "20261129120000"

    ordine = root.find("Ordini/Ordine")
    assert ordine.find("Anno").text == "2026"
    assert ordine.find("Filiale").text == "SE"
    assert ordine.find("ElementoId").text == "20261129120000"
    assert ordine.find("OrdineRiferimento").text == "ZA1-1"
    assert ordine.find("RiferimentoInterno").text == "ZA1-1"

    carico_scarico = ordine.find("CarichiScarichi/CaricoScarico")
    # Mittente Lacchi
    assert carico_scarico.find("CaricoMittenteCodice").text == "1"
    assert carico_scarico.find("CaricoMittenteInformazioniAnagrafiche/RagioneSociale").text == LACCHI_HUB["ragione_sociale"]

    # Destinatario Negozio
    assert carico_scarico.find("ScaricoDestinatarioCodice").text == "298"
    assert carico_scarico.find("ScaricoDestinatarioInformazioniAnagrafiche/RagioneSociale").text == "Stradivarius Megalo - 16647"

    # Merci
    merce = carico_scarico.find("Merci/Merce")
    assert merce.find("Codice").text == "VAR"
    assert merce.find("Um1Codice").text == "KG"
    assert merce.find("Um1Valore").text == "1020.000"
    assert merce.find("Um2Codice").text == "CL"
    assert merce.find("Um2Valore").text == "68"
    assert merce.find("Um3Codice").text == "MC"
    assert merce.find("Um3Valore").text == "7.200"


def test_build_ritiro_xml_structure():
    st_info = {
        "store_id": "16647",
        "brand": "STRADIVARIUS",
        "store_name": "CHIETI-MEGALO",
        "cod_sga": 298,
        "giro": "ZA1",
        "ragione_sociale": "Stradivarius Megalo - 16647",
        "indirizzo": "Località santa Filomena",
        "cap": "66100",
        "localita": "Chieti Megalò",
        "provincia": "CH",
        "nazione": "IT",
    }
    xml_str = build_tms_order_xml(
        delivery_date="2026-11-29",
        store_info=st_info,
        giro="ZA1",
        stop_sequence=1,
        peso_kg=0.0,
        colli=0,
        volume_mc=0.0,
        is_ritiro=True,
        elemento_id="20261129120000R",
        id_flusso="20261129120000",
    )
    root = ET.fromstring(xml_str)
    assert root.tag == "TrasportoEntrataOrdini_1_00"

    ordine = root.find("Ordini/Ordine")
    assert ordine.find("ElementoId").text == "20261129120000R"
    assert ordine.find("OrdineRiferimento").text == "ZA1-1R"
    assert ordine.find("RiferimentoInterno").text == "ZA1-1R"

    carico_scarico = ordine.find("CarichiScarichi/CaricoScarico")
    # Mittente Negozio
    assert carico_scarico.find("CaricoMittenteCodice").text == "298"
    assert carico_scarico.find("CaricoMittenteInformazioniAnagrafiche/RagioneSociale").text == "Stradivarius Megalo - 16647"

    # Destinatario Lacchi
    assert carico_scarico.find("ScaricoDestinatarioCodice").text == "1"
    assert carico_scarico.find("ScaricoDestinatarioInformazioniAnagrafiche/RagioneSociale").text == LACCHI_HUB["ragione_sociale"]

    # Merci a 0
    merce = carico_scarico.find("Merci/Merce")
    assert merce.find("Um1Valore").text == "0.000"
    assert merce.find("Um2Valore").text == "0"
    assert merce.find("Um3Valore").text == "0.000"


def test_generate_tms_xml_files_and_zip(tmp_path):
    records = [
        {
            "store_id": "16647",
            "giro": "ZA1",
            "delivery_date": "2026-10-28",
            "colli": 50,
            "volume_mc": 5.0,
            "peso_kg": 750.0,
        },
        {
            "store_id": "16351",
            "giro": "ZA1",
            "delivery_date": "2026-10-28",
            "colli": 30,
            "volume_mc": 3.0,
            "peso_kg": 450.0,
        }
    ]
    xml_files, zip_path = generate_tms_xml_files(records, output_dir=tmp_path)
    # 2 files per store: 2 * 2 = 4 XMLs
    assert len(xml_files) == 4
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 4
        assert any("16647_CONSEGNA.xml" in n for n in namelist)
        assert any("16647_RITIRO.xml" in n for n in namelist)
        assert any("16351_CONSEGNA.xml" in n for n in namelist)
        assert any("16351_RITIRO.xml" in n for n in namelist)


def test_create_tms_xml_zip_bytes():
    records = [
        {
            "store_id": "16647",
            "giro": "ZA1",
            "delivery_date": "2026-10-28",
            "colli": 50,
            "volume_mc": 5.0,
            "peso_kg": 750.0,
        }
    ]
    raw_zip = create_tms_xml_zip_bytes(records)
    assert len(raw_zip) > 0
    import io
    with zipfile.ZipFile(io.BytesIO(raw_zip), "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        assert any("16647_CONSEGNA.xml" in n for n in namelist)
        assert any("16647_RITIRO.xml" in n for n in namelist)
