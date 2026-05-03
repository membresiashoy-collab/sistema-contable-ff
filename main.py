import hashlib
import importlib
import inspect
import os
import subprocess
from pathlib import Path

import streamlit as st

from database import init_db

from core.ui import (
    aplicar_estilos_globales,
    mostrar_encabezado_modulo_visual,
    mostrar_sidebar_marca,
)

from core.ui_state import (
    obtener_resumen_limpieza,
    preparar_cambio_modulo,
)

from services.seguridad_service import (
    inicializar_seguridad,
    login_usuario,
    obtener_permisos_usuario,
    obtener_empresas_usuario,
    cambiar_password,
)

from services.sesion_service import (
    inicializar_tabla_sesiones,
    crear_sesion,
    obtener_sesion_valida,
    actualizar_actividad,
    actualizar_empresa_sesion,
    cerrar_sesion,
    limpiar_sesiones_vencidas,
)

from services.bancos_service import inicializar_bancos
from services.cajas_service import inicializar_cajas


# ======================================================
# CONFIGURACIÓN GENERAL
# ======================================================

st.set_page_config(
    page_title="Sistema Contable FF",
    page_icon="📘",
    layout="wide",
)

aplicar_estilos_globales()


# ======================================================
# FLAGS DE DESARROLLO
# ======================================================

RECARGAR_MODULOS_DESARROLLO = (
    os.getenv("SISTEMA_CONTABLE_RECARGA_MODULOS", "1").strip() != "0"
)

MOSTRAR_DIAGNOSTICO_TECNICO = (
    os.getenv("SISTEMA_CONTABLE_MOSTRAR_DIAGNOSTICO", "1").strip() != "0"
)


# ======================================================
# INICIALIZACIÓN GENERAL
# ======================================================

init_db()
inicializar_seguridad()
inicializar_bancos()
inicializar_cajas()
inicializar_tabla_sesiones()
limpiar_sesiones_vencidas()


# ======================================================
# CONFIGURACIÓN CENTRAL DE MÓDULOS
# ======================================================

MODULOS_UI = {
    "Ventas": {
        "icono": "📤",
        "titulo": "Ventas",
        "descripcion": (
            "Carga de ventas, Libro IVA Ventas, estadísticas comerciales "
            "y cuenta corriente de clientes."
        ),
    },
    "Cobranzas": {
        "icono": "💵",
        "titulo": "Cobranzas",
        "descripcion": (
            "Registro de cobranzas de clientes, imputación contra cuenta corriente, "
            "retenciones sufridas y operaciones pendientes de conciliación."
        ),
    },
    "Compras": {
        "icono": "📥",
        "titulo": "Compras",
        "descripcion": (
            "Carga de compras, clasificación contable por proveedor, "
            "Libro IVA Compras y cuenta corriente de proveedores."
        ),
    },
    "Pagos": {
        "icono": "💸",
        "titulo": "Pagos",
        "descripcion": (
            "Registro de pagos a proveedores, imputación contra cuenta corriente, "
            "retenciones practicadas y operaciones pendientes de conciliación."
        ),
    },
    "Caja": {
        "icono": "💰",
        "titulo": "Caja",
        "descripcion": (
            "Gestión de efectivo: cajas configurables, ingresos, egresos, "
            "depósitos, retiros, transferencias internas, arqueos y diferencias controladas."
        ),
    },
    "Banco / Caja": {
        "icono": "🏦",
        "titulo": "Banco / Caja",
        "descripcion": (
            "Importación flexible de extractos bancarios, control de saldos, "
            "gastos bancarios, reglas recurrentes y base para conciliación."
        ),
    },
    "Conciliación": {
        "icono": "🔗",
        "titulo": "Conciliación",
        "descripcion": (
            "Cruce entre extractos bancarios y operaciones reales de Tesorería: "
            "sugerencias automáticas, confirmación manual, trazabilidad y desconciliación controlada."
        ),
    },
    "IVA": {
        "icono": "🧾",
        "titulo": "IVA",
        "descripcion": (
            "Control de posición mensual de IVA, débito fiscal, crédito fiscal, "
            "percepciones, retenciones y saldos técnicos."
        ),
    },
    "Contabilidad": {
        "icono": "📚",
        "titulo": "Contabilidad",
        "descripcion": (
            "Libros y reportes contables: Libro Diario, Libro Mayor, "
            "Balance de Sumas y Saldos y control por origen/archivo."
        ),
    },
    "Estado de Cargas": {
        "icono": "📋",
        "titulo": "Estado de Cargas y Auditoría",
        "descripcion": (
            "Auditoría de archivos procesados, errores, advertencias, "
            "eliminación controlada de cargas y backups."
        ),
    },
    "Configuración": {
        "icono": "⚙️",
        "titulo": "Configuración",
        "descripcion": (
            "Parámetros base del sistema, categorías, cuentas contables, "
            "conceptos fiscales, datos maestros y configuraciones generales."
        ),
    },
    "Seguridad": {
        "icono": "🔐",
        "titulo": "Seguridad",
        "descripcion": (
            "Usuarios, roles, permisos y control de acceso al sistema."
        ),
    },
}


