import json
import re
import unicodedata

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
    ("LECTURA", "Solo lectura"),
]


TABLAS_DEPENDENCIAS_ADMINISTRATIVAS = {
    "usuario_empresas",
    "empresas_actividades",
    "auditoria_cambios",
}


# ======================================================
# UTILIDADES GENERALES
# ======================================================

def _texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def _entero(valor, default=0):
    try:
        if valor is None or pd.isna(valor):
            return default
    except Exception:
        if valor is None:
            return default

    try:
        return int(valor)
    except Exception:
        return default


def _activo(valor):
    return _entero(valor, 0) == 1


def _normalizar_clave(valor):
    texto = _texto(valor)

    if not texto:
        return ""

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    return texto.upper().strip()


def normalizar_cuit(cuit):
    return re.sub(r"\D+", "", _texto(cuit))


def _respuesta(ok, mensaje, **datos):
    resultado = {
        "ok": bool(ok),
        "mensaje": mensaje,
    }
    resultado.update(datos)
    return resultado


def _obtener_empresa_desde_df(empresa_id):
    df = obtener_empresas()

    if df.empty:
        return None

    filtrado = df[df["id"].astype(int) == int(empresa_id)]

    if filtrado.empty:
        return None

    return filtrado.iloc[0].to_dict()


def obtener_empresa(empresa_id):
    return _obtener_empresa_desde_df(empresa_id)


def _usuario_es_administrador(usuario_id):
    if usuario_id is None:
        return False

    df = ejecutar_query("""
        SELECT rol
        FROM usuarios
        WHERE id = ?
          AND activo = 1
    """, (int(usuario_id),), fetch=True)

    if df.empty:
        return False

    rol = _texto(df.iloc[0]["rol"]).upper()
    return rol in {"ADMINISTRADOR", "ADMIN", "SUPERADMIN"}


def _asegurar_usuario_empresa(usuario_id, empresa_id):
    if usuario_id is None or empresa_id is None:
        return

    if not _tabla_existe("usuario_empresas"):
        return

    ejecutar_query("""
        INSERT OR IGNORE INTO usuario_empresas
        (usuario_id, empresa_id, activo)
        VALUES (?, ?, 1)
    """, (int(usuario_id), int(empresa_id)))

    ejecutar_query("""
        UPDATE usuario_empresas
        SET activo = 1
        WHERE usuario_id = ?
          AND empresa_id = ?
    """, (int(usuario_id), int(empresa_id)))


def _buscar_conflicto_empresa(nombre, cuit="", razon_social="", excluir_empresa_id=None):
    df = obtener_empresas()

    if df.empty:
        return None

    nombre_norm = _normalizar_clave(nombre)
    razon_norm = _normalizar_clave(razon_social)
    cuit_norm = normalizar_cuit(cuit)
    excluir_id = int(excluir_empresa_id) if excluir_empresa_id is not None else None

    for _, fila in df.iterrows():
        empresa_id = int(fila["id"])

        if excluir_id is not None and empresa_id == excluir_id:
            continue

        fila_activa = _activo(fila.get("activo"))
        fila_nombre_norm = _normalizar_clave(fila.get("nombre"))
        fila_razon_norm = _normalizar_clave(fila.get("razon_social"))
        fila_cuit_norm = normalizar_cuit(fila.get("cuit"))

        if cuit_norm and fila_cuit_norm and cuit_norm == fila_cuit_norm:
            return {
                "campo": "CUIT",
                "empresa_id": empresa_id,
                "empresa_nombre": _texto(fila.get("nombre")),
                "empresa_activa": fila_activa,
                "mensaje": (
                    "Ya existe una empresa registrada con ese CUIT. "
                    "No corresponde crear otro cliente duplicado; si está inactiva, debe reactivarse o editarse."
                ),
            }

        if fila_activa and nombre_norm and fila_nombre_norm == nombre_norm:
            return {
                "campo": "Nombre interno",
                "empresa_id": empresa_id,
                "empresa_nombre": _texto(fila.get("nombre")),
                "empresa_activa": fila_activa,
                "mensaje": "Ya existe una empresa activa con ese nombre interno.",
            }

        if fila_activa and razon_norm and fila_razon_norm and fila_razon_norm == razon_norm:
            return {
                "campo": "Razón social",
                "empresa_id": empresa_id,
                "empresa_nombre": _texto(fila.get("nombre")),
                "empresa_activa": fila_activa,
                "mensaje": "Ya existe una empresa activa con esa razón social.",
            }

    return None


