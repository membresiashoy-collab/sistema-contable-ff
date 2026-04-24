import streamlit as st
import pandas as pd

from database import (
    obtener_historial,
    eliminar_carga,
    limpiar_historial,
    obtener_errores,
    obtener_errores_por_archivo,
    limpiar_errores,
    limpiar_base_pruebas
)

from services.backups_service import (
    crear_backup_sqlite,
    listar_backups_sqlite,
    restaurar_backup_sqlite
)


# ======================================================
# FUNCIONES AUXILIARES
# ======================================================

def preparar_vista(df):
    df_vista = df.copy()
    df_vista.index = range(1, len(df_vista) + 1)
    df_vista.index.name = "N°"
    return df_vista


# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

def mostrar_estado():
    st.title("📋 Estado de Cargas y Auditoría")

    tab1, tab2, tab3 = st.tabs([
        "Historial de cargas",
        "Errores de auditoría",
        "Backups"
    ])

    with tab1:
        mostrar_historial_cargas()

    with tab2:
        mostrar_errores_auditoria()

    with tab3:
        mostrar_backups()


# ======================================================
# TAB 1 - HISTORIAL DE CARGAS
# ======================================================

def mostrar_historial_cargas():
    st.subheader("Archivos procesados")

    df = obtener_historial()

    if df.empty:
        st.info("No existen archivos cargados.")
    else:
        st.dataframe(preparar_vista(df), use_container_width=True)

        st.divider()

        st.subheader("Eliminar archivo individual")

        for i, fila in df.iterrows():
            archivo = fila["nombre_archivo"]
            modulo = fila["modulo"]
            registros = fila["registros"]

            col1, col2, col3, col4, col5 = st.columns([1, 4, 2, 2, 1])

            with col1:
                st.write(i + 1)

            with col2:
                st.write(f"📄 **{archivo}**")

            with col3:
                st.write(f"**{modulo}**")

            with col4:
                st.write(f"Registros: {registros}")

            with col5:
                if st.button("❌", key=f"eliminar_{archivo}"):
                    st.session_state["archivo_a_eliminar"] = archivo

            if st.session_state.get("archivo_a_eliminar") == archivo:
                st.warning(f"¿Confirmás eliminar el archivo **{archivo}**?")

                c1, c2 = st.columns(2)

                with c1:
                    if st.button("Sí, eliminar", key=f"confirmar_{archivo}"):
                        crear_backup_sqlite("antes_eliminar_carga")
                        eliminar_carga(archivo)
                        st.success("Archivo eliminado junto con sus movimientos relacionados.")
                        st.session_state["archivo_a_eliminar"] = None
                        st.rerun()

                with c2:
                    if st.button("Cancelar", key=f"cancelar_{archivo}"):
                        st.session_state["archivo_a_eliminar"] = None
                        st.rerun()

        st.divider()

        st.subheader("Acciones generales")

        if "confirmar_vaciar_historial" not in st.session_state:
            st.session_state["confirmar_vaciar_historial"] = False

        if st.button("Vaciar historial completo"):
            st.session_state["confirmar_vaciar_historial"] = True

        if st.session_state["confirmar_vaciar_historial"]:
            st.warning(
                "¿Confirmás vaciar el historial? "
                "Esto elimina historial, comprobantes procesados y errores, "
                "pero no elimina el Libro Diario."
            )

            c1, c2 = st.columns(2)

            with c1:
                if st.button("Sí, vaciar historial"):
                    crear_backup_sqlite("antes_vaciar_historial")
                    limpiar_historial()
                    st.success("Historial eliminado.")
                    st.session_state["confirmar_vaciar_historial"] = False
                    st.rerun()

            with c2:
                if st.button("Cancelar vaciado"):
                    st.session_state["confirmar_vaciar_historial"] = False
                    st.rerun()

        st.divider()

    st.subheader("Zona de pruebas")

    if "confirmar_limpiar_base" not in st.session_state:
        st.session_state["confirmar_limpiar_base"] = False

    if st.button("🧨 Limpiar toda la base de pruebas"):
        st.session_state["confirmar_limpiar_base"] = True

    if st.session_state["confirmar_limpiar_base"]:
        st.error(
            "Esto eliminará Libro Diario, historial, comprobantes procesados, "
            "ventas, compras, cuentas corrientes y errores."
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Sí, limpiar todo"):
                crear_backup_sqlite("antes_limpiar_base_pruebas")
                limpiar_base_pruebas()
                st.success("Base de pruebas limpiada.")
                st.session_state["confirmar_limpiar_base"] = False
                st.rerun()

        with c2:
            if st.button("Cancelar limpieza"):
                st.session_state["confirmar_limpiar_base"] = False
                st.rerun()


# ======================================================
# TAB 2 - ERRORES DE AUDITORÍA
# ======================================================

def mostrar_errores_auditoria():
    st.subheader("Errores detectados")

    df_historial = obtener_historial()

    archivos = ["Todos"]

    if not df_historial.empty:
        archivos += df_historial["nombre_archivo"].tolist()

    archivo_error = st.selectbox(
        "Filtrar errores por archivo",
        archivos
    )

    if archivo_error == "Todos":
        df_errores = obtener_errores()
    else:
        df_errores = obtener_errores_por_archivo(archivo_error)

    if df_errores.empty:
        st.success("No hay errores registrados.")
    else:
        st.warning(f"Errores encontrados: {len(df_errores)}")
        st.dataframe(preparar_vista(df_errores), use_container_width=True)

    st.divider()

    if "confirmar_vaciar_errores" not in st.session_state:
        st.session_state["confirmar_vaciar_errores"] = False

    if st.button("Vaciar registro de errores"):
        st.session_state["confirmar_vaciar_errores"] = True

    if st.session_state["confirmar_vaciar_errores"]:
        st.warning("¿Confirmás eliminar todos los errores de auditoría?")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Sí, eliminar errores"):
                crear_backup_sqlite("antes_eliminar_errores")
                limpiar_errores()
                st.success("Errores de auditoría eliminados.")
                st.session_state["confirmar_vaciar_errores"] = False
                st.rerun()

        with c2:
            if st.button("Cancelar eliminación"):
                st.session_state["confirmar_vaciar_errores"] = False
                st.rerun()


# ======================================================
# TAB 3 - BACKUPS
# ======================================================

def mostrar_backups():
    st.subheader("Backups de base de datos")

    st.info(
        "Los backups se guardan en la carpeta backups/sqlite. "
        "Antes de operaciones riesgosas, el sistema crea un respaldo automático."
    )

    if st.button("Crear backup manual"):
        resultado = crear_backup_sqlite("manual")

        if resultado["ok"]:
            st.success(resultado["mensaje"])
            st.caption(resultado["archivo"])
            st.rerun()
        else:
            st.error(resultado["mensaje"])

    st.divider()

    backups = listar_backups_sqlite()

    if not backups:
        st.info("No hay backups disponibles.")
        return

    df = pd.DataFrame(backups)

    st.subheader("Backups disponibles")
    st.dataframe(preparar_vista(df), use_container_width=True)

    st.divider()

    st.subheader("Restaurar backup")

    archivo = st.selectbox(
        "Seleccionar backup",
        df["archivo"].tolist()
    )

    ruta = df[df["archivo"] == archivo].iloc[0]["ruta"]

    if "confirmar_restaurar_backup" not in st.session_state:
        st.session_state["confirmar_restaurar_backup"] = False

    if st.button("Restaurar backup seleccionado"):
        st.session_state["confirmar_restaurar_backup"] = True

    if st.session_state["confirmar_restaurar_backup"]:
        st.error(
            "Restaurar un backup reemplaza la base actual. "
            "El sistema creará un backup previo antes de restaurar."
        )

        c1, c2 = st.columns(2)

        with c1:
            if st.button("Sí, restaurar"):
                resultado = restaurar_backup_sqlite(ruta)

                if resultado["ok"]:
                    st.success(resultado["mensaje"])
                else:
                    st.error(resultado["mensaje"])

                st.session_state["confirmar_restaurar_backup"] = False
                st.rerun()

        with c2:
            if st.button("Cancelar restauración"):
                st.session_state["confirmar_restaurar_backup"] = False
                st.rerun()