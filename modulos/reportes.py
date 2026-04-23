import streamlit as st
import pandas as pd
import database

def mostrar_diario():
    st.title("📓 Libro Diario Unificado")
    
    df = database.ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df.empty:
        st.info("No hay registros en el diario.")
        return

    # Filtros
    c1, c2 = st.columns([3, 1])
    with c1:
        tipo = st.selectbox("Filtrar por origen:", ["Todos", "Ventas", "Compras"])
    with c2:
        if st.button("🗑️ VACIAR DIARIO"):
            database.eliminar_todo_diario()
            st.rerun()

    df_f = df.copy()
    if tipo == "Ventas":
        df_f = df_f[df_f['glosa'].str.contains("Venta", case=False, na=False)]
    elif tipo == "Compras":
        df_f = df_f[df_f['glosa'].str.contains("Compra", case=False, na=False)]

    # Formateo para quitar el "None" y poner rayitas separadoras
    res = []
    ids = df_f['id_asiento'].unique()
    for i, id_as in enumerate(ids):
        filas = df_f[df_f['id_asiento'] == id_as]
        for _, r in filas.iterrows():
            res.append({
                "Asiento": int(r['id_asiento']), 
                "Fecha": r['fecha'], 
                "Cuenta": r['cuenta'], 
                "Debe": f"{r['debe']:,.2f}" if r['debe'] > 0 else "", 
                "Haber": f"{r['haber']:,.2f}" if r['haber'] > 0 else "", 
                "Glosa": r['glosa']
            })
        if i < len(ids) - 1:
            res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": "", "Haber": "", "Glosa": "---"})
    
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)