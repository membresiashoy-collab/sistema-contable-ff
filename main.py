import streamlit as st
from database import init_db
from modulos import ventas, reportes, auditoria, configuracion

# Configuración de la página (Debe ser la primera instrucción de Streamlit)
st.set_page_config(
    page_title="Sistema Contable FF",
    page_icon="🚀",
    layout="wide"
)

# Inicializar la base de datos y las tablas al arrancar
init_db()

# --- ESTILOS PERSONALIZADOS ---
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        background-color: #007bff;
        color: white;
    }
    .stDataFrame {
        border: 1px solid #e6e9ef;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- NAVEGACIÓN LATERAL ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2645/2645300.png", width=100)
st.sidebar.title("Navegación")
st.sidebar.divider()

menu = st.sidebar.radio(
    "Seleccione un módulo:",
    ["🏠 Inicio", "📂 Ventas", "📓 Libro Diario", "📊 Estado de Cargas", "⚙️ Configuración"]
)

st.sidebar.divider()
st.sidebar.info("Sistema Contable v2.0 - Control de Partida Doble")

# --- LÓGICA DE ENRUTAMIENTO ---

if menu == "🏠 Inicio":
    st.title("Bienvenido al Sistema Contable")
    st.write("""
    Este sistema permite gestionar la contabilidad de manera automatizada a partir de archivos de ARCA.
    
    **Pasos recomendados:**
    1. Asegúrese de tener el **Plan de Cuentas** cargado en Configuración.
    2. Suba sus archivos CSV en el módulo de **Ventas**.
    3. Revise y edite sus asientos en el **Libro Diario**.
    4. Controle qué archivos ya procesó en **Estado de Cargas**.
    """)
    
    # Resumen rápido en el inicio
    col1, col2 = st.columns(2)
    with col1:
        st.success("Base de datos conectada correctamente.")
    with col2:
        st.info("Listo para procesar asientos exentos y gravados.")

elif menu == "📂 Ventas":
    ventas.mostrar_ventas()

elif menu == "📓 Libro Diario":
    reportes.mostrar_diario()

elif menu == "📊 Estado de Cargas":
    auditoria.mostrar_estado()

elif menu == "⚙️ Configuración":
    configuracion.mostrar_configuracion()

# --- PIE DE PÁGINA ---
st.sidebar.markdown("---")
st.sidebar.caption("Desarrollado para Gestión Contable Profesional")