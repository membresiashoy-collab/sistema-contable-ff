import streamlit as st
import pandas as pd
from database import ejecutar_query
from core.ui import preparar_vista
from core.numeros import moneda


def mostrar_estados():

    df = ejecutar_query("""
        SELECT cuenta, debe, haber
        FROM libro_diario
    """, fetch=True)

    if df.empty:
        st.info("Sin datos contables.")
        return

    df["saldo"] = df["debe"] - df["haber"]

    st.subheader("📈 Estado de Resultados Básico")

    ingresos = df[df["cuenta"].str.contains("VENTAS", na=False)]["haber"].sum()
    costos = df[df["cuenta"].str.contains("COMPRAS", na=False)]["debe"].sum()

    resultado = ingresos - costos

    c1, c2, c3 = st.columns(3)
    c1.metric("Ingresos", moneda(ingresos))
    c2.metric("Costos / Compras", moneda(costos))
    c3.metric("Resultado", moneda(resultado))

    st.divider()

    st.subheader("📊 Balance General Básico")

    balance = df.groupby("cuenta")[["debe", "haber"]].sum().reset_index()
    balance["saldo"] = balance["debe"] - balance["haber"]

    st.dataframe(preparar_vista(balance), use_container_width=True)