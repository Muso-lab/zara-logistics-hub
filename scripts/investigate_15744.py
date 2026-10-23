import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from src.config import DB_PATH

conn = sqlite3.connect(DB_PATH)

import json

print("--- STORES in DB ---")
df_s = pd.read_sql("SELECT store_id, store_name, brand, giro FROM stores WHERE store_id LIKE '15%' OR store_id LIKE '14%'", conn)
print(df_s)

print("\n--- PLANNER TEMPLATE SHOES ROWS ---")
with open("data/planner_template.json", encoding="utf-8") as f:
    pt = json.load(f)

shoes_rows = [r for r in pt if "SHOES" in str(r.get("brand")).upper() or "CALZ" in str(r.get("brand")).upper()]
print(f"Total SHOES rows in planner template: {len(shoes_rows)}")
for r in shoes_rows:
    print(r)

print("\n--- SPUNTA TEMPLATE SHOES ROWS ---")
with open("data/spunta_template.json", encoding="utf-8") as f:
    st_rows = json.load(f)

st_shoes = [r for r in st_rows if "SHOES" in str(r.get("brand")).upper() or "CALZ" in str(r.get("brand")).upper() or "157" in str(r.get("store_id"))]
print(f"Spunta template shoes/157: {len(st_shoes)}")
for r in st_shoes:
    print(r)

conn.close()