MODULOS_RENDER = {
    "Ventas": {
        "modulo": "modulos.ventas",
        "funcion": "mostrar_ventas",
        "dependencias": [
            "modulos.ventas",
        ],
    },
    "Cobranzas": {
        "modulo": "modulos.cobranzas",
        "funcion": "mostrar_cobranzas",
        "dependencias": [
            "services.tesoreria_service",
            "services.cobranzas_service",
            "services.documentos_tesoreria_service",
            "modulos.cobranzas",
        ],
    },
    "Compras": {
        "modulo": "modulos.compras",
        "funcion": "mostrar_compras",
        "dependencias": [
            "services.clasificacion_compras_service",
            "services.compras_service",
            "modulos.compras",
        ],
    },
    "Pagos": {
        "modulo": "modulos.pagos",
        "funcion": "mostrar_pagos",
        "dependencias": [
            "services.tesoreria_service",
            "services.pagos_service",
            "services.documentos_tesoreria_service",
            "modulos.pagos",
        ],
    },
    "Caja": {
        "modulo": "modulos.caja",
        "funcion": "mostrar_caja",
        "dependencias": [
            "services.tesoreria_service",
            "services.cajas_service",
            "modulos.caja",
        ],
    },
    "Banco / Caja": {
        "modulo": "modulos.bancos",
        "funcion": "mostrar_bancos",
        "dependencias": [
            "services.bancos_operaciones_service",
            "services.bancos_service",
            "modulos.bancos",
        ],
    },
    "Conciliación": {
        "modulo": "modulos.conciliacion",
        "funcion": "mostrar_conciliacion",
        "dependencias": [
            "services.tesoreria_service",
            "services.bancos_service",
            "services.conciliacion_service",
            "modulos.conciliacion",
        ],
    },
    "IVA": {
        "modulo": "modulos.iva",
        "funcion": "mostrar_iva",
        "dependencias": [
            "services.iva_service",
            "modulos.iva",
        ],
    },
    "Contabilidad": {
        "modulo": "modulos.reportes",
        "funcion": "mostrar_diario",
        "dependencias": [
            "services.reportes_service",
            "modulos.reportes",
        ],
    },
    "Estado de Cargas": {
        "modulo": "modulos.auditoria",
        "funcion": "mostrar_estado",
        "dependencias": [
            "modulos.auditoria",
        ],
    },
    "Configuración": {
        "modulo": "modulos.configuracion",
        "funcion": "mostrar_configuracion",
        "dependencias": [
            "modulos.configuracion",
        ],
    },
    "Seguridad": {
        "modulo": "modulos.seguridad",
        "funcion": "mostrar_seguridad",
        "dependencias": [
            "modulos.seguridad",
        ],
    },
}


# ======================================================
# UTILIDADES DE DIAGNÓSTICO / RECARGA
# ======================================================

def obtener_commit_actual():
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )

        commit = resultado.stdout.strip()

        if commit:
            return commit

    except Exception:
        pass

    return "sin-git"


def obtener_estado_git_corto():
    try:
        resultado = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            check=False,
        )

        estado = resultado.stdout.strip()

        if estado:
            return "con cambios"

        return "limpio"

    except Exception:
        return "no disponible"


