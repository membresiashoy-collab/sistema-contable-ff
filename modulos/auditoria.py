import streamlit as st
from database import obtener_historial, eliminar_carga, limpiar_historial


def mostrar_estado():
    st.title("📋 Estado de Cargas")

    df = obtener_historial()

    if df.empty:
        st.info("No existen archivos cargados.")
        return

    st.subheader("Historial de Archivos Procesados")
    st.dataframe(df, use_container_width=True)

    st.divider()

    st.subheader("🗑️ Eliminar archivo cargado")

    archivos = df["nombre_archivo"].tolist()

    archivo = st.selectbox(
        "Seleccionar archivo",
        archivos
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Eliminar archivo seleccionado", use_container_width=True):
            eliminar_carga(archivo)
            st.success("Archivo eliminado correctamente.")
            st.rerun()

    with col2:
        if st.button("Vaciar historial completo", use_container_width=True):
            limpiar_historial()
            st.success("Historial eliminado.")
            st.rerun()