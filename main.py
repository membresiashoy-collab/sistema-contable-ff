import streamlit as st
from database import init_db
from modulos import ventas, compras, reportes, auditoria, configuracion

st.set_page_config(
    page_title="Sistema Contable FF",
    layout="wide"
)

init_db()

st.sidebar.title("📘 Menú")

menu = st.sidebar.radio(
    "Ir a:",
    [
        "Ventas",
        "Compras",
        "Libro Diario",
        "Estado de Cargas",
        "Configuración"
    ]
)

if menu == "Ventas":
    ventas.mostrar_ventas()

elif menu == "Compras":
    compras.mostrar_compras()

elif menu == "Libro Diario":
    reportes.mostrar_diario()

elif menu == "Estado de Cargas":
    auditoria.mostrar_estado()

elif menu == "Configuración":
    configuracion.mostrar_configuracion()