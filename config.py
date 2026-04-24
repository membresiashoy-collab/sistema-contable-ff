import os
from pathlib import Path


# ======================================================
# CONFIGURACIÓN GENERAL DEL SISTEMA
# ======================================================

BASE_DIR = Path(__file__).resolve().parent

APP_NAME = "Sistema Contable FF"

# Entornos posibles:
# local       -> uso en PC / desarrollo
# web         -> uso desplegado en servidor
# production  -> producción real
APP_ENV = os.getenv("APP_ENV", "local").lower()

# Motor de base de datos:
# sqlite por ahora
# postgresql más adelante
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

# Carpetas principales
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
BACKUPS_DIR = Path(os.getenv("BACKUPS_DIR", BASE_DIR / "backups"))

SQLITE_BACKUPS_DIR = BACKUPS_DIR / "sqlite"
EXPORTACIONES_DIR = BACKUPS_DIR / "exportaciones"

# Base SQLite
DB_NAME = os.getenv("DB_NAME", "contabilidad_ff.db")
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / DB_NAME))

# Debug
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Cantidad máxima de backups SQLite a conservar
MAX_BACKUPS_SQLITE = int(os.getenv("MAX_BACKUPS_SQLITE", "20"))


def asegurar_directorios():
    """
    Crea las carpetas necesarias si no existen.
    Esto permite correr el sistema tanto local como web.
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    SQLITE_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTACIONES_DIR.mkdir(parents=True, exist_ok=True)


def es_modo_local():
    return APP_ENV == "local"


def es_modo_web():
    return APP_ENV in ["web", "production"]


def es_sqlite():
    return DB_ENGINE == "sqlite"


# Asegura carpetas al importar configuración
asegurar_directorios()