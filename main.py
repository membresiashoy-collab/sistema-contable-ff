import streamlit as st
from database import init_db, ejecutar_query
from modulos import ventas, reportes

# Configuración y estilos
st.set_page_config(page_title="Sistema FF", layout="wide", page_icon="📈")
init_db()

# Menú de Navegación Profesional
st.sidebar.title("🚀 Gestión Contable")
menu = st.sidebar.radio("Módulos:", 
    ["Inicio", "Importar Ventas ARCA", "Libro Diario", "Balance y Saldos", "Configuración"])

if menu == "Inicio":
    st.title("Sistema Contable Automatizado")
    st.write("Bienvenido. Este sistema procesa comprobantes de ARCA y genera asientos automáticos.")

elif menu == "Importar Ventas ARCA":
    ventas.mostrar_ventas()

elif menu == "Libro Diario":
    reportes.mostrar_diario()

elif menu == "Balance y Saldos":
    reportes.mostrar_balance()

elif menu == "Configuración":
    st.title("⚙️ Mantenimiento")
    st.warning("Esta acción borrará todos los asientos generados.")
    if st.button("🗑️ Limpiar Libro Diario"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Base de datos reseteada con éxito.")