import streamlit as st
import pandas as pd
from core.database import ejecutar_query


def mostrar_estados():
    st.title("📊 Estados Financieros")

    df = ejecutar_query("""
        SELECT cuenta, debe, haber
        FROM libro_diario
    """, fetch=True)

    if df.empty:
        st.info("Sin datos contables.")
        return

    df["saldo"] = df["debe"] - df["haber"]

    # ---------------------------
    # ESTADO DE RESULTADOS
    # ---------------------------
    st.subheader("📈 Estado de Resultados")

    ingresos = df[df["cuenta"].str.contains("VENTAS", na=False)]["haber"].sum()
    costos = df[df["cuenta"].str.contains("COMPRAS", na=False)]["debe"].sum()

    resultado = ingresos - costos

    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos", f"$ {ingresos:,.2f}")
    c2.metric("Costos", f"$ {costos:,.2f}")
    c3.metric("Resultado", f"$ {resultado:,.2f}")

    st.divider()

    # ---------------------------
    # BALANCE SIMPLE
    # ---------------------------
    st.subheader("📊 Balance General (Simple)")

    balance = df.groupby("cuenta")[["debe", "haber"]].sum().reset_index()
    balance["saldo"] = balance["debe"] - balance["haber"]

    st.dataframe(balance, use_container_width=True)