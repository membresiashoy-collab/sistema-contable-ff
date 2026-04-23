import streamlit as st
import pandas as pd
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    # Botón de limpieza para corregir errores de carga anteriores
    if st.button("🗑️ Vaciar Libro Diario"):
        eliminar_todo_diario()
        st.success("Diario limpiado correctamente.")
        st.rerun()

    df = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario", fetch=True)

    if not df.empty:
        res = []
        # El formato ya viene como DD/MM/YYYY del CSV, lo respetamos
        ultimo_id = df.iloc[0]['id_asiento']
        
        for _, r in df.iterrows():
            # Solo insertamos separador si NO es el primer asiento de la lista
            if r['id_asiento'] != ultimo_id:
                res.append({
                    "Asiento": "---", "Fecha": "---", "Cuenta": "-----------", 
                    "Debe": None, "Haber": None, "Glosa": "---"
                })
                ultimo_id = r['id_asiento']
            
            res.append({
                "Asiento": r['id_asiento'], 
                "Fecha": r['fecha'], 
                "Cuenta": r['cuenta'], 
                "Debe": r['debe'], 
                "Haber": r['haber'], 
                "Glosa": r['glosa']
            })
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
        
        # Totales rápidos
        c1, c2 = st.columns(2)
        c1.metric("Total Debe", f"$ {df['debe'].sum():,.2f}")
        c2.metric("Total Haber", f"$ {df['haber'].sum():,.2f}")
    else:
        st.info("El Libro Diario está vacío.")