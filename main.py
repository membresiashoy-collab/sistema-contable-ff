import streamlit as st
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("Menú")
opcion = st.sidebar.radio("Ir a:", ["Inicio", "Ventas", "Compras", "Libro Diario", "Configuración"])

if opcion == "Inicio":
    st.title("📊 Posición de IVA")
    # ... (Misma lógica de cálculo de IVA de antes) ...
    st.info("Utilice el menú de la izquierda para cargar archivos.")

elif opcion == "Configuración":
    st.title("⚙️ Administración del Sistema")
    st.subheader("Limpieza de Datos")
    st.warning("Esta acción eliminará todos los asientos y permitirá volver a cargar archivos ya procesados.")
    
    if st.button("🗑️ BORRAR TODO (Asientos y Archivos)"):
        database.resetear_sistema()
        st.success("Sistema reseteado correctamente.")
        st.rerun()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()