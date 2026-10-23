import argparse
import sys
from pathlib import Path
from datetime import datetime, date, timedelta

from src.config import (
    DEFAULT_NETWORK_INPUT_DIR,
    DEFAULT_NETWORK_OUTPUT_DIR,
    DATA_DIR
)
from src.pipeline import run_pipeline
from src.scraper import InditexExtranetScraper
from src.utils import get_cycle_date_range, format_number_it, format_date_it


def main():
    parser = argparse.ArgumentParser(description="Zara Logistics Automation CLI Tool")
    parser.add_argument("--run-date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="Run date (YYYY-MM-DD)")
    parser.add_argument("--cycle", type=str, default="GIOV-DOM", choices=["GIOV-DOM", "LUN-MER"], help="Delivery cycle")
    parser.add_argument("--input-dir", type=str, default=str(DEFAULT_NETWORK_INPUT_DIR), help="Directory containing input files")
    parser.add_argument("--from-extranet", action="store_true", help="Download input files automatically from Inditex Extranet")
    parser.add_argument("--desde", type=str, default=None, help="Extranet filter start date (YYYY-MM-DD)")
    parser.add_argument("--hasta", type=str, default=None, help="Extranet filter end date (YYYY-MM-DD)")
    parser.add_argument("--notes", type=str, default="CLI execution", help="Optional run notes")
    parser.add_argument("--save-to-network", action="store_true", help="Also save copies of generated files to network folder")

    args = parser.parse_args()

    input_path = Path(args.input_dir)

    if args.from_extranet:
        print("=== Downloading files from Inditex Extranet ===")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_path = DATA_DIR / "downloads" / f"cli_{ts}"
        input_path.mkdir(parents=True, exist_ok=True)

        if args.desde and args.hasta:
            d_desde = datetime.strptime(args.desde, "%Y-%m-%d").date()
            d_hasta = datetime.strptime(args.hasta, "%Y-%m-%d").date()
        else:
            ref_dt = datetime.strptime(args.run_date, "%Y-%m-%d").date()
            d_desde, d_hasta = get_cycle_date_range(args.cycle, ref_dt)

        print(f"Extranet Date Range ({args.cycle}): {format_date_it(d_desde)} -> {format_date_it(d_hasta)}")

        scraper = InditexExtranetScraper(headless=True)
        res_scrape = scraper.scrape_all(desde_date=d_desde, hasta_date=d_hasta, output_dir=input_path)
        print(f"Extracted {res_scrape['total_shipments_found']} shipments ({res_scrape['other_files_downloaded']} other files).")

    if not input_path.exists():
        print(f"Error: Input directory does not exist: {input_path}")
        sys.exit(1)

    total_path = input_path / "TOTAL.xls"
    shoes_path = input_path / "SHOES.xls"
    texile_path = input_path / "TEXILE.xls"
    ecom_path = input_path / "ECOM.xls"
    other_path = input_path / "OTHER"
    esp_path = DEFAULT_NETWORK_INPUT_DIR / "esportazione.xlsx"
    if not esp_path.exists():
        esp_path = input_path / "esportazione.xlsx"

    print(f"\n=== Starting Zara Logistics Processing ===")
    print(f"Date: {args.run_date} | Cycle: {args.cycle}")
    print(f"Input Directory: {input_path}")

    res = run_pipeline(
        total_source=total_path if total_path.exists() else None,
        shoes_source=shoes_path if shoes_path.exists() else None,
        texile_source=texile_path if texile_path.exists() else None,
        ecom_source=ecom_path if ecom_path.exists() else None,
        other_source=other_path if other_path.exists() else None,
        esportazione_source=esp_path if esp_path.exists() else None,
        run_date=args.run_date,
        cycle_type=args.cycle,
        notes=args.notes,
        save_to_network=args.save_to_network
    )

    totals = res["totals"]
    print(f"\nProcessing Completed Successfully! Run ID: #{res['run_id']}")
    print(f"  - Total Colli:   {format_number_it(totals['total_bultos'], 0)}")
    print(f"  - Total Volume:  {format_number_it(totals['total_volume'], 2)} m3")
    print(f"  - Total Weight:  {format_number_it(totals['total_weight'], 0)} kg")
    print(f"  - Total Pedane:  {format_number_it(totals['total_pedane'], 0)}")
    print(f"\nGenerated Files:")
    for name, p in res["exported_files"].items():
        print(f"  - [{name.upper()}]: {p}")


if __name__ == "__main__":
    main()
