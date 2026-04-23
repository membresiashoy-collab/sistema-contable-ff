import sys
import os
import streamlit as st

# Asegura que Python encuentre la carpeta de módulos
sys.path.append(os.path.dirname(__file__))

from database import init_db
from modulos import ventas, reportes  # Importamos el nuevo módulo

# Configuración de página
st.set_page_config(page_title="Sistema Contable FF", layout="wide", page_icon="📈")

# Inicialización de la base de datos (Crea tablas si no existen)
init_db()

# Menú Lateral
st.sidebar.title("Sistema Contable FF")
opcion = st.sidebar.radio("Navegación", ["Dashboard", "Ventas", "Reportes Contables", "Configuración"])

if opcion == "Dashboard":
    st.title("📊 Panel de Control")
    st.write("Bienvenido al sistema. Use el menú lateral para procesar datos.")

elif opcion == "Ventas":
    ventas.mostrar_ventas()

elif opcion == "Reportes Contables":
    reportes.mostrar_reportes()  # Llamada al nuevo módulo gigante

elif opcion == "Configuración":
    st.title("⚙️ Configuración del Sistema")
    st.info("Aquí podrás cargar el Plan de Cuentas personalizado en el futuro.")