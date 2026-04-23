import sys
import os
import streamlit as st
from database import init_db, ejecutar_query
from modulos import ventas, reportes

# Inicialización
sys.path.append(os.path.dirname(__file__))
st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

st.sidebar.title("Navegación")
opcion = st.sidebar.radio("Ir a:", ["Dashboard", "Ventas", "Reportes", "Configuración"])

if opcion == "Dashboard":
    st.title("📊 Panel de Control")
    st.write("Bienvenido al sistema contable.")

elif opcion == "Ventas":
    ventas.mostrar_ventas()

elif opcion == "Reportes":
    reportes.mostrar_reportes()

elif opcion == "Configuración":
    st.title("⚙️ Configuración")
    st.subheader("Mantenimiento de Datos")
    if st.button("🗑️ Borrar todos los Asientos"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Base de datos de asientos limpiada correctamente.")