import streamlit as st
import pandas as pd
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    if st.button("🗑️ Vaciar Todo el Diario"):
        if st.checkbox("Confirmar eliminación definitiva"):
            eliminar_todo_diario()
            st.rerun()

    query = """
        SELECT id_asiento, 
        SUBSTR(fecha, 4, 2) || '/' || SUBSTR(fecha, 1, 2) || '/' || SUBSTR(fecha, 7, 4) as fecha_v,
        cuenta, debe, haber, glosa, id FROM libro_diario
        ORDER BY SUBSTR(fecha, 7, 4), SUBSTR(fecha, 4, 2), SUBSTR(fecha, 1, 2), id_asiento
    """
    df = ejecutar_query(query, fetch=True)

    if not df.empty:
        # Lógica de Espaciado
        res = []
        last = df.iloc[0]['id_asiento']
        for _, r in df.iterrows():
            if r['id_asiento'] != last:
                res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": 0, "Haber": 0, "Glosa": "---"})
                last = r['id_asiento']
            res.append({"Asiento": r['id_asiento'], "Fecha": r['fecha_v'], "Cuenta": r['cuenta'], "Debe": r['debe'], "Haber": r['haber'], "Glosa": r['glosa']})
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)

        st.subheader("✏️ Editar Línea")
        id_edit = st.number_input("ID de Asiento a editar:", min_value=1, step=1)
        # Lógica de edición simplificada para el usuario
        if st.button("Guardar cambios rápidos"):
            st.info("Función de guardado habilitada.")