import streamlit as st
import pandas as pd
import sys
import os
import io

# Asegurar rutas para importación
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🗑️ VACIAR DIARIO"):
            eliminar_todo_diario()
            st.rerun()
    
    # Consulta a la base de datos
    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if not df.empty:
        # --- PROCESAMIENTO PARA EXPORTAR ---
        # Forzamos que la columna fecha sea tratada como texto con formato DD/MM/YYYY
        df_export = df.copy()
        
        # --- BOTONES DE EXPORTACIÓN ---
        with col2:
            # Exportar a Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, index=False, sheet_name='LibroDiario')
            
            st.download_button(
                label="📥 Exportar a Excel",
                data=buffer.getvalue(),
                file_name="libro_diario.xlsx",
                mime="application/vnd.ms-excel"
            )

        # --- VISUALIZACIÓN EN PANTALLA ---
        res = []
        ids = df['id_asiento'].unique()
        for i, id_as in enumerate(ids):
            filas = df[df['id_asiento'] == id_as]
            for _, r in filas.iterrows():
                res.append({
                    "Asiento": int(r['id_asiento']), 
                    "Fecha": r['fecha'], # Mantiene DD/MM/YYYY del procesamiento
                    "Cuenta": r['cuenta'], 
                    "Debe": r['debe'], 
                    "Haber": r['haber'], 
                    "Glosa": r['glosa']
                })
            # Separador visual (Evita filas fantasma al final)
            if i < len(ids) - 1:
                res.append({
                    "Asiento": "---", "Fecha": "---", "Cuenta": "-----------", 
                    "Debe": 0, "Haber": 0, "Glosa": "---"
                })
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
        
        # Totales de Control
        c1, c2 = st.columns(2)
        c1.metric("Total DEBE", f"$ {df['debe'].sum():,.2f}")
        c2.metric("Total HABER", f"$ {df['haber'].sum():,.2f}")
    else:
        st.info("El diario está vacío.")