import streamlit as st
import pandas as pd
import sys
import os
import io

# Configuración de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    # 1. Traer datos puros de la base de datos
    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El Libro Diario está vacío.")
        if st.button("🗑️ VACIAR DATOS"): 
            eliminar_todo_diario()
            st.rerun()
        return

    # 2. BARRA DE HERRAMIENTAS (Ubicada sobre la tabla)
    c1, c2, c3, c4, c5 = st.columns([1.5, 2, 0.8, 0.8, 1.2])

    with c1:
        opciones_as = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
        sel_asiento = st.selectbox("Asiento", opciones_as, label_visibility="collapsed")
    
    with c2:
        txt_buscar = st.text_input("Filtrar...", label_visibility="collapsed", placeholder="Buscar cuenta o glosa...")

    # 3. Aplicar Filtros
    df_f = df_base.copy()
    if sel_asiento != "Todos":
        df_f = df_f[df_f['id_asiento'] == sel_asiento]
    if txt_buscar:
        df_f = df_f[df_f['cuenta'].str.contains(txt_buscar, case=False) | 
                    df_f['glosa'].str.contains(txt_buscar, case=False)]

    # 4. BOTONES DE ACCIÓN (Excel y Limpieza)
    with c3:
        # EXCEL MEJORADO: Con formato profesional
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            df_f.to_excel(writer, index=False, sheet_name='Diario')
            workbook = writer.book
            worksheet = writer.sheets['Diario']
            
            # Formatos
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            
            # Aplicar formatos a las columnas de dinero
            worksheet.set_column('D:E', 15, num_fmt)
            worksheet.set_column('A:C', 18)
            worksheet.set_column('F:F', 40)
            
        st.download_button("📊 Excel", buf.getvalue(), "Reporte_Diario.xlsx")

    with c4:
        # Alternativa CSV (Siempre funciona y es ligero)
        st.download_button("📄 CSV", df_f.to_csv(index=False).encode('utf-8'), "Reporte_Diario.csv")

    with c5:
        if st.button("🗑️ VACIAR", use_container_width=True):
            eliminar_todo_diario()
            st.rerun()

    # 5. PREPARAR TABLA VISUAL (Sin la palabra "None")
    res_visual = []
    ids_visibles = df_f['id_asiento'].unique()
    
    for i, id_as in enumerate(ids_visibles):
        sub_df = df_f[df_f['id_asiento'] == id_as]
        for _, r in sub_df.iterrows():
            res_visual.append({
                "Asiento": int(r['id_asiento']), 
                "Fecha": r['fecha'],
                "Cuenta": r['cuenta'], 
                "Debe": r['debe'], 
                "Haber": r['haber'], 
                "Glosa": r['glosa']
            })
        # Separador estético: Usamos "" para que no aparezca "None"
        if i < len(ids_visibles) - 1:
            res_visual.append({
                "Asiento": "---", "Fecha": "---", "Cuenta": "-----------", 
                "Debe": "", "Haber": "", "Glosa": "---"
            })
    
    st.dataframe(pd.DataFrame(res_visual), use_container_width=True, hide_index=True)

    # Totales inferiores
    m1, m2 = st.columns(2)
    m1.metric("Total DEBE", f"$ {df_f['debe'].sum():,.2f}")
    m2.metric("Total HABER", f"$ {df_f['haber'].sum():,.2f}")