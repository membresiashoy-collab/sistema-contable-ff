import streamlit as st
import pandas as pd
from database import init_db, ejecutar_query
from modulos import ventas, reportes, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

st.sidebar.title("🚀 Navegación")
opcion = st.sidebar.radio("Ir a:", ["🏠 Inicio", "📂 Ventas", "📓 Libro Diario", "⚙️ Configuración"])

if opcion == "🏠 Inicio":
    st.title("📊 Resumen Ejecutivo de Ventas")
    
    # Query para obtener Neto, IVA y Total agrupado por mes
    # Se calcula: Neto (Ventas), IVA (IVA DF), Total (Deudores)
    query_stats = """
        SELECT 
            SUBSTR(fecha, 4, 7) as Mes,
            SUM(CASE WHEN cuenta LIKE '%VENTAS%' THEN (haber - debe) ELSE 0 END) as Neto,
            SUM(CASE WHEN cuenta LIKE '%IVA%' THEN (haber - debe) ELSE 0 END) as IVA,
            SUM(CASE WHEN cuenta LIKE '%DEUDORES%' OR cuenta LIKE '%CLIENTES%' THEN (debe - haber) ELSE 0 END) as Total
        FROM libro_diario
        GROUP BY Mes
        ORDER BY Mes ASC
    """
    df_stats = ejecutar_query(query_stats, fetch=True)
    
    if not df_stats.empty:
        # 1. Gráfico Multilineal o de Barras comparativo
        st.subheader("📈 Evolución Mensual")
        st.bar_chart(df_stats.set_index('Mes'))
        
        # 2. Tabla Detallada
        st.subheader("📋 Detalle por Período")
        # Formateamos los números para que se entiendan
        df_display = df_stats.copy()
        for col in ['Neto', 'IVA', 'Total']:
            df_display[col] = df_display[col].apply(lambda x: f"$ {x:,.2f}")
        st.table(df_display)
        
        # 3. Métricas Destacadas del mes actual
        ult_mes = df_stats.iloc[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Neto ({ult_mes['Mes']})", f"$ {ult_mes['Neto']:,.2f}")
        c2.metric(f"IVA ({ult_mes['Mes']})", f"$ {ult_mes['IVA']:,.2f}")
        c3.metric(f"Total ({ult_mes['Mes']})", f"$ {ult_mes['Total']:,.2f}")
    else:
        st.info("Cargue ventas para visualizar el Dashboard.")

# ... resto de las opciones (Ventas, Diario, Configuración) ...