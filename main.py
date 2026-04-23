import streamlit as st
import pandas as pd
import database
from modulos import ventas, compras, reportes

# Esto DEBE funcionar si database.py tiene la función
database.init_db()

st.sidebar.title("Menú Contable")
opcion = st.sidebar.radio("Ir a:", ["Inicio", "Ventas", "Compras", "Libro Diario", "⚙️ Configuración ARCA"])

if opcion == "Inicio":
    st.title("📊 Posición Mensual de IVA")
    m, a = st.columns(2)
    mes = m.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    anio = a.number_input("Año", value=2025)

    idx = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    f_sql = f"WHERE fecha LIKE '{anio}%'" if mes == "ANUAL" else f"WHERE fecha LIKE '%{anio}{idx[mes]}%'"

    dv = database.ejecutar_query(f"SELECT SUM(haber) - SUM(debe) as t FROM libro_diario {f_sql} AND cuenta = 'IVA DEBITO FISCAL'", fetch=True)['t'].iloc[0] or 0.0
    cv = database.ejecutar_query(f"SELECT SUM(debe) - SUM(haber) as t FROM libro_diario {f_sql} AND cuenta = 'IVA CREDITO FISCAL'", fetch=True)['t'].iloc[0] or 0.0
    
    st.metric("Saldo Técnico", f"$ {abs(dv-cv):,.2f}", delta="PAGAR" if (dv-cv)>0 else "A FAVOR")

elif opcion == "⚙️ Configuración ARCA":
    st.title("⚙️ Configuración")
    archivo_tabla = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"])
    if archivo_tabla:
        df_t = pd.read_csv(archivo_tabla, sep=';', encoding='latin-1')
        if st.button("Sincronizar Códigos"):
            database.cargar_tabla_referencia(df_t)
            st.success("Sincronizado.")

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()