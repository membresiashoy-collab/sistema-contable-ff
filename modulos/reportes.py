import streamlit as st
import pandas as pd
import sys
import os
import io

# Parche de rutas para asegurar que encuentre database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🗑️ VACIAR DIARIO"):
            eliminar_todo_diario()
            st.rerun()
    
    # Traemos los datos de la DB
    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if not df.empty:
        # --- SECCIÓN DE EXPORTACIÓN ---
        with col2:
            try:
                import xlsxwriter
                buffer = io.BytesIO()
                # Generamos el Excel con los datos puros
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='LibroDiario')
                
                st.download_button(
                    label="📥 Descargar reporte (Excel)",
                    data=buffer.getvalue(),
                    file_name="libro_diario_sistema.xlsx",
                    mime="application/vnd.ms-excel"
                )
            except ImportError:
                st.error("⚠️ Falta instalar 'xlsxwriter'. Agregalo a tu requirements.txt.")

        # --- SECCIÓN DE VISUALIZACIÓN (Sin filas fantasma) ---
        res = []
        ids_unicos = df['id_asiento'].unique()
        
        for i, id_as in enumerate(ids_unicos):
            asiento_actual = df[df['id_asiento'] == id_as]
            for _, r in asiento_actual.iterrows():
                res.append({
                    "Asiento": int(r['id_asiento']),
                    "Fecha": r['fecha'], # Formato DD/MM/YYYY
                    "Cuenta": r['cuenta'],
                    "Debe": r['debe'],
                    "Haber": r['haber'],
                    "Glosa": r['glosa']
                })
            
            # Solo agregamos separador si NO es el último asiento
            # Esto evita los guiones y ceros al final de la tabla
            if i < len(ids_unicos) - 1:
                res.append({
                    "Asiento": "---", "Fecha": "---", "Cuenta": "-----------",
                    "Debe": None, "Haber": None, "Glosa": "---"
                })
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
        
        # Resumen de totales
        c_debe, c_haber = st.columns(2)
        c_debe.metric("Total DEBE", f"$ {df['debe'].sum():,.2f}")
        c_haber.metric("Total HABER", f"$ {df['haber'].sum():,.2f}")
    else:
        st.info("El Libro Diario está vacío.")