import streamlit as st

from database import (
    obtener_historial,
    eliminar_carga,
    limpiar_historial,
    obtener_errores,
    obtener_errores_por_archivo
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
            st.dataframe(df, use_container_width=True)

            st.divider()

            archivos = df["nombre_archivo"].tolist()

            archivo = st.selectbox(
                "Seleccionar archivo a eliminar",
                archivos
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Eliminar archivo seleccionado"):
                    eliminar_carga(archivo)
                    st.success("Archivo eliminado junto con sus asientos, comprobantes y errores.")
                    st.rerun()

            with col2:
                if st.button("Vaciar historial completo"):
                    limpiar_historial()
                    st.success("Historial, comprobantes y errores eliminados.")
                    st.rerun()

    with tab2:
        st.subheader("Errores detectados")

        df_historial = obtener_historial()

        if df_historial.empty:
            st.info("No hay archivos cargados.")
            return

        archivos = ["Todos"] + df_historial["nombre_archivo"].tolist()

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
            st.dataframe(df_errores, use_container_width=True)