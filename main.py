import streamlit as st
from database import init_db
from modulos import ventas, reportes, auditoria, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

st.sidebar.title("Navegación")
opcion = st.sidebar.radio("Ir a:", ["Ventas", "Libro Diario", "Estado de Cargas", "Configuración"])

if opcion == "Ventas":
    ventas.mostrar_ventas()
elif opcion == "Libro Diario":
    reportes.mostrar_diario()
elif opcion == "Estado de Cargas":
    auditoria.mostrar_estado()
elif opcion == "Configuración":
    configuracion.mostrar_configuracion()