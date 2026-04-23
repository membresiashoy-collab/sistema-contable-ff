import streamlit as st
from database import init_db, ejecutar_query
from modulos import ventas, reportes

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

opcion = st.sidebar.radio("Navegación", ["Ventas", "Reportes", "Configuración"])

if opcion == "Ventas":
    ventas.mostrar_ventas()
elif opcion == "Reportes":
    reportes.mostrar_reportes()
elif opcion == "Configuración":
    st.title("⚙️ Configuración")
    if st.button("🗑️ Borrar Datos Viejos"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Base de datos reseteada.")