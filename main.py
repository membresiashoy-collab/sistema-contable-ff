import streamlit as st
import database
from modulos import ventas, compras, reportes

st.set_page_config(page_title="Sistema Contable FF", layout="wide")

# Inicializar DB al arrancar
database.init_db()

menu = ["Ventas", "Compras", "Libro Diario / Reportes"]
choice = st.sidebar.selectbox("Menú Principal", menu)

if choice == "Ventas":
    ventas.mostrar_ventas()
elif choice == "Compras":
    compras.mostrar_compras()
elif choice == "Libro Diario / Reportes":
    reportes.mostrar_reportes()