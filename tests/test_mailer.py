import pytest
from pathlib import Path
from src.db import init_db, get_email_config, save_email_config
from src.mailer import send_operativa_email, send_test_email, build_operativa_zip


def test_email_config_persistence(tmp_path):
    test_db = tmp_path / "test_zara.db"
    init_db(db_path=test_db)

    # Default config
    cfg = get_email_config(db_path=test_db)
    assert "smtp_host" in cfg
    assert "default_to" in cfg
    assert cfg["smtp_port"] == 587

    # Save new config
    cfg["smtp_host"] = "smtp.custom.test"
    cfg["smtp_port"] = 465
    cfg["smtp_user"] = "test@custom.test"
    cfg["default_to"] = "dest1@test.com, dest2@test.com"
    save_email_config(cfg, db_path=test_db)

    loaded = get_email_config(db_path=test_db)
    assert loaded["smtp_host"] == "smtp.custom.test"
    assert loaded["smtp_port"] == 465
    assert loaded["smtp_user"] == "test@custom.test"
    assert "dest1@test.com" in loaded["default_to"]


def test_send_operativa_email_simulation(tmp_path):
    dummy_file = tmp_path / "test_doc.xlsx"
    dummy_file.write_text("dummy content")

    # Simulation when no host/user/pass
    ok, msg = send_operativa_email(
        recipients=["test@example.com"],
        subject="Test Oggetto",
        body_text="Test Body",
        attachment_paths=[dummy_file],
        smtp_config={"smtp_host": "", "smtp_user": "", "smtp_password": ""}
    )
    assert ok is True
    assert "Simulazione" in msg


def test_send_test_email_validation():
    # Empty recipient
    ok, msg = send_test_email("", smtp_config={})
    assert ok is False
    assert "non valido" in msg

    # Missing credentials
    ok, msg = send_test_email("dest@test.com", smtp_config={"smtp_host": ""})
    assert ok is False
    assert "incompleti" in msg


def test_build_operativa_zip(tmp_path):
    f1 = tmp_path / "f1.txt"
    f2 = tmp_path / "f2.txt"
    f1.write_text("file 1")
    f2.write_text("file 2")

    zip_out = tmp_path / "out.zip"
    build_operativa_zip({"f1.txt": f1, "f2.txt": f2}, zip_out)
    assert zip_out.exists()
    assert zip_out.stat().st_size > 0
