import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_diario():
    st.title("📓 Libro Diario")
    st.subheader("Registros Cronológicos")
    # Ordenamos por fecha (campo TEXT en formato YYYY-MM-DD o similar)
    query = "SELECT fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY fecha ASC, id ASC"
    df = ejecutar_query(query, fetch=True)
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("El Libro Diario está vacío. Por favor, cargue ventas primero.")

def mostrar_balance():
    st.title("⚖️ Balance de Sumas y Saldos")
    sql = """
        SELECT cuenta, 
               SUM(debe) as "Suma Debe", 
               SUM(haber) as "Suma Haber",
               (SUM(debe) - SUM(haber)) as "Saldo"
        FROM libro_diario 
        GROUP BY cuenta
    """
    df = ejecutar_query(sql, fetch=True)
    if not df.empty:
        st.dataframe(df, use_container_width=True)
        # Validación de partida doble
        if abs(df["Suma Debe"].sum() - df["Suma Haber"].sum()) < 0.01:
            st.success(f"Balance Cuadrado: $ {df['Suma Debe'].sum():,.2f}")