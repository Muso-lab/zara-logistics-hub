import os
from pathlib import Path

# Base Paths (portable across any OS / Cloud / Container)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("ZARA_DATA_DIR", str(BASE_DIR / "data")))
TEMPLATES_DIR = DATA_DIR / "templates"
OUTPUT_DIR = Path(os.getenv("ZARA_OUTPUT_DIR", str(BASE_DIR / "output")))

# Optional network paths (used only if configured via env and accessible)
DEFAULT_NETWORK_INPUT_DIR = Path(os.getenv("ZARA_NETWORK_INPUT_DIR", str(DATA_DIR / "input")))
DEFAULT_NETWORK_OUTPUT_DIR = Path(os.getenv("ZARA_NETWORK_OUTPUT_DIR", str(OUTPUT_DIR)))

# Database Path
DB_PATH = Path(os.getenv("ZARA_DB_PATH", str(DATA_DIR / "zara_history.db")))

# Master Data Paths
ANAGRAFICA_FILE = DATA_DIR / "anagrafica_negozi.xlsx"
PLANNER_TEMPLATE_FILE = TEMPLATES_DIR / "Planning ITX_RM.xlsx"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Logistics Constants
PESO_SPECIFICO_COLLO_KG = 15.0  # 15 kg per collo standard
VOLUME_DIVISORE_COLLI_BARRA9 = 0.092  # Colli B9 = Volume / 0.092
VOLUME_DIVISORE_PEDANA = 1.9  # Pedane = ceil(Volume / 1.9)
PERCENTUALE_BARRA0_SPLIT = 0.7  # 70% Barra 0
PERCENTUALE_BARRA9_SPLIT = 0.3  # 30% Barra 9
MAGAZZINO_CARICO_DEFAULT = "MAMONT"
COD_MITTENTE_DEFAULT = 1

# Inditex Extranet Settings (configurable via environment variables)
EXTRANET_LOGIN_URL = os.getenv(
    "EXTRANET_LOGIN_URL",
    "https://extranet.inditex.com/AgenteAduanas/home.html?method=getHome"
)
EXTRANET_BUZON_URL = os.getenv(
    "EXTRANET_BUZON_URL",
    "https://extranet.inditex.com/AgenteAduanas/Plataformas/getPlataforma.html?method=getBuzonPlataforma"
)
EXTRANET_DEFAULT_USER = os.getenv("EXTRANET_USER", "plt_it_transmec_ro")
EXTRANET_DEFAULT_PASS = os.getenv("EXTRANET_PASS", "")
