import streamlit as st
import sys
import os
import pandas as pd

# Fix de rutas para que main vea la raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import init_db, ejecutar_query
from modulos import ventas, reportes, compras, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

st.sidebar.title("🚀 Menú Principal")
opcion = st.sidebar.radio("Seleccione:", ["Inicio", "Ventas", "Compras", "Libro Diario", "Configuración"])

if opcion == "Inicio":
    st.title("🏠 Posición Mensual de IVA")
    
    # Traemos totales de las cuentas específicas
    df_v = ejecutar_query("SELECT SUM(haber) as debito FROM libro_diario WHERE cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = ejecutar_query("SELECT SUM(debe) as credito FROM libro_diario WHERE cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    debito = df_v['debito'].iloc[0] or 0.0
    credito = df_c['credito'].iloc[0] or 0.0
    saldo = debito - credito

    c1, c2, c3 = st.columns(3)
    c1.metric("IVA Débito (Ventas)", f"$ {debito:,.2f}")
    c2.metric("IVA Crédito (Compras)", f"$ {credito:,.2f}")
    c3.metric("Saldo del Mes", f"$ {abs(saldo):,.2f}", delta="A Pagar" if saldo > 0 else "A Favor", delta_color="inverse" if saldo > 0 else "normal")

elif opcion == "Ventas":
    ventas.mostrar_ventas()
elif opcion == "Compras":
    compras.mostrar_compras()
elif opcion == "Libro Diario":
    reportes.mostrar_diario()
elif opcion == "Configuración":
    configuracion.mostrar_configuracion()