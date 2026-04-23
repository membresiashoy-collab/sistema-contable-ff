import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    if st.button("🗑️ VACIAR DIARIO"):
        eliminar_todo_diario()
        st.rerun()

    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if not df.empty:
        res = []
        ids = df['id_asiento'].unique()
        for i, id_as in enumerate(ids):
            filas = df[df['id_asiento'] == id_as]
            for _, r in filas.iterrows():
                res.append({
                    "Asiento": int(r['id_asiento']), "Fecha": r['fecha'], 
                    "Cuenta": r['cuenta'], "Debe": r['debe'], 
                    "Haber": r['haber'], "Glosa": r['glosa']
                })
            # Separador solo entre asientos, nunca al final
            if i < len(ids) - 1:
                res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": 0, "Haber": 0, "Glosa": "---"})
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
    else:
        st.info("Diario vacío.")