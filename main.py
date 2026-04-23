import streamlit as st
import pandas as pd
import sqlite3
from database import init_db, ejecutar_query, DB_NAME
from modulos import ventas

st.set_page_config(page_title="Sistema FF", layout="wide", page_icon="📈")
init_db()

st.sidebar.title("Sistema Contable FF")
menu = st.sidebar.radio("Navegación", ["Dashboard", "Ventas", "Configuración"])

if menu == "Dashboard":
    st.title("📊 Resumen Contable")
    asientos = ejecutar_query("SELECT * FROM libro_diario ORDER BY id DESC", fetch=True)
    if not asientos.empty:
        st.write("### Últimos Asientos en el Libro Diario")
        st.dataframe(asientos, use_container_width=True)
    else:
        st.info("No hay movimientos registrados aún.")

elif menu == "Ventas":
    ventas.mostrar_ventas()

elif menu == "Configuración":
    st.title("⚙️ Configuración")
    st.subheader("Carga de Plan de Cuentas")
    archivo_p = st.file_uploader("Subir Plan de Cuentas (CSV)", type=["csv"])
    if archivo_p:
        try:
            df_p = pd.read_csv(archivo_p)
            conn = sqlite3.connect(DB_NAME)
            df_p.to_sql('plan_cuentas', conn, if_exists='replace', index=False)
            conn.close()
            st.success("✅ Plan de Cuentas vinculado con éxito.")
        except Exception as e:
            st.error(f"Error al cargar el plan: {e}")