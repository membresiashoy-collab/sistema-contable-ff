import streamlit as st
import pandas as pd
import sys
import os
import io
from fpdf import FPDF # Asegúrate de agregar fpdf2 a tu requirements.txt

# Parche de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def generar_pdf(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 10, "Libro Diario - Sistema Contable FF", ln=True, align="C")
    pdf.ln(10)
    
    # Encabezados
    pdf.set_font("Arial", "B", 10)
    pdf.cell(20, 10, "Asiento", 1)
    pdf.cell(30, 10, "Fecha", 1)
    pdf.cell(50, 10, "Cuenta", 1)
    pdf.cell(30, 10, "Debe", 1)
    pdf.cell(30, 10, "Haber", 1)
    pdf.ln()
    
    # Datos
    pdf.set_font("Arial", "", 9)
    for _, r in df.iterrows():
        if r['Asiento'] != "---":
            pdf.cell(20, 10, str(r['Asiento']), 1)
            pdf.cell(30, 10, str(r['Fecha']), 1)
            pdf.cell(50, 10, str(r['Cuenta'])[:25], 1)
            pdf.cell(30, 10, f"{r['Debe']:,.2f}", 1)
            pdf.cell(30, 10, f"{r['Haber']:,.2f}", 1)
            pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def mostrar_diario():
    st.title("📓 Libro Diario")

    # 1. Obtener datos base
    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El Libro Diario está vacío.")
        if st.button("🗑️ VACIAR DATOS"):
            eliminar_todo_diario()
        return

    # 2. BARRA DE HERRAMIENTAS (Ubicada sobre las X rojas)
    # Creamos una fila de columnas para que todo esté alineado arriba de la tabla
    col_f1, col_f2, col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1.5, 2, 0.8, 0.8, 0.8, 1.2])

    with col_f1:
        asientos = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
        filtro_as = st.selectbox("Asiento:", asientos, label_visibility="collapsed")

    with col_f2:
        busqueda = st.text_input("Buscar cuenta/glosa...", label_visibility="collapsed")

    # Filtrado lógico
    df_filtrado = df_base.copy()
    if filtro_as != "Todos":
        df_filtrado = df_filtrado[df_filtrado['id_asiento'] == filtro_as]
    if busqueda:
        df_filtrado = df_filtrado[df_filtrado['cuenta'].str.contains(busqueda, case=False) | df_filtrado['glosa'].str.contains(busqueda, case=False)]

    # 3. BOTONES DE ACCIÓN (Compactos)
    with col_btn1:
        try:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
                df_filtrado.to_excel(w, index=False)
            st.download_button("📊 Excel", buf.getvalue(), "diario.xlsx")
        except: st.error("Excel Error")

    with col_btn2:
        try:
            # Procesamos el DF para el PDF (quitando filas de separación)
            pdf_bytes = generar_pdf(df_filtrado)
            st.download_button("📕 PDF", pdf_bytes, "diario.pdf", "application/pdf")
        except: st.write("📝 PDF") # Fallback si no está fpdf

    with col_btn3:
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button("📄 CSV", csv, "diario.csv")

    with col_btn4:
        if st.button("🗑️ VACIAR", use_container_width=True):
            eliminar_todo_diario()
            st.rerun()

    # 4. TABLA DE RESULTADOS
    res = []
    ids_unicos = df_filtrado['id_asiento'].unique()
    for i, id_as in enumerate(ids_unicos):
        asiento_actual = df_filtrado[df_filtrado['id_asiento'] == id_as]
        for _, r in asiento_actual.iterrows():
            res.append({
                "Asiento": int(r['id_asiento']), "Fecha": r['fecha'],
                "Cuenta": r['cuenta'], "Debe": r['debe'],
                "Haber": r['haber'], "Glosa": r['glosa']
            })
        if i < len(ids_unicos) - 1:
            res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": 0, "Haber": 0, "Glosa": "---"})
    
    st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)

    # Totales
    t1, t2 = st.columns(2)
    t1.metric("Total DEBE", f"$ {df_filtrado['debe'].sum():,.2f}")
    t2.metric("Total HABER", f"$ {df_filtrado['haber'].sum():,.2f}")