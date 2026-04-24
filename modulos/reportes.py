import streamlit as st
import pandas as pd
from database import ejecutar_query, eliminar_todo_diario, eliminar_diferencias_redondeo


def formatear_fecha(fecha):
    try:
        fecha_convertida = pd.to_datetime(fecha, dayfirst=True, errors="coerce")

        if pd.isna(fecha_convertida):
            return fecha

        return fecha_convertida.strftime("%d/%m/%Y")

    except Exception:
        return fecha


def insertar_espacios_entre_asientos(df):
    filas = []

    for _, grupo in df.groupby("id_asiento", sort=False):
        filas.append(grupo)

        fila_vacia = pd.DataFrame([{
            "id_asiento": "",
            "fecha": "",
            "cuenta": "",
            "debe": "",
            "haber": "",
            "glosa": "",
            "origen": "",
            "archivo": ""
        }])

        filas.append(fila_vacia)

    if filas:
        return pd.concat(filas, ignore_index=True)

    return df


def mostrar_diario():
    st.title("📓 Libro Diario")

    df = ejecutar_query("""
        SELECT 
            id,
            id_asiento,
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            origen,
            archivo
        FROM libro_diario
    """, fetch=True)

    if df.empty:
        st.info("Sin movimientos.")
        return

    # --------------------------------------------------
    # Control de movimientos viejos de redondeo
    # --------------------------------------------------
    df_redondeo = df[df["cuenta"] == "DIFERENCIA POR REDONDEO"]

    if not df_redondeo.empty:
        st.error(
            f"Se detectaron {len(df_redondeo)} movimientos antiguos en la cuenta "
            "'DIFERENCIA POR REDONDEO'. Estos movimientos corresponden a pruebas "
            "anteriores y deben eliminarse."
        )

        if "confirmar_eliminar_redondeo" not in st.session_state:
            st.session_state["confirmar_eliminar_redondeo"] = False

        if st.button("Eliminar movimientos de DIFERENCIA POR REDONDEO"):
            st.session_state["confirmar_eliminar_redondeo"] = True

        if st.session_state["confirmar_eliminar_redondeo"]:
            st.warning("¿Confirmás eliminar esos movimientos del Libro Diario?")

            c1, c2 = st.columns(2)

            with c1:
                if st.button("Sí, eliminar redondeos"):
                    eliminar_diferencias_redondeo()
                    st.success("Movimientos de diferencia por redondeo eliminados.")
                    st.session_state["confirmar_eliminar_redondeo"] = False
                    st.rerun()

            with c2:
                if st.button("Cancelar eliminación"):
                    st.session_state["confirmar_eliminar_redondeo"] = False
                    st.rerun()

        st.divider()

    # Filtramos para que no se vean mientras existan
    df = df[df["cuenta"] != "DIFERENCIA POR REDONDEO"].copy()

    if df.empty:
        st.info("No hay movimientos contables luego de excluir redondeos antiguos.")
        return

    df["fecha_orden"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    df["fecha"] = df["fecha"].apply(formatear_fecha)

    st.subheader("Filtros")

    col1, col2 = st.columns(2)

    with col1:
        origenes = ["Todos"] + sorted(df["origen"].dropna().unique().tolist())
        origen_seleccionado = st.selectbox("Filtrar por origen", origenes)

    if origen_seleccionado != "Todos":
        df = df[df["origen"] == origen_seleccionado]

    with col2:
        archivos = ["Todos"] + sorted(df["archivo"].dropna().unique().tolist())
        archivo_seleccionado = st.selectbox("Filtrar por archivo", archivos)

    if archivo_seleccionado != "Todos":
        df = df[df["archivo"] == archivo_seleccionado]

    df = df.sort_values(
        by=["fecha_orden", "id_asiento", "id"],
        ascending=True
    )

    df_vista = df[[
        "id_asiento",
        "fecha",
        "cuenta",
        "debe",
        "haber",
        "glosa",
        "origen",
        "archivo"
    ]].copy()

    total_debe = df_vista["debe"].sum()
    total_haber = df_vista["haber"].sum()
    diferencia = round(total_debe - total_haber, 2)

    df_vista_con_espacios = insertar_espacios_entre_asientos(df_vista)

    df_vista_con_espacios.index = range(1, len(df_vista_con_espacios) + 1)
    df_vista_con_espacios.index.name = "N°"

    st.subheader("Movimientos contables")
    st.dataframe(df_vista_con_espacios, use_container_width=True)

    st.divider()

    c1, c2, c3 = st.columns(3)

    c1.metric("Total Debe", f"$ {total_debe:,.2f}")
    c2.metric("Total Haber", f"$ {total_haber:,.2f}")
    c3.metric("Diferencia", f"$ {diferencia:,.2f}")

    if diferencia != 0:
        st.error("El Libro Diario no está cuadrando.")
    else:
        st.success("El Libro Diario está cuadrado.")

    st.divider()

    st.subheader("Resumen por origen")

    resumen = df.groupby("origen")[["debe", "haber"]].sum().reset_index()
    resumen["diferencia"] = resumen["debe"] - resumen["haber"]

    st.dataframe(resumen, use_container_width=True)

    st.divider()

    if "confirmar_limpiar_diario" not in st.session_state:
        st.session_state["confirmar_limpiar_diario"] = False

    if st.button("🧹 Limpiar Libro Diario"):
        st.session_state["confirmar_limpiar_diario"] = True

    if st.session_state["confirmar_limpiar_diario"]:
        st.warning("¿Confirmás eliminar todos los movimientos del Libro Diario?")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sí, limpiar libro diario"):
                eliminar_todo_diario()
                st.success("Libro Diario limpiado.")
                st.session_state["confirmar_limpiar_diario"] = False
                st.rerun()

        with col2:
            if st.button("Cancelar"):
                st.session_state["confirmar_limpiar_diario"] = False
                st.rerun()