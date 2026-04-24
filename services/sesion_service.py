from datetime import datetime, timedelta
import secrets

from database import ejecutar_query
from config import SESSION_TIMEOUT_MINUTES


def inicializar_tabla_sesiones():
    """
    Crea la tabla de sesiones persistentes.
    Permite mantener login aunque se refresque la página.
    """

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS sesiones_usuario (
            token TEXT PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            empresa_id INTEGER,
            activa INTEGER DEFAULT 1,
            creada_en TEXT,
            ultima_actividad TEXT,
            expira_en TEXT
        )
    """)

    ejecutar_query("""
        CREATE INDEX IF NOT EXISTS idx_sesiones_usuario_id
        ON sesiones_usuario(usuario_id)
    """)

    ejecutar_query("""
        CREATE INDEX IF NOT EXISTS idx_sesiones_activa
        ON sesiones_usuario(activa)
    """)


def _ahora():
    return datetime.now()


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def crear_sesion(usuario_id, empresa_id=1):
    """
    Crea una sesión persistente para el usuario.
    """

    token = secrets.token_urlsafe(32)
    ahora = _ahora()
    expira = ahora + timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    ejecutar_query("""
        INSERT INTO sesiones_usuario
        (token, usuario_id, empresa_id, activa, creada_en, ultima_actividad, expira_en)
        VALUES (?, ?, ?, 1, ?, ?, ?)
    """, (
        token,
        int(usuario_id),
        int(empresa_id) if empresa_id is not None else None,
        _fmt(ahora),
        _fmt(ahora),
        _fmt(expira)
    ))

    return token


def obtener_sesion_valida(token):
    """
    Devuelve datos de sesión y usuario si el token es válido.
    Si está vencido, lo invalida.
    """

    if not token:
        return None

    df = ejecutar_query("""
        SELECT 
            s.token,
            s.usuario_id,
            s.empresa_id,
            s.activa,
            s.expira_en,
            u.usuario,
            u.nombre,
            u.email,
            u.rol,
            u.activo,
            u.debe_cambiar_password
        FROM sesiones_usuario s
        INNER JOIN usuarios u ON u.id = s.usuario_id
        WHERE s.token = ?
          AND s.activa = 1
    """, (token,), fetch=True)

    if df.empty:
        return None

    fila = df.iloc[0]

    if int(fila["activo"]) != 1:
        cerrar_sesion(token)
        return None

    try:
        expira = datetime.strptime(str(fila["expira_en"]), "%Y-%m-%d %H:%M:%S")
    except Exception:
        cerrar_sesion(token)
        return None

    if _ahora() > expira:
        cerrar_sesion(token)
        return None

    return {
        "token": str(fila["token"]),
        "usuario_id": int(fila["usuario_id"]),
        "empresa_id": int(fila["empresa_id"]) if fila["empresa_id"] is not None else 1,
        "usuario": {
            "id": int(fila["usuario_id"]),
            "usuario": str(fila["usuario"]),
            "nombre": str(fila["nombre"]),
            "email": str(fila["email"]),
            "rol": str(fila["rol"]),
            "debe_cambiar_password": int(fila["debe_cambiar_password"])
        }
    }


def actualizar_actividad(token):
    """
    Renueva la sesión según actividad del usuario.
    """

    if not token:
        return

    ahora = _ahora()
    expira = ahora + timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    ejecutar_query("""
        UPDATE sesiones_usuario
        SET ultima_actividad = ?,
            expira_en = ?
        WHERE token = ?
          AND activa = 1
    """, (_fmt(ahora), _fmt(expira), token))


def actualizar_empresa_sesion(token, empresa_id):
    """
    Guarda la empresa activa actual dentro de la sesión.
    """

    if not token:
        return

    ejecutar_query("""
        UPDATE sesiones_usuario
        SET empresa_id = ?
        WHERE token = ?
          AND activa = 1
    """, (int(empresa_id), token))


def cerrar_sesion(token):
    """
    Invalida una sesión.
    """

    if not token:
        return

    ejecutar_query("""
        UPDATE sesiones_usuario
        SET activa = 0
        WHERE token = ?
    """, (token,))


def limpiar_sesiones_vencidas():
    """
    Marca como inactivas las sesiones vencidas.
    """

    ahora = _fmt(_ahora())

    ejecutar_query("""
        UPDATE sesiones_usuario
        SET activa = 0
        WHERE activa = 1
          AND expira_en < ?
    """, (ahora,))