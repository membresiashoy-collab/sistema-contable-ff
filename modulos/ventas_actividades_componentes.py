from __future__ import annotations

import pandas as pd
import streamlit as st

from services.ventas_actividades_service import (
    TIPOS_VENTA,
    TRATAMIENTOS_IVA,
    asignar_actividad_a_ventas,
    asignar_actividad_a_ventas_pendientes,
    crear_actividad_venta,
    listar_actividades_venta,
    listar_archivos_ventas_importadas,
    listar_ventas_sin_actividad,
    obtener_resumen_actividades_ventas,
    obtener_resumen_ventas_por_agrupacion,
)


def _empresa_id_actual(empresa_id: int | None = None) -> int:
    if empresa_id is not None:
        try:
            return max(int(empresa_id), 1)
        except Exception:
            return 1

    for clave in ("empresa_id", "empresa_actual_id", "id_empresa"):
        valor = st.session_state.get(clave)
        if valor:
            try:
                return max(int(valor), 1)
            except Exception:
                continue
    return 1


def _usuario_actual(usuario: str | None = None) -> str:
    if usuario:
        return str(usuario)
    for clave in ("usuario", "username", "usuario_actual", "email_usuario"):
        valor = st.session_state.get(clave)
        if valor:
            return str(valor)
    return "sistema"


def _columnas_ventas(df: pd.DataFrame) -> list[str]:
    preferidas = [
        "id",
        "fecha",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "neto",
        "iva",
        "total",
        "archivo",
    ]
    return [col for col in preferidas if col in df.columns]


def _df_resumen_agrupaciones(resumen: dict) -> pd.DataFrame:
    datos = resumen.get("por_actividad", {}) if isinstance(resumen, dict) else {}
    filas = []
    for nombre, valores in datos.items():
        if isinstance(valores, dict):
            filas.append(
                {
                    "Agrupación": nombre,
                    "Comprobantes": valores.get("cantidad", 0),
                    "Neto": valores.get("neto", 0),
                    "IVA": valores.get("iva", 0),
                    "Total": valores.get("total", 0),
                }
            )
        else:
            filas.append({"Agrupación": nombre, "Comprobantes": valores})
    return pd.DataFrame(filas)


