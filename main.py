import streamlit as st
from database import init_db, ejecutar_query
from modulos import ventas, reportes

# Configuración inicial
st.set_page_config(page_title="Sistema Contable FF", layout="wide", page_icon="📝")
init_db()

# Panel de Navegación Profesional
st.sidebar.title("🚀 Gestión Contable")
menu = st.sidebar.selectbox("Seleccione un Módulo:", 
    ["🏠 Inicio", "📂 Carga de Ventas", "📓 Libro Diario", "🔍 Libro Mayor", "⚖️ Balance de Sumas y Saldos", "⚙️ Configuración"])

if menu == "🏠 Inicio":
    st.title("Bienvenido al Sistema Contable FF")
    st.write("Seleccione una opción en el menú de la izquierda para comenzar.")

elif menu == "📂 Carga de Ventas":
    ventas.mostrar_ventas()

elif menu == "📓 Libro Diario":
    reportes.mostrar_diario()

elif menu == "🔍 Libro Mayor":
    reportes.mostrar_mayor()

elif menu == "⚖️ Balance de Sumas y Saldos":
    reportes.mostrar_balance()

elif menu == "⚙️ Configuración":
    st.title("⚙️ Mantenimiento")
    if st.button("🗑️ Resetear Base de Datos (Borrar Asientos)"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Base de datos de asientos limpiada.")