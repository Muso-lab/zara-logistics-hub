"""
Automated Pure-HTTP Scraper for Inditex Extranet (Plataforma / Buzon).
Uses direct DWR HTTP requests via requests.Session (zero browser/Chromium overhead,
<5 MB RAM, 10x faster, 100% compatible with Streamlit Community Cloud).
Extracts TOTAL.xls, SHOES.xls, ECOM.xls, TEXILE.xls and all OTHER/*.xls packages.
"""

import json
import re
import time
import urllib.parse
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import requests

from src.config import (
    EXTRANET_LOGIN_URL,
    EXTRANET_BUZON_URL,
    EXTRANET_DEFAULT_USER,
    EXTRANET_DEFAULT_PASS,
)

DWR_BASE = "https://extranet.inditex.com/AgenteAduanas/Plataformas/dwr/exec"
EXCEL_GROUP_URL = "https://extranet.inditex.com/AgenteAduanas/Plataformas/excelAltaAgrupacionPlataforma.html?tipoExcel=altaAgrupacionPlataforma"
EXCEL_INDIV_URL = "https://extranet.inditex.com/AgenteAduanas/Plataformas/excelInformeSeguimiento.html"


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
        str(row_data.get("full_text", "")),
    ]
    combined = " ".join(targets)
    if "ecom" in combined.lower():
        return True
    if re.search(r"(^|[\s\-_/.,;:()\[\]])EC([\s\-_/.,;:()\[\]]|$)", combined, re.IGNORECASE):
        return True
    return False


def _parse_dwr_array(dwr_text: str) -> List[Dict[str, Any]]:
    """
    Parses a DWR JavaScript response (e.g. `var s0=[]; var s1={}; ... s0[0]=s1;`)
    into a Python list of dicts without using eval().
    """
    vars_map: Dict[str, Any] = {}
    tokens = re.split(r"[;\r\n]+", dwr_text)
    for tok in tokens:
        tok = tok.strip()
        if not tok or tok.startswith("DWREngine"):
            continue
        m_var = re.match(r"^var\s+(s\d+)=(.*)$", tok)
        if m_var:
            vname, vval = m_var.group(1), m_var.group(2).strip()
            if vval == "[]":
                vars_map[vname] = []
            elif vval == "{}":
                vars_map[vname] = {}
            elif vval == "null":
                vars_map[vname] = None
            elif vval == "true":
                vars_map[vname] = True
            elif vval == "false":
                vars_map[vname] = False
            elif vval.startswith('"') and vval.endswith('"'):
                try:
                    vars_map[vname] = json.loads(vval)
                except Exception:
                    vars_map[vname] = vval[1:-1]
            else:
                try:
                    vars_map[vname] = int(vval) if "." not in vval else float(vval)
                except Exception:
                    vars_map[vname] = vval
            continue

        m_prop = re.match(r"^(s\d+)\.([a-zA-Z0-9_]+)=(s\d+)$", tok)
        if m_prop:
            obj_name, prop, ref_name = m_prop.groups()
            if isinstance(vars_map.get(obj_name), dict):
                vars_map[obj_name][prop] = vars_map.get(ref_name)
            continue

        m_arr = re.match(r"^(s\d+)\[(\d+)\]=(s\d+)$", tok)
        if m_arr:
            arr_name, _, ref_name = m_arr.groups()
            if isinstance(vars_map.get(arr_name), list):
                vars_map[arr_name].append(vars_map.get(ref_name))
            continue

    res = vars_map.get("s0", [])
    return res if isinstance(res, list) else []


def _encode_dwr_group_excel(shipments: List[Dict[str, Any]]) -> str:
    """Builds DWR request body for agrupacionesDWR.getAgrupacionExcel."""
    lines = [
        "callCount=1",
        "c0-scriptName=agrupacionesDWR",
        "c0-methodName=getAgrupacionExcel",
        f"c0-id={int(time.time() * 1000) % 10000}_{int(time.time() * 1000)}",
    ]
    refs = []
    idx = 1
    for sh in shipments:
        obj_id = f"c0-e{idx}"
        e_cod = f"c0-e{idx + 1}"
        e_fec = f"c0-e{idx + 2}"
        e_hor = f"c0-e{idx + 3}"
        idx += 4
        cod = urllib.parse.quote(str(sh.get("cod_envio", "")))
        fec = urllib.parse.quote(str(sh.get("fecha_salida", "")))
        hor = urllib.parse.quote(str(sh.get("hora_salida", "")))
        lines.append(f"{e_cod}=string:{cod}")
        lines.append(f"{e_fec}=string:{fec}")
        lines.append(f"{e_hor}=string:{hor}")
        lines.append(
            f"{obj_id}=Object:{{codEnvio:reference:{e_cod}, fecEnvio:reference:{e_fec}, horaEnvio:reference:{e_hor}}}"
        )
        refs.append(f"reference:{obj_id}")

    lines.append(f"c0-param0=Array:[{','.join(refs)}]")
    lines.append("c0-param1=null:null")
    lines.append("c0-param2=boolean:false")
    lines.append("xml=true")
    return "\n".join(lines) + "\n"


