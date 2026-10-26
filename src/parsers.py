import io
import os
import re
from pathlib import Path
from typing import Union, List, Dict, Any, Tuple
import pandas as pd
import numpy as np


def clean_store_id(store_val: Any) -> str:
    """Extracts numeric store id from strings like '1265-ROM-VIA APPIA' or '5349B'."""
    if pd.isna(store_val):
        return ""
    s = str(store_val).strip()
    # Check if format like 1265-ROM-VIA APPIA
    if "-" in s:
        s = s.split("-")[0].strip()
    # Remove leading/trailing spaces or quotes
    s = s.replace('"', '').replace("'", "")
    # If ends with .0 from float conversion, strip
    if s.endswith(".0"):
        s = s[:-2]
    return s


def parse_grupo_envio(source: Union[str, Path, bytes, io.BytesIO, io.StringIO, pd.DataFrame]) -> pd.DataFrame:
    """
    Parses 'Previsión grupo de envío' format from .xls, .xlsx, or CSV/plain text.
    Returns DataFrame with columns:
    ['store_id', 'raw_tienda', 'p_colgada', 'paqueteria', 'peso', 'volumen', 'bultos']
    """
    # 0. If already a DataFrame
    if isinstance(source, pd.DataFrame):
        if "store_id" in source.columns and "bultos" in source.columns:
            return source
        return _normalize_grupo_envio_df(source)

    # 1. If it's a string containing multiple lines (pasted text), parse as CSV
    if isinstance(source, str) and ("\n" in source or not os.path.exists(source)):
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        # Find header line with Tienda
        header_idx = -1
        for i, line in enumerate(lines):
            tokens = [t.strip().strip('"').lower() for t in line.split(",")]
            if "tienda" in tokens or "store" in tokens:
                header_idx = i
                break
        
        if header_idx == -1:
            return pd.DataFrame(columns=['store_id', 'raw_tienda', 'p_colgada', 'paqueteria', 'peso', 'volumen', 'bultos'])
        
        # Parse CSV starting from header_idx
        csv_text = "\n".join(lines[header_idx:])
        df = pd.read_csv(io.StringIO(csv_text), sep=",", on_bad_lines="skip")
        return _normalize_grupo_envio_df(df)

    # 2. If it's a file path
    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.exists():
            return pd.DataFrame(columns=['store_id', 'raw_tienda', 'p_colgada', 'paqueteria', 'peso', 'volumen', 'bultos'])
        if p.suffix.lower() == ".xls":
            import xlrd
            wb = xlrd.open_workbook(str(p))
            sheet = wb.sheet_by_index(0)
            return _parse_xlrd_grupo_envio(sheet)
        else:
            df = pd.read_excel(p)
            return _normalize_grupo_envio_df(df)

    # 3. If it's bytes or buffer (e.g. Streamlit upload)
    if isinstance(source, (bytes, io.BytesIO)):
        buffer = io.BytesIO(source) if isinstance(source, bytes) else source
        try:
            import xlrd
            wb = xlrd.open_workbook(file_contents=buffer.getvalue())
            sheet = wb.sheet_by_index(0)
            return _parse_xlrd_grupo_envio(sheet)
        except Exception:
            buffer.seek(0)
            try:
                df = pd.read_excel(buffer)
                return _normalize_grupo_envio_df(df)
            except Exception:
                buffer.seek(0)
                df = pd.read_csv(buffer)
                return _normalize_grupo_envio_df(df)

    return pd.DataFrame(columns=['store_id', 'raw_tienda', 'p_colgada', 'paqueteria', 'peso', 'volumen', 'bultos'])


