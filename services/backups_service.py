import shutil
from datetime import datetime
from pathlib import Path

from config import DB_PATH, SQLITE_BACKUPS_DIR, MAX_BACKUPS_SQLITE


def crear_backup_sqlite(motivo="manual"):
    """
    Crea una copia de seguridad de la base SQLite.
    No modifica la base original.
    """

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLITE_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        return {
            "ok": False,
            "mensaje": "No existe base de datos para respaldar.",
            "archivo": ""
        }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    motivo_limpio = str(motivo).strip().replace(" ", "_").replace("/", "_")

    nombre_backup = f"backup_{timestamp}_{motivo_limpio}.db"
    destino = SQLITE_BACKUPS_DIR / nombre_backup

    shutil.copy2(DB_PATH, destino)

    limpiar_backups_antiguos()

    return {
        "ok": True,
        "mensaje": "Backup creado correctamente.",
        "archivo": str(destino)
    }


def listar_backups_sqlite():
    """
    Devuelve una lista de backups disponibles.
    """

    SQLITE_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    archivos = sorted(
        SQLITE_BACKUPS_DIR.glob("*.db"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    datos = []

    for archivo in archivos:
        stat = archivo.stat()

        datos.append({
            "archivo": archivo.name,
            "ruta": str(archivo),
            "fecha_modificacion": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M:%S"),
            "tamano_mb": round(stat.st_size / 1024 / 1024, 2)
        })

    return datos


def limpiar_backups_antiguos():
    """
    Conserva solo los últimos MAX_BACKUPS_SQLITE backups.
    """

    archivos = sorted(
        SQLITE_BACKUPS_DIR.glob("*.db"),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    if len(archivos) <= MAX_BACKUPS_SQLITE:
        return

    for archivo in archivos[MAX_BACKUPS_SQLITE:]:
        try:
            archivo.unlink()
        except Exception:
            pass


def restaurar_backup_sqlite(ruta_backup):
    """
    Restaura un backup reemplazando la base actual.
    Antes de restaurar, crea un backup preventivo.
    """

    backup = Path(ruta_backup)

    if not backup.exists():
        return {
            "ok": False,
            "mensaje": "El archivo de backup no existe."
        }

    if DB_PATH.exists():
        crear_backup_sqlite("antes_de_restaurar")

    shutil.copy2(backup, DB_PATH)

    return {
        "ok": True,
        "mensaje": "Backup restaurado correctamente."
    }