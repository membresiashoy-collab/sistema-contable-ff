import streamlit as st
import pandas as pd
import sys
import os
import io
from fpdf import FPDF

# Configuración de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def generar_pdf(df_original):
    # FILTRADO CRÍTICO: Eliminamos filas de separación antes de procesar el PDF
    # Esto evita errores de tipo de dato (NoneType)
    df = df_original[df_original['Asiento'] != "---"].copy()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(190, 10, "LIBRO DIARIO - SISTEMA CONTABLE FF", ln=True, align="C")
    pdf.ln(5)
    
    # Encabezados
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    cols = [("Asn", 15), ("Fecha", 25), ("Cuenta", 60), ("Debe", 30), ("Haber", 30), ("Glosa", 30)]
    for txt, w in cols:
        pdf.cell(w, 8, txt, 1, 0, "C", True)
    pdf.ln()
    
    # Datos
    pdf.set_font("Arial", "", 8)
    for _, r in df.iterrows():
        pdf.cell(15, 7, str(r['Asiento']), 1)
        pdf.cell(25, 7, str(r['Fecha']), 1)
        pdf.cell(60, 7, str(r['Cuenta'])[:35], 1)
        # Forzamos conversión a float para evitar errores con None
        d = float(r['Debe']) if r['Debe'] else 0.0
        h = float(r['Haber']) if r['Haber'] else 0.0
        pdf.cell(30, 7, f"{d:,.2f}", 1, 0, "R")
        pdf.cell(30, 7, f"{h:,.2f}", 1, 0, "R")
        pdf.cell(30, 7, str(r['Glosa'])[:15], 1, 1)
        
    return pdf.output()

def mostrar_diario():
    st.title("📓 Libro Diario")

    df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)

    if df_base.empty:
        st.info("El Libro Diario está vacío.")
        if st.button("🗑️ VACIAR DATOS"): eliminar_todo_diario()
        return

    # BARRA DE HERRAMIENTAS SOBRE LA TABLA
    c1, c2, c3, c4, c5, c6 = st.columns([1.5, 2, 0.8, 0.8, 0.8, 1.2])

    with c1:
        asientos = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
        f_as = st.selectbox("Asiento", asientos, label_visibility="collapsed")
    with c2:
        busq = st.text_input("Buscador...", label_visibility="collapsed", placeholder="Buscar...")

    # Aplicar Filtros
    df_f = df_base.copy()
    if f_as != "Todos": df_f = df_f[df_f['id_asiento'] == f_as]
    if busq: df_f = df_f[df_f['cuenta'].str.contains(busq, case=False) | df_f['glosa'].str.contains(busq, case=False)]

    # PROCESAMIENTO VISUAL: Evitamos que aparezca la palabra "None"
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
            # Usamos strings vacíos o guiones en lugar de None para que Streamlit no lo escriba
            res_pantalla.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": "", "Haber": "", "Glosa": "---"})
    
    df_visual = pd.DataFrame(res_pantalla)

    # BOTONES DE ACCIÓN
    with c3:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
            df_f.to_excel(w, index=False)
        st.download_button("📊 Excel", buf.getvalue(), "diario.xlsx")

    with c4:
        try:
            pdf_bytes = generar_pdf(df_visual)
            st.download_button("📕 PDF", pdf_bytes, "diario.pdf", "application/pdf")
        except Exception as e:
            st.error("Error PDF") # Aquí ya no debería entrar con el filtrado previo

    with c5:
        st.download_button("📄 CSV", df_f.to_csv(index=False).encode('utf-8'), "diario.csv")

    with c6:
        if st.button("🗑️ VACIAR", use_container_width=True):
            eliminar_todo_diario()
            st.rerun()

    # Mostrar Tabla (Ajustamos el estilo para que no muestre None)
    st.dataframe(df_visual, use_container_width=True, hide_index=True)

    # Totales
    t1, t2 = st.columns(2)
    t1.metric("Total DEBE (Vista)", f"$ {df_f['debe'].sum():,.2f}")
    t2.metric("Total HABER (Vista)", f"$ {df_f['haber'].sum():,.2f}")