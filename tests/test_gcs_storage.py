import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.gcs_storage import (
    DEFAULT_GCS_CONFIG,
    get_gcs_config,
    save_gcs_config,
    upload_xml_files_to_gcs,
    generate_windows_download_script,
)


def test_default_gcs_config():
    cfg = get_gcs_config()
    assert cfg["bucket_name"] == "lacchi-tms-zara"
    assert "IMPORT_SGA" in cfg["remote_prefix"]
    assert "IMPORT_SGA" in cfg["local_destination_dir"]


def test_save_gcs_config(tmp_path):
    custom_cfg = {
        "bucket_name": "custom-bucket-test",
        "remote_prefix": "CUSTOM/PREFIX",
        "local_destination_dir": r"D:\TEST\INBOX"
    }
    with patch("src.gcs_storage.GCS_CONFIG_FILE", tmp_path / "gcs_cfg.json"):
        ok = save_gcs_config(custom_cfg)
        assert ok is True
        disk = json.loads((tmp_path / "gcs_cfg.json").read_text(encoding="utf-8"))
        assert disk["bucket_name"] == "custom-bucket-test"
        assert disk["remote_prefix"] == "CUSTOM/PREFIX"


def test_generate_windows_download_script():
    ps1, bat = generate_windows_download_script({
        "bucket_name": "mio-bucket-test",
        "remote_prefix": "MIA/CARTELLA",
        "local_destination_dir": r"C:\MIA_CARTELLA_TMS"
    })
    assert "$BucketName = \"mio-bucket-test\"" in ps1
    assert "$RemotePrefix = \"MIA/CARTELLA\"" in ps1
    assert "C:\\MIA_CARTELLA_TMS" in ps1
    assert "powershell" in bat


def test_upload_xml_files_to_gcs_empty():
    res = upload_xml_files_to_gcs([])
    assert res["status"] == "error"
    assert res["uploaded_count"] == 0


def test_upload_xml_files_to_gcs_rest_mocked(tmp_path):
    f1 = tmp_path / "3680_B0_CONSEGNA.xml"
    f1.write_text("<test/>", encoding="utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp):
        res = upload_xml_files_to_gcs([f1], config={"bucket_name": "test-bkt", "remote_prefix": "TEST"})
        assert res["status"] == "ok"
        assert res["uploaded_count"] == 1
        assert res["bucket"] == "test-bkt"
