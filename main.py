import streamlit as st
import sys
import os

# 1. CONFIGURACIÓN DE RUTAS 
# Esto asegura que Python encuentre los archivos en la carpeta raíz y en 'modulos'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# 2. IMPORTACIONES DE TUS MÓDULOS
from database import init_db
# Importamos el nuevo módulo de compras junto con los anteriores
from modulos import ventas, reportes, auditoria, configuracion, compras 

# Configuración de la página
st.set_page_config(page_title="Sistema Contable FF", layout="wide", page_icon="📊")

# 3. INICIALIZAR BASE DE DATOS
# Crea las tablas de ventas, diario y ahora la de compras
init_db()

# 4. MENÚ LATERAL (Navegación)
st.sidebar.title("🚀 Menú Principal")
st.sidebar.divider()

# Añadimos "Compras" a la lista de opciones
opcion = st.sidebar.radio(
    "Seleccione un módulo:",
    ["Inicio / Panel", "Ventas", "Compras", "Libro Diario", "Auditoría", "Configuración"]
)

st.sidebar.divider()
st.sidebar.info("Sistema Contable FF v1.0")

# 5. LÓGICA DE NAVEGACIÓN
# Aquí es donde el sistema decide qué mostrar según lo que clickeaste
if opcion == "Inicio / Panel":
    st.title("🏠 Panel de Control")
    st.write("Bienvenido al sistema. Aquí visualizaremos la posición de IVA próximamente.")
    # Aquí podrías llamar a una función de resumen si la tienes

elif opcion == "Ventas":
    ventas.mostrar_ventas()

elif opcion == "Compras":
    # Llamamos a la función que creamos en modulos/compras.py
    compras.mostrar_compras()

elif opcion == "Libro Diario":
    reportes.mostrar_diario()

elif opcion == "Auditoría":
    auditoria.mostrar_estado()

elif opcion == "Configuración":
    configuracion.mostrar_configuracion()