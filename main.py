import streamlit as st
import database
from datetime import datetime

# ... (Configuración inicial de sys.path e init_db igual que antes) ...

if opcion == "Inicio / IVA":
    st.title("🏠 Estado de IVA Detallado")
    
    # Selectores de período
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        mes_sel = st.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    with col_p2:
        anio_sel = st.number_input("Año", value=2025)

    # Lógica de filtrado de fechas
    meses_dict = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    
    query_v = "SELECT SUM(haber) as d FROM libro_diario WHERE cuenta = 'IVA DEBITO FISCAL'"
    query_c = "SELECT SUM(debe) as c FROM libro_diario WHERE cuenta = 'IVA CREDITO FISCAL'"
    
    if mes_sel != "ANUAL":
        query_v += f" AND fecha LIKE '%{anio_sel}{meses_dict[mes_sel]}%'"
        query_c += f" AND fecha LIKE '%{anio_sel}{meses_dict[mes_sel]}%'"
    else:
        query_v += f" AND fecha LIKE '{anio_sel}%'"
        query_c += f" AND fecha LIKE '{anio_sel}%'"

    df_v = database.ejecutar_query(query_v, fetch=True)
    df_c = database.ejecutar_query(query_c, fetch=True)
    
    deb = df_v['d'].iloc[0] or 0.0
    cre = df_c['c'].iloc[0] or 0.0
    saldo = deb - cre

    st.metric(f"Saldo {mes_sel} {anio_sel}", f"$ {abs(saldo):,.2f}", delta="A PAGAR" if saldo > 0 else "A FAVOR", delta_color="inverse" if saldo > 0 else "normal")
    
    # Detalle de comprobantes del periodo
    st.subheader(f"Detalle de Movimientos - {mes_sel}")
    det = database.ejecutar_query(f"SELECT fecha, glosa, cuenta, debe, haber FROM libro_diario WHERE (cuenta LIKE 'IVA%') AND fecha LIKE '%{anio_sel}%' ORDER BY fecha DESC", fetch=True)
    st.dataframe(det, use_container_width=True)