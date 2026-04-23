import streamlit as st
import pandas as pd
from database import ejecutar_query

def mostrar_diario():
    st.title("📓 Libro Diario")

    # --- FILTROS DE VISTA ---
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info("Visualización cronológica de asientos contables.")
    with col2:
        if st.button("🔄 Refrescar Datos"):
            st.rerun()

    # --- QUERY CON ORDEN CRONOLÓGICO REAL ---
    # Convertimos la fecha de texto (DD/MM/AAAA) a un formato ordenable por SQL
    query = """
        SELECT 
            id_asiento as 'Asiento',
            fecha as 'Fecha',
            cuenta as 'Cuenta',
            debe as 'Debe',
            haber as 'Haber',
            glosa as 'Glosa'
        FROM libro_diario
        ORDER BY 
            SUBSTR(fecha, 7, 4) ASC, -- Año
            SUBSTR(fecha, 4, 2) ASC, -- Mes
            SUBSTR(fecha, 1, 2) ASC, -- Día
            id_asiento ASC           -- Correlativo por si hay misma fecha
    """

    df = ejecutar_query(query, fetch=True)

    if not df.empty:
        # Formateo de números para mejor lectura
        df_display = df.copy()
        
        # --- TABLA PRINCIPAL ---
        st.dataframe(
            df_display, 
            use_container_width=True, 
            height=500,
            hide_index=True
        )

        # --- COMPROBACIÓN DE PARTIDA DOBLE TOTAL ---
        total_debe = df['Debe'].sum()
        total_haber = df['Haber'].sum()
        diferencia = round(total_debe - total_haber, 2)

        st.divider()
        c1, c2, c3 = st.columns(3)
        
        c1.metric("Total DEBE", f"$ {total_debe:,.2f}")
        c2.metric("Total HABER", f"$ {total_haber:,.2f}")
        
        if diferencia == 0:
            c3.success("✅ Balance Cuadrado")
        else:
            c3.error(f"❌ Desbalance: $ {diferencia:,.2f}")
            st.warning("Revise los asientos. La suma del Debe y el Haber no coincide.")

        # --- OPCIÓN DE DESCARGA ---
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Libro Diario (CSV)",
            data=csv,
            file_name="libro_diario_ff.csv",
            mime="text/csv",
        )
    else:
        st.warning("El Libro Diario está vacío. Cargue operaciones en el módulo de Ventas.")

def mostrar_mayores():
    """Opcional: Para ver el movimiento por cuenta individual"""
    st.title("📖 Libros Mayores")
    df = ejecutar_query("SELECT DISTINCT cuenta FROM libro_diario", fetch=True)
    
    if not df.empty:
        cuenta_sel = st.selectbox("Seleccione una cuenta:", df['cuenta'].tolist())
        query_m = "SELECT fecha, debe, haber, glosa FROM libro_diario WHERE cuenta = ? ORDER BY id ASC"
        df_m = ejecutar_query(query_m, params=(cuenta_sel,), fetch=True)
        st.table(df_m)
        st.metric("Saldo", f"$ {(df_m['debe'].sum() - df_m['haber'].sum()):,.2f}")