import streamlit as st
import pandas as pd
from database import init_db, ejecutar_query
from modulos import ventas, reportes, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide")
init_db()

st.sidebar.title("🚀 Navegación")
opcion = st.sidebar.radio("Ir a:", ["🏠 Inicio", "📂 Ventas", "📓 Libro Diario", "⚙️ Configuración"])

if opcion == "🏠 Inicio":
    st.title("📊 Dashboard de Gestión")
    
    # 1. Verificación de PDC
    check_pdc = ejecutar_query("SELECT COUNT(*) as total FROM plan_cuentas", fetch=True)
    if check_pdc.iloc[0]['total'] == 0:
        st.warning("⚠️ Plan de Cuentas no detectado. Cargue uno en Configuración.")
    
    # 2. Lógica del Dashboard (Ventas Mensuales)
    st.subheader("📈 Ventas Mensuales (Neto)")
    # Buscamos en el diario los movimientos al haber de la cuenta 'VENTAS'
    query_ventas = """
        SELECT SUBSTR(fecha, 4, 7) as mes, SUM(haber - debe) as neto
        FROM libro_diario 
        WHERE cuenta LIKE '%VENTAS%'
        GROUP BY mes
        ORDER BY mes ASC
    """
    df_grafico = ejecutar_query(query_ventas, fetch=True)
    
    if not df_grafico.empty:
        # Mostramos gráfico de barras
        st.bar_chart(data=df_grafico, x='mes', y='neto')
        
        # Métricas rápidas
        col1, col2 = st.columns(2)
        total_acumulado = df_grafico['neto'].sum()
        col1.metric("Total Ventas Netas", f"$ {total_acumulado:,.2f}")
        col2.metric("Mes con mayor venta", df_grafico.loc[df_grafico['neto'].idxmax()]['mes'])
    else:
        st.info("No hay datos en el Libro Diario para mostrar estadísticas.")

elif opcion == "📂 Ventas":
    ventas.mostrar_ventas()

elif opcion == "📓 Libro Diario":
    reportes.mostrar_diario()

elif opcion == "⚙️ Configuración":
    configuracion.mostrar_configuracion()