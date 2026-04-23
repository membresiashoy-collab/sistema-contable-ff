import streamlit as st
import pandas as pd  # IMPORTACIÓN CRUCIAL PARA EVITAR EL NAMEERROR
import database
from modulos import ventas, compras, reportes

database.init_db()

st.sidebar.title("Sistema Contable FF")
opcion = st.sidebar.radio("Navegación", ["Inicio", "Ventas", "Compras", "Libro Diario", "⚙️ Configuración ARCA"])

if opcion == "Inicio":
    st.title("📊 Posición Mensual de IVA")
    
    c1, c2 = st.columns(2)
    mes = c1.selectbox("Mes", ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre", "ANUAL"])
    anio = c2.number_input("Año", value=2025)

    idx_meses = {"Enero":"-01-", "Febrero":"-02-", "Marzo":"-03-", "Abril":"-04-", "Mayo":"-05-", "Junio":"-06-", "Julio":"-07-", "Agosto":"-08-", "Septiembre":"-09-", "Octubre":"-10-", "Noviembre":"-11-", "Diciembre":"-12-"}
    
    filtro = f"WHERE fecha LIKE '{anio}%'" if mes == "ANUAL" else f"WHERE fecha LIKE '%{anio}{idx_meses[mes]}%'"

    # Consultas SQL robustas para el saldo técnico
    df_v = database.ejecutar_query(f"SELECT SUM(haber) - SUM(debe) as total FROM libro_diario {filtro} AND cuenta = 'IVA DEBITO FISCAL'", fetch=True)
    df_c = database.ejecutar_query(f"SELECT SUM(debe) - SUM(haber) as total FROM libro_diario {filtro} AND cuenta = 'IVA CREDITO FISCAL'", fetch=True)
    
    debito = df_v['total'].iloc[0] or 0.0
    credito = df_c['total'].iloc[0] or 0.0
    saldo = debito - credito
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Débito Fiscal", f"$ {debito:,.2f}")
    m2.metric("Crédito Fiscal", f"$ {credito:,.2f}")
    m3.metric("Saldo Técnico", f"$ {abs(saldo):,.2f}", delta="PAGAR" if saldo > 0 else "A FAVOR", delta_color="inverse")

elif opcion == "⚙️ Configuración ARCA":
    st.title("⚙️ Configuración de Comprobantes")
    
    if st.button("🗑️ Limpiar Tabla de Comprobantes"):
        database.ejecutar_query("DELETE FROM tabla_comprobantes")
        st.warning("Tabla de comprobantes vaciada.")
        st.rerun()

    archivo_tabla = st.file_uploader("Subir TABLACOMPROBANTES.csv", type=["csv"])
    if archivo_tabla:
        df_t = pd.read_csv(archivo_tabla, sep=';', encoding='latin-1')
        if st.button("Actualizar Base de Datos"):
            database.cargar_tabla_referencia(df_t)
            st.success("Tabla actualizada.")

elif opcion == "Ventas": ventas.mostrar_ventas()
elif opcion == "Compras": compras.mostrar_compras()
elif opcion == "Libro Diario": reportes.mostrar_diario()