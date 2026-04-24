import streamlit as st
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from core.database import init_db, ejecutar_query
from modulos import ventas, compras, reportes, auditoria, configuracion

st.set_page_config(
    page_title="Sistema Contable FF",
    page_icon="📊",
    layout="wide"
)

init_db()

st.sidebar.title("📌 Sistema Contable FF")
menu = st.sidebar.radio(
    "Menú",
    [
        "Dashboard",
        "Ventas",
        "Compras",
        "Libro Diario",
        "Estado de Cargas",
        "Configuración"
    ]
)

if menu == "Dashboard":
    st.title("📊 Dashboard General")

    df = ejecutar_query(
        "SELECT * FROM libro_diario",
        fetch=True
    )

    if df.empty:
        st.info("Sin movimientos.")
    else:
        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Asientos",
            df["id_asiento"].nunique()
        )

        c2.metric(
            "Debe",
            f"$ {df['debe'].sum():,.2f}"
        )

        c3.metric(
            "Haber",
            f"$ {df['haber'].sum():,.2f}"
        )

        c4.metric(
            "Cuentas",
            df["cuenta"].nunique()
        )

elif menu == "Ventas":
    ventas.mostrar_ventas()

elif menu == "Compras":
    compras.mostrar_compras()

elif menu == "Libro Diario":
    reportes.mostrar_diario()

elif menu == "Estado de Cargas":
    auditoria.mostrar_estado()

elif menu == "Configuración":
    configuracion.mostrar_configuracion()

elif menu == "Estados Financieros":
    estados_financieros.mostrar_estados()    