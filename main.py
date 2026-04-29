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
# En Codespaces conviene mantener la recarga activa.
# Si más adelante se usa en producción y se quiere desactivar:
# export SISTEMA_CONTABLE_RECARGA_MODULOS=0
# export SISTEMA_CONTABLE_MOSTRAR_DIAGNOSTICO=0

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
    "Compras": {
        "icono": "📥",
        "titulo": "Compras",
        "descripcion": (
            "Carga de compras, clasificación contable por proveedor, "
            "Libro IVA Compras y cuenta corriente de proveedores."
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
    "Compras": {
        "modulo": "modulos.compras",
        "funcion": "mostrar_compras",
        "dependencias": [
            "services.clasificacion_compras_service",
            "services.compras_service",
            "modulos.compras",
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
        st.session_state["empresa_id"] = 1

    if "empresa_nombre" not in st.session_state:
        st.session_state["empresa_nombre"] = "Empresa Demo"

    if "session_token" not in st.session_state:
        st.session_state["session_token"] = ""


def cargar_usuario_en_estado(datos_usuario, empresa_id_preferida=None):
    st.session_state["autenticado"] = True
    st.session_state["usuario"] = datos_usuario
    st.session_state["permisos"] = obtener_permisos_usuario(datos_usuario["id"])

    empresas = obtener_empresas_usuario(datos_usuario["id"])

    if not empresas.empty:
        opciones = empresas["id"].tolist()

        if empresa_id_preferida in opciones:
            empresa_id = empresa_id_preferida
        else:
            empresa_id = int(empresas.iloc[0]["id"])

        fila = empresas[empresas["id"] == empresa_id].iloc[0]

        st.session_state["empresa_id"] = int(fila["id"])
        st.session_state["empresa_nombre"] = str(fila["nombre"])


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
        empresa_id_preferida=sesion.get("empresa_id", 1),
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

                empresas = obtener_empresas_usuario(datos["id"])

                empresa_id = 1
                empresa_nombre = "Empresa Demo"

                if not empresas.empty:
                    empresa_id = int(empresas.iloc[0]["id"])
                    empresa_nombre = str(empresas.iloc[0]["nombre"])

                token = crear_sesion(datos["id"], empresa_id)

                st.session_state["session_token"] = token
                st.session_state["empresa_id"] = empresa_id
                st.session_state["empresa_nombre"] = empresa_nombre

                cargar_usuario_en_estado(
                    datos,
                    empresa_id_preferida=empresa_id,
                )
                poner_sid_url(token)

                st.rerun()


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
                    st.warning("Usá una contraseña de al menos 8 caracteres.")

                else:
                    cambiar_password(usuario["id"], nueva)
                    st.success("Contraseña actualizada. Volvé a ingresar.")
                    cerrar_sesion_actual()

    return True


# ======================================================
# EMPRESA ACTIVA
# ======================================================

def selector_empresa_sidebar():
    usuario = st.session_state["usuario"]
    empresas = obtener_empresas_usuario(usuario["id"])

    if empresas.empty:
        st.sidebar.error("El usuario no tiene empresas asignadas.")
        return

    opciones = empresas["id"].tolist()
    empresa_actual = st.session_state.get("empresa_id", opciones[0])

    if empresa_actual not in opciones:
        empresa_actual = opciones[0]

    seleccion = st.sidebar.selectbox(
        "Empresa activa",
        opciones,
        index=opciones.index(empresa_actual),
        format_func=lambda x: empresas[empresas["id"] == x].iloc[0]["nombre"],
    )

    fila = empresas[empresas["id"] == seleccion].iloc[0]

    st.session_state["empresa_id"] = int(fila["id"])
    st.session_state["empresa_nombre"] = str(fila["nombre"])

    actualizar_empresa_sesion(
        st.session_state.get("session_token", ""),
        int(fila["id"]),
    )


# ======================================================
# MENÚ PRINCIPAL
# ======================================================

def obtener_opciones_menu():
    opciones = []

    if tiene_permiso("ventas.ver"):
        opciones.append("Ventas")

    if tiene_permiso("compras.ver"):
        opciones.append("Compras")

    if tiene_permiso("bancos.ver"):
        opciones.append("Banco / Caja")

    if tiene_permiso("iva.ver"):
        opciones.append("IVA")

    if tiene_permiso("diario.ver"):
        opciones.append("Contabilidad")

    if tiene_permiso("auditoria.ver"):
        opciones.append("Estado de Cargas")

    if tiene_permiso("configuracion.ver"):
        opciones.append("Configuración")

    if tiene_permiso("seguridad.ver"):
        opciones.append("Seguridad")

    return opciones


def renderizar_modulo(menu):
    if menu == "Banco / Caja":
        inicializar_bancos()

    try:
        modulo, funcion = cargar_modulo_render(menu)
        funcion()
        return modulo

    except ModuleNotFoundError:
        st.warning(f"El módulo {menu} todavía no está disponible.")
        return None

    except Exception as e:
        st.error(f"No se pudo renderizar el módulo {menu}: {e}")
        raise


def menu_principal():
    refrescar_permisos_usuario_actual()

    usuario = st.session_state["usuario"]

    mostrar_sidebar_marca(
        usuario=usuario["usuario"],
        rol=usuario["rol"],
    )

    selector_empresa_sidebar()

    opciones = obtener_opciones_menu()

    if not opciones:
        st.error("Tu usuario no tiene permisos asignados.")
        return

    st.sidebar.markdown("#### Navegación")

    menu = st.sidebar.radio(
        "Ir a:",
        opciones,
        key="menu_principal_modulo",
    )

    st.sidebar.divider()

    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        cerrar_sesion_actual()

    mostrar_encabezado_modulo(menu)

    modulo_renderizado = renderizar_modulo(menu)

    mostrar_diagnostico_tecnico_sidebar(
        menu=menu,
        modulo=modulo_renderizado,
    )


# ======================================================
# EJECUCIÓN
# ======================================================

iniciar_estado()
restaurar_sesion_desde_url()

if not st.session_state["autenticado"]:
    pantalla_login()
else:
    if validar_sesion_actual():
        if not pantalla_cambio_password():
            menu_principal()
    else:
        pantalla_login()