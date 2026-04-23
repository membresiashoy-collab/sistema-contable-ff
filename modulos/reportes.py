import streamlit as st
import pandas as pd
import sys
import os
import io

# Parche de rutas para que los módulos encuentren la base de datos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🗑️ VACIAR DIARIO"):
            eliminar_todo_diario()
            st.rerun()
    
    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if not df.empty:
        # --- EXPORTACIÓN ---
        with col2:
            try:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='LibroDiario')
                st.download_button(label="📥 Descargar Excel (DD/MM/YYYY)", data=buffer.getvalue(), file_name="reporte_diario.xlsx", mime="application/vnd.ms-excel")
            except:
                st.warning("Nota: Instale 'xlsxwriter' para habilitar la descarga.")

        # --- VISUALIZACIÓN ---
        res = []
        ids = df['id_asiento'].unique()
        for i, id_as in enumerate(ids):
            filas = df[df['id_asiento'] == id_as]
            for _, r in filas.iterrows():
                res.append({
                    "Asiento": int(r['id_asiento']),
                    "Fecha": r['fecha'], # Formato DD/MM/YYYY
                    "Cuenta": r['cuenta'],
                    "Debe": r['debe'],
                    "Haber": r['haber'],
                    "Glosa": r['glosa']
                })
            # Separador (Solo si no es el último para evitar filas fantasma)
            if i < len(ids) - 1:
                res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": None, "Haber": None, "Glosa": "---"})
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
    else:
        st.info("El diario está vacío.")