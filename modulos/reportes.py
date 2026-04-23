import streamlit as st
import pandas as pd
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario Unificado")

    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El diario está vacío.")
        return

    # BARRA DE HERRAMIENTAS CON FILTRO DE ORIGEN
    c1, c2, c3, c4 = st.columns([1.5, 1.5, 2, 1])
    
    with c1:
        tipo_op = st.selectbox("Operación:", ["Todas", "Ventas", "Compras"], label_visibility="collapsed")
    
    with c2:
        asientos = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
        sel_as = st.selectbox("Asiento", asientos, label_visibility="collapsed")
        
    with c3:
        busq = st.text_input("Buscar...", placeholder="Cuenta o Proveedor...", label_visibility="collapsed")

    # APLICAR FILTROS LÓGICOS
    df_f = df_base.copy()
    
    if tipo_op == "Ventas":
        df_f = df_f[df_f['glosa'].str.contains("Venta", case=False, na=False)]
    elif tipo_op == "Compras":
        df_f = df_f[df_f['glosa'].str.contains("Compra", case=False, na=False)]
        
    if sel_as != "Todos":
        df_f = df_f[df_f['id_asiento'] == sel_as]
        
    if busq:
        df_f = df_f[df_f['cuenta'].str.contains(busq, case=False) | df_f['glosa'].str.contains(busq, case=False)]

    # Construcción Visual (Sin la palabra "None")
    res_visual = []
    ids = df_f['id_asiento'].unique()
    for i, id_as in enumerate(ids):
        filas = df_f[df_f['id_asiento'] == id_as]
        for _, r in filas.iterrows():
            res_visual.append({
                "Asiento": int(r['id_asiento']), "Fecha": r['fecha'],
                "Cuenta": r['cuenta'], "Debe": r['debe'], "Haber": r['haber'], "Glosa": r['glosa']
            })
        if i < len(ids) - 1:
            res_visual.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": "", "Haber": "", "Glosa": "---"})
    
    st.dataframe(pd.DataFrame(res_visual), use_container_width=True, hide_index=True)

    # Métricas de Posición de IVA rápidas
    m1, m2 = st.columns(2)
    m1.metric("Total DEBE", f"$ {df_f['debe'].sum():,.2f}")
    m2.metric("Total HABER", f"$ {df_f['haber'].sum():,.2f}")