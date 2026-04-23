import streamlit as st
import pandas as pd
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    # Botón de mantenimiento para limpiar errores previos
    if st.button("🗑️ Vaciar Todo el Diario"):
        if st.checkbox("Confirmar para recargar datos"):
            eliminar_todo_diario()
            st.rerun()

    # Consulta SQL que asegura el orden cronológico real
    query = """
        SELECT id_asiento, fecha, cuenta, debe, haber, glosa 
        FROM libro_diario
        ORDER BY SUBSTR(fecha, 7, 4), SUBSTR(fecha, 4, 2), SUBSTR(fecha, 1, 2), id_asiento
    """
    df = ejecutar_query(query, fetch=True)

    if not df.empty:
        res = []
        # El formato original es DD/MM/YYYY, nos aseguramos de mantenerlo en la vista
        ultimo_asiento = df.iloc[0]['id_asiento']
        
        for _, r in df.iterrows():
            # Solo inserta separador si cambia el número de asiento (y no es el primero)
            if r['id_asiento'] != ultimo_asiento:
                res.append({
                    "Asiento": "---", "Fecha": "---", "Cuenta": "-----------", 
                    "Debe": None, "Haber": None, "Glosa": "---"
                })
                ultimo_asiento = r['id_asiento']
            
            res.append({
                "Asiento": r['id_asiento'], 
                "Fecha": r['fecha'], # Mantenemos el formato DD/MM/YYYY
                "Cuenta": r['cuenta'], 
                "Debe": r['debe'], 
                "Haber": r['haber'], 
                "Glosa": r['glosa']
            })
        
        # Mostramos la tabla formateada
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
        
        # Totales de control al final
        c1, c2 = st.columns(2)
        c1.metric("Total General Debe", f"$ {df['debe'].sum():,.2f}")
        c2.metric("Total General Haber", f"$ {df['haber'].sum():,.2f}")
    else:
        st.info("El Libro Diario está vacío. Cargue ventas para ver los registros.")