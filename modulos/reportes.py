import streamlit as st
import pandas as pd
import sys
import os
import io
from fpdf import FPDF

# Configuración de rutas para asegurar la importación de database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def generar_pdf_seguro(df_real):
    """Genera el PDF usando solo datos numéricos y de texto reales."""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(190, 10, "LIBRO DIARIO - REPORTE OFICIAL", ln=True, align="C")
        pdf.ln(5)
        
        # Encabezados con color
        pdf.set_font("Arial", "B", 8)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(10, 8, "ID", 1, 0, "C", True)
        pdf.cell(20, 8, "Fecha", 1, 0, "C", True)
        pdf.cell(55, 8, "Cuenta", 1, 0, "C", True)
        pdf.cell(25, 8, "Debe", 1, 0, "C", True)
        pdf.cell(25, 8, "Haber", 1, 0, "C", True)
        pdf.cell(55, 8, "Glosa", 1, 1, "C", True)
        
        # Filas de datos (df_real no contiene las filas "---")
        pdf.set_font("Arial", "", 8)
        for _, r in df_real.iterrows():
            # Limpieza de datos para el PDF
            val_debe = float(r['debe']) if r['debe'] else 0.0
            val_haber = float(r['haber']) if r['haber'] else 0.0
            
            pdf.cell(10, 7, str(r['id_asiento']), 1)
            pdf.cell(20, 7, str(r['fecha']), 1)
            pdf.cell(55, 7, str(r['cuenta'])[:30], 1)
            pdf.cell(25, 7, f"{val_debe:,.2f}", 1, 0, "R")
            pdf.cell(25, 7, f"{val_haber:,.2f}", 1, 0, "R")
            pdf.cell(55, 7, str(r['glosa'])[:35], 1, 1)
            
        return pdf.output()
    except Exception as e:
        return None

def mostrar_diario():
    st.title("📓 Libro Diario")

    # 1. Obtener datos crudos (Siempre limpios de la DB)
    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El Libro Diario está vacío.")
        if st.button("🗑️ VACIAR DATOS"): eliminar_todo_diario()
        return

    # 2. BARRA DE HERRAMIENTAS (Alineada sobre la tabla)
    col_f1, col_f2, col_b1, col_b2, col_b3, col_b4 = st.columns([1.5, 2, 0.8, 0.8, 0.8, 1.2])

    with col_f1:
        opciones_as = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
        sel_asiento = st.selectbox("Asiento", opciones_as, label_visibility="collapsed")
    
    with col_f2:
        txt_buscar = st.text_input("Filtrar...", label_visibility="collapsed", placeholder="Buscar cuenta o glosa...")

    # 3. Aplicar Filtros a los datos REALES
    df_filtrado = df_base.copy()
    if sel_asiento != "Todos":
        df_filtrado = df_filtrado[df_filtrado['id_asiento'] == sel_asiento]
    if txt_buscar:
        df_filtrado = df_filtrado[
            df_filtrado['cuenta'].str.contains(txt_buscar, case=False) | 
            df_filtrado['glosa'].str.contains(txt_buscar, case=False)
        ]

    # 4. BOTONES DE ACCIÓN (Blindados)
    with col_b1:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
            df_filtrado.to_excel(w, index=False)
        st.download_button("📊 Excel", buf.getvalue(), "reporte.xlsx")

    with col_b2:
        # Aquí generamos el PDF usando solo los datos reales filtrados
        pdf_data = generar_pdf_seguro(df_filtrado)
        if pdf_data:
            st.download_button("📕 PDF", pdf_data, "reporte.pdf", "application/pdf")
        else:
            st.error("Error")

    with col_b3:
        st.download_button("📄 CSV", df_filtrado.to_csv(index=False).encode('utf-8'), "reporte.csv")

    with col_b4:
        if st.button("🗑️ VACIAR", use_container_width=True):
            eliminar_todo_diario()
            st.rerun()

    # 5. CONSTRUCCIÓN DE LA TABLA VISUAL (Sin la palabra "None")
    res_visual = []
    ids_visibles = df_filtrado['id_asiento'].unique()
    
    for i, id_as in enumerate(ids_visibles):
        sub_df = df_filtrado[df_filtrado['id_asiento'] == id_as]
        for _, r in sub_df.iterrows():
            res_visual.append({
                "Asiento": int(r['id_asiento']), 
                "Fecha": r['fecha'],
                "Cuenta": r['cuenta'], 
                "Debe": r['debe'], 
                "Haber": r['haber'], 
                "Glosa": r['glosa']
            })
        # Agregar separador estético (Evita el "None" usando strings vacíos)
        if i < len(ids_visibles) - 1:
            res_visual.append({
                "Asiento": "---", "Fecha": "---", "Cuenta": "-----------", 
                "Debe": "", "Haber": "", "Glosa": "---"
            })
    
    # Mostrar la tabla final
    st.dataframe(pd.DataFrame(res_visual), use_container_width=True, hide_index=True)

    # Totales de la vista actual
    t_debe = df_filtrado['debe'].sum()
    t_haber = df_filtrado['haber'].sum()
    
    m1, m2 = st.columns(2)
    m1.metric("Total DEBE", f"$ {t_debe:,.2f}")
    m2.metric("Total HABER", f"$ {t_haber:,.2f}")