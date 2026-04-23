import streamlit as st
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("Menú Sistema")
opcion = st.sidebar.radio("Ir a:", ["Inicio", "Ventas", "Compras", "Libro Diario"])

if opcion == "Inicio":
    st.title("📊 Posición Mensual de IVA")
    
    mes = st.selectbox("Seleccione Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    anio = st.number_input("Año", value=2025)

    # Botón de limpieza total
    if st.sidebar.button("🗑️ ELIMINAR TODO"):
        database.borrar_todo_el_sistema()
        st.rerun()

    meses_idx = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    filtro = f"WHERE fecha LIKE '{anio}%'" if mes == "ANUAL" else f"WHERE fecha LIKE '%{anio}{meses_idx[mes]}%'"

    # Cálculos netos (Débito Haber-Debe / Crédito Debe-Haber)
    df_v = database.ejecutar_query(f"SELECT (SUM(haber) - SUM(debe)) as res FROM libro_diario {filtro} AND cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = database.ejecutar_query(f"SELECT (SUM(debe) - SUM(haber)) as res FROM libro_diario {filtro} AND cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    dv = df_v['res'].iloc[0] or 0.0
    cv = df_c['res'].iloc[0] or 0.0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("IVA Ventas", f"$ {dv:,.2f}")
    c2.metric("IVA Compras", f"$ {cv:,.2f}")
    c3.metric("Saldo", f"$ {abs(dv-cv):,.2f}", delta="A Pagar" if (dv-cv) > 0 else "A Favor")

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()