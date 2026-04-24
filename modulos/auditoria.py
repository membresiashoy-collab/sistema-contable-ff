import streamlit as st

from database import (
    obtener_historial,
    eliminar_carga,
    limpiar_historial,
    obtener_errores,
    obtener_errores_por_archivo,
    limpiar_errores,
    limpiar_base_pruebas
)


def mostrar_estado():
    st.title("📋 Estado de Cargas y Auditoría")

    tab1, tab2 = st.tabs(["Historial de cargas", "Errores de auditoría"])

    with tab1:
        st.subheader("Archivos procesados")

        df = obtener_historial()

        if df.empty:
            st.info("No existen archivos cargados.")
        else:
            df_vista = df.copy()
            df_vista.index = range(1, len(df_vista) + 1)
            df_vista.index.name = "N°"

            st.dataframe(df_vista, use_container_width=True)

            st.divider()

            st.subheader("Eliminar archivo individual")

            for i, fila in df.iterrows():
                archivo = fila["nombre_archivo"]
                modulo = fila["modulo"]
                registros = fila["registros"]
                fecha = fila["fecha"]

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
                            eliminar_carga(archivo)
                            st.success("Archivo eliminado junto con sus asientos, ventas, cuenta corriente y errores.")
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
                    "ventas, cuenta corriente y errores."
                )

                c1, c2 = st.columns(2)

                with c1:
                    if st.button("Sí, limpiar todo"):
                        limpiar_base_pruebas()
                        st.success("Base de pruebas limpiada.")
                        st.session_state["confirmar_limpiar_base"] = False
                        st.rerun()

                with c2:
                    if st.button("Cancelar limpieza"):
                        st.session_state["confirmar_limpiar_base"] = False
                        st.rerun()

    with tab2:
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
            df_errores_vista = df_errores.copy()
            df_errores_vista.index = range(1, len(df_errores_vista) + 1)
            df_errores_vista.index.name = "N°"

            st.warning(f"Errores encontrados: {len(df_errores_vista)}")
            st.dataframe(df_errores_vista, use_container_width=True)

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
                    limpiar_errores()
                    st.success("Errores de auditoría eliminados.")
                    st.session_state["confirmar_vaciar_errores"] = False
                    st.rerun()

            with c2:
                if st.button("Cancelar eliminación"):
                    st.session_state["confirmar_vaciar_errores"] = False
                    st.rerun()