def obtener_ruta_base_datos():
    try:
        from database import conectar

        conn = conectar()
        cur = conn.cursor()
        cur.execute("PRAGMA database_list")
        filas = cur.fetchall()
        conn.close()

        for fila in filas:
            if len(fila) >= 3 and str(fila[1]) == "main":
                return str(fila[2])

    except Exception:
        pass

    return "no disponible"


def obtener_sha_archivo(ruta):
    try:
        ruta = Path(ruta)

        if not ruta.exists():
            return "sin-archivo"

        contenido = ruta.read_bytes()
        return hashlib.sha256(contenido).hexdigest()[:16]

    except Exception:
        return "sha-error"


def importar_modulo(nombre_modulo, recargar=True):
    modulo = importlib.import_module(nombre_modulo)

    if recargar:
        modulo = importlib.reload(modulo)

    return modulo


def cargar_modulo_render(menu):
    config = MODULOS_RENDER.get(menu)

    if config is None:
        raise RuntimeError(f"No existe configuración de render para el menú: {menu}")

    dependencias = config.get("dependencias", [])
    modulo_objetivo = None

    for nombre_modulo in dependencias:
        modulo = importar_modulo(
            nombre_modulo,
            recargar=RECARGAR_MODULOS_DESARROLLO,
        )

        if nombre_modulo == config["modulo"]:
            modulo_objetivo = modulo

    if modulo_objetivo is None:
        modulo_objetivo = importar_modulo(
            config["modulo"],
            recargar=RECARGAR_MODULOS_DESARROLLO,
        )

    funcion = getattr(modulo_objetivo, config["funcion"], None)

    if funcion is None:
        raise RuntimeError(
            f"El módulo {config['modulo']} no tiene la función {config['funcion']}."
        )

    return modulo_objetivo, funcion


def mostrar_diagnostico_tecnico_sidebar(menu, modulo=None):
    if not MOSTRAR_DIAGNOSTICO_TECNICO:
        return

    with st.sidebar.expander("Diagnóstico técnico", expanded=False):
        st.caption(f"Commit: `{obtener_commit_actual()}`")
        st.caption(f"Git: `{obtener_estado_git_corto()}`")
        st.caption(f"Recarga módulos: `{RECARGAR_MODULOS_DESARROLLO}`")
        st.caption(f"DB: `{obtener_ruta_base_datos()}`")

        limpieza = obtener_resumen_limpieza(st.session_state)

        if limpieza:
            st.caption(
                "UI última limpieza: "
                f"`{limpieza.get('desde', '')}` → `{limpieza.get('hacia', '')}`"
            )
            st.caption(f"UI claves limpiadas: `{limpieza.get('cantidad', 0)}`")

        if modulo is not None:
            try:
                ruta = Path(inspect.getfile(modulo)).resolve()
                st.caption(f"Módulo activo: `{menu}`")
                st.caption(f"Archivo: `{ruta}`")
                st.caption(f"SHA: `{obtener_sha_archivo(ruta)}`")
            except Exception as e:
                st.caption(f"Módulo activo: `{menu}`")
                st.caption(f"No se pudo leer ruta del módulo: {e}")


# ======================================================
# ENCABEZADO
# ======================================================

def mostrar_encabezado_modulo(menu):
    datos = MODULOS_UI.get(menu)

    if datos is None:
        icono = ""
        titulo = str(menu)
        descripcion = ""
    else:
        icono = str(datos.get("icono", ""))
        titulo = str(datos.get("titulo", menu))
        descripcion = str(datos.get("descripcion", ""))

    mostrar_encabezado_modulo_visual(
        icono=icono,
        titulo=titulo,
        descripcion=descripcion,
        empresa_nombre=st.session_state.get("empresa_nombre", ""),
    )


# ======================================================
# UTILIDADES DE QUERY PARAMS
# ======================================================

def obtener_sid_url():
    try:
        return st.query_params.get("sid", "")
    except Exception:
        try:
            params = st.experimental_get_query_params()
            valor = params.get("sid", [""])

            if isinstance(valor, list):
                return valor[0]

            return valor

        except Exception:
            return ""


def poner_sid_url(token):
    try:
        st.query_params["sid"] = token
    except Exception:
        try:
            st.experimental_set_query_params(sid=token)
        except Exception:
            pass


def limpiar_sid_url():
    try:
        if "sid" in st.query_params:
            del st.query_params["sid"]
    except Exception:
        try:
            st.experimental_set_query_params()
        except Exception:
            pass


