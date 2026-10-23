import pytest
from pathlib import Path
from src.access_reader import (
    DEFAULT_ACCESS_PATH,
    check_access_connection,
    get_available_dates,
    fetch_actual_deliveries_df,
    fetch_bolle_summary_df
)


def test_access_connection_and_queries():
    if not DEFAULT_ACCESS_PATH.exists():
        pytest.skip("Access MDB file not present on Desktop, skipping test.")

    # 1. Test connection
    ok, msg, info = check_access_connection(DEFAULT_ACCESS_PATH)
    assert ok is True
    assert "total_deliveries" in info
    assert info["total_deliveries"] > 0

    # 2. Test get_available_dates
    dates = get_available_dates(DEFAULT_ACCESS_PATH, limit=5)
    assert len(dates) > 0
    test_date = dates[0]

    # 3. Test fetch_actual_deliveries_df
    df_act = fetch_actual_deliveries_df(DEFAULT_ACCESS_PATH, target_date=test_date)
    assert not df_act.empty
    expected_cols = [
        "ID_STORE", "TIPO_CONS", "TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM",
        "TOT_OTHERS", "TOT_VARIO", "TOT_CONT", "colli_mat_vario", "stringa"
    ]
    for col in expected_cols:
        assert col in df_act.columns

    # 4. Test fetch_bolle_summary_df
    df_bolle = fetch_bolle_summary_df(DEFAULT_ACCESS_PATH, target_date=test_date)
    assert not df_bolle.empty
    assert "TOTALE_COLLI" in df_bolle.columns
    assert "ID_STORE" in df_bolle.columns