def _encode_dwr_indiv_query(sh: Dict[str, Any]) -> str:
    """Builds DWR request body for entregasDWR.getEntregasIndividual."""
    cod = urllib.parse.quote(str(sh.get("cod_envio", "")))
    fec = urllib.parse.quote(str(sh.get("fecha_salida", "")))
    hor = urllib.parse.quote(str(sh.get("hora_salida", "")))
    transp = urllib.parse.quote(str(sh.get("transporte", "TR")))
    id_env = urllib.parse.quote(str(sh.get("id_envio", "0")))
    id_plat = urllib.parse.quote(str(sh.get("id_plataforma", "708")))
    id_pais = urllib.parse.quote(str(sh.get("id_pais_plat", "5")))
    pos = int(sh.get("pos", 0))

    lines = [
        "callCount=1",
        "c0-scriptName=entregasDWR",
        "c0-methodName=getEntregasIndividual",
        f"c0-id={int(time.time() * 1000) % 10000}_{int(time.time() * 1000)}",
        f"c0-e1=string:{cod}",
        f"c0-e2=string:{fec}",
        f"c0-e3=string:{hor}",
        f"c0-e4=string:{transp}",
        f"c0-e5=string:{id_env}",
        f"c0-e6=string:{id_plat}",
        f"c0-e7=string:{id_pais}",
        f"c0-e8=number:{pos}",
        "c0-param0=Object:{codEnvio:reference:c0-e1, fecEnvio:reference:c0-e2, horaEnvio:reference:c0-e3, tipoEnvio:reference:c0-e4, idEnvio:reference:c0-e5, idPlataforma:reference:c0-e6, idPaisPlat:reference:c0-e7, posEnvioTabla:reference:c0-e8}",
        "xml=true",
    ]
    return "\n".join(lines) + "\n"


