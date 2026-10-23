"""
Automated Scraper for Inditex Extranet (Plataforma / Buzon).
Extracts TOTAL.xls, SHOES.xls, ECOM.xls, TEXILE.xls and all OTHER/*.xls packages.
"""

import os
import sys
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
import re

from src.config import (
    EXTRANET_LOGIN_URL,
    EXTRANET_BUZON_URL,
    EXTRANET_DEFAULT_USER,
    EXTRANET_DEFAULT_PASS,
)


def is_ecom_shipment(row_data: Dict[str, Any]) -> bool:
    """
    Identifies if a shipment is E-Commerce (ECOM):
    - Contains 'ecom' in cod_envio or camion
    - Contains standalone acronym/sigla 'EC' (e.g. -EC-, EC 12, /EC/) in cod_envio or camion/mezzo
    """
    targets = [
        str(row_data.get("cod_envio", "")),
        str(row_data.get("camion", "")),
        str(row_data.get("transporte", "")),
        str(row_data.get("full_text", ""))
    ]
    combined = " ".join(targets)
    if "ecom" in combined.lower():
        return True
    if re.search(r'(^|[\s\-_/.,;:()\[\]])EC([\s\-_/.,;:()\[\]]|$)', combined, re.IGNORECASE):
        return True
    return False


