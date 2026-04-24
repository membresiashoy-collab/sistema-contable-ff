import streamlit as st
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from core.database import init_db
from modulos import ventas, compras, reportes, auditoria, configuracion

st.set_page_config(
    page_title="Sistema Contable FF",
    page_icon="📊",
    layout="wide"
)

init_db()

st.sidebar.title("📌 Sistema Contable FF")
st.sidebar.caption("Versión Profesional")

menu = st.sidebar.radio(
    "Menú",
    [
        "Dashboard",
        "Ventas",
        "Compras",
        "Libro Diario",
        "Estado de Cargas",
        "Configuración"
    ]
)

if menu == "Dashboard":
    st.title("📊 Dashboard")
    st.success("Sistema listo para operar.")

elif menu == "Ventas":
    ventas.mostrar_ventas()

elif menu == "Compras":
    compras.mostrar_compras()

elif menu == "Libro Diario":
    reportes.mostrar_diario()

elif menu == "Estado de Cargas":
    auditoria.mostrar_estado()

elif menu == "Configuración":
    configuracion.mostrar_configuracion()