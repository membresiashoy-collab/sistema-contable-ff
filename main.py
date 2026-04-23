import streamlit as st
from database import init_db, ejecutar_query
from modulos import ventas, reportes, configuracion

st.set_page_config(page_title="Sistema Contable FF", layout="wide", page_icon="📈")
init_db()

# --- NAVEGACIÓN ---
st.sidebar.title("🚀 Gestión Contable")
menu = ["🏠 Inicio", "📂 Ventas (ARCA)", "🛒 Compras", "⚖️ Impuestos", "👔 Sueldos y Jornales", "🏦 Bancos", "📓 Libro Diario", "⚖️ Sumas y Saldos", "⚙️ Configuración"]
opcion = st.sidebar.selectbox("Seleccione Módulo:", menu)

if opcion == "🏠 Inicio":
    st.title("Sistema Contable Automatizado FF")
    
    # Verificación automática del Plan de Cuentas
    check_pdc = ejecutar_query("SELECT COUNT(*) as total FROM plan_cuentas", fetch=True)
    if check_pdc.iloc[0]['total'] > 0:
        st.success(f"✅ Plan de Cuentas detectado ({check_pdc.iloc[0]['total']} cuentas). El sistema está listo para operar.")
    else:
        st.warning("⚠️ Paso 1: Ve a 'Configuración' y carga tu Plan de Cuentas para empezar.")
    
    st.info("Utilice el menú lateral para navegar entre los diferentes módulos operativos.")

elif opcion == "📂 Ventas (ARCA)":
    ventas.mostrar_ventas()

elif opcion == "🛒 Compras":
    st.title("🛒 Módulo de Compras")
    st.info("Próximamente: Importación de comprobantes recibidos y carga manual.")

elif opcion == "⚖️ Impuestos":
    st.title("⚖️ Módulo de Impuestos")
    st.info("Próximamente: Liquidación de IVA y Retenciones.")

elif opcion == "👔 Sueldos y Jornales":
    st.title("👔 Módulo de Sueldos")
    st.info("Próximamente: Liquidación de haberes y cargas sociales.")

elif opcion == "🏦 Bancos":
    st.title("🏦 Módulo de Bancos")
    st.info("Próximamente: Conciliación bancaria y carga de extractos.")

elif opcion == "📓 Libro Diario":
    reportes.mostrar_diario()

elif opcion == "⚖️ Sumas y Saldos":
    reportes.mostrar_balance()

elif opcion == "⚙️ Configuración":
    configuracion.mostrar_configuracion()