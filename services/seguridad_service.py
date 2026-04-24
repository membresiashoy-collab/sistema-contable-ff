import pandas as pd

from database import ejecutar_query
from core.seguridad import generar_hash_password, verificar_password


PERMISOS_BASE = [
    ("ventas.ver", "Ver módulo Ventas", "Ventas"),
    ("ventas.cargar", "Cargar ventas", "Ventas"),

    ("compras.ver", "Ver módulo Compras", "Compras"),
    ("compras.cargar", "Cargar compras", "Compras"),
    ("compras.reclasificar", "Reclasificar compras", "Compras"),

    ("iva.ver", "Ver módulo IVA", "IVA"),

    ("diario.ver", "Ver Libro Diario", "Libro Diario"),
    ("diario.limpiar", "Limpiar Libro Diario", "Libro Diario"),

    ("auditoria.ver", "Ver auditoría y cargas", "Auditoría"),
    ("auditoria.eliminar", "Eliminar cargas y errores", "Auditoría"),

    ("configuracion.ver", "Ver configuración", "Configuración"),
    ("configuracion.editar", "Editar configuración", "Configuración"),

    ("seguridad.ver", "Ver seguridad", "Seguridad"),
    ("seguridad.administrar", "Administrar usuarios y permisos", "Seguridad"),

    ("estados.ver", "Ver estados contables", "Estados Contables"),
]


ROLES_BASE = [
    ("ADMINISTRADOR", "Administrador general del sistema"),
    ("CONTADOR", "Usuario contador"),
    ("AUXILIAR", "Carga de datos"),
    ("CLIENTE", "Cliente con acceso limitado"),
    ("LECTURA", "Solo lectura")
]


def inicializar_seguridad():
    for rol, descripcion in ROLES_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO roles (rol, descripcion)
            VALUES (?, ?)
        """, (rol, descripcion))

    for permiso, descripcion, modulo in PERMISOS_BASE:
        ejecutar_query("""
            INSERT OR IGNORE INTO permisos (permiso, descripcion, modulo)
            VALUES (?, ?, ?)
        """, (permiso, descripcion, modulo))

    asignar_permisos_base()

    ejecutar_query("""
        INSERT OR IGNORE INTO empresas
        (id, nombre, cuit, razon_social, activo)
        VALUES (1, 'Empresa Demo', '', 'Empresa Demo', 1)
    """)

    crear_admin_si_no_existe()


def asignar_permisos_base():
    permisos_todos = [p[0] for p in PERMISOS_BASE]

    for permiso in permisos_todos:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("ADMINISTRADOR", permiso))

    permisos_contador = [
        "ventas.ver", "ventas.cargar",
        "compras.ver", "compras.cargar", "compras.reclasificar",
        "iva.ver",
        "diario.ver",
        "auditoria.ver",
        "configuracion.ver", "configuracion.editar",
        "estados.ver"
    ]

    for permiso in permisos_contador:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("CONTADOR", permiso))

    permisos_auxiliar = [
        "ventas.ver", "ventas.cargar",
        "compras.ver", "compras.cargar",
        "auditoria.ver"
    ]

    for permiso in permisos_auxiliar:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("AUXILIAR", permiso))

    permisos_cliente = [
        "ventas.ver",
        "compras.ver",
        "iva.ver",
        "diario.ver",
        "estados.ver"
    ]

    for permiso in permisos_cliente:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("CLIENTE", permiso))

    permisos_lectura = [
        "ventas.ver",
        "compras.ver",
        "iva.ver",
        "diario.ver"
    ]

    for permiso in permisos_lectura:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("LECTURA", permiso))


def crear_admin_si_no_existe():
    df = ejecutar_query("""
        SELECT id
        FROM usuarios
        WHERE usuario = 'admin'
    """, fetch=True)

    if not df.empty:
        return

    password_hash = generar_hash_password("admin123")

    ejecutar_query("""
        INSERT INTO usuarios
        (usuario, nombre, email, password_hash, rol, activo, debe_cambiar_password)
        VALUES (?, ?, ?, ?, ?, 1, 1)
    """, (
        "admin",
        "Administrador",
        "",
        password_hash,
        "ADMINISTRADOR"
    ))

    df_admin = ejecutar_query("""
        SELECT id
        FROM usuarios
        WHERE usuario = 'admin'
    """, fetch=True)

    if not df_admin.empty:
        usuario_id = int(df_admin.iloc[0]["id"])

        ejecutar_query("""
            INSERT OR IGNORE INTO usuario_empresas
            (usuario_id, empresa_id, activo)
            VALUES (?, 1, 1)
        """, (usuario_id,))


def login_usuario(usuario, password):
    df = ejecutar_query("""
        SELECT id, usuario, nombre, email, password_hash, rol, activo, debe_cambiar_password
        FROM usuarios
        WHERE usuario = ?
    """, (usuario,), fetch=True)

    if df.empty:
        return None

    fila = df.iloc[0]

    if int(fila["activo"]) != 1:
        return None

    if not verificar_password(password, fila["password_hash"]):
        return None

    ejecutar_query("""
        UPDATE usuarios
        SET ultimo_login = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (int(fila["id"]),))

    return {
        "id": int(fila["id"]),
        "usuario": str(fila["usuario"]),
        "nombre": str(fila["nombre"]),
        "email": str(fila["email"]),
        "rol": str(fila["rol"]),
        "debe_cambiar_password": int(fila["debe_cambiar_password"])
    }


