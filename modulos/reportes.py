import streamlit as st
import pandas as pd
import sys
import os
import io
from fpdf import FPDF

# Configuración de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def generar_pdf(df_datos_reales):
    # El PDF solo recibe los datos puros de la base de datos (sin filas "---")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(190, 10, "LIBRO DIARIO - SISTEMA CONTABLE FF", ln=True, align="C")
    pdf.ln(5)
    
    # Encabezados
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(15, 8, "Asn", 1, 0, "C", True)
    pdf.cell(25, 8, "Fecha", 1, 0, "C", True)
    pdf.cell(60, 8, "Cuenta", 1, 0, "C", True)
    pdf.cell(30, 8, "Debe", 1, 0, "C", True)
    pdf.cell(30, 8, "Haber", 1, 0, "C", True)
    pdf.cell(30, 8, "Glosa", 1, 1, "C", True)
    
    # Datos
    pdf.set_font("Arial", "", 8)
    for _, r in df_datos_reales.iterrows():
        pdf.cell(15, 7, str(r['id_asiento']), 1)
        pdf.cell(25, 7, str(r['fecha']), 1)
        pdf.cell(60, 7, str(r['cuenta'])[:35], 1)
        pdf.cell(30, 7, f"{float(r['debe']):,.2f}", 1, 0, "R")
        pdf.cell(30, 7, f"{float(r['haber']):,.2f}", 1, 0, "R")
        pdf.cell(30, 7, str(r['glosa'])[:15], 1, 1)
        
    return pdf.output()

def mostrar_diario():
    st.title("📓 Libro Diario")

    # 1. Traer datos puros
    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El Libro Diario está vacío.")
        if st.button("🗑️ VACIAR DATOS"): eliminar_todo_diario()
        return

    # 2. BARRA DE HERRAMIENTAS
    c1, c2, c3, c4, c5, c6 = st.columns([1.5, 2, 0.8, 0.8, 0.8, 1.2])

    with c1:
        asientos = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
        f_as = st.selectbox("Asiento", asientos, label_visibility="collapsed")
    with c2:
        busq = st.text_input("Buscar...", label_visibility="collapsed", placeholder="Filtrar...")

    # 3. Aplicar Filtros a los datos puros
    df_f = df_base.copy()
    if f_as != "Todos": df_f = df_f[df_f['id_asiento'] == f_as]
    if busq: df_f = df_f[df_f['cuenta'].str.contains(busq, case=False) | df_f['glosa'].str.contains(busq, case=False)]

    # 4. BOTONES DE ACCIÓN (Usan df_f que son datos limpios)
    with c3:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
            df_f.to_excel(w, index=False)
        st.download_button("📊 Excel", buf.getvalue(), "diario.xlsx")

    with c4:
        try:
            # ENVIAMOS df_f (datos reales), NO el de pantalla
            pdf_bytes = generar_pdf(df_f)
            st.download_button("📕 PDF", pdf_bytes, "diario.pdf", "application/pdf")
        except Exception as e:
            st.error("Error PDF")

    with c5:
        st.download_button("📄 CSV", df_f.to_csv(index=False).encode('utf-8'), "diario.csv")

    with c6:
        if st.button("🗑️ VACIAR", use_container_width=True):
            eliminar_todo_diario()
            st.rerun()

    # 5. PREPARAR TABLA PARA PANTALLA (Estética con "---")
    res_pantalla = []
    ids = df_f['id_asiento'].unique()
    for i, id_as in enumerate(ids):
        filas = df_f[df_f['id_asiento'] == id_as]
        for _, r in filas.iterrows():
            res_pantalla.append({
                "Asiento": int(r['id_asiento']), "Fecha": r['fecha'],
                "Cuenta": r['cuenta'], "Debe": r['debe'], "Haber": r['haber'], "Glosa": r['glosa']
            })
        if i < len(ids) - 1:
            # Usamos "" para que no aparezca la palabra "None"
            res_pantalla.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": "", "Haber": "", "Glosa": "---"})
    
    st.dataframe(pd.DataFrame(res_pantalla), use_container_width=True, hide_index=True)

    # Totales
    t1, t2 = st.columns(2)
    t1.metric("Total DEBE", f"$ {df_f['debe'].sum():,.2f}")
    t2.metric("Total HABER", f"$ {df_f['haber'].sum():,.2f}")