import streamlit as st
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("Navegación")
opcion = st.sidebar.radio("Ir a:", ["Inicio", "Ventas", "Compras", "Libro Diario", "Configuración / ARCA"])

if opcion == "Inicio":
    st.title("📊 Resumen de IVA")
    # Lógica de métricas de IVA simplificada...
    st.info("Seleccione un módulo para operar.")

elif opcion == "Configuración / ARCA":
    st.title("🛠️ Configuración de Comprobantes")
    st.write("Esta tabla define cómo se comporta cada documento en el Libro Diario.")
    
    comp_df = database.ejecutar_query("SELECT * FROM tabla_comprobantes", fetch=True)
    st.table(comp_df)
    
    with st.expander("Añadir nuevo tipo de comprobante"):
        c1, c2, c3 = st.columns(3)
        cod = c1.number_input("Código ARCA", step=1)
        nom = c2.text_input("Nombre (ej: Nota de Crédito A)")
        rev = c3.selectbox("¿Es Reverso? (Resta)", ["No", "Si"])
        if st.button("Guardar Comprobante"):
            database.ejecutar_query("INSERT INTO tabla_comprobantes VALUES (?,?,?)", (cod, nom, 1 if rev=="Si" else 0))
            st.rerun()

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()