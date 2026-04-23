import streamlit as st
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("Sistema Contable FF")
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario"])

if opcion == "Inicio":
    st.title("📊 Posición de IVA")
    
    mes = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    anio = st.number_input("Año", value=2025)

    idx_meses = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    query_fecha = f"WHERE fecha LIKE '{anio}%'" if mes == "ANUAL" else f"WHERE fecha LIKE '%{anio}{idx_meses[mes]}%'"

    # Cálculo neto (Haber - Debe para pasivos de IVA)
    df_v = database.ejecutar_query(f"SELECT (SUM(haber) - SUM(debe)) as total FROM libro_diario {query_fecha} AND cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = database.ejecutar_query(f"SELECT (SUM(debe) - SUM(haber)) as total FROM libro_diario {query_fecha} AND cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    dv = df_v['total'].iloc[0] or 0.0
    cv = df_c['total'].iloc[0] or 0.0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Débito Fiscal (Ventas)", f"$ {dv:,.2f}")
    c2.metric("Crédito Fiscal (Compras)", f"$ {cv:,.2f}")
    c3.metric("Saldo Técnico", f"$ {abs(dv-cv):,.2f}", delta="A PAGAR" if (dv-cv) > 0 else "A FAVOR")

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()