import streamlit as st
import sys
import os
import pandas as pd

# Configuración de rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from database import init_db, ejecutar_query
from modulos import ventas, reportes, auditoria, configuracion, compras 

st.set_page_config(page_title="Sistema Contable FF", layout="wide", page_icon="📊")
init_db()

# --- NAVEGACIÓN ---
st.sidebar.title("🚀 Menú Principal")
opcion = st.sidebar.radio(
    "Seleccione un módulo:",
    ["Inicio / Posición IVA", "Ventas", "Compras", "Libro Diario", "Configuración"]
)

if opcion == "Inicio / Posición IVA":
    st.title("🏠 Panel de Control: Posición Mensual")
    
    # Cálculo de IVA desde el Libro Diario
    df_v = ejecutar_query("SELECT SUM(haber) as debito FROM libro_diario WHERE cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = ejecutar_query("SELECT SUM(debe) as credito FROM libro_diario WHERE cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    iva_debito = df_v['debito'].iloc[0] if not df_v.empty and df_v['debito'].iloc[0] else 0.0
    iva_credito = df_c['credito'].iloc[0] if not df_c.empty and df_c['credito'].iloc[0] else 0.0
    resultado = iva_debito - iva_credito

    # Métricas Visuales
    c1, c2, c3 = st.columns(3)
    c1.metric("IVA Débito (Ventas)", f"$ {iva_debito:,.2f}")
    c2.metric("IVA Crédito (Compras)", f"$ {iva_credito:,.2f}")
    
    if resultado > 0:
        c3.metric("IVA a Pagar", f"$ {resultado:,.2f}", delta=f"-{resultado:,.2f}", delta_color="inverse")
    else:
        c3.metric("Saldo a Favor", f"$ {abs(resultado):,.2f}", delta=f"+{abs(resultado):,.2f}")

    st.divider()
    st.subheader("Análisis de Saldos")
    res_data = pd.DataFrame({
        "Concepto": ["Débito Fiscal", "Crédito Fiscal"],
        "Monto": [iva_debito, iva_credito]
    })
    st.bar_chart(res_data.set_index("Concepto"))

elif opcion == "Ventas":
    ventas.mostrar_ventas()
elif opcion == "Compras":
    compras.mostrar_compras()
elif opcion == "Libro Diario":
    reportes.mostrar_diario()
elif opcion == "Configuración":
    configuracion.mostrar_configuracion()