def _parse_xlrd_grupo_envio(sheet) -> pd.DataFrame:
    header_r = -1
    for r in range(sheet.nrows):
        val = str(sheet.cell_value(r, 0)).strip().lower()
        if val in ("tienda", "store"):
            header_r = r
            break
    
    if header_r == -1:
        return pd.DataFrame(columns=['store_id', 'raw_tienda', 'p_colgada', 'paqueteria', 'peso', 'volumen', 'bultos'])

    records = []
    for r in range(header_r + 1, sheet.nrows):
        tienda_val = str(sheet.cell_value(r, 0)).strip()
        if not tienda_val or tienda_val.upper() == "TOTAL":
            continue
        
        def safe_float(col_idx):
            if col_idx < sheet.ncols:
                v = sheet.cell_value(r, col_idx)
                try:
                    return float(v)
                except:
                    return 0.0
            return 0.0

        p_colgada = safe_float(1)
        paqueteria = safe_float(2)
        peso = safe_float(3)
        volumen = safe_float(4)
        bultos = safe_float(5)

        sid = clean_store_id(tienda_val)
        records.append({
            "store_id": sid,
            "raw_tienda": tienda_val,
            "p_colgada": p_colgada,
            "paqueteria": paqueteria,
            "peso": peso,
            "volumen": volumen,
            "bultos": bultos
        })
    return pd.DataFrame(records)


