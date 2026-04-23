import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")
    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("Diario vacío.")
        return

    # Filtros rápidos
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: tipo = st.selectbox("Ver:", ["Todos", "Ventas", "Compras"], label_visibility="collapsed")
    with c3: 
        if st.button("🗑️ VACIAR"):
            eliminar_todo_diario()
            st.rerun()

    df_f = df_base.copy()
    if tipo == "Ventas": df_f = df_f[df_f['glosa'].str.contains("Venta", case=False, na=False)]
    if tipo == "Compras": df_f = df_f[df_f['glosa'].str.contains("Compra", case=False, na=False)]

    res = []
    ids = df_f['id_asiento'].unique()
    for i, id_as in enumerate(ids):
        filas = df_f[df_f['id_asiento'] == id_as]
        for _, r in filas.iterrows():
            res.append({"Asiento": int(r['id_asiento']), "Fecha": r['fecha'], "Cuenta": r['cuenta'], "Debe": r['debe'], "Haber": r['haber'], "Glosa": r['glosa']})
        if i < len(ids) - 1:
            res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": "", "Haber": "", "Glosa": "---"})
    
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)