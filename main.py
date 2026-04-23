import streamlit as st
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("Navegación")
opcion = st.sidebar.radio("Ir a:", ["Inicio", "Ventas", "Compras", "Libro Diario", "⚙️ Configuración ARCA"])

if opcion == "⚙️ Configuración ARCA":
    st.title("Configuración de Comprobantes")
    st.write("Cargue el archivo TABLACOMPROBANTES.csv para sincronizar códigos y tipos.")
    
    archivo_tabla = st.file_uploader("Subir Tabla de Comprobantes", type=["csv"])
    if archivo_tabla:
        df_tabla = pd.read_csv(archivo_tabla, sep=';', encoding='latin-1')
        if st.button("Actualizar Tabla de Referencia"):
            database.cargar_tabla_referencia(df_tabla)
            st.success("Tabla de comprobantes actualizada con éxito.")
    
    st.subheader("Códigos cargados actualmente:")
    df_actual = database.ejecutar_query("SELECT * FROM tabla_comprobantes", fetch=True)
    st.dataframe(df_actual, hide_index=True)

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()
# ... resto del código de Inicio ...