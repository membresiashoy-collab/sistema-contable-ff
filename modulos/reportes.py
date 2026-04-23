import streamlit as st
import pandas as pd
import sys
import os

# Parche de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    if st.button("🗑️ VACIAR DIARIO"):
        eliminar_todo_diario()
        st.rerun()

    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario", fetch=True)

    if not df.empty:
        res = []
        asientos = df['id_asiento'].unique()
        for i, id_as in enumerate(asientos):
            filas = df[df['id_asiento'] == id_as]
            for _, r in filas.iterrows():
                res.append({"Asiento": r['id_asiento'], "Fecha": r['fecha'], "Cuenta": r['cuenta'], "Debe": r['debe'], "Haber": r['haber'], "Glosa": r['glosa']})
            if i < len(asientos) - 1:
                res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": None, "Haber": None, "Glosa": "---"})
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
    else:
        st.info("El diario está vacío.")