def validar_datos_empresa(
    nombre,
    cuit="",
    razon_social="",
    domicilio="",
    actividad="",
    excluir_empresa_id=None,
    exigir_datos_completos=True,
):
    nombre = _texto(nombre)
    razon_social = _texto(razon_social)
    domicilio = _texto(domicilio)
    actividad = _texto(actividad)
    cuit_norm = normalizar_cuit(cuit)

    if not nombre:
        return _respuesta(False, "El nombre interno de la empresa es obligatorio.")

    if exigir_datos_completos:
        faltantes = []

        if not cuit_norm:
            faltantes.append("CUIT")
        if not razon_social:
            faltantes.append("Razón social")
        if not domicilio:
            faltantes.append("Domicilio")
        if not actividad:
            faltantes.append("Actividad")

        if faltantes:
            return _respuesta(
                False,
                "Para crear u operar una empresa deben completarse todos los datos mínimos: "
                + ", ".join(faltantes)
                + ".",
            )

    if cuit_norm and len(cuit_norm) != 11:
        return _respuesta(False, "El CUIT debe tener 11 dígitos.")

    conflicto = _buscar_conflicto_empresa(
        nombre=nombre,
        cuit=cuit_norm,
        razon_social=razon_social,
        excluir_empresa_id=excluir_empresa_id,
    )

    if conflicto:
        return _respuesta(False, conflicto["mensaje"], conflicto=conflicto)

    return _respuesta(True, "Datos de empresa válidos.")


def _registrar_auditoria_segura(
    usuario_id,
    empresa_id,
    accion,
    entidad_id="",
    valor_anterior=None,
    valor_nuevo=None,
    motivo="",
):
    if usuario_id is None:
        return

    try:
        ejecutar_query("""
            INSERT INTO auditoria_cambios
            (usuario_id, empresa_id, modulo, accion, entidad, entidad_id, valor_anterior, valor_nuevo, motivo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(usuario_id),
            int(empresa_id) if empresa_id is not None else None,
            "Seguridad",
            accion,
            "empresas",
            str(entidad_id or ""),
            json.dumps(valor_anterior or {}, ensure_ascii=False, default=str),
            json.dumps(valor_nuevo or {}, ensure_ascii=False, default=str),
            _texto(motivo),
        ))
    except Exception:
        pass


def _identificador_sql_seguro(nombre):
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", _texto(nombre)))


def _tabla_existe(tabla):
    if not _identificador_sql_seguro(tabla):
        return False

    df = ejecutar_query("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
    """, (tabla,), fetch=True)

    return not df.empty


def _tabla_tiene_columna(tabla, columna):
    if not _identificador_sql_seguro(tabla) or not _identificador_sql_seguro(columna):
        return False

    if not _tabla_existe(tabla):
        return False

    try:
        df = ejecutar_query(f"PRAGMA table_info({tabla})", fetch=True)
    except Exception:
        return False

    if df.empty or "name" not in df.columns:
        return False

    return columna in set(df["name"].astype(str).tolist())


