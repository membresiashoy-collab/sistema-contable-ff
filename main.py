import streamlit as st
import pandas as pd
import database
from modulos import ventas, compras, reportes

# Inicialización forzosa
database.init_db()

st.sidebar.title("SISTEMA CONTABLE FF")
opcion = st.sidebar.radio("Menú Principal", ["Inicio", "Ventas", "Compras", "Libro Diario", "⚙️ Configuración ARCA"])

if opcion == "⚙️ Configuración ARCA":
    st.title("⚙️ Configuración de Tipos de Comprobante")
    
    # Mostrar lo que hay en la base de datos
    df_actual = database.ejecutar_query("SELECT codigo, descripcion, es_reverso FROM tabla_comprobantes", fetch=True)
    
    if not df_actual.empty:
        st.subheader("Tipos de Comprobantes Registrados")
        df_actual['Efecto Contable'] = df_actual['es_reverso'].map({1: "REVERSO (NC)", 0: "DIRECTO (Factura)"})
        st.dataframe(df_actual[['codigo', 'descripcion', 'Efecto Contable']], use_container_width=True, hide_index=True)
    else:
        st.info("No hay datos. Cargue el archivo TABLACOMPROBANTES.csv abajo.")

    archivo = st.file_uploader("Subir Tabla de ARCA", type=["csv"])
    if archivo:
        # Usamos el delimitador ';' que tiene tu archivo
        df_sub = pd.read_csv(archivo, sep=';', encoding='latin-1')
        if st.button("💾 Guardar Configuración"):
            database.cargar_tabla_referencia(df_sub)
            st.success("Configuración actualizada correctamente.")
            st.rerun()

elif opcion == "Libro Diario":
    st.title("📓 Libro Diario")
    if st.button("🗑️ Borrar todos los asientos"):
        database.ejecutar_query("DELETE FROM libro_diario")
        st.rerun()
    reportes.mostrar_diario()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()