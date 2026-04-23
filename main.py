import streamlit as st
import os
from database import init_db

# Configuración inicial
st.set_page_config(page_title="Sistema Contable FF", layout="wide")

# Inicializar base de datos al arrancar
try:
    init_db()
except Exception as e:
    st.error(f"Error al inicializar la base de datos: {e}")

# Importación segura de módulos
try:
    from modulos import ventas, reportes, configuracion
except ImportError as e:
    st.error(f"Error importando módulos. Verifique que la carpeta 'modulos' tenga un archivo __init__.py vacío. Error: {e}")
    st.stop()

# Navegación
st.sidebar.title("🚀 Navegación")
opcion = st.sidebar.radio("Ir a:", ["🏠 Inicio", "📂 Ventas", "📓 Libro Diario", "⚙️ Configuración"])

if opcion == "🏠 Inicio":
    st.title("📊 Dashboard de Gestión")
    st.write("Bienvenido al Sistema Contable FF.")
    # Aquí puedes llamar a una función de dashboard más adelante

elif opcion == "📂 Ventas":
    ventas.mostrar_ventas()

elif opcion == "📓 Libro Diario":
    reportes.mostrar_diario()

elif opcion == "⚙️ Configuración":
    configuracion.mostrar_configuracion()