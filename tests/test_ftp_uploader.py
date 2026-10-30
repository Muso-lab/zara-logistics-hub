import ftplib
import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.ftp_uploader import (
    DEFAULT_FTP_CONFIG,
    get_tms_ftp_config,
    ensure_ftp_directory,
    upload_xml_files_to_ftp,
    test_tms_ftp_connection as check_ftp_conn,
)


def test_default_ftp_config():
    cfg = get_tms_ftp_config()
    assert cfg["host"] == "servizi.lacchi.com"
    assert cfg["port"] == 2121
    assert cfg["user"] == "user-sga-464531"
    assert cfg["password"] == "CHyFe9u!R3y@gJQr2hvs8nyd*ddxYb"
    assert cfg["remote_dir"] == "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA"


def test_ensure_ftp_directory():
    mock_ftp = MagicMock(spec=ftplib.FTP)
    ensure_ftp_directory(mock_ftp, "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA")

    mock_ftp.cwd.assert_any_call("/")
    mock_ftp.cwd.assert_any_call("IMPORT_SGA")
    mock_ftp.cwd.assert_any_call("RICEZIONE_ORDINI")
    mock_ftp.cwd.assert_any_call("ZARA")


def test_upload_xml_files_to_ftp_mocked(tmp_path):
    # Create 3 dummy XML files
    f1 = tmp_path / "3680_B0_CONSEGNA.xml"
    f2 = tmp_path / "3680_B0_RITIRO.xml"
    f3 = tmp_path / "3680B_B9_CONSEGNA.xml"

    f1.write_text("<xml>1</xml>", encoding="utf-8")
    f2.write_text("<xml>2</xml>", encoding="utf-8")
    f3.write_text("<xml>3</xml>", encoding="utf-8")

    stored_cmds = []

    mock_ftp_inst = MagicMock(spec=ftplib.FTP)
    def fake_storbinary(cmd, fp):
        stored_cmds.append((cmd, fp.read()))
        return "226 Transfer complete"

    mock_ftp_inst.storbinary.side_effect = fake_storbinary

    with patch("ftplib.FTP", return_value=mock_ftp_inst):
        res = upload_xml_files_to_ftp([f1, f2, f3])

        assert res["status"] == "ok"
        assert res["uploaded_count"] == 3
        assert res["total_count"] == 3
        assert len(res["failed_files"]) == 0
        assert mock_ftp_inst.connect.called
        assert mock_ftp_inst.connect.call_args[0][0] == "servizi.lacchi.com"
        assert mock_ftp_inst.connect.call_args[0][1] == 2121
        assert mock_ftp_inst.login.call_args[0][0] == "user-sga-464531"
        assert mock_ftp_inst.login.call_args[0][1] == "CHyFe9u!R3y@gJQr2hvs8nyd*ddxYb"

        assert len(stored_cmds) == 3
        assert stored_cmds[0][0] == "STOR 3680_B0_CONSEGNA.xml"
        assert stored_cmds[0][1] == b"<xml>1</xml>"
        assert stored_cmds[1][0] == "STOR 3680_B0_RITIRO.xml"
        assert stored_cmds[2][0] == "STOR 3680B_B9_CONSEGNA.xml"


def test_upload_xml_tuple_data_mocked():
    files = [
        ("file_a.xml", b"<dataA/>"),
        ("file_b", "<dataB/>"),
    ]
    stored_files = []

    mock_ftp_inst = MagicMock(spec=ftplib.FTP)
    def fake_storbinary(cmd, fp):
        stored_files.append((cmd, fp.read()))
        return "226 OK"

    mock_ftp_inst.storbinary.side_effect = fake_storbinary

    with patch("ftplib.FTP", return_value=mock_ftp_inst):
        res = upload_xml_files_to_ftp(files)
        assert res["status"] == "ok"
        assert res["uploaded_count"] == 2
        assert stored_files[0][0] == "STOR file_a.xml"
        assert stored_files[0][1] == b"<dataA/>"
        assert stored_files[1][0] == "STOR file_b.xml"
        assert stored_files[1][1] == b"<dataB/>"


def test_upload_empty_files():
    res = upload_xml_files_to_ftp([])
    assert res["status"] == "error"
    assert res["uploaded_count"] == 0


def test_upload_connection_failure():
    mock_ftp_inst = MagicMock(spec=ftplib.FTP)
    mock_ftp_inst.connect.side_effect = ConnectionRefusedError("Connection refused")

    with patch("ftplib.FTP", return_value=mock_ftp_inst):
        res = upload_xml_files_to_ftp([("test.xml", b"<xml/>")])
        assert res["status"] == "error"
        assert "Connection refused" in res["message"]


def test_check_tms_ftp_connection_mocked():
    mock_ftp_inst = MagicMock(spec=ftplib.FTP)
    mock_ftp_inst.pwd.return_value = "/IMPORT_SGA/RICEZIONE_ORDINI/ZARA"

    with patch("ftplib.FTP", return_value=mock_ftp_inst):
        ok, msg = check_ftp_conn()
        assert ok is True
        assert "Connessione FTP stabilita con successo" in msg
