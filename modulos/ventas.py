import streamlit as st
import pandas as pd
import database

def mostrar_ventas():
    st.title("📤 Módulo de Ventas")
    
    # Botón de reset: USALO UNA VEZ antes de cargar
    if st.button("🔴 RESETEAR SISTEMA (Borrar todo y empezar limpio)"):
        database.init_db()
        st.success("Base de datos recreada desde cero.")

    archivo = st.file_uploader("Subir CSV de AFIP", type=["csv"])
    
    if archivo:
        try:
            df = pd.read_csv(archivo, sep=None, engine='python', encoding='latin-1')
            df.columns = [c.strip().upper() for c in df.columns]
            
            c_f = next(c for c in df.columns if "FECHA" in c)
            c_t = next(c for c in df.columns if "TIPO" in c and "COMPROBANTE" in c)
            c_tot = next(c for c in df.columns if "TOTAL" in c and "IVA" not in c)
            c_iva = next((c for c in df.columns if "TOTAL IVA" in c or "IVA 21%" in c), None)

            if st.button("🚀 PROCESAR AHORA"):
                # Obtenemos el ID de asiento actual
                res = database.ejecutar_query("SELECT MAX(id_asiento) FROM libro_diario", fetch=True)
                n_asiento = 1 if res.empty or res.iloc[0,0] is None else int(res.iloc[0,0]) + 1
                
                exitos = 0
                for _, r in df.iterrows():
                    f, t = r[c_f], str(r[c_t])
                    total = float(str(r[c_tot]).replace(',', '.'))
                    iva = 0
                    if c_iva and pd.notnull(r[c_iva]):
                        try: iva = float(str(r[c_iva]).replace(',', '.'))
                        except: iva = 0
                    
                    neto = total - iva

                    # INSERTAMOS Y FORZAMOS
                    database.ejecutar_query(
                        "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)",
                        (n_asiento, f, "DEUDORES POR VENTAS", total, 0, f"Venta {t}", "VENTAS")
                    )
                    database.ejecutar_query(
                        "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)",
                        (n_asiento, f, "VENTAS", 0, neto, f"Venta {t}", "VENTAS")
                    )
                    if iva > 0:
                        database.ejecutar_query(
                            "INSERT INTO libro_diario (id_asiento, fecha, cuenta, debe, haber, glosa, origen) VALUES (?,?,?,?,?,?,?)",
                            (n_asiento, f, "IVA DEBITO FISCAL", 0, iva, f"Venta {t}", "VENTAS")
                        )
                    n_asiento += 1
                    exitos += 1
                
                if exitos > 0:
                    st.balloons()
                    st.success(f"¡LOGRADO! Se guardaron {exitos} comprobantes en la base de datos.")
                    # Mostramos una vista previa rápida para confirmar que NO hay ceros
                    debug_df = database.ejecutar_query("SELECT * FROM libro_diario ORDER BY id DESC LIMIT 5", fetch=True)
                    st.write("Vista previa de lo guardado:", debug_df)
                else:
                    st.error("El archivo se leyó pero no se insertó nada.")
                    
        except Exception as e:
            st.error(f"Error fatal: {e}")