import streamlit as st
import database
from modulos import ventas, compras, reportes

database.init_db()
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario"])

if opcion == "Inicio":
    st.title("📊 Posición de IVA")
    
    mes = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    anio = st.number_input("Año", value=2025)

    meses_idx = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    filtro = f"WHERE fecha LIKE '{anio}%'" if mes == "ANUAL" else f"WHERE fecha LIKE '%{anio}{meses_idx[mes]}%'"

    # Cálculo con reverso automático (Neto = Debe - Haber)
    df_v = database.ejecutar_query(f"SELECT (SUM(haber) - SUM(debe)) as total FROM libro_diario {filtro} AND cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = database.ejecutar_query(f"SELECT (SUM(debe) - SUM(haber)) as total FROM libro_diario {filtro} AND cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    deb = df_v['total'].iloc[0] or 0.0
    cre = df_c['total'].iloc[0] or 0.0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("IVA Ventas (Débito)", f"$ {deb:,.2f}")
    c2.metric("IVA Compras (Crédito)", f"$ {cre:,.2f}")
    c3.metric("Saldo Técnico", f"$ {abs(deb-cre):,.2f}", delta="Pagar" if (deb-cre)>0 else "A Favor")

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()