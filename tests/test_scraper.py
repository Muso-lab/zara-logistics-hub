import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.scraper import InditexExtranetScraper, is_ecom_shipment


def test_scraper_init():
    scraper = InditexExtranetScraper(headless=True)
    assert scraper.username == "plt_it_transmec_ro"
    assert scraper.headless is True


def test_scraper_notify():
    notified = []
    def callback(msg, pct):
        notified.append((msg, pct))

    scraper = InditexExtranetScraper(progress_callback=callback)
    scraper._notify("Test message", 50)
    assert len(notified) == 1
    assert notified[0] == ("Test message", 50)


def test_is_ecom_shipment_detection():
    assert is_ecom_shipment({"cod_envio": "ECOM ROMA BSK"}) is True
    assert is_ecom_shipment({"cod_envio": "BSK-EC-ONTIGOLA"}) is True
    assert is_ecom_shipment({"camion": "CAMION EC 12"}) is True
    assert is_ecom_shipment({"camion": "MEZZO-EC-01"}) is True
    assert is_ecom_shipment({"full_text": "Spedizione EC diretta"}) is True

    # Negative cases (avoid false positives)
    assert is_ecom_shipment({"cod_envio": "R4366BDB + MECO"}) is False
    assert is_ecom_shipment({"cod_envio": "BSK ROMA DECO SESE CONSOL"}) is False
    assert is_ecom_shipment({"cod_envio": "FERCAM DIRECTO"}) is False
    assert is_ecom_shipment({"cod_envio": "PAQUETERIA ITALIA"}) is False

