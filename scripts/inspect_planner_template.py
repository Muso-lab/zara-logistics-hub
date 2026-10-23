import json

with open("data/planner_template.json", encoding="utf-8") as f:
    pt = json.load(f)

print("--- ROWS IN PLANNER TEMPLATE ---")
for r in pt:
    sc = str(r["store_code"])
    br = str(r["brand"])
    if any(k in sc for k in ["3680", "15733", "14825", "5349", "6525", "1265"]):
        print(f"Row {r['row_idx']} | code={sc} | brand={br} | name={r['store_name']}")
