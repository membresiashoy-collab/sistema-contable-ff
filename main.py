import streamlit as st
import sys
import os

# CONFIGURACIÓN DE RUTAS (Soluciona el ImportError)
# Agrega la carpeta actual al camino de búsqueda de Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Ahora las importaciones funcionarán correctamente
from database import init_db
from modulos import ventas, reportes, auditoria, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide")

# Inicializar base de datos
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