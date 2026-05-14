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


def mostrar_actividades_ventas_ui(
    empresa_id: int | None = None,
    usuario: str | None = None,
) -> None:
    empresa_id_final = _empresa_id_actual(empresa_id)
    usuario_final = _usuario_actual(usuario)

    st.divider()
    st.subheader("🏷️ Actividades de venta")

    st.caption(
        "Configure actividades internas de la empresa y asígnelas a ventas importadas o manuales. "
        "Esta información será usada luego para generar asientos propuestos de Ventas en Bandeja."
    )

    try:
        resumen = obtener_resumen_actividades_ventas(empresa_id=empresa_id_final)
        actividades = listar_actividades_venta(empresa_id=empresa_id_final)
    except Exception as exc:
        st.error(f"No se pudieron cargar actividades de venta: {exc}")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Ventas cargadas", resumen.get("total", 0))
    col2.metric("Con actividad", resumen.get("con_actividad", 0))
    col3.metric("Sin actividad", resumen.get("sin_actividad", 0))

    with st.expander("Crear actividad interna de venta", expanded=actividades.empty):
        col_a, col_b = st.columns(2)
        nombre = col_a.text_input(
            "Nombre de actividad",
            placeholder="Ej.: Servicios profesionales, Venta de indumentaria, Exportación de servicios",
            key=f"venta_actividad_nombre_{empresa_id_final}",
        )
        codigo = col_b.text_input(
            "Código interno",
            placeholder="Ej.: SERVICIOS_PROFESIONALES",
            key=f"venta_actividad_codigo_{empresa_id_final}",
        )

        tipo_labels = {v: k for k, v in TIPOS_VENTA.items()}
        tipo_label = st.selectbox(
            "Tipo de venta",
            options=list(tipo_labels.keys()),
            key=f"venta_actividad_tipo_{empresa_id_final}",
        )
        tratamiento_labels = {v: k for k, v in TRATAMIENTOS_IVA.items()}
        tratamiento_label = st.selectbox(
            "Tratamiento IVA habitual",
            options=list(tratamiento_labels.keys()),
            key=f"venta_actividad_tratamiento_{empresa_id_final}",
        )

        descripcion = st.text_area(
            "Descripción / criterio de uso",
            placeholder="Cuándo usar esta actividad.",
            key=f"venta_actividad_descripcion_{empresa_id_final}",
        )

        if st.button(
            "Guardar actividad de venta",
            type="primary",
            use_container_width=True,
            key=f"venta_actividad_guardar_{empresa_id_final}",
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
                st.error(f"No se pudo crear la actividad: {exc}")
            else:
                st.success(f"Actividad creada: {resultado.get('nombre', nombre)}")
                st.rerun()

    if not actividades.empty:
        with st.expander("Actividades disponibles", expanded=False):
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
            st.dataframe(actividades[columnas], use_container_width=True, hide_index=True)

    archivos = ["Todas las ventas sin actividad"] + listar_archivos_ventas_importadas(empresa_id=empresa_id_final)
    archivo_opcion = st.selectbox(
        "Alcance para asignar actividad",
        options=archivos,
        key=f"venta_actividad_archivo_{empresa_id_final}",
    )
    archivo = "" if archivo_opcion == "Todas las ventas sin actividad" else archivo_opcion

    try:
        pendientes = listar_ventas_sin_actividad(
            empresa_id=empresa_id_final,
            archivo=archivo or None,
        )
    except Exception as exc:
        st.error(f"No se pudieron leer ventas sin actividad: {exc}")
        return

    if pendientes.empty:
        st.success("No hay ventas pendientes de actividad para el alcance seleccionado.")
        return

    st.warning(
        "Antes de generar asientos de Ventas, asigne una actividad. "
        "Esto evita enviar ventas genéricas a Bandeja."
    )

    columnas = _columnas_ventas(pendientes)
    st.dataframe(pendientes[columnas] if columnas else pendientes, use_container_width=True, hide_index=True)

    if actividades.empty:
        st.info("Primero cree una actividad de venta para poder asignarla.")
        return

    opciones = {
        f"{int(fila['id'])} - {fila['nombre']}": int(fila["id"])
        for _, fila in actividades.iterrows()
    }
    actividad_label = st.selectbox(
        "Actividad a asignar",
        options=list(opciones.keys()),
        key=f"venta_actividad_asignar_{empresa_id_final}",
    )
    actividad_id = opciones[actividad_label]

    modo = st.radio(
        "Ventas a actualizar",
        options=["Todas las pendientes del alcance", "Seleccionar por ID"],
        horizontal=True,
        key=f"venta_actividad_modo_{empresa_id_final}",
    )

    ids_seleccionados: list[int] = []
    if modo == "Seleccionar por ID":
        ids_disponibles = [int(v) for v in pendientes["id"].tolist()]
        ids_seleccionados = st.multiselect(
            "IDs de ventas",
            options=ids_disponibles,
            key=f"venta_actividad_ids_{empresa_id_final}",
        )
        if not ids_seleccionados:
            st.info("Seleccione al menos una venta.")
            return

    confirmar = st.checkbox(
        "Confirmo que esta actividad corresponde a las ventas seleccionadas",
        key=f"venta_actividad_confirmar_{empresa_id_final}",
    )
    if not confirmar:
        st.info("Marque la confirmación para habilitar la asignación.")
        return

    if st.button(
        "Asignar actividad a ventas",
        type="primary",
        use_container_width=True,
        key=f"venta_actividad_aplicar_{empresa_id_final}",
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
            st.error(f"No se pudo asignar la actividad: {exc}")
            return

        if resultado.get("ok"):
            st.success(f"Ventas actualizadas: {resultado.get('ventas_actualizadas', 0)}")
            st.info("Luego estas ventas podrán enviarse a Bandeja con la actividad seleccionada.")
            st.rerun()
        else:
            st.error(resultado.get("mensaje", "No se pudo asignar la actividad."))

