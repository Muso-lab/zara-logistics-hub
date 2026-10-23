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
            # 1. Prova prima eventuali binari Chromium di sistema (es. Streamlit Cloud Linux)
            for sys_exec in ["/usr/bin/chromium", "/usr/bin/chromium-browser"]:
                if Path(sys_exec).exists():
                    try:
                        browser = p.chromium.launch(
                            executable_path=sys_exec,
                            headless=self.headless,
                            args=["--no-sandbox", "--disable-dev-shm-usage"],
                        )
                        break
                    except Exception:
                        continue
            # 2. Altrimenti prova i canali standard Playwright / Edge / Chrome
            if browser is None:
                for ch in [None, "msedge", "chrome"]:
                    try:
                        if ch:
                            browser = p.chromium.launch(channel=ch, headless=self.headless)
                        else:
                            browser = p.chromium.launch(headless=self.headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
                        break
                    except Exception:
                        continue
            # 3. Se manca l'eseguibile Playwright su server Cloud, installalo al volo
            if browser is None:
                try:
                    import subprocess
                    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                    browser = p.chromium.launch(headless=self.headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
                except Exception:
                    pass
            if browser is None:
                raise RuntimeError("Impossibile avviare il browser per la connessione a Extranet.")

            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            try:
                # 1. Login
                self._notify(f"Accesso al portale Extranet Inditex ({self.username})...", 10)
                self._login(page)

                # 2. Go to Buzon Plataforma
                self._notify("Apertura sezione Piattaforma Spedizioni...", 20)
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
                self._notify("Scansione consegne tessili per estrazione dettaglio colli (OTHER)...", 65)
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
        self._clear_overlays_and_select(page, [])
        page.fill("#diaDesdeB", str(desde.day))
        page.fill("#mesDesdeB", f"{desde.month:02d}")
        page.fill("#anoDesdeB", str(desde.year))

        page.fill("#diaHastaB", str(hasta.day))
        page.fill("#mesHastaB", f"{hasta.month:02d}")
        page.fill("#anoHastaB", str(hasta.year))

        page.evaluate("""() => {
            const btn = document.getElementById('botBuscPlt');
            if (btn) btn.click();
        }""")
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

    def _clear_overlays_and_select(self, page: Page, target_ids: List[str]):
        """
        Chiude eventuali finestre modali aperte, nasconde il livello divCapaObservaciones
        e seleziona i checkbox richiesti invocando cb.click() per attivare gli handler onclick di Inditex.
        """
        page.evaluate(
            """(targetIds) => {
                // 1. Chiudi correttamente eventuali modali aperte da iterazioni precedenti
                ['divCapaObservaciones', 'divCapaTAgrupacion', 'divCapaTIndividual'].forEach(id => {
                    try {
                        if (typeof cerrarCapa === 'function') cerrarCapa(id);
                    } catch (e) {}
                });
                const obs = document.getElementById('divCapaObservaciones');
                if (obs) {
                    obs.style.display = 'none';
                    obs.style.visibility = 'hidden';
                }
                document.querySelectorAll('.capaSemiTransparenteObservaciones').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                });

                // 2. Seleziona/deseleziona i checkbox invocando .click() per popolare gli array JS di Inditex
                const idSet = new Set(targetIds);
                const checkboxes = document.querySelectorAll('input[id^="checkGroup_"]');
                checkboxes.forEach(cb => {
                    const shouldCheck = idSet.has(cb.id);
                    if (cb.checked !== shouldCheck) {
                        cb.click();
                    }
                });
            }""",
            list(target_ids),
        )

    def _download_group_file(self, page: Page, cids: List[str], target_path: Path):
        """
        Selects specified checkboxes, opens Grupo de entrega modal,
        waits for DWR callback to populate global `envios` array,
        triggers generarExcelDetalleAgrupacion() download, saves and closes.
        """
        self._clear_overlays_and_select(page, cids)
        time.sleep(0.5)

        # Reset global envios variable and open modal Grupo de entrega
        page.evaluate("""() => {
            try { window.envios = undefined; } catch (e) {}
            const btn = document.getElementById('botonAgrupacionPlat');
            if (btn) btn.click();
        }""")

        # Attendi che la chiamata DWR di Inditex popoli l'array globale `envios`
        try:
            page.wait_for_function(
                "() => typeof envios !== 'undefined' && envios !== null && envios.length > 0",
                timeout=15000,
            )
        except Exception:
            time.sleep(2.5)
        time.sleep(0.5)

        # Trigger download
        with page.expect_download(timeout=30000) as download_info:
            page.evaluate("generarExcelDetalleAgrupacion()")
        download = download_info.value
        download.save_as(str(target_path))

        # Close modal
        try:
            page.evaluate("""() => {
                const closeBtn = document.getElementById('cl_02des5');
                if (closeBtn) closeBtn.click();
                else if (typeof cerrarCapa === 'function') cerrarCapa('divCapaTAgrupacion');
            }""")
        except Exception:
            pass
        time.sleep(0.6)

    def _download_other_files(
        self, page: Page, textile_rows: List[Dict[str, Any]], other_dir: Path
    ) -> List[Path]:
        """
        Iterates over textile shipments, checks for 'Otros bultos', and downloads them.
        """
        downloaded = []
        file_num = 1
        total_to_scan = len(textile_rows)

        for idx, row in enumerate(textile_rows):
            cid = row["id"]
            progress_pct = 65 + int((idx / max(total_to_scan, 1)) * 28)
            self._notify(
                f"Controllo dettaglio colli ({idx + 1}/{total_to_scan}): {row['centro']} - {row['cod_envio']}...",
                progress_pct,
            )

            # Uncheck all, check only this row via JS (immune to detached DOM & overlay interception)
            self._clear_overlays_and_select(page, [cid])
            time.sleep(0.3)

            # Open modal Entrega via JS click
            try:
                page.evaluate("""() => {
                    const btn = document.getElementById('botonEntregaPlat');
                    if (btn) btn.click();
                }""")
                page.wait_for_selector("#totOEnv", state="attached", timeout=10000)
                time.sleep(0.5)
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
                    f"  Trovati {val:g} colli extra in {row['cod_envio']} -> salvataggio {out_file.name}",
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
                page.evaluate("""() => {
                    if (typeof cerrarCapa === 'function') cerrarCapa('divCapaTIndividual');
                    const el = document.getElementById('divCapaTIndividual');
                    if (el) el.style.display = 'none';
                }""")
            except Exception:
                pass
            time.sleep(0.3)

        return downloaded