def _encode_dwr_indiv_excel(items: List[Dict[str, Any]]) -> str:
    """Builds DWR request body for entregasDWR.getExcelEIndividual."""
    lines = [
        "callCount=1",
        "c0-scriptName=entregasDWR",
        "c0-methodName=getExcelEIndividual",
        f"c0-id={int(time.time() * 1000) % 10000}_{int(time.time() * 1000)}",
    ]
    refs = []
    idx = 1
    for item in items:
        obj_id = f"c0-e{idx}"
        idx += 1
        props = []
        for k, v in item.items():
            eid = f"c0-e{idx}"
            idx += 1
            if v is None:
                lines.append(f"{eid}=null:null")
            elif isinstance(v, bool):
                lines.append(f"{eid}=boolean:{str(v).lower()}")
            elif isinstance(v, (int, float)):
                lines.append(f"{eid}=number:{v}")
            else:
                lines.append(f"{eid}=string:{urllib.parse.quote(str(v))}")
            props.append(f"{k}:reference:{eid}")
        joined_props = ", ".join(props)
        lines.append(f"{obj_id}=Object:{{{joined_props}}}")
        refs.append(f"reference:{obj_id}")

    joined_refs = ",".join(refs)
    lines.append(f"c0-param0=Array:[{joined_refs}]")
    lines.append("c0-param1=boolean:false")
    lines.append("xml=true")
    return "\n".join(lines) + "\n"


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
        Executes complete Extranet workflow via direct HTTP/DWR calls:
        1. Authenticate against F5 BigIP /my.policy
        2. Open Buzon Plataforma session
        3. Query shipments by date range via plataformasDWR.getBuzon.dwr
        4. Download TOTAL.xls, SHOES.xls, ECOM.xls, TEXILE.xls
        5. Scan textile shipments and download all OTHER/*.xls files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        other_dir = output_dir / "OTHER"
        other_dir.mkdir(parents=True, exist_ok=True)

        result_summary: Dict[str, Any] = {
            "success": False,
            "error": None,
            "total_shipments_found": 0,
            "shoes_shipments": 0,
            "ecom_shipments": 0,
            "textile_shipments": 0,
            "other_files_downloaded": 0,
            "files": {},
        }

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "it-IT,it;q=0.9,es-ES;q=0.8,en;q=0.7",
            }
        )

        try:
            # 1. Login
            self._notify(f"Accesso diretto al portale Extranet Inditex ({self.username})...", 10)
            self._login(session)

            # 2. Initialize Buzon Plataforma session state
            self._notify("Apertura sessione Piattaforma Spedizioni...", 20)
            r_buzon_page = session.get(EXTRANET_BUZON_URL, timeout=30)
            r_buzon_page.raise_for_status()

            # 3. Search Date Range via DWR
            self._notify(
                f"Ricerca spedizioni dal {desde_date.strftime('%d/%m/%Y')} al {hasta_date.strftime('%d/%m/%Y')}...",
                25,
            )
            rows_data = self._search_shipments(session, desde_date, hasta_date)
            tot_count = len(rows_data)
            result_summary["total_shipments_found"] = tot_count

            if tot_count == 0:
                raise ValueError(
                    f"Nessuna spedizione trovata nel periodo {desde_date.strftime('%d/%m/%Y')} - {hasta_date.strftime('%d/%m/%Y')}."
                )

            shoes_rows = [r for r in rows_data if r["centro"].lower() == "elche"]
            ecom_rows = [r for r in rows_data if is_ecom_shipment(r)]
            textile_rows = [
                r
                for r in rows_data
                if r["centro"].lower() != "elche" and not is_ecom_shipment(r)
            ]

            result_summary["shoes_shipments"] = len(shoes_rows)
            result_summary["ecom_shipments"] = len(ecom_rows)
            result_summary["textile_shipments"] = len(textile_rows)

            # 4. Download TOTAL.xls
            self._notify(f"Estrazione file TOTAL.xls ({tot_count} spedizioni)...", 40)
            total_path = output_dir / "TOTAL.xls"
            self._download_group_file(session, rows_data, total_path)
            result_summary["files"]["total"] = str(total_path)

            # 5. Download SHOES.xls
            if shoes_rows:
                self._notify(f"Estrazione file SHOES.xls ({len(shoes_rows)} spedizioni Calzature)...", 50)
                shoes_path = output_dir / "SHOES.xls"
                self._download_group_file(session, shoes_rows, shoes_path)
                result_summary["files"]["shoes"] = str(shoes_path)
            else:
                self._notify("Nessuna spedizione Calzature rilevata per questo periodo.", 50)

            # 6. Download ECOM.xls
            if ecom_rows:
                self._notify(f"Estrazione file ECOM.xls ({len(ecom_rows)} spedizioni E-Commerce)...", 55)
                ecom_path = output_dir / "ECOM.xls"
                self._download_group_file(session, ecom_rows, ecom_path)
                result_summary["files"]["ecom"] = str(ecom_path)
            else:
                self._notify("Nessuna spedizione E-Commerce rilevata per questo periodo.", 55)

            # 7. Download TEXILE.xls
            if textile_rows:
                self._notify(f"Estrazione file TEXILE.xls ({len(textile_rows)} spedizioni Tessile)...", 60)
                textile_path = output_dir / "TEXILE.xls"
                self._download_group_file(session, textile_rows, textile_path)
                result_summary["files"]["textile"] = str(textile_path)

            # 8. Download OTHER/*.xls
            self._notify("Scansione consegne tessili per estrazione dettaglio colli extra (OTHER)...", 65)
            other_files = self._download_other_files(session, textile_rows, other_dir)
            result_summary["other_files_downloaded"] = len(other_files)
            result_summary["files"]["other"] = [str(f) for f in other_files]

            self._notify("Estrazione da Extranet completata con successo!", 100)
            result_summary["success"] = True
            return result_summary

        except Exception as e:
            result_summary["error"] = str(e)
            self._notify(f"Errore durante l'estrazione: {e}", 100)
            raise
        finally:
            session.close()

    def _login(self, session: requests.Session):
        r1 = session.get(EXTRANET_LOGIN_URL, timeout=30)
        r1.raise_for_status()
        r2 = session.post(
            "https://extranet.inditex.com/my.policy",
            data={
                "username": self.username,
                "password": self.password,
                "vhost": "standard",
                "check": "checkbox",
            },
            timeout=30,
        )
        r2.raise_for_status()
        if "my.policy" in r2.url and "error" in r2.text.lower():
            raise RuntimeError("Credenziali Extranet Inditex non valide o sessione rifiutata.")

    def _search_shipments(
        self,
        session: requests.Session,
        desde: datetime.date,
        hasta: datetime.date,
    ) -> List[Dict[str, Any]]:
        desde_str = urllib.parse.quote(desde.strftime("%d/%m/%Y"))
        hasta_str = urllib.parse.quote(hasta.strftime("%d/%m/%Y"))
        body = (
            "callCount=1\n"
            "c0-scriptName=plataformasDWR\n"
            "c0-methodName=getBuzon\n"
            f"c0-id={int(time.time() * 1000) % 10000}_{int(time.time() * 1000)}\n"
            f"c0-param0=string:{desde_str}\n"
            f"c0-param1=string:{hasta_str}\n"
            "c0-param2=null:null\n"
            "c0-param3=null:null\n"
            "xml=true\n"
        )
        r = session.post(
            f"{DWR_BASE}/plataformasDWR.getBuzon.dwr",
            data=body,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        r.raise_for_status()
        raw_items = _parse_dwr_array(r.text)

        rows: List[Dict[str, Any]] = []
        for idx, item in enumerate(raw_items):
            centro = str(item.get("ordenador", "") or "").strip()
            cod_envio = str(item.get("codigoEnvio", "") or "").strip()
            camion = str(item.get("camion", "") or "").strip()
            remolque = str(item.get("remolque", "") or "").strip()
            transporte = str(item.get("tipoTransporte", "TR") or "TR").strip()
            rows.append(
                {
                    "id": f"checkGroup_{idx}",
                    "pos": idx,
                    "centro": centro,
                    "cod_envio": cod_envio,
                    "camion": camion,
                    "remolque": remolque,
                    "transporte": transporte,
                    "fecha_salida": str(item.get("fechaSalida", "") or "").strip(),
                    "hora_salida": str(item.get("horaSalida", "") or "").strip(),
                    "id_envio": str(item.get("idEnvio", 0)),
                    "id_plataforma": str(item.get("idPlataforma", 708)),
                    "id_pais_plat": str(item.get("idPaisPlat", 5)),
                    "bultos": item.get("bultos", 0),
                    "full_text": f"{centro} {cod_envio} {camion} {remolque} {transporte}",
                }
            )
        return rows

    def _download_group_file(
        self,
        session: requests.Session,
        shipments: List[Dict[str, Any]],
        target_path: Path,
    ):
        body = _encode_dwr_group_excel(shipments)
        r_prep = session.post(
            f"{DWR_BASE}/agrupacionesDWR.getAgrupacionExcel.dwr",
            data=body,
            headers={"Content-Type": "text/plain"},
            timeout=30,
        )
        r_prep.raise_for_status()

        r_xls = session.get(EXCEL_GROUP_URL, timeout=30)
        r_xls.raise_for_status()
        target_path.write_bytes(r_xls.content)

    def _download_other_files(
        self,
        session: requests.Session,
        textile_rows: List[Dict[str, Any]],
        other_dir: Path,
    ) -> List[Path]:
        downloaded: List[Path] = []
        file_num = 1
        total_to_scan = len(textile_rows)

        for idx, row in enumerate(textile_rows):
            progress_pct = 65 + int((idx / max(total_to_scan, 1)) * 30)
            self._notify(
                f"Controllo dettaglio colli ({idx + 1}/{total_to_scan}): {row['centro']} - {row['cod_envio']}...",
                progress_pct,
            )

            body_query = _encode_dwr_indiv_query(row)
            r_indiv = session.post(
                f"{DWR_BASE}/entregasDWR.getEntregasIndividual.dwr",
                data=body_query,
                headers={"Content-Type": "text/plain"},
                timeout=30,
            )
            r_indiv.raise_for_status()
            store_items = _parse_dwr_array(r_indiv.text)
            if not store_items:
                continue

            tot_otros = 0.0
            for st_item in store_items:
                try:
                    tot_otros += float(st_item.get("otrosEnt", 0) or 0)
                except Exception:
                    pass

            if tot_otros > 0:
                out_file = other_dir / f"{file_num}.xls"
                self._notify(
                    f"  Trovati {tot_otros:g} colli extra in {row['cod_envio']} -> salvataggio {out_file.name}",
                    progress_pct,
                )
                body_excel = _encode_dwr_indiv_excel(store_items)
                r_prep = session.post(
                    f"{DWR_BASE}/entregasDWR.getExcelEIndividual.dwr",
                    data=body_excel,
                    headers={"Content-Type": "text/plain"},
                    timeout=30,
                )
                r_prep.raise_for_status()

                params = {
                    "tipoExcel": "seguimientoPlataforma",
                    "codEnvio": row["cod_envio"],
                    "fecEnvio": row["fecha_salida"],
                    "horaEnvio": row["hora_salida"],
                }
                r_xls = session.get(EXCEL_INDIV_URL, params=params, timeout=30)
                r_xls.raise_for_status()
                out_file.write_bytes(r_xls.content)
                downloaded.append(out_file)
                file_num += 1

        return downloaded
