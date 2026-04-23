import streamlit as st
import sys
import os

# Configuración de rutas para evitar ImportErrors
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db
from modulos import ventas, reportes, auditoria, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide")

# Inicializar base de datos
init_db()

# Navegación
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