import streamlit as st
import pandas as pd
import database

def mostrar_diario():
    st.title("📓 Libro Diario")
    df_base = database.ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El diario está vacío.")
        return

    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        filtro = st.selectbox("Operación:", ["Todos", "Ventas", "Compras"])
    with c3:
        if st.button("🗑️ VACIAR TODO"):
            database.eliminar_todo_diario()
            st.rerun()

    df_f = df_base.copy()
    if filtro == "Ventas":
        df_f = df_f[df_f['glosa'].str.contains("Venta", case=False, na=False)]
    elif filtro == "Compras":
        df_f = df_f[df_f['glosa'].str.contains("Compra", case=False, na=False)]

    # Procesamiento visual
    res = []
    ids = df_f['id_asiento'].unique()
    for i, id_as in enumerate(ids):
        filas = df_f[df_f['id_asiento'] == id_as]
        for _, r in filas.iterrows():
            res.append({"Asiento": int(r['id_asiento']), "Fecha": r['fecha'], "Cuenta": r['cuenta'], "Debe": r['debe'], "Haber": r['haber'], "Glosa": r['glosa']})
        if i < len(ids) - 1:
            res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": "", "Haber": "", "Glosa": "---"})
    
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)