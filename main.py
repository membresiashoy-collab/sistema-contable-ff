import streamlit as st
import sys
import os
import database
from modulos import ventas, compras, reportes

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
database.init_db()

opcion = st.sidebar.radio("Navegación", ["Inicio / IVA", "Ventas", "Compras", "Libro Diario"])

if opcion == "Inicio / IVA":
    st.title("📊 Posición Mensual y Anual de IVA")
    
    mes = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    anio = st.number_input("Año", value=2025)

    # Filtro de fecha para SQL
    meses_idx = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    filtro = f"WHERE fecha LIKE '{anio}%'" if mes == "ANUAL" else f"WHERE fecha LIKE '%{anio}{meses_idx[mes]}%'"

    # Cálculo Neto (Haber - Debe para Débito / Debe - Haber para Crédito)
    df_v = database.ejecutar_query(f"SELECT (SUM(haber) - SUM(debe)) as total FROM libro_diario {filtro} AND cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = database.ejecutar_query(f"SELECT (SUM(debe) - SUM(haber)) as total FROM libro_diario {filtro} AND cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    debito = df_v['total'].iloc[0] or 0.0
    credito = df_c['total'].iloc[0] or 0.0
    posicion = debito - credito

    st.metric(f"IVA {mes}", f"$ {abs(posicion):,.2f}", delta="A PAGAR" if posicion > 0 else "A FAVOR", delta_color="inverse" if posicion > 0 else "normal")
    
    st.subheader("Movimientos Detallados")
    movs = database.ejecutar_query(f"SELECT fecha, glosa, cuenta, debe, haber FROM libro_diario {filtro} AND cuenta LIKE 'IVA%'", fetch=True)
    st.dataframe(movs, use_container_width=True)

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()