def obtener_dependencias_empresa(empresa_id, incluir_administrativas=False):
    empresa_id = int(empresa_id)

    df_tablas = ejecutar_query("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """, fetch=True)

    if df_tablas.empty:
        return pd.DataFrame(columns=["tabla", "cantidad", "tipo", "bloquea_borrado"])

    dependencias = []
    tablas_excluidas = {"empresas"}

    for tabla in df_tablas["name"].astype(str).tolist():
        if tabla in tablas_excluidas:
            continue

        if not _identificador_sql_seguro(tabla):
            continue

        if not _tabla_tiene_columna(tabla, "empresa_id"):
            continue

        try:
            df_count = ejecutar_query(
                f"SELECT COUNT(*) AS cantidad FROM {tabla} WHERE empresa_id = ?",
                (empresa_id,),
                fetch=True,
            )
        except Exception:
            continue

        cantidad = 0

        if not df_count.empty and "cantidad" in df_count.columns:
            cantidad = _entero(df_count.iloc[0]["cantidad"], 0)

        if cantidad <= 0:
            continue

        es_administrativa = tabla in TABLAS_DEPENDENCIAS_ADMINISTRATIVAS

        if es_administrativa and not incluir_administrativas:
            continue

        dependencias.append({
            "tabla": tabla,
            "cantidad": cantidad,
            "tipo": "Administrativa" if es_administrativa else "Operativa",
            "bloquea_borrado": 0 if es_administrativa else 1,
        })

    return pd.DataFrame(dependencias)


def empresa_tiene_movimientos(empresa_id):
    dependencias = obtener_dependencias_empresa(empresa_id, incluir_administrativas=False)
    return not dependencias.empty


# ======================================================
# INICIALIZACIÓN
# ======================================================

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


# ======================================================
# ROLES Y PERMISOS BASE
# ======================================================

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
        "estados.ver",
    ]

    for permiso in permisos_contador:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("CONTADOR", permiso))

    permisos_auxiliar = [
        "ventas.ver", "ventas.cargar",
        "compras.ver", "compras.cargar",
        "auditoria.ver",
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
        "estados.ver",
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
        "diario.ver",
    ]

    for permiso in permisos_lectura:
        ejecutar_query("""
            INSERT OR IGNORE INTO rol_permisos (rol, permiso)
            VALUES (?, ?)
        """, ("LECTURA", permiso))


# ======================================================
# USUARIOS / LOGIN
# ======================================================

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
        "ADMINISTRADOR",
    ))

    df_admin = ejecutar_query("""
        SELECT id
        FROM usuarios
        WHERE usuario = 'admin'
    """, fetch=True)

    if not df_admin.empty:
        usuario_id = int(df_admin.iloc[0]["id"])
        _asegurar_usuario_empresa(usuario_id, 1)


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
        "debe_cambiar_password": int(fila["debe_cambiar_password"]),
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
        _asegurar_usuario_empresa(usuario_id, empresa_id)


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


def obtener_usuarios():
    return ejecutar_query("""
        SELECT id, usuario, nombre, email, rol, activo, debe_cambiar_password, ultimo_login
        FROM usuarios
        ORDER BY usuario
    """, fetch=True)


# ======================================================
# EMPRESAS
# ======================================================

def obtener_empresas_usuario(usuario_id):
    """
    Devuelve empresas activas operables por el usuario.

    Regla:
    - ADMINISTRADOR ve todas las empresas activas.
    - Usuarios no administradores ven solo empresas activas asignadas.
    """

    if _usuario_es_administrador(usuario_id):
        return ejecutar_query("""
            SELECT id, nombre, cuit, razon_social
            FROM empresas
            WHERE activo = 1
            ORDER BY nombre
        """, fetch=True)

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


def obtener_empresas(incluir_inactivas=True):
    condicion = "" if incluir_inactivas else "WHERE activo = 1"

    return ejecutar_query(f"""
        SELECT id, nombre, cuit, razon_social, domicilio, actividad, activo
        FROM empresas
        {condicion}
        ORDER BY activo DESC, nombre
    """, fetch=True)