class InditexExtranetScraper:
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ):
        self.username = username or EXTRANET_DEFAULT_USER
        self.password = password or EXTRANET_DEFAULT_PASS
        self.headless = headless
        self.progress_callback = progress_callback or (lambda msg, pct: None)

    def _notify(self, msg: str, pct: int):
        print(f"[{pct}%] {msg}")
        self.progress_callback(msg, pct)

    def scrape_all(
        self,
        desde_date: datetime.date,
        hasta_date: datetime.date,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """
        Executes complete extranet workflow:
        1. Login
        2. Navigate to Buzon Plataforma
        3. Search shipments by date range
        4. Download TOTAL.xls, SHOES.xls, ECOM.xls, TEXILE.xls
        5. Scan textile shipments and download all OTHER/*.xls files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        other_dir = output_dir / "OTHER"
        other_dir.mkdir(parents=True, exist_ok=True)

        result_summary = {
            "success": False,
            "error": None,
            "total_shipments_found": 0,
            "shoes_shipments": 0,
            "ecom_shipments": 0,
            "textile_shipments": 0,
            "other_files_downloaded": 0,
            "files": {},
        }

        self._notify("Avvio del browser per connessione a Extranet Inditex...", 5)

        with sync_playwright() as p:
            browser = None
            for ch in [None, "msedge", "chrome"]:
                try:
                    if ch:
                        browser = p.chromium.launch(channel=ch, headless=self.headless)
                    else:
                        browser = p.chromium.launch(headless=self.headless)
                    break
                except Exception:
                    continue
            if browser is None:
                raise RuntimeError("Impossibile avviare il browser Chromium/Edge per Playwright.")

            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            try:
                # 1. Login
                self._notify(f"Accesso all'Extranet Inditex ({self.username})...", 10)
                self._login(page)

                # 2. Go to Buzon Plataforma
                self._notify("Apertura Buzón Plataforma...", 20)
                page.goto(EXTRANET_BUZON_URL, timeout=30000)
                time.sleep(2)

                # 3. Search Date Range
                self._notify(
                    f"Ricerca spedizioni dal {desde_date.strftime('%d/%m/%Y')} al {hasta_date.strftime('%d/%m/%Y')}...",
                    25,
                )
                self._search_shipments(page, desde_date, hasta_date)

                # 4. Read Shipment Rows
                self._notify("Analisi lista spedizioni trovate...", 35)
                rows_data = self._get_shipment_rows(page)
                tot_count = len(rows_data)
                result_summary["total_shipments_found"] = tot_count

                if tot_count == 0:
                    raise ValueError(
                        f"Nessuna spedizione trovata nel periodo {desde_date.strftime('%d/%m/%Y')} - {hasta_date.strftime('%d/%m/%Y')}."
                    )

                shoes_cids = [r["id"] for r in rows_data if r["centro"].lower() == "elche"]
                ecom_cids = [r["id"] for r in rows_data if is_ecom_shipment(r)]
                textile_rows = [
                    r
                    for r in rows_data
                    if r["centro"].lower() != "elche" and not is_ecom_shipment(r)
                ]
                textile_cids = [r["id"] for r in textile_rows]

                result_summary["shoes_shipments"] = len(shoes_cids)
                result_summary["ecom_shipments"] = len(ecom_cids)
                result_summary["textile_shipments"] = len(textile_rows)

                # 5. Download TOTAL.xls
                self._notify("Estrazione file TOTAL.xls (tutte le spedizioni)...", 40)
                all_cids = [r["id"] for r in rows_data]
                total_path = output_dir / "TOTAL.xls"
                self._download_group_file(page, all_cids, total_path)
                result_summary["files"]["total"] = str(total_path)

                # 6. Download SHOES.xls
                if shoes_cids:
                    self._notify(f"Estrazione file SHOES.xls ({len(shoes_cids)} spedizioni Calzature)...", 50)
                    shoes_path = output_dir / "SHOES.xls"
                    self._download_group_file(page, shoes_cids, shoes_path)
                    result_summary["files"]["shoes"] = str(shoes_path)
                else:
                    self._notify("Nessuna spedizione SHOES rilevata per questo periodo.", 50)

                # 7. Download ECOM.xls
                if ecom_cids:
                    self._notify(f"Estrazione file ECOM.xls ({len(ecom_cids)} spedizioni E-Commerce)...", 55)
                    ecom_path = output_dir / "ECOM.xls"
                    self._download_group_file(page, ecom_cids, ecom_path)
                    result_summary["files"]["ecom"] = str(ecom_path)
                else:
                    self._notify("Nessuna spedizione ECOM rilevata per questo periodo.", 55)

                # 8. Download TEXILE.xls
                if textile_cids:
                    self._notify(f"Estrazione file TEXILE.xls ({len(textile_cids)} spedizioni Tessile)...", 60)
                    textile_path = output_dir / "TEXILE.xls"
                    self._download_group_file(page, textile_cids, textile_path)
                    result_summary["files"]["textile"] = str(textile_path)

                # 9. Download OTHER/*.xls
                self._notify("Scansione consegne tessili per estrazione 'Altri bultos'...", 65)
                other_files = self._download_other_files(page, textile_rows, other_dir)
                result_summary["other_files_downloaded"] = len(other_files)
                result_summary["files"]["other"] = [str(f) for f in other_files]

                self._notify("Estrazione da Extranet completata con successo!", 95)
                result_summary["success"] = True

            except Exception as e:
                result_summary["error"] = str(e)
                self._notify(f"Errore durante l'estrazione: {e}", 100)
                raise
            finally:
                browser.close()

        self._notify("Processo browser terminato.", 100)
        return result_summary

    def _login(self, page: Page):
        page.goto(EXTRANET_LOGIN_URL, timeout=30000)
        page.wait_for_selector("#userLogin", timeout=10000)
        page.fill("#userLogin", self.username)
        page.fill("#real_pass", self.password)
        if not page.is_checked('input[type="checkbox"]'):
            page.check('input[type="checkbox"]')
        page.click("#indexBtnAccept")
        time.sleep(3)

    def _search_shipments(self, page: Page, desde: datetime.date, hasta: datetime.date):
        page.wait_for_selector("#diaDesdeB", timeout=15000)
        page.fill("#diaDesdeB", str(desde.day))
        page.fill("#mesDesdeB", f"{desde.month:02d}")
        page.fill("#anoDesdeB", str(desde.year))

        page.fill("#diaHastaB", str(hasta.day))
        page.fill("#mesHastaB", f"{hasta.month:02d}")
        page.fill("#anoHastaB", str(hasta.year))

        page.click("#botBuscPlt")
        time.sleep(4)

    def _get_shipment_rows(self, page: Page) -> List[Dict[str, Any]]:
        return page.evaluate("""() => {
            const checkboxes = document.querySelectorAll('input[id^="checkGroup_"]');
            return Array.from(checkboxes).map(cb => {
                const tr = cb.closest('tr');
                const tds = tr ? Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()) : [];
                return {
                    id: cb.id,
                    centro: tds[2] || '',
                    cod_envio: tds[3] || '',
                    camion: tds[4] || '',
                    transporte: tds[5] || '',
                    bultos: tds[10] || '',
                    full_text: tr ? tr.innerText : ''
                };
            });
        }""")

    def _download_group_file(self, page: Page, cids: List[str], target_path: Path):
        """
        Selects specified checkboxes, opens Grupo de entrega modal,
        triggers generarExcelDetalleAgrupacion() download, saves and closes.
        """
        cid_set = set(cids)
        checks = page.query_selector_all('input[id^="checkGroup_"]')
        for c in checks:
            cid = c.get_attribute("id")
            should_be = cid in cid_set
            if c.is_checked() != should_be:
                c.set_checked(should_be)
        time.sleep(1)

        # Open modal Grupo de entrega
        page.click("#botonAgrupacionPlat")
        time.sleep(3)

        # Trigger download
        with page.expect_download(timeout=25000) as download_info:
            page.evaluate("generarExcelDetalleAgrupacion()")
        download = download_info.value
        download.save_as(str(target_path))

        # Close modal
        try:
            page.click("#cl_02des5")
        except Exception:
            try:
                page.evaluate("cerrarCapa('divCapaTAgrupacion')")
            except Exception:
                pass
        time.sleep(1)

    def _download_other_files(
        self, page: Page, textile_rows: List[Dict[str, Any]], other_dir: Path
    ) -> List[Path]:
        """
        Iterates over textile shipments, checks for 'Otros bultos', and downloads them.
        """
        downloaded = []
        file_num = 1
        total_to_scan = len(textile_rows)
        checks = page.query_selector_all('input[id^="checkGroup_"]')

        for idx, row in enumerate(textile_rows):
            cid = row["id"]
            progress_pct = 65 + int((idx / total_to_scan) * 28)
            self._notify(
                f"Controllo Altri bultos ({idx + 1}/{total_to_scan}): {row['centro']} - {row['cod_envio']}...",
                progress_pct,
            )

            # Uncheck all, check only this row
            for c in checks:
                should_be = (c.get_attribute("id") == cid)
                if c.is_checked() != should_be:
                    c.set_checked(should_be)

            # Open modal Entrega
            try:
                page.click("#botonEntregaPlat")
                page.wait_for_selector("#totOEnv", state="visible", timeout=10000)
            except Exception as e:
                print(f"Warning: could not open Entrega for {cid}: {e}")
                continue

            tot_o_env = page.evaluate("""() => {
                const el = document.getElementById('totOEnv');
                return el ? el.innerText.trim() : '0';
            }""")

            try:
                val = float(str(tot_o_env).replace(",", "."))
            except Exception:
                val = 0.0

            if val > 0:
                out_file = other_dir / f"{file_num}.xls"
                self._notify(
                    f"  Trovati {val} altri bultos in {row['cod_envio']}! Download -> {out_file.name}",
                    progress_pct,
                )
                try:
                    with page.expect_download(timeout=20000) as download_info:
                        page.evaluate("generarExcelSeguimiento(false)")
                    download = download_info.value
                    download.save_as(str(out_file))
                    downloaded.append(out_file)
                    file_num += 1
                except Exception as e:
                    print(f"Warning: failed download for {cid}: {e}")

            # Close modal
            try:
                page.evaluate("cerrarCapa('divCapaTIndividual')")
            except Exception:
                pass
            time.sleep(0.3)

        return downloaded
