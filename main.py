import streamlit as st

from database import init_db
from services.seguridad_service import (
    inicializar_seguridad,
    login_usuario,
    obtener_permisos_usuario,
    obtener_empresas_usuario,
    cambiar_password
)

from modulos import ventas, compras, reportes, auditoria, configuracion, seguridad

st.set_page_config(
    page_title="Sistema Contable FF",
    layout="wide"
)

init_db()
inicializar_seguridad()


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


def tiene_permiso(permiso):
    return permiso in st.session_state.get("permisos", set())


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

            st.session_state["autenticado"] = True
            st.session_state["usuario"] = datos
            st.session_state["permisos"] = obtener_permisos_usuario(datos["id"])

            empresas = obtener_empresas_usuario(datos["id"])

            if not empresas.empty:
                st.session_state["empresa_id"] = int(empresas.iloc[0]["id"])
                st.session_state["empresa_nombre"] = str(empresas.iloc[0]["nombre"])

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
                st.session_state.clear()
                st.rerun()

    return True


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
        opciones.append("Libro Diario")

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
        st.session_state.clear()
        st.rerun()

    st.caption(f"Empresa activa: **{st.session_state['empresa_nombre']}**")

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

    elif menu == "Libro Diario":
        reportes.mostrar_diario()

    elif menu == "Estado de Cargas":
        auditoria.mostrar_estado()

    elif menu == "Configuración":
        configuracion.mostrar_configuracion()

    elif menu == "Seguridad":
        seguridad.mostrar_seguridad()


iniciar_estado()

if not st.session_state["autenticado"]:
    pantalla_login()
else:
    if not pantalla_cambio_password():
        menu_principal()