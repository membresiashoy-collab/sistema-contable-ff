import streamlit as st
import pandas as pd
import sys
import os
import io

# Parche de rutas para encontrar database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🗑️ VACIAR DIARIO"):
            eliminar_todo_diario()
            st.rerun()
    
    # Obtenemos los datos ordenados
    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if not df.empty:
        # --- Lógica de Exportación ---
        with col2:
            try:
                buffer = io.BytesIO()
                # Creamos un Excel limpio para el usuario
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Diario')
                
                st.download_button(
                    label="📥 Descargar Excel (DD/MM/YYYY)",
                    data=buffer.getvalue(),
                    file_name="libro_diario_ff.xlsx",
                    mime="application/vnd.ms-excel"
                )
            except Exception as e:
                st.error("Para exportar a Excel, asegúrate de tener 'xlsxwriter' instalado.")

        # --- Lógica de Visualización (Sin movimientos fantasma) ---
        res = []
        ids_unicos = df['id_asiento'].unique()
        
        for i, id_as in enumerate(ids_unicos):
            filas_asiento = df[df['id_asiento'] == id_as]
            for _, r in filas_asiento.iterrows():
                res.append({
                    "Asiento": int(r['id_asiento']),
                    "Fecha": r['fecha'], # Formato DD/MM/YYYY heredado de la carga
                    "Cuenta": r['cuenta'],
                    "Debe": r['debe'],
                    "Haber": r['haber'],
                    "Glosa": r['glosa']
                })
            
            # Solo agregar separador si hay más asientos después
            if i < len(ids_unicos) - 1:
                res.append({
                    "Asiento": "---", "Fecha": "---", "Cuenta": "-----------",
                    "Debe": None, "Haber": None, "Glosa": "---"
                })
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
        
        # Totales al final de la tabla
        c1, c2 = st.columns(2)
        c1.metric("Total Debe", f"$ {df['debe'].sum():,.2f}")
        c2.metric("Total Haber", f"$ {df['haber'].sum():,.2f}")
    else:
        st.info("No hay asientos registrados actualmente.")