def obtener_permisos_usuario(usuario_id):
    df = ejecutar_query("""
        SELECT rp.permiso
        FROM usuarios u
        INNER JOIN rol_permisos rp ON rp.rol = u.rol
        WHERE u.id = ?
          AND u.activo = 1
    """, (usuario_id,), fetch=True)

    if df.empty:
        return set()

    return set(df["permiso"].tolist())


def tiene_permiso(usuario_id, permiso):
    permisos = obtener_permisos_usuario(usuario_id)
    return permiso in permisos


def obtener_empresas_usuario(usuario_id):
    df = ejecutar_query("""
        SELECT e.id, e.nombre, e.cuit, e.razon_social
        FROM empresas e
        INNER JOIN usuario_empresas ue ON ue.empresa_id = e.id
        WHERE ue.usuario_id = ?
          AND ue.activo = 1
          AND e.activo = 1
        ORDER BY e.nombre
    """, (usuario_id,), fetch=True)

    return df


def crear_empresa(nombre, cuit="", razon_social="", domicilio="", actividad=""):
    ejecutar_query("""
        INSERT INTO empresas
        (nombre, cuit, razon_social, domicilio, actividad, activo)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (nombre, cuit, razon_social, domicilio, actividad))


def obtener_empresas():
    return ejecutar_query("""
        SELECT id, nombre, cuit, razon_social, domicilio, actividad, activo
        FROM empresas
        ORDER BY nombre
    """, fetch=True)


def obtener_usuarios():
    return ejecutar_query("""
        SELECT id, usuario, nombre, email, rol, activo, debe_cambiar_password, ultimo_login
        FROM usuarios
        ORDER BY usuario
    """, fetch=True)


def crear_usuario(usuario, nombre, email, password, rol, empresa_ids):
    password_hash = generar_hash_password(password)

    ejecutar_query("""
        INSERT INTO usuarios
        (usuario, nombre, email, password_hash, rol, activo, debe_cambiar_password)
        VALUES (?, ?, ?, ?, ?, 1, 1)
    """, (usuario, nombre, email, password_hash, rol))

    df = ejecutar_query("""
        SELECT id
        FROM usuarios
        WHERE usuario = ?
    """, (usuario,), fetch=True)

    if df.empty:
        return

    usuario_id = int(df.iloc[0]["id"])

    for empresa_id in empresa_ids:
        ejecutar_query("""
            INSERT OR IGNORE INTO usuario_empresas
            (usuario_id, empresa_id, activo)
            VALUES (?, ?, 1)
        """, (usuario_id, int(empresa_id)))


def resetear_password_usuario(usuario_id, nueva_password):
    password_hash = generar_hash_password(nueva_password)

    ejecutar_query("""
        UPDATE usuarios
        SET password_hash = ?,
            debe_cambiar_password = 1
        WHERE id = ?
    """, (password_hash, int(usuario_id)))


def cambiar_password(usuario_id, nueva_password):
    password_hash = generar_hash_password(nueva_password)

    ejecutar_query("""
        UPDATE usuarios
        SET password_hash = ?,
            debe_cambiar_password = 0
        WHERE id = ?
    """, (password_hash, int(usuario_id)))


def actualizar_estado_usuario(usuario_id, activo):
    ejecutar_query("""
        UPDATE usuarios
        SET activo = ?
        WHERE id = ?
    """, (int(activo), int(usuario_id)))


def actualizar_rol_usuario(usuario_id, rol):
    ejecutar_query("""
        UPDATE usuarios
        SET rol = ?
        WHERE id = ?
    """, (rol, int(usuario_id)))


def obtener_roles():
    return ejecutar_query("""
        SELECT rol, descripcion
        FROM roles
        ORDER BY rol
    """, fetch=True)


def obtener_permisos():
    return ejecutar_query("""
        SELECT permiso, descripcion, modulo
        FROM permisos
        ORDER BY modulo, permiso
    """, fetch=True)


def obtener_rol_permisos(rol):
    df = ejecutar_query("""
        SELECT permiso
        FROM rol_permisos
        WHERE rol = ?
    """, (rol,), fetch=True)

    if df.empty:
        return set()

    return set(df["permiso"].tolist())


def guardar_permisos_rol(rol, permisos):
    ejecutar_query("""
        DELETE FROM rol_permisos
        WHERE rol = ?
    """, (rol,))

    for permiso in permisos:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos
            (rol, permiso)
            VALUES (?, ?)
        """, (rol, permiso))


def registrar_auditoria(usuario_id, empresa_id, modulo, accion, entidad="", entidad_id="", valor_anterior="", valor_nuevo="", motivo=""):
    ejecutar_query("""
        INSERT INTO auditoria_cambios
        (usuario_id, empresa_id, modulo, accion, entidad, entidad_id, valor_anterior, valor_nuevo, motivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        usuario_id,
        empresa_id,
        modulo,
        accion,
        entidad,
        entidad_id,
        valor_anterior,
        valor_nuevo,
        motivo
    ))