# ======================================================
# UTILIDADES DE EMPRESA OPERATIVA
# ======================================================

def _entero_seguro(valor, default=None):
    try:
        if valor is None:
            return default

        return int(valor)

    except Exception:
        return default


def _rol_es_administrador(datos_usuario):
    rol = str((datos_usuario or {}).get("rol", "")).strip().upper()
    return rol in {"ADMINISTRADOR", "ADMIN", "SUPERADMIN"}


def _actualizar_empresa_sesion_segura(empresa_id):
    token = st.session_state.get("session_token", "")

    if not token or empresa_id is None:
        return

    try:
        actualizar_empresa_sesion(token, int(empresa_id))
    except TypeError:
        try:
            actualizar_empresa_sesion(
                token=token,
                empresa_id=int(empresa_id),
            )
        except Exception:
            pass
    except Exception:
        pass


def _obtener_empresas_activas_usuario(usuario_id):
    try:
        empresas = obtener_empresas_usuario(usuario_id)
    except Exception:
        return None

    return empresas


def _marcar_sin_empresa_operativa():
    st.session_state["empresa_id"] = None
    st.session_state["empresa_nombre"] = "Sin empresa activa"
    st.session_state["empresa_operativa_bloqueada"] = True
    st.session_state["empresa_operativa_mensaje"] = (
        "No hay una empresa activa habilitada para operar."
    )


def _marcar_empresa_operativa(empresa_id, empresa_nombre):
    st.session_state["empresa_id"] = int(empresa_id)
    st.session_state["empresa_nombre"] = str(empresa_nombre)
    st.session_state["empresa_operativa_bloqueada"] = False
    st.session_state["empresa_operativa_mensaje"] = ""


def asegurar_empresa_operativa_actual():
    usuario = st.session_state.get("usuario")

    if not usuario:
        _marcar_sin_empresa_operativa()
        return False

    empresas = _obtener_empresas_activas_usuario(usuario["id"])

    if empresas is None or empresas.empty:
        _marcar_sin_empresa_operativa()
        return False

    empresas = empresas.copy()
    empresas["id"] = empresas["id"].astype(int)

    ids_validos = empresas["id"].tolist()
    empresa_actual = _entero_seguro(st.session_state.get("empresa_id"), default=None)

    if empresa_actual in ids_validos:
        fila = empresas[empresas["id"] == empresa_actual].iloc[0]
        _marcar_empresa_operativa(
            empresa_id=int(fila["id"]),
            empresa_nombre=str(fila["nombre"]),
        )
        return True

    fila = empresas.iloc[0]
    nueva_empresa_id = int(fila["id"])
    nueva_empresa_nombre = str(fila["nombre"])

    _marcar_empresa_operativa(
        empresa_id=nueva_empresa_id,
        empresa_nombre=nueva_empresa_nombre,
    )

    _actualizar_empresa_sesion_segura(nueva_empresa_id)

    if "selector_empresa_activa" in st.session_state:
        del st.session_state["selector_empresa_activa"]

    return True


def puede_operar_modulo(menu):
    if menu == "Seguridad" and usuario_es_administrador():
        return True

    return not bool(st.session_state.get("empresa_operativa_bloqueada", False))


def mostrar_bloqueo_empresa_operativa():
    mostrar_encabezado_modulo_visual(
        icono="🏢",
        titulo="Sin empresa operativa activa",
        descripcion=(
            "Para operar módulos como Ventas, Compras, Banco, Caja, Pagos o IVA, "
            "el usuario debe tener asignada una empresa activa."
        ),
        empresa_nombre=st.session_state.get("empresa_nombre", "Sin empresa activa"),
    )

    if usuario_es_administrador():
        st.warning(
            "No hay una empresa activa disponible para operar. "
            "Entrá a Seguridad para crear una empresa, reactivar una existente o asignarla al usuario."
        )
        st.info(
            "Por seguridad, mientras no exista una empresa activa, solo se permite ingresar a Seguridad."
        )
    else:
        st.error(
            "Tu usuario no tiene ninguna empresa activa asignada. "
            "Pedile al administrador que reactive una empresa o te asigne una empresa activa."
        )


