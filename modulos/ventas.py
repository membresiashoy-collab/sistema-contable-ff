import streamlit as st
import pandas as pd
from database import ejecutar_query

def limpiar_num(v):
    if pd.isna(v) or v == "": return 0.0
    try:
        s = str(v).replace('.', '').replace(',', '.')
        return round(float(s), 2)
    except:
        return 0.0

def mostrar_ventas():
    st.title("📂 Procesamiento de Ventas (Partida Doble)")
    
    st.info("Nota: Los números de asiento son provisorios. Se recomienda ordenar por fecha en el Libro Diario para mantener la cronología.")

    archivo = st.file_uploader("Subir Ventas ARCA (CSV)", type=["csv"])
    
    if archivo:
        pdc = ejecutar_query("SELECT nombre FROM plan_cuentas", fetch=True)
        tipos = ejecutar_query("SELECT * FROM tipos_comprobantes", fetch=True)
        
        if pdc.empty or tipos.empty:
            st.error("❌ Configure el Plan de Cuentas y los Tipos de Comprobantes.")
            return

        lista_ctas = pdc['nombre'].tolist()
        cta_deudores = next((c for c in lista_ctas if "DEUDORES" in c), "DEUDORES POR VENTAS")
        cta_ventas = next((c for c in lista_ctas if "VENTAS" in c and "IVA" not in c), "VENTAS")
        cta_iva = next((c for c in lista_ctas if "IVA" in c and ("DF" in c or "DEBITO" in c)), "IVA DF")

        df = pd.read_csv(archivo, sep=';', encoding='latin-1')

        if st.button("🚀 Generar Asientos Validados"):
            # Obtenemos el último ID para continuar la secuencia
            res = ejecutar_query("SELECT MAX(id_asiento) as u FROM libro_diario", fetch=True)
            asiento_actual = (int(res.iloc[0]['u']) if not res.empty and pd.notna(res.iloc[0]['u']) else 0) + 1
            
            error_balance = False

            for _, fila in df.iterrows():
                f = fila.iloc[0]
                cod_arca = int(fila.iloc[1])
                nro_comp = fila.iloc[2]
                cliente = fila.iloc[8]
                
                # Valores numéricos redondeados a 2 decimales
                neto = limpiar_num(fila.iloc[22])
                iva = limpiar_num(fila.iloc[26])
                total = limpiar_num(fila.iloc[27])
                
                # COMPROBACIÓN DE PARTIDA DOBLE
                # En contabilidad: Neto + IVA debe ser igual a Total
                if round(neto + iva, 2) != total:
                    st.warning(f"⚠️ Desbalance en comp. {nro_comp}: Neto({neto}) + IVA({iva}) != Total({total}). Ajustando diferencia en cuenta Ventas.")
                    neto = round(total - iva, 2)

                info = tipos[tipos['codigo'] == cod_arca]
                signo = info['signo'].values[0] if not info.empty else 1
                glosa = f"{info['descripcion'].values[0] if not info.empty else 'FC'} {nro_comp} - {cliente}"

                # Inserción de líneas
                if signo == 1:
                    lineas = [
                        (asiento_actual, f, cta_deudores, total, 0, glosa),
                        (asiento_actual, f, cta_ventas, 0, neto, glosa)
                    ]
                    if iva > 0: lineas.append((asiento_actual, f, cta_iva, 0, iva, glosa))
                else:
                    lineas = [
                        (asiento_actual, f, cta_ventas, neto, 0, glosa),
                        (asiento_actual, f, cta_deudores, 0, total, glosa)
                    ]
                    if iva > 0: lineas.append((asiento_actual, f, cta_iva, iva, 0, glosa))

                for l in lineas:
                    ejecutar_query("INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa) VALUES (?,?,?,?,?,?)", l)
                
                asiento_actual += 1

            st.success("✅ Proceso finalizado. Los asientos se han grabado respetando la partida doble.")