def crear_empresa(nombre, cuit="", razon_social="", domicilio="", actividad="", usuario_id=None):
    nombre = _texto(nombre)
    cuit_norm = normalizar_cuit(cuit)
    razon_social = _texto(razon_social)
    domicilio = _texto(domicilio)
    actividad = _texto(actividad)

    validacion = validar_datos_empresa(
        nombre=nombre,
        cuit=cuit_norm,
        razon_social=razon_social,
        domicilio=domicilio,
        actividad=actividad,
        exigir_datos_completos=True,
    )

    if not validacion.get("ok"):
        return validacion

    ejecutar_query("""
        INSERT INTO empresas
        (nombre, cuit, razon_social, domicilio, actividad, activo)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (nombre, cuit_norm, razon_social, domicilio, actividad))

    df_id = ejecutar_query("SELECT last_insert_rowid() AS id", fetch=True)
    empresa_id = None

    if not df_id.empty and "id" in df_id.columns:
        empresa_id = int(df_id.iloc[0]["id"])

    if empresa_id is None:
        df = obtener_empresas()

        if not df.empty:
            candidatos = df[
                (df["nombre"].apply(_normalizar_clave) == _normalizar_clave(nombre))
                & (df["activo"].astype(int) == 1)
            ].copy()

            if cuit_norm:
                candidatos = candidatos[candidatos["cuit"].apply(normalizar_cuit) == cuit_norm]

            if not candidatos.empty:
                empresa_id = int(candidatos.sort_values("id", ascending=False).iloc[0]["id"])

    if usuario_id is not None and empresa_id is not None:
        _asegurar_usuario_empresa(usuario_id, empresa_id)

    valor_nuevo = {
        "id": empresa_id,
        "nombre": nombre,
        "cuit": cuit_norm,
        "razon_social": razon_social,
        "domicilio": domicilio,
        "actividad": actividad,
        "activo": 1,
    }

    _registrar_auditoria_segura(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        accion="CREAR_EMPRESA",
        entidad_id=empresa_id,
        valor_anterior={},
        valor_nuevo=valor_nuevo,
        motivo="Alta de empresa desde Seguridad.",
    )

    return _respuesta(
        True,
        "Empresa creada correctamente.",
        empresa_id=empresa_id,
        empresa=valor_nuevo,
    )


def actualizar_empresa(empresa_id, nombre, cuit="", razon_social="", domicilio="", actividad="", usuario_id=None, motivo=""):
    empresa_id = int(empresa_id)
    anterior = obtener_empresa(empresa_id)

    if not anterior:
        return _respuesta(False, "La empresa seleccionada no existe.")

    nombre = _texto(nombre)
    cuit_norm = normalizar_cuit(cuit)
    razon_social = _texto(razon_social)
    domicilio = _texto(domicilio)
    actividad = _texto(actividad)

    validacion = validar_datos_empresa(
        nombre=nombre,
        cuit=cuit_norm,
        razon_social=razon_social,
        domicilio=domicilio,
        actividad=actividad,
        excluir_empresa_id=empresa_id,
        exigir_datos_completos=True,
    )

    if not validacion.get("ok"):
        return validacion

    ejecutar_query("""
        UPDATE empresas
        SET nombre = ?,
            cuit = ?,
            razon_social = ?,
            domicilio = ?,
            actividad = ?
        WHERE id = ?
    """, (nombre, cuit_norm, razon_social, domicilio, actividad, empresa_id))

    nuevo = obtener_empresa(empresa_id) or {
        "id": empresa_id,
        "nombre": nombre,
        "cuit": cuit_norm,
        "razon_social": razon_social,
        "domicilio": domicilio,
        "actividad": actividad,
    }

    if usuario_id is not None:
        _asegurar_usuario_empresa(usuario_id, empresa_id)

    _registrar_auditoria_segura(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        accion="EDITAR_EMPRESA",
        entidad_id=empresa_id,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        motivo=motivo or "Edición de datos de empresa desde Seguridad.",
    )

    return _respuesta(True, "Empresa actualizada correctamente.", empresa_id=empresa_id, empresa=nuevo)


def actualizar_estado_empresa(empresa_id, activo, usuario_id=None, motivo=""):
    empresa_id = int(empresa_id)
    activo = int(bool(activo))
    anterior = obtener_empresa(empresa_id)

    if not anterior:
        return _respuesta(False, "La empresa seleccionada no existe.")

    if activo == 1:
        validacion = validar_datos_empresa(
            nombre=anterior.get("nombre", ""),
            cuit=anterior.get("cuit", ""),
            razon_social=anterior.get("razon_social", ""),
            domicilio=anterior.get("domicilio", ""),
            actividad=anterior.get("actividad", ""),
            excluir_empresa_id=empresa_id,
            exigir_datos_completos=True,
        )

        if not validacion.get("ok"):
            return _respuesta(
                False,
                "No se puede reactivar la empresa porque sus datos están incompletos o chocan con otra empresa.",
                detalle=validacion,
            )

    ejecutar_query("""
        UPDATE empresas
        SET activo = ?
        WHERE id = ?
    """, (activo, empresa_id))

    nuevo = obtener_empresa(empresa_id) or anterior.copy()
    accion = "REACTIVAR_EMPRESA" if activo == 1 else "DESACTIVAR_EMPRESA"
    mensaje = "Empresa reactivada correctamente." if activo == 1 else "Empresa desactivada correctamente."

    if activo == 1 and usuario_id is not None:
        _asegurar_usuario_empresa(usuario_id, empresa_id)

    _registrar_auditoria_segura(
        usuario_id=usuario_id,
        empresa_id=empresa_id,
        accion=accion,
        entidad_id=empresa_id,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        motivo=motivo or mensaje,
    )

    return _respuesta(True, mensaje, empresa_id=empresa_id, empresa=nuevo)


def desactivar_empresa(empresa_id, usuario_id=None, motivo=""):
    return actualizar_estado_empresa(
        empresa_id=empresa_id,
        activo=0,
        usuario_id=usuario_id,
        motivo=motivo or "Baja lógica de empresa.",
    )


def reactivar_empresa(empresa_id, usuario_id=None, motivo=""):
    return actualizar_estado_empresa(
        empresa_id=empresa_id,
        activo=1,
        usuario_id=usuario_id,
        motivo=motivo or "Reactivación de empresa.",
    )


def eliminar_empresa_si_vacia(empresa_id, usuario_id=None, motivo=""):
    empresa_id = int(empresa_id)
    anterior = obtener_empresa(empresa_id)

    if not anterior:
        return _respuesta(False, "La empresa seleccionada no existe.")

    if _activo(anterior.get("activo")):
        return _respuesta(
            False,
            "Para eliminar físicamente una empresa, primero debe estar desactivada. Si se puede operar con ella, no corresponde borrarla.",
        )

    dependencias_bloqueantes = obtener_dependencias_empresa(empresa_id, incluir_administrativas=False)

    if not dependencias_bloqueantes.empty:
        return _respuesta(
            False,
            "La empresa tiene movimientos o registros operativos asociados. Por seguridad no se borra físicamente; corresponde mantenerla desactivada.",
            dependencias=dependencias_bloqueantes,
        )

    if _tabla_existe("usuario_empresas"):
        ejecutar_query("DELETE FROM usuario_empresas WHERE empresa_id = ?", (empresa_id,))

    if _tabla_existe("empresas_actividades"):
        ejecutar_query("DELETE FROM empresas_actividades WHERE empresa_id = ?", (empresa_id,))

    if _tabla_existe("auditoria_cambios") and _tabla_tiene_columna("auditoria_cambios", "empresa_id"):
        ejecutar_query("UPDATE auditoria_cambios SET empresa_id = NULL WHERE empresa_id = ?", (empresa_id,))

    ejecutar_query("DELETE FROM empresas WHERE id = ?", (empresa_id,))

    _registrar_auditoria_segura(
        usuario_id=usuario_id,
        empresa_id=None,
        accion="ELIMINAR_EMPRESA_VACIA",
        entidad_id=empresa_id,
        valor_anterior=anterior,
        valor_nuevo={},
        motivo=motivo or "Eliminación física de empresa desactivada y sin movimientos operativos.",
    )

    return _respuesta(True, "Empresa desactivada y sin movimientos operativos eliminada correctamente.", empresa_id=empresa_id)


# ======================================================
# ROLES / PERMISOS
# ======================================================

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


# ======================================================
# AUDITORÍA
# ======================================================

def registrar_auditoria(
    usuario_id,
    empresa_id,
    modulo,
    accion,
    entidad="",
    entidad_id="",
    valor_anterior="",
    valor_nuevo="",
    motivo="",
):
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
        motivo,
    ))
