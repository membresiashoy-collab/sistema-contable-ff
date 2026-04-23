import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_reportes():
    st.title("📑 Reportes Contables Integrales")
    
    tab1, tab2, tab3 = st.tabs(["Libro Diario", "Libro Mayor", "Sumas y Saldos"])

    with tab1:
        st.subheader("📓 Libro Diario")
        query = "SELECT id, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id DESC"
        diario = ejecutar_query(query, fetch=True)
        if not diario.empty:
            st.dataframe(diario, use_container_width=True)
        else:
            st.warning("El Libro Diario está vacío.")

    with tab2:
        st.subheader("🔍 Libro Mayor")
        # Obtenemos la lista de cuentas que tienen movimientos
        cuentas_query = "SELECT DISTINCT cuenta FROM libro_diario"
        cuentas = ejecutar_query(cuentas_query, fetch=True)
        
        if not cuentas.empty:
            cuenta_sel = st.selectbox("Seleccione una cuenta para analizar:", cuentas['cuenta'])
            mayor = ejecutar_query("SELECT fecha, glosa, debe, haber FROM libro_diario WHERE cuenta = ?", (cuenta_sel,), fetch=True)
            st.table(mayor)
            
            # Cálculo de saldo
            total_debe = mayor['debe'].sum()
            total_haber = mayor['haber'].sum()
            saldo = total_debe - total_haber
            
            col1, col2 = st.columns(2)
            col1.metric("Total Debe", f"$ {total_debe:,.2;}")
            col2.metric("Saldo Actual", f"$ {saldo:,.2f}", delta_color="normal")
        else:
            st.info("No hay cuentas con registros para mayorizar.")

    with tab3:
        st.subheader("⚖️ Balance de Sumas y Saldos")
        balance_query = """
            SELECT cuenta, 
                   SUM(debe) as "Suma Debe", 
                   SUM(haber) as "Suma Haber",
                   (SUM(debe) - SUM(haber)) as "Saldo"
            FROM libro_diario 
            GROUP BY cuenta
        """
        balance = ejecutar_query(balance_query, fetch=True)
        if not balance.empty:
            st.dataframe(balance, use_container_width=True)
            # Verificación de partida doble
            t_debe = balance['Suma Debe'].sum()
            t_haber = balance['Suma Haber'].sum()
            if abs(t_debe - t_haber) < 0.01:
                st.success(f"Balance Cuadrado: $ {t_debe:,.2f}")
            else:
                st.error(f"Diferencia en Balance: {t_debe - t_haber:,.2f}")