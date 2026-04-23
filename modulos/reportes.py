import streamlit as st
import pandas as pd
import database

def mostrar_diario():
    st.title("📓 Libro Diario")
    
    tipo_filtro = st.selectbox("Filtrar por Origen:", ["Todos", "VENTAS", "COMPRAS"])
    
    query = "SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario"
    if tipo_filtro != "Todos":
        query += f" WHERE origen = '{tipo_filtro}'"
    query += " ORDER BY id_asiento ASC"
    
    df = database.ejecutar_query(query, fetch=True)

    if df.empty:
        st.info("No hay registros con ese filtro.")
        return

    # Visualización limpia
    res = []
    ids = df['id_asiento'].unique()
    for id_as in ids:
        filas = df[df['id_asiento'] == id_as]
        for _, r in filas.iterrows():
            res.append({
                "Asiento": int(r['id_asiento']),
                "Fecha": r['fecha'],
                "Cuenta": r['cuenta'],
                "Debe": r['debe'] if r['debe'] > 0 else "",
                "Haber": r['haber'] if r['haber'] > 0 else "",
                "Glosa": r['glosa']
            })
    
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)