# ======================================================
# ESTADO DE SESIÓN
# ======================================================

def iniciar_estado():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if "usuario" not in st.session_state:
        st.session_state["usuario"] = None

    if "permisos" not in st.session_state:
        st.session_state["permisos"] = set()

    if "empresa_id" not in st.session_state:
        st.session_state["empresa_id"] = None

    if "empresa_nombre" not in st.session_state:
        st.session_state["empresa_nombre"] = "Sin empresa activa"

    if "empresa_operativa_bloqueada" not in st.session_state:
        st.session_state["empresa_operativa_bloqueada"] = True

    if "empresa_operativa_mensaje" not in st.session_state:
        st.session_state["empresa_operativa_mensaje"] = ""

    if "session_token" not in st.session_state:
        st.session_state["session_token"] = ""

    if "menu_actual" not in st.session_state:
        st.session_state["menu_actual"] = "Ventas"

    if "ui_modulo_activo" not in st.session_state:
        st.session_state["ui_modulo_activo"] = st.session_state.get("menu_actual", "Ventas")

    if "ui_estado_version" not in st.session_state:
        st.session_state["ui_estado_version"] = 1


def cargar_usuario_en_estado(datos_usuario, empresa_id_preferida=None):
    st.session_state["autenticado"] = True
    st.session_state["usuario"] = datos_usuario
    st.session_state["permisos"] = obtener_permisos_usuario(datos_usuario["id"])

    empresas = _obtener_empresas_activas_usuario(datos_usuario["id"])

    if empresas is None or empresas.empty:
        _marcar_sin_empresa_operativa()
        return False

    empresas = empresas.copy()
    empresas["id"] = empresas["id"].astype(int)

    opciones = empresas["id"].tolist()
    preferida = _entero_seguro(empresa_id_preferida, default=None)

    if preferida in opciones:
        empresa_id = preferida
    else:
        empresa_id = int(empresas.iloc[0]["id"])

    fila = empresas[empresas["id"] == empresa_id].iloc[0]

    _marcar_empresa_operativa(
        empresa_id=int(fila["id"]),
        empresa_nombre=str(fila["nombre"]),
    )

    _actualizar_empresa_sesion_segura(int(fila["id"]))

    return True


def restaurar_sesion_desde_url():
    if st.session_state.get("autenticado"):
        return

    token = obtener_sid_url()

    if not token:
        return

    sesion = obtener_sesion_valida(token)

    if sesion is None:
        limpiar_sid_url()
        return

    st.session_state["session_token"] = token

    cargar_usuario_en_estado(
        sesion["usuario"],
        empresa_id_preferida=sesion.get("empresa_id", None),
    )

    actualizar_actividad(token)


def validar_sesion_actual():
    token = st.session_state.get("session_token", "")

    if not token:
        return False

    sesion = obtener_sesion_valida(token)

    if sesion is None:
        st.session_state.clear()
        limpiar_sid_url()
        st.warning("La sesión venció por inactividad. Ingresá nuevamente.")
        return False

    actualizar_actividad(token)

    return True


def cerrar_sesion_actual():
    token = st.session_state.get("session_token", "")

    if token:
        cerrar_sesion(token)

    st.session_state.clear()
    limpiar_sid_url()
    st.rerun()


def tiene_permiso(permiso):
    return permiso in st.session_state.get("permisos", set())


def refrescar_permisos_usuario_actual():
    usuario = st.session_state.get("usuario")

    if not usuario:
        return

    st.session_state["permisos"] = obtener_permisos_usuario(usuario["id"])


def usuario_es_administrador():
    usuario = st.session_state.get("usuario") or {}
    return _rol_es_administrador(usuario)


# ======================================================
# LOGIN
# ======================================================

