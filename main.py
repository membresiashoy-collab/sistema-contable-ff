import streamlit as st
import pandas as pd
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("CONTABILIDAD FF")
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario", "⚙️ Configuración ARCA"])

if opcion == "Inicio":
    st.title("📊 Posición de IVA")
    # Cálculos rápidos para el Dashboard
    dv = database.ejecutar_query("SELECT SUM(haber) - SUM(debe) as t FROM libro_diario WHERE cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    cv = database.ejecutar_query("SELECT SUM(debe) - SUM(haber) as t FROM libro_diario WHERE cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    debito = dv['t'].iloc[0] if not dv.empty and pd.notnull(dv['t'].iloc[0]) else 0
    credito = cv['t'].iloc[0] if not cv.empty and pd.notnull(cv['t'].iloc[0]) else 0
    
    st.metric("Saldo Técnico", f"$ {abs(debito-credito):,.2f}", delta="A PAGAR" if debito > credito else "A FAVOR")

elif opcion == "⚙️ Configuración ARCA":
    st.title("Tipos de Comprobantes")
    df = database.ejecutar_query("SELECT * FROM tabla_comprobantes", fetch=True)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    archivo = st.file_uploader("Cargar TABLACOMPROBANTES.csv", type=["csv"])
    if archivo:
        df_csv = pd.read_csv(archivo, sep=';', encoding='latin-1')
        if st.button("Actualizar Tabla"):
            database.cargar_tabla_referencia(df_csv)
            st.success("Configuración guardada.")
            st.rerun()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario":
    st.title("Libro Diario")
    if st.button("🗑️ Limpiar Diario"):
        database.ejecutar_query("DELETE FROM libro_diario")
    reportes.mostrar_diario()