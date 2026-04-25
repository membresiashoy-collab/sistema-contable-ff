import json
import re

import pandas as pd
import streamlit as st

from database import ejecutar_query
from core.ui import preparar_vista
from core.exportadores import exportar_excel


# ======================================================
# UTILIDADES
# ======================================================

def key_segura(texto):
    texto = str(texto)
    texto = re.sub(r"[^A-Za-z0-9_]+", "_", texto)
    texto = texto.strip("_")

    if texto == "":
        texto = "SIN_KEY"

    return texto


def asegurar_tabla_advertencias():
    try:
        ejecutar_query("""
            CREATE TABLE IF NOT EXISTS advertencias_carga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modulo TEXT,
                archivo TEXT,
                fila INTEGER,
                motivo TEXT,
                contenido TEXT,
                fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass


def archivo_base(nombre_archivo):
    nombre = str(nombre_archivo)

    if "__" in nombre:
        return nombre.split("__")[0]

    return nombre


def patron_archivo_base(nombre):
    return f"{nombre}__%"


def contar_registros(tabla, archivo):
    try:
        df = ejecutar_query(f"""
            SELECT COUNT(*) AS cantidad
            FROM {tabla}
            WHERE archivo = ?
               OR archivo LIKE ?
        """, (archivo, patron_archivo_base(archivo)), fetch=True)

        if df.empty:
            return 0

        return int(df.iloc[0]["cantidad"])
    except Exception:
        return 0


def obtener_historial_agrupado():
    asegurar_tabla_advertencias()

    try:
        historial = ejecutar_query("""
            SELECT 
                fecha,
                modulo,
                nombre_archivo,
                registros
            FROM historial_cargas
            ORDER BY id DESC
        """, fetch=True)
    except Exception:
        return pd.DataFrame()

    if historial.empty:
        return historial

    historial["archivo_base"] = historial["nombre_archivo"].apply(archivo_base)

    filas = []

    for base, grupo in historial.groupby("archivo_base"):
        registros = int(pd.to_numeric(grupo["registros"], errors="coerce").fillna(0).sum())
        modulos = ", ".join(sorted(grupo["modulo"].dropna().astype(str).unique().tolist()))
        fecha = grupo["fecha"].max()
        partes = len(grupo)

        filas.append({
            "archivo": base,
            "modulo": modulos,
            "fecha": fecha,
            "partes": partes,
            "registros": registros,
            "errores": contar_registros("errores_carga", base),
            "advertencias": contar_registros("advertencias_carga", base),
            "ventas": contar_registros("ventas_comprobantes", base),
            "compras": contar_registros("compras_comprobantes", base),
            "diario": contar_registros("libro_diario", base),
        })

    df = pd.DataFrame(filas)

    if df.empty:
        return df

    return df.sort_values(by="fecha", ascending=False)


def obtener_partes_carga(archivo):
    try:
        return ejecutar_query("""
            SELECT 
                fecha,
                modulo,
                nombre_archivo,
                registros
            FROM historial_cargas
            WHERE nombre_archivo = ?
               OR nombre_archivo LIKE ?
            ORDER BY fecha DESC
        """, (archivo, patron_archivo_base(archivo)), fetch=True)
    except Exception:
        return pd.DataFrame()


def obtener_errores_carga(archivo):
    try:
        return ejecutar_query("""
            SELECT 
                fecha,
                modulo,
                archivo,
                fila,
                motivo,
                contenido
            FROM errores_carga
            WHERE archivo = ?
               OR archivo LIKE ?
            ORDER BY id DESC
        """, (archivo, patron_archivo_base(archivo)), fetch=True)
    except Exception:
        return pd.DataFrame()


def obtener_advertencias_carga(archivo):
    asegurar_tabla_advertencias()

    try:
        return ejecutar_query("""
            SELECT 
                fecha_carga AS fecha,
                modulo,
                archivo,
                fila,
                motivo,
                contenido
            FROM advertencias_carga
            WHERE archivo = ?
               OR archivo LIKE ?
            ORDER BY id DESC
        """, (archivo, patron_archivo_base(archivo)), fetch=True)
    except Exception:
        return pd.DataFrame()


def preparar_detalle_json(df):
    if df.empty:
        return df

    filas = []

    for _, row in df.iterrows():
        contenido = row.get("contenido", "")
        normalizado = {}

        try:
            data = json.loads(contenido)
            normalizado = data.get("_normalizado", {})
        except Exception:
            normalizado = {}

        filas.append({
            "fecha": row.get("fecha", ""),
            "modulo": row.get("modulo", ""),
            "archivo": row.get("archivo", ""),
            "fila": row.get("fila", ""),
            "motivo": row.get("motivo", ""),
            "codigo": normalizado.get("codigo", ""),
            "numero": normalizado.get("numero", ""),
            "proveedor_cliente": normalizado.get("proveedor", normalizado.get("cliente", "")),
            "cuit": normalizado.get("cuit", ""),
            "total": normalizado.get("total", ""),
            "categoria": normalizado.get("categoria_compra", "")
        })

    return pd.DataFrame(filas)


# ======================================================
# BORRADO COMPLETO DE CARGA
# ======================================================

def marcar_reset_clasificacion_streamlit(archivo):
    try:
        st.session_state[f"reset_clasificacion_compras_{key_segura(archivo)}"] = True
    except Exception:
        pass


def eliminar_carga_completa(archivo):
    """
    Borra solo los datos asociados al archivo seleccionado.

    La clasificación futura se recalcula desde compras_comprobantes.
    Por eso, al borrar la carga, también desaparece su efecto sobre el aprendizaje,
    sin borrar toda la historia del proveedor.
    """

    tablas_archivo = [
        "libro_diario",
        "comprobantes_procesados",
        "errores_carga",
        "advertencias_carga",
        "ventas_comprobantes",
        "cuenta_corriente_clientes",
        "compras_comprobantes",
        "cuenta_corriente_proveedores",
    ]

    for tabla in tablas_archivo:
        try:
            ejecutar_query(
                f"DELETE FROM {tabla} WHERE archivo = ? OR archivo LIKE ?",
                (archivo, patron_archivo_base(archivo))
            )
        except Exception:
            pass

    try:
        ejecutar_query(
            "DELETE FROM historial_cargas WHERE nombre_archivo = ? OR nombre_archivo LIKE ?",
            (archivo, patron_archivo_base(archivo))
        )
    except Exception:
        pass

    marcar_reset_clasificacion_streamlit(archivo)


# ======================================================
# PANTALLA ESTADO DE CARGAS
# ======================================================

def mostrar_estado_cargas():
    st.title("📦 Estado de Cargas")

    df = obtener_historial_agrupado()

    if df.empty:
        st.info("No hay cargas registradas.")
        return

    st.subheader("Resumen de cargas")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Archivos cargados", len(df))
    c2.metric("Registros procesados", int(df["registros"].sum()))
    c3.metric("Errores", int(df["errores"].sum()))
    c4.metric("Advertencias", int(df["advertencias"].sum()))

    col1, col2, col3 = st.columns(3)

    with col1:
        modulo = st.selectbox("Módulo", ["Todos"] + sorted(df["modulo"].dropna().unique().tolist()))

    with col2:
        estado = st.selectbox("Estado", ["Todos", "Con errores", "Con advertencias", "Sin observaciones"])

    with col3:
        buscar = st.text_input("Buscar archivo")

    vista = df.copy()

    if modulo != "Todos":
        vista = vista[vista["modulo"] == modulo]

    if estado == "Con errores":
        vista = vista[vista["errores"] > 0]
    elif estado == "Con advertencias":
        vista = vista[vista["advertencias"] > 0]
    elif estado == "Sin observaciones":
        vista = vista[(vista["errores"] == 0) & (vista["advertencias"] == 0)]

    if buscar.strip():
        b = buscar.strip().upper()
        vista = vista[vista["archivo"].astype(str).str.upper().str.contains(b, na=False)]

    st.dataframe(preparar_vista(vista), use_container_width=True)

    excel = exportar_excel({
        "Estado de Cargas": vista
    })

    st.download_button(
        "Descargar Estado de Cargas Excel",
        data=excel,
        file_name="estado_de_cargas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.divider()

    st.subheader("Detalle de una carga")

    if vista.empty:
        st.info("No hay cargas para los filtros seleccionados.")
        return

    archivo = st.selectbox(
        "Seleccionar archivo",
        vista["archivo"].tolist()
    )

    partes = obtener_partes_carga(archivo)
    errores = obtener_errores_carga(archivo)
    advertencias = obtener_advertencias_carga(archivo)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Partes internas", len(partes))
    col2.metric("Registros", int(partes["registros"].sum()) if not partes.empty else 0)
    col3.metric("Errores", len(errores))
    col4.metric("Advertencias", len(advertencias))

    with st.expander("Partes internas de la carga", expanded=False):
        if partes.empty:
            st.info("No hay partes internas.")
        else:
            st.dataframe(preparar_vista(partes), use_container_width=True)

    with st.expander("Errores de la carga", expanded=not errores.empty):
        if errores.empty:
            st.success("No hay errores para esta carga.")
        else:
            st.dataframe(preparar_vista(preparar_detalle_json(errores)), use_container_width=True)

    with st.expander("Advertencias de la carga", expanded=not advertencias.empty):
        if advertencias.empty:
            st.success("No hay advertencias para esta carga.")
        else:
            st.dataframe(preparar_vista(preparar_detalle_json(advertencias)), use_container_width=True)

    st.divider()

    st.subheader("Eliminar / reprocesar carga")

    st.warning(
        "Eliminar una carga borra solo los movimientos asociados a ese archivo: libro diario, "
        "comprobantes procesados, compras/ventas, cuenta corriente, errores y advertencias. "
        "No borra datos base ni elimina toda la historia del proveedor. "
        "La próxima sugerencia se recalcula con las compras que sigan cargadas."
    )

    confirmar = st.checkbox(f"Confirmo que quiero eliminar completamente la carga: {archivo}")

    if st.button("Eliminar carga seleccionada"):
        if not confirmar:
            st.warning("Primero marcá la confirmación.")
        else:
            eliminar_carga_completa(archivo)
            st.success("Carga eliminada. Ya podés reprocesar el archivo.")
            try:
                st.rerun()
            except Exception:
                pass


# ======================================================
# COMPATIBILIDAD CON MAIN.PY
# ======================================================

def mostrar_estado():
    mostrar_estado_cargas()


def mostrar_auditoria():
    mostrar_estado_cargas()


def mostrar_estado_de_cargas():
    mostrar_estado_cargas()


def mostrar():
    mostrar_estado_cargas()