def pantalla_login():
    col1, col2, col3 = st.columns([1, 1.05, 1])

    with col2:
        st.markdown("## Sistema Contable")

        with st.form("form_login"):
            usuario = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")

            ingresar = st.form_submit_button(
                "Ingresar",
                use_container_width=True,
            )

            if ingresar:
                datos = login_usuario(usuario.strip(), password)

                if datos is None:
                    st.error("Usuario o contraseña incorrectos.")
                    return

                empresas = _obtener_empresas_activas_usuario(datos["id"])

                if empresas is None or empresas.empty:
                    if not _rol_es_administrador(datos):
                        st.error(
                            "Tu usuario no tiene ninguna empresa activa asignada. "
                            "Pedile al administrador que reactive una empresa o te asigne una empresa activa."
                        )
                        return

                    token = crear_sesion(datos["id"], None)

                    st.session_state["session_token"] = token
                    st.session_state["usuario"] = datos
                    st.session_state["autenticado"] = True
                    st.session_state["permisos"] = obtener_permisos_usuario(datos["id"])
                    _marcar_sin_empresa_operativa()

                    poner_sid_url(token)
                    st.rerun()

                empresas = empresas.copy()
                empresas["id"] = empresas["id"].astype(int)

                empresa_id = int(empresas.iloc[0]["id"])
                empresa_nombre = str(empresas.iloc[0]["nombre"])

                token = crear_sesion(datos["id"], empresa_id)

                st.session_state["session_token"] = token
                _marcar_empresa_operativa(
                    empresa_id=empresa_id,
                    empresa_nombre=empresa_nombre,
                )

                cargar_usuario_en_estado(
                    datos,
                    empresa_id_preferida=empresa_id,
                )

                poner_sid_url(token)

                st.rerun()


def _cambiar_password_seguro(usuario_id, nueva_password):
    try:
        resultado = cambiar_password(usuario_id, nueva_password)
    except TypeError:
        resultado = cambiar_password(
            usuario_id=usuario_id,
            nueva_password=nueva_password,
        )

    return resultado


def pantalla_cambio_password():
    usuario = st.session_state["usuario"]

    if int(usuario.get("debe_cambiar_password", 0)) != 1:
        return False

    mostrar_encabezado_modulo_visual(
        icono="🔑",
        titulo="Cambio de contraseña obligatorio",
        descripcion="Por seguridad, antes de continuar tenés que definir una nueva contraseña.",
        empresa_nombre=st.session_state.get("empresa_nombre", ""),
    )

    col1, col2, col3 = st.columns([1, 1.15, 1])

    with col2:
        with st.form("form_cambio_password"):
            nueva = st.text_input("Nueva contraseña", type="password")
            repetir = st.text_input("Repetir contraseña", type="password")

            guardar = st.form_submit_button(
                "Cambiar contraseña",
                use_container_width=True,
            )

            if guardar:
                if nueva.strip() == "":
                    st.warning("La contraseña no puede estar vacía.")

                elif nueva != repetir:
                    st.warning("Las contraseñas no coinciden.")

                elif len(nueva) < 8:
                    st.warning("La contraseña debe tener al menos 8 caracteres.")

                else:
                    resultado = _cambiar_password_seguro(usuario["id"], nueva)

                    if resultado is False:
                        st.error("No se pudo cambiar la contraseña.")
                        return True

                    st.success("Contraseña actualizada correctamente.")

                    st.session_state["usuario"]["debe_cambiar_password"] = 0
                    refrescar_permisos_usuario_actual()

                    st.rerun()

    return True


# ======================================================
# SIDEBAR / NAVEGACIÓN
# ======================================================

def obtener_menus_disponibles():
    menus = list(MODULOS_UI.keys())

    empresa_bloqueada = bool(st.session_state.get("empresa_operativa_bloqueada", False))

    if empresa_bloqueada:
        if usuario_es_administrador():
            return ["Seguridad"]

        return []

    if usuario_es_administrador():
        return menus

    return [menu for menu in menus if menu != "Seguridad"]


