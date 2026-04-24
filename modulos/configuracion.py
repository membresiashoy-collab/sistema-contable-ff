import streamlit as st
import pandas as pd
from core.database import ejecutar_query


def mostrar_configuracion():
    st.title("⚙️ Configuración del Sistema")

    st.subheader("📚 Plan de Cuentas")
    df_cuentas = ejecutar_query("SELECT * FROM plan_cuentas", fetch=True)
    st.dataframe(df_cuentas, use_container_width=True)

    st.subheader("📄 Tipos de Comprobantes")
    df_comp = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
    st.dataframe(df_comp, use_container_width=True)

    st.subheader("📥 Cargar Plan de Cuentas")

    archivo = st.file_uploader("Subir CSV", type=["csv"])

    if archivo:
        if st.button("Guardar Plan"):
            df = pd.read_csv(archivo, sep=None, engine="python", encoding="latin-1")

            ejecutar_query("DELETE FROM plan_cuentas")

            for _, fila in df.iterrows():
                ejecutar_query(
                    "INSERT INTO plan_cuentas VALUES (?, ?)",
                    (str(fila.iloc[0]), str(fila.iloc[1]).upper())
                )

            st.success("Plan de cuentas actualizado")
            st.rerun()