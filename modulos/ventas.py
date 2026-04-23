import streamlit as st
import pandas as pd
import io
from database import ejecutar_query

def limpiar_num(valor):
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def mostrar_ventas():
    st.title("📂 Carga de Ventas con Validación de Plan")
    archivo = st.file_uploader("Subir CSV ARCA", type=["csv"])
    
    if archivo:
        # Cargamos el Plan de Cuentas para validar
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        lista_cuentas = pdc['nombre'].tolist() if not pdc.empty else []

        if not lista_cuentas:
            st.error("❌ No hay un Plan de Cuentas cargado. Subalo en Configuración.")
            return

        contenido = archivo.read().decode('latin-1').replace('"', '')
        df = pd.read_csv(io.StringIO(contenido), sep=';')

        if st.button("🚀 Generar Asientos "):
            # Validamos que existan las cuentas básicas en tu PDC
            cuenta_debe = "DEUDORES POR VENTAS"
            if cuenta_debe in lista_cuentas:
                for _, fila in df.iterrows():
                    f, r = fila.iloc[0], fila.iloc[8]
                    n, i, t = limpiar_num(fila.iloc[22]), limpiar_num(fila.iloc[26]), limpiar_num(fila.iloc[27])
                    
                    glosa = f"Venta s/Fac. ARCA - {r}"
                    
                    # El PDC manda: Se usa el nombre exacto del plan
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, cuenta_debe, t, 0, glosa))
                    ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "VENTAS GRAVADAS", 0, n, glosa))
                    if i > 0:
                        ejecutar_query("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?)", (f, "IVA DEBITO FISCAL", 0, i, glosa))
                st.success("✅ Asientos generados y validados contra el Plan de Cuentas.")
            else:
                st.error(f"❌ La cuenta '{cuenta_debe}' no existe en tu Plan de Cuentas cargado.")