def _normalize_grupo_envio_df(df: pd.DataFrame) -> pd.DataFrame:
    # Find Tienda column
    tienda_col = None
    for c in df.columns:
        if str(c).strip().lower() in ("tienda", "store"):
            tienda_col = c
            break
    if tienda_col is None:
        return pd.DataFrame(columns=['store_id', 'raw_tienda', 'p_colgada', 'paqueteria', 'peso', 'volumen', 'bultos'])

    df = df[df[tienda_col].notna()].copy()
    df = df[~df[tienda_col].astype(str).str.strip().str.upper().isin(["TOTAL", ""])]

    # Col mapping
    cols = list(df.columns)
    t_idx = cols.index(tienda_col)
    
    def get_num(idx):
        if idx < len(cols):
            return pd.to_numeric(df[cols[idx]].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
        return pd.Series(0.0, index=df.index)

    p_colgada = get_num(t_idx + 1)
    paqueteria = get_num(t_idx + 2)
    peso = get_num(t_idx + 3)
    volumen = get_num(t_idx + 4)
    bultos = get_num(t_idx + 5)

    res = pd.DataFrame({
        "store_id": df[tienda_col].apply(clean_store_id),
        "raw_tienda": df[tienda_col].astype(str).str.strip(),
        "p_colgada": p_colgada,
        "paqueteria": paqueteria,
        "peso": peso,
        "volumen": volumen,
        "bultos": bultos
    })
    return res


def parse_other_files(folder_or_files: Union[str, Path, List[Any]]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parses OTHER shipments from a folder or list of file objects.
    Returns:
    - other_raw_df: all extracted rows (with file, raw_tienda, store_id, otros_bultos_enviado, etc.)
    - other_agg_df: aggregated by store_id with sum of 'otros_bultos_enviado' (Somma di Enviado3)
    """
    import xlrd
    records = []

    files_to_process = []
    if isinstance(folder_or_files, (str, Path)):
        p = Path(folder_or_files)
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.suffix.lower() == ".xls":
                    files_to_process.append((f.name, f))
    elif isinstance(folder_or_files, list):
        for item in folder_or_files:
            fname = getattr(item, "name", "file.xls")
            files_to_process.append((fname, item))

    for fname, fsource in files_to_process:
        try:
            if isinstance(fsource, (str, Path)):
                wb = xlrd.open_workbook(str(fsource))
            else:
                fsource.seek(0)
                wb = xlrd.open_workbook(file_contents=fsource.read())
            sheet = wb.sheet_by_index(0)

            # Dynamic header & column detection
            header_r = -1
            tienda_col = 1
            otros_col = 13
            bultos_col = 6
            for r in range(min(15, sheet.nrows)):
                row_str = " ".join(str(sheet.cell_value(r, c)).strip().lower() for c in range(sheet.ncols))
                if "confirm" in row_str or "tienda" in row_str:
                    header_r = r
                    for c in range(sheet.ncols):
                        c_val = str(sheet.cell_value(r, c)).strip().lower()
                        if "tienda" in c_val:
                            tienda_col = c
                        elif "bultos" in c_val and c < 10:
                            bultos_col = c
                    for check_r in [r - 1, r]:
                        if check_r >= 0:
                            for c in range(sheet.ncols):
                                if "otro" in str(sheet.cell_value(check_r, c)).strip().lower():
                                    otros_col = c
                                    break
                    break

            if header_r != -1:
                for r in range(header_r + 1, sheet.nrows):
                    raw_tienda = str(sheet.cell_value(r, tienda_col)).strip()
                    if not raw_tienda or raw_tienda.lower().startswith("total"):
                        continue
                    sid = clean_store_id(raw_tienda)
                    if not sid:
                        continue

                    val_enviado = 0.0
                    if sheet.ncols > otros_col:
                        try:
                            val_enviado = float(sheet.cell_value(r, otros_col))
                        except Exception:
                            val_enviado = 0.0

                    bultos_tot = 0.0
                    if sheet.ncols > bultos_col:
                        try:
                            bultos_tot = float(sheet.cell_value(r, bultos_col))
                        except Exception:
                            bultos_tot = 0.0

                    conf = str(sheet.cell_value(r, 0)).strip() if sheet.ncols > 0 else ""

                    records.append({
                        "file_name": fname,
                        "raw_tienda": raw_tienda,
                        "store_code": sid,
                        "confirm": conf,
                        "bultos": bultos_tot,
                        "otros_bultos_enviado": val_enviado
                    })
        except Exception as e:
            print(f"Error parsing other file {fname}: {e}")

    df_raw = pd.DataFrame(records)
    if df_raw.empty:
        df_agg = pd.DataFrame(columns=["store_code", "store_id", "otros_enviado"])
    else:
        df_agg = df_raw.groupby("store_code")["otros_bultos_enviado"].sum().reset_index()
        df_agg.rename(columns={"otros_bultos_enviado": "otros_enviado"}, inplace=True)
        df_agg["store_id"] = df_agg["store_code"]

    return df_raw, df_agg


def parse_esportazione(source: Union[str, Path, bytes, io.BytesIO, pd.DataFrame]) -> pd.DataFrame:
    """
    Parses esportazione.xlsx or CSV text containing actual delivery data from Access,
    or directly receives a DataFrame from access_reader.
    Extracts columns:
    ['ID_STORE', 'TIPO_CONS', 'TOT_ABBIGL', 'TOT_CALZAT', 'TOT_ECOM', 'TOT_OTHERS', 'TOT_VARIO', 'TOT_CONT', 'colli_mat_vario', 'stringa']
    """
    if source is None:
        return pd.DataFrame()

    # 0. If already a DataFrame
    if isinstance(source, pd.DataFrame):
        return _normalize_esportazione_df(source)

    # 1. If text/CSV string
    if isinstance(source, str) and ("\n" in source or not os.path.exists(source)):
        # Handle possible multiple CSV blocks (e.g. STD and DOPPIA concatenated)
        lines = [line.strip() for line in source.splitlines() if line.strip()]
        header_lines = [i for i, l in enumerate(lines) if "id_store" in l.lower()]
        if not header_lines:
            return pd.DataFrame()
        
        dfs = []
        for i, h_idx in enumerate(header_lines):
            end_idx = header_lines[i+1] if i+1 < len(header_lines) else len(lines)
            block_text = "\n".join(lines[h_idx:end_idx])
            df_b = pd.read_csv(io.StringIO(block_text), sep=",", on_bad_lines="skip")
            dfs.append(df_b)
        df_all = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        return _normalize_esportazione_df(df_all)

    # 2. If Excel file
    if isinstance(source, (str, Path, bytes, io.BytesIO)):
        excel_file = source
        xl = pd.ExcelFile(excel_file)
        dfs = []
        for sheet_name in xl.sheet_names:
            df_s = xl.parse(sheet_name)
            if not df_s.empty and any("store" in str(c).lower() for c in df_s.columns):
                dfs.append(df_s)
        if dfs:
            df_all = pd.concat(dfs, ignore_index=True)
            return _normalize_esportazione_df(df_all)
        return pd.DataFrame()

    return pd.DataFrame()


def _normalize_esportazione_df(df: pd.DataFrame) -> pd.DataFrame:
    # Rename case-insensitively
    col_map = {}
    for c in df.columns:
        cl = str(c).strip().upper()
        if "ID_STORE" in cl or "STORE" in cl:
            col_map[c] = "ID_STORE"
        elif "TIPO" in cl:
            col_map[c] = "TIPO_CONS"
        elif "ABBIGL" in cl:
            col_map[c] = "TOT_ABBIGL"
        elif "CALZAT" in cl:
            col_map[c] = "TOT_CALZAT"
        elif "ECOM" in cl:
            col_map[c] = "TOT_ECOM"
        elif "OTHERS" in cl:
            col_map[c] = "TOT_OTHERS"
        elif "VARIO" in cl and "MAT" not in cl:
            col_map[c] = "TOT_VARIO"
        elif "CONT" in cl:
            col_map[c] = "TOT_CONT"
        elif "MAT_VARIO" in cl:
            col_map[c] = "colli_mat_vario"
        elif "STRINGA" in cl:
            col_map[c] = "stringa"

    df = df.rename(columns=col_map)
    required = ["ID_STORE", "TIPO_CONS", "TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM", "TOT_OTHERS", "TOT_VARIO", "TOT_CONT", "colli_mat_vario", "stringa"]
    for req in required:
        if req not in df.columns:
            df[req] = 0 if "TOT_" in req or "colli" in req else ""

    df = df[df["ID_STORE"].notna()].copy()
    df["ID_STORE"] = df["ID_STORE"].apply(clean_store_id)
    df = df[df["ID_STORE"] != ""]

    # Fill NaNs
    num_cols = ["TOT_ABBIGL", "TOT_CALZAT", "TOT_ECOM", "TOT_OTHERS", "TOT_VARIO", "TOT_CONT", "colli_mat_vario"]
    for nc in num_cols:
        df[nc] = pd.to_numeric(df[nc], errors="coerce").fillna(0.0)

    df["stringa"] = df["stringa"].fillna("").astype(str)
    df["TIPO_CONS"] = df["TIPO_CONS"].fillna("STD").astype(str)
    return df[required]


class NamedBytesIO(io.BytesIO):
    """BytesIO buffer carrying a filename attribute for seamless in-memory processing."""
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


def classify_uploaded_files(uploaded_files: List[Any]) -> Dict[str, Any]:
    """
    Takes a list of uploaded files (or a .zip archive) from a single multi-file uploader
    and automatically classifies them into TOTAL, SHOES, TEXILE, ECOM, and OTHER packages.
    """
    import zipfile

    expanded_files: List[NamedBytesIO] = []
    for uf in (uploaded_files or []):
        fname = getattr(uf, "name", "file.xls")
        uf.seek(0)
        raw_bytes = uf.read()
        uf.seek(0)

        if fname.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                    for zinfo in zf.infolist():
                        if zinfo.is_dir():
                            continue
                        zname = Path(zinfo.filename).name
                        if zname.startswith(".") or zname.startswith("~$"):
                            continue
                        if Path(zname).suffix.lower() in (".xls", ".xlsx", ".csv"):
                            expanded_files.append(NamedBytesIO(zf.read(zinfo.filename), zname))
            except Exception as e:
                print(f"Error reading zip file {fname}: {e}")
        else:
            expanded_files.append(NamedBytesIO(raw_bytes, Path(fname).name))

    total_source = None
    shoes_source = None
    texile_source = None
    ecom_source = None
    other_files = []

    for f in expanded_files:
        u_name = f.name.upper()
        if "TOTAL" in u_name:
            total_source = f
        elif any(k in u_name for k in ["SHOE", "ZAPATO", "CALZAT"]):
            shoes_source = f
        elif any(k in u_name for k in ["TEXIL", "TEXTIL", "ABBIGL"]):
            texile_source = f
        elif "ECOM" in u_name:
            ecom_source = f
        else:
            other_files.append(f)

    return {
        "total": total_source,
        "shoes": shoes_source,
        "texile": texile_source,
        "ecom": ecom_source,
        "other": other_files,
        "summary": {
            "total": total_source.name if total_source else None,
            "shoes": shoes_source.name if shoes_source else None,
            "texile": texile_source.name if texile_source else None,
            "ecom": ecom_source.name if ecom_source else None,
            "other_count": len(other_files),
            "other_names": [f.name for f in other_files]
        }
    }