def mostrar_selector_empresa_sidebar():
    usuario = st.session_state.get("usuario")

    if not usuario:
        return

    try:
        empresas = obtener_empresas_usuario(usuario["id"])
    except Exception:
        empresas = None

    st.sidebar.caption("Empresa activa")

    if empresas is None or empresas.empty:
        st.sidebar.info("Sin empresa activa")
        return

    opciones = []

    for _, fila in empresas.iterrows():
        opciones.append(
            {
                "id": int(fila["id"]),
                "nombre": str(fila["nombre"]),
            }
        )

    ids = [op["id"] for op in opciones]
    labels = [op["nombre"] for op in opciones]

    empresa_actual = _entero_seguro(st.session_state.get("empresa_id"), default=ids[0])

    try:
        index_actual = ids.index(empresa_actual)
    except ValueError:
        index_actual = 0
        empresa_actual = ids[0]
        st.session_state["empresa_id"] = empresa_actual
        st.session_state["empresa_nombre"] = labels[0]
        _actualizar_empresa_sesion_segura(empresa_actual)

    seleccion = st.sidebar.selectbox(
        "Empresa",
        labels,
        index=index_actual,
        label_visibility="collapsed",
        key="selector_empresa_activa",
    )

    nueva_empresa_id = ids[labels.index(seleccion)]
    nueva_empresa_nombre = seleccion

    if nueva_empresa_id != empresa_actual:
        st.session_state["empresa_id"] = nueva_empresa_id
        st.session_state["empresa_nombre"] = nueva_empresa_nombre
        st.session_state["empresa_operativa_bloqueada"] = False
        st.session_state["empresa_operativa_mensaje"] = ""

        _actualizar_empresa_sesion_segura(nueva_empresa_id)

        st.rerun()


def mostrar_sidebar_usuario():
    usuario = st.session_state.get("usuario") or {}
    nombre = str(usuario.get("nombre") or usuario.get("usuario") or "Usuario")
    rol = str(usuario.get("rol") or "").upper()

    st.sidebar.markdown(
        f"""
        <div style="
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 14px;
            background: rgba(15, 23, 42, 0.35);
        ">
            <div style="font-weight: 700;">👤 {nombre}</div>
            <div style="font-size: 12px; opacity: 0.8; margin-top: 6px;">
                Rol: {rol}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_sidebar_navegacion():
    try:
        mostrar_sidebar_marca()
    except TypeError:
        try:
            mostrar_sidebar_marca(titulo="Sistema Contable FF")
        except Exception:
            st.sidebar.markdown("### Sistema Contable FF")
            st.sidebar.caption(
                "Contabilidad, IVA, compras, ventas, bancos y auditoría en un flujo integrado."
            )
    except Exception:
        st.sidebar.markdown("### Sistema Contable FF")
        st.sidebar.caption(
            "Contabilidad, IVA, compras, ventas, bancos y auditoría en un flujo integrado."
        )

    mostrar_sidebar_usuario()
    mostrar_selector_empresa_sidebar()

    st.sidebar.markdown("### Navegación")
    st.sidebar.caption("Ir a:")

    menus = obtener_menus_disponibles()

    if not menus:
        st.sidebar.warning("Sin empresa activa para operar.")

        st.sidebar.divider()

        if st.sidebar.button("Cerrar sesión", use_container_width=True):
            cerrar_sesion_actual()

        return None

    menu_actual = st.session_state.get("menu_actual", "Ventas")

    if menu_actual not in menus:
        menu_actual = menus[0]

    index_actual = menus.index(menu_actual)

    menu = st.sidebar.radio(
        "Módulos",
        menus,
        index=index_actual,
        label_visibility="collapsed",
        key="radio_menu_principal",
    )

    st.session_state["menu_actual"] = menu

    st.sidebar.divider()

    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        cerrar_sesion_actual()

    return menu


# ======================================================
# APLICACIÓN PRINCIPAL
# ======================================================

def ejecutar_modulo(menu):
    modulo = None

    try:
        modulo, funcion = cargar_modulo_render(menu)

        mostrar_encabezado_modulo(menu)

        funcion()

    except Exception as e:
        mostrar_encabezado_modulo(menu)

        st.error("No se pudo cargar el módulo seleccionado.")
        st.exception(e)

    finally:
        mostrar_diagnostico_tecnico_sidebar(menu, modulo=modulo)


def main():
    iniciar_estado()
    restaurar_sesion_desde_url()

    if not st.session_state.get("autenticado"):
        pantalla_login()
        return

    if not validar_sesion_actual():
        pantalla_login()
        return

    if pantalla_cambio_password():
        return

    asegurar_empresa_operativa_actual()

    menu = mostrar_sidebar_navegacion()

    if menu is None:
        mostrar_bloqueo_empresa_operativa()
        return

    if not puede_operar_modulo(menu):
        mostrar_bloqueo_empresa_operativa()
        return

    if preparar_cambio_modulo(st.session_state, menu):
        st.rerun()

    ejecutar_modulo(menu)


main()