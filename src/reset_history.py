import sqlite3
from pathlib import Path
import shutil

from src.config import DB_PATH, OUTPUT_DIR, DATA_DIR

def reset_all_history():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tables_to_clear = [
        'forecast_raw', 'other_items', 'actual_deliveries',
        'planning_results', 'spunta_arrivi', 'sga_flows', 'runs'
    ]

    for t in tables_to_clear:
        cur.execute(f"DELETE FROM {t}")
        print(f"Cleared table {t}")

    cur.execute("DELETE FROM sqlite_sequence WHERE name != 'stores'")
    conn.commit()
    conn.close()

    # Clean output folder
    if OUTPUT_DIR.exists():
        for p in OUTPUT_DIR.iterdir():
            if p.is_dir() and p.name.startswith("run_"):
                shutil.rmtree(p)
                print(f"Deleted output folder {p.name}")

    # Clean data/downloads folder
    dl_dir = DATA_DIR / "downloads"
    if dl_dir.exists():
        for p in dl_dir.iterdir():
            if p.is_dir():
                shutil.rmtree(p)
                print(f"Deleted download cache {p.name}")

    print("Reset completed successfully! Stores count preserved.")

if __name__ == "__main__":
    reset_all_history()
