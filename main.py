from html import escape

import streamlit as st

from database import init_db
from services.seguridad_service import (
    inicializar_seguridad,
    login_usuario,
    obtener_permisos_usuario,
    obtener_empresas_usuario,
    cambiar_password
)

from services.sesion_service import (
    inicializar_tabla_sesiones,
    crear_sesion,
    obtener_sesion_valida,
    actualizar_actividad,
    actualizar_empresa_sesion,
    cerrar_sesion,
    limpiar_sesiones_vencidas
)

from modulos import ventas, compras, reportes, auditoria, configuracion, seguridad


# ======================================================
# CONFIGURACIÓN GENERAL STREAMLIT
# ======================================================

st.set_page_config(
    page_title="Sistema Contable FF",
    layout="wide"
)


# ======================================================
# INICIALIZACIÓN GENERAL
# ======================================================

init_db()
inicializar_seguridad()
inicializar_tabla_sesiones()
limpiar_sesiones_vencidas()


# ======================================================
# ENCABEZADOS CENTRALES DE MÓDULOS
# ======================================================

MODULOS_UI = {
    "Ventas": {
        "icono": "📤",
        "titulo": "Ventas",
        "descripcion": (
            "Carga de ventas, Libro IVA Ventas, estadísticas comerciales "
            "y cuenta corriente de clientes."
        )
    },
    "Compras": {
        "icono": "📥",
        "titulo": "Compras",
        "descripcion": (
            "Carga de compras, clasificación contable por proveedor, "
            "Libro IVA Compras y cuenta corriente de proveedores."
        )
    },
    "IVA": {
        "icono": "🧾",
        "titulo": "IVA",
        "descripcion": (
            "Control de posición mensual de IVA, débito fiscal, crédito fiscal, "
            "percepciones, retenciones y saldos técnicos."
        )
    },
    "Contabilidad": {
        "icono": "📚",
        "titulo": "Contabilidad",
        "descripcion": (
            "Libros y reportes contables: Libro Diario, Libro Mayor, "
            "Balance de Sumas y Saldos y control por origen/archivo."
        )
    },
    "Estado de Cargas": {
        "icono": "📋",
        "titulo": "Estado de Cargas y Auditoría",
        "descripcion": (
            "Auditoría de archivos procesados, errores, advertencias, "
            "eliminación controlada de cargas y backups."
        )
    },
    "Configuración": {
        "icono": "⚙️",
        "titulo": "Configuración",
        "descripcion": (
            "Parámetros base del sistema, categorías, cuentas contables, "
            "conceptos fiscales, datos maestros y configuraciones generales."
        )
    },
    "Seguridad": {
        "icono": "🔐",
        "titulo": "Seguridad",
        "descripcion": (
            "Usuarios, roles, permisos y control de acceso al sistema."
        )
    }
}


def mostrar_encabezado_modulo(menu):
    """
    Encabezado principal único del sistema.

    Regla de arquitectura:
    - El encabezado principal vive solo en main.py.
    - Los archivos dentro de modulos/ no deben usar st.title().
    - Los módulos pueden usar st.subheader(), st.info(), st.tabs(), etc.
    - Se usa markdown/HTML controlado en vez de st.title() para evitar
      que Streamlit arrastre visualmente títulos anteriores entre módulos.
    """

    datos = MODULOS_UI.get(menu)

    if datos is None:
        icono = ""
        titulo = str(menu)
        descripcion = ""
    else:
        icono = str(datos.get("icono", ""))
        titulo = str(datos.get("titulo", menu))
        descripcion = str(datos.get("descripcion", ""))

    icono_html = escape(icono)
    titulo_html = escape(titulo)
    descripcion_html = escape(descripcion)

    st.markdown(
        f"""
        <div style="margin-top: 0.25rem; margin-bottom: 1.35rem;">
            <div style="
                display: flex;
                align-items: center;
                gap: 0.85rem;
                margin-bottom: 0.45rem;
            ">
                <div style="font-size: 2.35rem; line-height: 1;">{icono_html}</div>
                <div style="
                    font-size: 2.65rem;
                    font-weight: 800;
                    line-height: 1.1;
                    letter-spacing: -0.03em;
                ">
                    {titulo_html}
                </div>
            </div>
            <div style="
                color: rgba(250, 250, 250, 0.68);
                font-size: 0.98rem;
                line-height: 1.45;
                margin-left: 0.1rem;
            ">
                {descripcion_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True
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
    """
    Si el usuario refresca la página, intenta recuperar la sesión usando el token.
    """

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
        empresa_id_preferida=sesion.get("empresa_id", 1)
    )

    actualizar_actividad(token)


def validar_sesion_actual():
    """
    Verifica que la sesión actual siga activa.
    Si venció, fuerza cierre de sesión.
    """

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


# ======================================================
# LOGIN
# ======================================================

def pantalla_login():
    st.title("🔐 Sistema Contable FF")

    st.info("Ingresá con tu usuario y contraseña.")

    with st.form("form_login"):
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        ingresar = st.form_submit_button("Ingresar")

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

            cargar_usuario_en_estado(datos, empresa_id_preferida=empresa_id)
            poner_sid_url(token)

            st.rerun()


def pantalla_cambio_password():
    usuario = st.session_state["usuario"]

    if int(usuario.get("debe_cambiar_password", 0)) != 1:
        return False

    st.title("🔑 Cambio de contraseña obligatorio")

    with st.form("form_cambio_password"):
        nueva = st.text_input("Nueva contraseña", type="password")
        repetir = st.text_input("Repetir contraseña", type="password")

        guardar = st.form_submit_button("Cambiar contraseña")

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
        format_func=lambda x: empresas[empresas["id"] == x].iloc[0]["nombre"]
    )

    fila = empresas[empresas["id"] == seleccion].iloc[0]

    st.session_state["empresa_id"] = int(fila["id"])
    st.session_state["empresa_nombre"] = str(fila["nombre"])

    actualizar_empresa_sesion(
        st.session_state.get("session_token", ""),
        int(fila["id"])
    )


# ======================================================
# MENÚ PRINCIPAL
# ======================================================

def menu_principal():
    usuario = st.session_state["usuario"]

    st.sidebar.title("📘 Menú")
    st.sidebar.caption(f"Usuario: {usuario['usuario']}")
    st.sidebar.caption(f"Rol: {usuario['rol']}")

    selector_empresa_sidebar()

    opciones = []

    if tiene_permiso("ventas.ver"):
        opciones.append("Ventas")

    if tiene_permiso("compras.ver"):
        opciones.append("Compras")

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

    if not opciones:
        st.error("Tu usuario no tiene permisos asignados.")
        return

    menu = st.sidebar.radio("Ir a:", opciones)

    st.sidebar.divider()

    if st.sidebar.button("Cerrar sesión"):
        cerrar_sesion_actual()

    st.caption(f"Empresa activa: **{st.session_state['empresa_nombre']}**")
    mostrar_encabezado_modulo(menu)

    if menu == "Ventas":
        ventas.mostrar_ventas()

    elif menu == "Compras":
        compras.mostrar_compras()

    elif menu == "IVA":
        try:
            from modulos import iva
            iva.mostrar_iva()
        except Exception:
            st.warning("El módulo IVA todavía no está disponible.")

    elif menu == "Contabilidad":
        reportes.mostrar_diario()

    elif menu == "Estado de Cargas":
        auditoria.mostrar_estado()

    elif menu == "Configuración":
        configuracion.mostrar_configuracion()

    elif menu == "Seguridad":
        seguridad.mostrar_seguridad()


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