def mostrar_actividades_ventas_ui(
    empresa_id: int | None = None,
    usuario: str | None = None,
) -> None:
    empresa_id_final = _empresa_id_actual(empresa_id)
    usuario_final = _usuario_actual(usuario)

    st.divider()
    st.subheader("🏷️ Agrupaciones internas de venta")

    st.caption(
        "Definí agrupaciones comerciales propias de esta empresa, por ejemplo Cubiertas, "
        "Movimiento de suelo o Servicios profesionales. Sirven para resumir ventas e IVA por actividad interna. "
        "No son cuentas contables y no obligan a crear una cuenta por cada agrupación."
    )

    try:
        resumen = obtener_resumen_actividades_ventas(empresa_id=empresa_id_final)
        actividades = listar_actividades_venta(empresa_id=empresa_id_final)
    except Exception as exc:
        st.error(f"No se pudieron cargar agrupaciones de venta: {exc}")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Ventas cargadas", resumen.get("total", 0))
    col2.metric("Con agrupación", resumen.get("con_actividad", 0))
    col3.metric("Sin agrupación", resumen.get("sin_actividad", 0))

    resumen_df = _df_resumen_agrupaciones(resumen)
    if not resumen_df.empty:
        with st.expander("Resumen por agrupación", expanded=False):
            st.dataframe(resumen_df, use_container_width=True, hide_index=True)

    with st.expander("Crear agrupación interna de venta", expanded=actividades.empty):
        st.info(
            "La agrupación es reportable. La cuenta contable se resolverá después por tipo fiscal/contable "
            "y tratamiento IVA desde el Plan Empresa / Plan Maestro FF."
        )

        col_a, col_b = st.columns(2)
        nombre = col_a.text_input(
            "Nombre de agrupación",
            placeholder="Ej.: Cubiertas, Movimiento de suelo, Servicios profesionales",
            key=f"venta_agrupacion_nombre_{empresa_id_final}",
        )
        codigo = col_b.text_input(
            "Código interno",
            placeholder="Ej.: CUBIERTAS, MOV_SUELO, SERV_PROF",
            key=f"venta_agrupacion_codigo_{empresa_id_final}",
        )

        tipo_labels = {v: k for k, v in TIPOS_VENTA.items()}
        tipo_label = st.selectbox(
            "Tipo fiscal/contable habitual",
            options=list(tipo_labels.keys()),
            key=f"venta_agrupacion_tipo_{empresa_id_final}",
            help="Este campo ayuda a resolver IVA y cuenta contable; la agrupación en sí no define cuenta.",
        )
        tratamiento_labels = {v: k for k, v in TRATAMIENTOS_IVA.items()}
        tratamiento_label = st.selectbox(
            "Tratamiento IVA habitual",
            options=list(tratamiento_labels.keys()),
            key=f"venta_agrupacion_tratamiento_{empresa_id_final}",
        )

        descripcion = st.text_area(
            "Descripción / criterio de uso",
            placeholder="Cuándo usar esta agrupación. Ej.: ventas de cubiertas importadas desde ARCA.",
            key=f"venta_agrupacion_descripcion_{empresa_id_final}",
        )

        if st.button(
            "Guardar agrupación de venta",
            type="primary",
            use_container_width=True,
            key=f"venta_agrupacion_guardar_{empresa_id_final}",
        ):
            try:
                resultado = crear_actividad_venta(
                    empresa_id=empresa_id_final,
                    codigo=codigo or nombre,
                    nombre=nombre,
                    tipo_venta=tipo_labels[tipo_label],
                    tratamiento_iva=tratamiento_labels[tratamiento_label],
                    descripcion=descripcion,
                    usuario=usuario_final,
                )
            except Exception as exc:
                st.error(f"No se pudo crear la agrupación: {exc}")
            else:
                st.success(f"Agrupación creada: {resultado.get('nombre', nombre)}")
                st.rerun()

    if not actividades.empty:
        with st.expander("Agrupaciones disponibles", expanded=False):
            columnas = [
                col
                for col in [
                    "id",
                    "codigo",
                    "nombre",
                    "tipo_venta",
                    "tratamiento_iva",
                    "activo",
                ]
                if col in actividades.columns
            ]
            vista = actividades[columnas].copy() if columnas else actividades.copy()
            renombres = {
                "codigo": "Código",
                "nombre": "Agrupación",
                "tipo_venta": "Tipo fiscal/contable",
                "tratamiento_iva": "Tratamiento IVA",
                "activo": "Activa",
            }
            vista = vista.rename(columns=renombres)
            st.dataframe(vista, use_container_width=True, hide_index=True)

    archivos = ["Todas las ventas sin agrupación"] + listar_archivos_ventas_importadas(empresa_id=empresa_id_final)
    archivo_opcion = st.selectbox(
        "Alcance para asignar agrupación",
        options=archivos,
        key=f"venta_agrupacion_archivo_{empresa_id_final}",
    )
    archivo = "" if archivo_opcion == "Todas las ventas sin agrupación" else archivo_opcion

    try:
        pendientes = listar_ventas_sin_actividad(
            empresa_id=empresa_id_final,
            archivo=archivo or None,
        )
    except Exception as exc:
        st.error(f"No se pudieron leer ventas sin agrupación: {exc}")
        return

    if pendientes.empty:
        st.success("No hay ventas pendientes de agrupación para el alcance seleccionado.")
        try:
            resumen_detallado = obtener_resumen_ventas_por_agrupacion(empresa_id=empresa_id_final)
            if not resumen_detallado.empty:
                with st.expander("Ver resumen detallado por agrupación / tipo fiscal", expanded=False):
                    st.dataframe(resumen_detallado, use_container_width=True, hide_index=True)
        except Exception:
            pass
        return

    st.warning(
        "Antes de generar asientos de Ventas, asigná una agrupación y un tipo fiscal/contable. "
        "La agrupación es para reportes; el asiento se resuelve por tipo/tratamiento."
    )

    columnas = _columnas_ventas(pendientes)
    st.dataframe(pendientes[columnas] if columnas else pendientes, use_container_width=True, hide_index=True)

    if actividades.empty:
        st.info("Primero creá una agrupación de venta para poder asignarla.")
        return

    opciones = {
        f"{int(fila['id'])} - {fila['codigo']} - {fila['nombre']}": int(fila["id"])
        for _, fila in actividades.iterrows()
    }
    actividad_label = st.selectbox(
        "Agrupación a asignar",
        options=list(opciones.keys()),
        key=f"venta_agrupacion_asignar_{empresa_id_final}",
    )
    actividad_id = opciones[actividad_label]

    modo = st.radio(
        "Ventas a actualizar",
        options=["Todas las pendientes del alcance", "Seleccionar por ID"],
        horizontal=True,
        key=f"venta_agrupacion_modo_{empresa_id_final}",
    )

    ids_seleccionados: list[int] = []
    if modo == "Seleccionar por ID":
        ids_disponibles = [int(v) for v in pendientes["id"].tolist()]
        ids_seleccionados = st.multiselect(
            "IDs de ventas",
            options=ids_disponibles,
            key=f"venta_agrupacion_ids_{empresa_id_final}",
        )
        if not ids_seleccionados:
            st.info("Seleccioná al menos una venta.")
            return

    confirmar = st.checkbox(
        "Confirmo que esta agrupación corresponde a las ventas seleccionadas",
        key=f"venta_agrupacion_confirmar_{empresa_id_final}",
    )
    if not confirmar:
        st.info("Marcá la confirmación para habilitar la asignación.")
        return

    if st.button(
        "Asignar agrupación a ventas",
        type="primary",
        use_container_width=True,
        key=f"venta_agrupacion_aplicar_{empresa_id_final}",
    ):
        try:
            if modo == "Seleccionar por ID":
                resultado = asignar_actividad_a_ventas(
                    empresa_id=empresa_id_final,
                    venta_ids=ids_seleccionados,
                    actividad_id=actividad_id,
                    usuario=usuario_final,
                )
            else:
                resultado = asignar_actividad_a_ventas_pendientes(
                    empresa_id=empresa_id_final,
                    actividad_id=actividad_id,
                    archivo=archivo or None,
                    usuario=usuario_final,
                )
        except Exception as exc:
            st.error(f"No se pudo asignar la agrupación: {exc}")
            return

        if resultado.get("ok"):
            st.success(f"Ventas actualizadas: {resultado.get('ventas_actualizadas', 0)}")
            st.info("Luego estas ventas podrán enviarse a Bandeja con el tipo fiscal/contable asignado.")
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo asignar la agrupación."))