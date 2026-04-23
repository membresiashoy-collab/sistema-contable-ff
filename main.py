import streamlit as st
from database import init_db, ejecutar_query
from modulos import ventas, reportes

st.set_page_config(page_title="Sistema FF", layout="wide")
init_db()

# Navegación clara y profesional
st.sidebar.title("📈 Menú Contable")
menu = st.sidebar.radio("Seleccione módulo:", 
    ["Inicio", "Importar Ventas", "Libro Diario", "Balance", "Configuración"])

if menu == "Inicio":
    st.title("Sistema Contable Automatizado FF")
    st.info("Cargue sus archivos de ARCA en el módulo de Importación.")

elif menu == "Importar Ventas":
    ventas.mostrar_ventas()

elif menu == "Libro Diario":
    st.title("📓 Libro Diario")
    df = ejecutar_query("SELECT * FROM libro_diario ORDER BY id DESC", fetch=True)
    st.dataframe(df, use_container_width=True)

elif menu == "Balance":
    st.title("⚖️ Sumas y Saldos")
    sql = "SELECT cuenta, SUM(debe) as Debe, SUM(haber) as Haber, (SUM(debe)-SUM(haber)) as Saldo FROM libro_diario GROUP BY cuenta"
    st.dataframe(ejecutar_query(sql, fetch=True), use_container_width=True)

elif menu == "Configuración":
    st.title("⚙️ Mantenimiento")
    if st.button("🗑️ Vaciar todos los registros"):
        ejecutar_query("DELETE FROM libro_diario")
        st.success("Sistema reseteado.")