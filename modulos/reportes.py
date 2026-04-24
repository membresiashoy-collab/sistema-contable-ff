import streamlit as st
import pandas as pd
from core.database import ejecutar_query, eliminar_todo_diario


def mostrar_diario():
    st.title("📓 Libro Diario")

    pestaña1, pestaña2, pestaña3 = st.tabs(
        ["Libro Diario", "Mayor", "Balance"]
    )

    # ----------------------------------
    # LIBRO DIARIO
    # ----------------------------------
    with pestaña1:
        df = ejecutar_query("""
        SELECT id_asiento, fecha, cuenta, debe, haber, glosa
        FROM libro_diario
        ORDER BY id_asiento, id
        """, fetch=True)

        if df.empty:
            st.info("Sin movimientos.")
        else:
            st.dataframe(df, use_container_width=True)

            c1, c2 = st.columns(2)
            c1.metric("Debe", f"$ {df['debe'].sum():,.2f}")
            c2.metric("Haber", f"$ {df['haber'].sum():,.2f}")

            if st.button("🗑 Vaciar Libro Diario"):
                eliminar_todo_diario()
                st.rerun()

    # ----------------------------------
    # MAYOR
    # ----------------------------------
    with pestaña2:
        df = ejecutar_query("""
        SELECT cuenta, fecha, glosa, debe, haber
        FROM libro_diario
        ORDER BY cuenta, fecha
        """, fetch=True)

        if df.empty:
            st.info("Sin datos.")
        else:
            cuentas = sorted(df["cuenta"].unique())
            cuenta_sel = st.selectbox(
                "Seleccionar Cuenta",
                cuentas
            )

            mayor = df[df["cuenta"] == cuenta_sel]

            mayor["saldo"] = (
                mayor["debe"].cumsum() -
                mayor["haber"].cumsum()
            )

            st.dataframe(mayor, use_container_width=True)

    # ----------------------------------
    # BALANCE
    # ----------------------------------
    with pestaña3:
        df = ejecutar_query("""
        SELECT cuenta,
               SUM(debe) as debe,
               SUM(haber) as haber
        FROM libro_diario
        GROUP BY cuenta
        ORDER BY cuenta
        """, fetch=True)

        if df.empty:
            st.info("Sin datos.")
        else:
            df["saldo"] = df["debe"] - df["haber"]

            st.dataframe(df, use_container_width=True)

            c1, c2, c3 = st.columns(3)

            c1.metric("Debe", f"$ {df['debe'].sum():,.2f}")
            c2.metric("Haber", f"$ {df['haber'].sum():,.2f}")
            c3.metric("Saldo", f"$ {df['saldo'].sum():,.2f}")