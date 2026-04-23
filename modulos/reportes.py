import streamlit as st
import pandas as pd
import sys
import os
import io

# Parche de rutas para asegurar que encuentre database.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database import ejecutar_query, eliminar_todo_diario

def mostrar_diario():
    st.title("📓 Libro Diario")

    # --- ZONA DE HERRAMIENTAS Y FILTROS ---
    with st.expander("🛠️ Herramientas de Filtro y Búsqueda", expanded=True):
        c1, c2, c3 = st.columns([1, 1, 2])
        
        # Obtener datos base para los filtros
        df_base = ejecutar_query("SELECT id_asiento, fecha, cuenta, debe, haber, glosa FROM libro_diario ORDER BY id_asiento ASC", fetch=True)
        
        if not df_base.empty:
            asientos_disponibles = ["Todos"] + sorted(df_base['id_asiento'].unique().tolist())
            filtro_asiento = c1.selectbox("Ver Asiento N°:", asientos_disponibles)
            
            busqueda = c2.text_input("Buscar en Cuentas/Glosa:", "")
            
            # Aplicar filtros
            df_filtrado = df_base.copy()
            if filtro_asiento != "Todos":
                df_filtrado = df_filtrado[df_filtrado['id_asiento'] == filtro_asiento]
            
            if busqueda:
                df_filtrado = df_filtrado[
                    df_filtrado['cuenta'].str.contains(busqueda, case=False) | 
                    df_filtrado['glosa'].str.contains(busqueda, case=False)
                ]
        else:
            st.info("No hay datos para filtrar.")
            df_filtrado = df_base

    # --- ZONA DE ACCIONES (DESCARGAS Y LIMPIEZA) ---
    if not df_filtrado.empty:
        col_acc1, col_acc2, col_acc3, col_acc4 = st.columns([1, 1, 1, 1])
        
        with col_acc1:
            if st.button("🗑️ VACIAR DIARIO"):
                eliminar_todo_diario()
                st.rerun()

        # Exportación a Excel
        with col_acc2:
            try:
                buffer_ex = io.BytesIO()
                with pd.ExcelWriter(buffer_ex, engine='xlsxwriter') as writer:
                    df_filtrado.to_excel(writer, index=False, sheet_name='Diario')
                st.download_button("📥 Excel", data=buffer_ex.getvalue(), file_name="diario_contable.xlsx")
            except:
                st.error("Error Excel")

        # Exportación a CSV (Alternativa rápida)
        with col_acc3:
            csv = df_filtrado.to_csv(index=False).encode('utf-8')
            st.download_button("📄 CSV", data=csv, file_name="diario_contable.csv", mime="text/csv")

        # --- VISUALIZACIÓN DE LA TABLA ---
        res = []
        ids_unicos = df_filtrado['id_asiento'].unique()
        
        for i, id_as in enumerate(ids_unicos):
            asiento_actual = df_filtrado[df_filtrado['id_asiento'] == id_as]
            for _, r in asiento_actual.iterrows():
                res.append({
                    "Asiento": int(r['id_asiento']),
                    "Fecha": r['fecha'],
                    "Cuenta": r['cuenta'],
                    "Debe": r['debe'],
                    "Haber": r['haber'],
                    "Glosa": r['glosa']
                })
            
            # Separador visual entre asientos (evita filas fantasma al final)
            if i < len(ids_unicos) - 1:
                res.append({"Asiento": "---", "Fecha": "---", "Cuenta": "-----------", "Debe": None, "Haber": None, "Glosa": "---"})
        
        st.dataframe(pd.DataFrame(res), use_container_width=True, hide_index=True)
        
        # Totales del área visible
        t1, t2 = st.columns(2)
        t1.metric("Total DEBE (Vista)", f"$ {df_filtrado['debe'].sum():,.2f}")
        t2.metric("Total HABER (Vista)", f"$ {df_filtrado['haber'].sum():,.2f}")
    else:
        if df_base.empty:
            st.info("El Libro Diario está vacío.")
        else:
            st.warning("No hay resultados para los filtros aplicados.")