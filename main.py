import streamlit as st
import pandas as pd
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("CONTABILIDAD FF")
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario", "Configuración ARCA"])

if opcion == "Configuración ARCA":
    st.title("⚙️ Configuración de Comprobantes")
    
    st.subheader("Reglas de Asiento Actuales")
    df_reglas = database.ejecutar_query("SELECT * FROM tabla_comprobantes", fetch=True)
    if not df_reglas.empty:
        # Mostramos la tabla con nombres claros
        df_display = df_reglas.copy()
        df_display['Acción Contable'] = df_display['es_reverso'].apply(lambda x: "REVERSA (NC)" if x==1 else "NORMAL (FACT)")
        st.dataframe(df_display[['codigo', 'descripcion', 'Acción Contable']], use_container_width=True, hide_index=True)
    else:
        st.warning("No hay comprobantes cargados.")

    archivo = st.file_uploader("Cargar TABLACOMPROBANTES.csv", type=["csv"])
    if archivo:
        df_sub = pd.read_csv(archivo, sep=';', encoding='latin-1')
        if st.button("Actualizar Reglas"):
            database.cargar_tabla_referencia(df_sub)
            st.success("Tabla sincronizada.")
            st.rerun()

elif opcion == "Libro Diario":
    st.title("📓 Libro Diario")
    if st.button("🗑️ Limpiar Todo el Diario"):
        database.ejecutar_query("DELETE FROM libro_diario")
        st.rerun()
    reportes.mostrar_diario()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()