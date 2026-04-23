import streamlit as st
import pandas as pd
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("SISTEMA CONTABLE FF")
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario", "Configuración ARCA"])

if opcion == "Configuración ARCA":
    st.title("⚙️ Tipos de Comprobantes (ARCA)")
    
    st.subheader("Contenido de la Tabla de Referencia")
    df_actual = database.ejecutar_query("SELECT codigo as 'Código', descripcion as 'Tipo de Comprobante', es_reverso FROM tabla_comprobantes", fetch=True)
    
    if not df_actual.empty:
        df_actual['Acción'] = df_actual['es_reverso'].map({1: "REVERSO (NC)", 0: "DIRECTO (Fact)"})
        st.dataframe(df_actual[['Código', 'Tipo de Comprobante', 'Acción']], use_container_width=True, hide_index=True)
    else:
        st.info("Cargue el archivo TABLACOMPROBANTES.csv para definir los tipos de asiento.")

    archivo = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"])
    if archivo:
        # Tu archivo usa punto y coma (;)
        df_t = pd.read_csv(archivo, sep=';', encoding='latin-1')
        if st.button("Sincronizar Tipos"):
            database.cargar_tabla_referencia(df_t)
            st.success("Tabla cargada. Ahora el sistema puede interpretar asientos.")
            st.rerun()

elif opcion == "Libro Diario":
    st.title("📓 Libro Diario")
    if st.button("🗑️ Limpiar Asientos"):
        database.ejecutar_query("DELETE FROM libro_diario")
        st.rerun()
    reportes.mostrar_diario()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()