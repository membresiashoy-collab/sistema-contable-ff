import streamlit as st
import pandas as pd
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("SISTEMA CONTABLE FF")
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario", "Configuración ARCA"])

if opcion == "Configuración ARCA":
    st.title("⚙️ Configuración: Tipos de Comprobante")
    
    # MOSTRAR TABLA ACTUAL (Corregido KeyError)
    df_reglas = database.ejecutar_query("SELECT * FROM tabla_comprobantes", fetch=True)
    if not df_reglas.empty:
        # Usamos los nombres exactos que devuelve el SQL: 'codigo', 'descripcion', 'es_reverso'
        df_reglas['Lógica Contable'] = df_reglas['es_reverso'].map({1: "INVERSO (NC)", 0: "DIRECTO (FACT)"})
        st.dataframe(df_reglas[['codigo', 'descripcion', 'Lógica Contable']], use_container_width=True, hide_index=True)
    else:
        st.info("Cargue el archivo TABLACOMPROBANTES.csv para iniciar.")

    archivo = st.file_uploader("Subir Tabla ARCA", type=["csv"])
    if archivo:
        # El separador de tu archivo es ';'
        df_sub = pd.read_csv(archivo, sep=';', encoding='latin-1')
        if st.button("Sincronizar Tipos de Comprobante"):
            database.cargar_tabla_referencia(df_sub)
            st.success("Tabla actualizada.")
            st.rerun()

elif opcion == "Libro Diario":
    st.title("📓 Libro Diario")
    if st.button("🗑️ Vaciar Todo el Libro Diario"):
        database.ejecutar_query("DELETE FROM libro_diario")
        st.rerun()
    reportes.mostrar_diario()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()