import streamlit as st
import sys
import os

# Forzar ruta raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
from modulos import ventas, compras, reportes

st.set_page_config(page_title="Sistema FF", layout="wide")
database.init_db()

st.sidebar.title("Menú Principal")
opcion = st.sidebar.radio("Ir a:", ["Inicio", "Ventas", "Compras", "Libro Diario"])

if opcion == "Inicio":
    st.title("📊 Estado de IVA")
    try:
        df_v = database.ejecutar_query("SELECT SUM(haber) as d FROM libro_diario WHERE cuenta = 'IVA DEBITO FISCAL'", fetch=True)
        df_c = database.ejecutar_query("SELECT SUM(debe) as c FROM libro_diario WHERE cuenta = 'IVA CREDITO FISCAL'", fetch=True)
        
        deb = df_v['d'].iloc[0] or 0.0
        cre = df_c['c'].iloc[0] or 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Débito (Ventas)", f"$ {deb:,.2f}")
        c2.metric("Crédito (Compras)", f"$ {cre:,.2f}")
        c3.metric("Saldo", f"$ {abs(deb-cre):,.2f}", delta="Pagar" if deb>cre else "A Favor")
    except Exception as e:
        st.error(f"Error en Panel: {e}")

elif opcion == "Ventas":
    ventas.mostrar_ventas()
elif opcion == "Compras":
    compras.mostrar_compras()
elif opcion == "Libro Diario":
    reportes.mostrar_diario()