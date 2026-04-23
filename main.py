import streamlit as st
from database import init_db
# 1. Asegúrate de importar el nuevo módulo aquí
from modulos import ventas, reportes, configuracion 

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

st.sidebar.title("🚀 Gestión Contable")
# 2. Agrega "Configuración" a la lista de radio
opcion = st.sidebar.radio("Ir a:", 
    ["Inicio", "Importar Ventas ARCA", "Libro Diario", "Sumas y Saldos", "Configuración"])

if opcion == "Inicio":
    st.title("Sistema Contable Automatizado")
    st.info("Paso 1: Ve a 'Configuración' y carga tu Plan de Cuentas.")

elif opcion == "Importar Ventas ARCA":
    ventas.mostrar_ventas()

elif opcion == "Libro Diario":
    reportes.mostrar_diario()

elif opcion == "Sumas y Saldos":
    reportes.mostrar_balance()

# 3. Este bloque es el que hace que aparezca el contenido al hacer clic
elif opcion == "Configuración":
    configuracion.mostrar_configuracion()