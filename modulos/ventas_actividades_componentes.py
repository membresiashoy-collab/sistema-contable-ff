from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.ventas_actividades_service import (
    TIPOS_VENTA,
    TRATAMIENTOS_IVA,
    asignar_actividad_a_ventas,
    asignar_actividad_a_ventas_pendientes,
    crear_actividad_venta,
    desactivar_agrupacion_venta,
    desasignar_agrupacion_ventas,
    editar_agrupacion_venta,
    listar_actividades_venta,
    listar_archivos_ventas_importadas,
    listar_ventas_por_agrupacion,
    listar_ventas_sin_actividad,
    obtener_resumen_actividades_ventas,
    obtener_resumen_ventas_por_agrupacion,
    reasignar_agrupacion_ventas,
    reactivar_agrupacion_venta,
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


def _rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass



CODIGOS_AGRUPACIONES_SISTEMA = {
    "VENTA_MERCADERIAS",
    "VENTA_SERVICIOS",
    "VENTA_EXENTA",
    "VENTA_NO_GRAVADA",
    "EXPORTACION_BIENES",
    "EXPORTACION_SERVICIOS",
}


def _solo_agrupaciones_usuario(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    if "codigo" not in df.columns:
        return df.copy()

    salida = df.copy()
    codigos = salida["codigo"].astype(str).str.upper().str.strip()
    return salida[~codigos.isin(CODIGOS_AGRUPACIONES_SISTEMA)].copy()


def _preparar_editor_seleccion_ventas(df: pd.DataFrame) -> pd.DataFrame:
    columnas_preferidas = [
        "id",
        "fecha",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "total",
        "actividad_venta_nombre",
        "archivo",
        "tiene_asiento_propuesto",
    ]
    columnas = [col for col in columnas_preferidas if col in df.columns]
    vista = df[columnas].copy() if columnas else df.copy()

    if "Seleccionar" not in vista.columns:
        vista.insert(0, "Seleccionar", False)

    return vista.rename(
        columns={
            "id": "ID",
            "fecha": "Fecha",
            "tipo": "Tipo",
            "punto_venta": "Pto. venta",
            "numero": "Número",
            "cliente": "Cliente",
            "cuit": "CUIT",
            "total": "Total",
            "actividad_venta_nombre": "Agrupación actual",
            "archivo": "Archivo",
            "tiene_asiento_propuesto": "Con propuesta",
        }
    )


def _ids_seleccionados_editor(editor: pd.DataFrame) -> list[int]:
    if editor is None or editor.empty:
        return []

    if "Seleccionar" not in editor.columns or "ID" not in editor.columns:
        return []

    seleccionados = editor[editor["Seleccionar"].astype(bool)].copy()

    ids = []
    for valor in seleccionados["ID"].tolist():
        try:
            ids.append(int(valor))
        except Exception:
            continue

    return ids


def _columnas_ventas(df: pd.DataFrame) -> list[str]:
    preferidas = [
        "id",
        "fecha",
        "tipo",
        "punto_venta",
        "numero",
        "cliente",
        "cuit",
        "actividad_venta_nombre",
        "tipo_venta",
        "tratamiento_iva_venta",
        "neto",
        "iva",
        "total",
        "archivo",
        "estado_correccion",
    ]
    return [col for col in preferidas if col in df.columns]


def _columnas_agrupaciones(df: pd.DataFrame) -> list[str]:
    preferidas = [
        "id",
        "codigo",
        "nombre",
        "tipo_venta",
        "tratamiento_iva",
        "activo",
        "descripcion",
    ]
    return [col for col in preferidas if col in df.columns]


def _opciones_actividades(df: pd.DataFrame) -> dict[str, int]:
    opciones: dict[str, int] = {}
    if df.empty:
        return opciones

    for _, fila in df.iterrows():
        estado = "" if int(fila.get("activo", 1) or 0) == 1 else " · INACTIVA"
        etiqueta = f"{int(fila['id'])} - {fila['codigo']} - {fila['nombre']}{estado}"
        opciones[etiqueta] = int(fila["id"])
    return opciones


def _labels_tipo() -> dict[str, str]:
    return {v: k for k, v in TIPOS_VENTA.items()}


def _labels_tratamiento() -> dict[str, str]:
    return {v: k for k, v in TRATAMIENTOS_IVA.items()}


def _label_actual(diccionario_label_codigo: dict[str, str], codigo: str) -> str:
    for label, valor in diccionario_label_codigo.items():
        if str(valor) == str(codigo):
            return label
    return list(diccionario_label_codigo.keys())[0]


def _mostrar_resultado_operacion(resultado: dict[str, Any]) -> None:
    if resultado.get("ok"):
        st.success(resultado.get("mensaje", "Operación realizada correctamente."))
    else:
        st.warning(resultado.get("mensaje", "La operación no pudo completarse."))

    bloqueadas = resultado.get("ventas_bloqueadas", [])
    if bloqueadas:
        st.info(
            "Ventas bloqueadas por propuesta en Bandeja: "
            + ", ".join(str(v) for v in bloqueadas)
            + ". El bloqueo aplica solo a esos comprobantes seleccionados."
        )


def _mostrar_resumen_por_agrupacion(empresa_id: int) -> None:
    try:
        resumen = obtener_resumen_ventas_por_agrupacion(empresa_id=empresa_id)
    except Exception as exc:
        st.warning(f"No se pudo construir el resumen por agrupación: {exc}")
        return

    with st.expander("Resumen por agrupación", expanded=True):
        if resumen.empty:
            st.info("No hay ventas para resumir por agrupación.")
            return

        vista = resumen.copy()
        columnas = [
            col
            for col in [
                "agrupacion_nombre",
                "cantidad_comprobantes",
                "neto",
                "iva",
                "total",
            ]
            if col in vista.columns
        ]
        vista = vista[columnas].rename(
            columns={
                "agrupacion_nombre": "Agrupación",
                "cantidad_comprobantes": "Comprobantes",
                "neto": "Neto",
                "iva": "IVA",
                "total": "Total",
            }
        )
        st.dataframe(vista, use_container_width=True, hide_index=True)


def _mostrar_crear_agrupacion(empresa_id: int, usuario: str, actividades_vacias: bool) -> None:
    with st.expander("Crear agrupación interna de venta", expanded=actividades_vacias):
        st.caption(
            "La agrupación la define el usuario para ordenar reportes de ventas/IVA. "
            "No es una cuenta contable y no obliga a crear cuentas por cada agrupación."
        )

        col_a, col_b = st.columns(2)
        nombre = col_a.text_input(
            "Agrupación",
            placeholder="Ej.: Cubiertas, Movimiento de suelo, Servicios profesionales",
            key=f"venta_agrupacion_nombre_{empresa_id}",
        )
        codigo = col_b.text_input(
            "Código interno",
            placeholder="Ej.: CUBIERTAS, MOV_SUELO, SERV_PROF",
            key=f"venta_agrupacion_codigo_{empresa_id}",
        )

        tipo_labels = _labels_tipo()
        tratamiento_labels = _labels_tratamiento()

        col_tipo, col_trat = st.columns(2)
        tipo_label = col_tipo.selectbox(
            "Tipo fiscal/contable base",
            options=list(tipo_labels.keys()),
            key=f"venta_agrupacion_tipo_{empresa_id}",
            help="Este dato ayuda a resolver el asiento propuesto. No es la agrupación comercial.",
        )
        tratamiento_label = col_trat.selectbox(
            "Tratamiento IVA habitual",
            options=list(tratamiento_labels.keys()),
            key=f"venta_agrupacion_tratamiento_{empresa_id}",
        )

        descripcion = st.text_area(
            "Descripción / criterio de uso",
            placeholder="Cuándo usar esta agrupación.",
            key=f"venta_agrupacion_descripcion_{empresa_id}",
        )

        if st.button(
            "Guardar agrupación",
            type="primary",
            use_container_width=True,
            key=f"venta_agrupacion_guardar_{empresa_id}",
        ):
            try:
                resultado = crear_actividad_venta(
                    empresa_id=empresa_id,
                    codigo=codigo or nombre,
                    nombre=nombre,
                    tipo_venta=tipo_labels[tipo_label],
                    tratamiento_iva=tratamiento_labels[tratamiento_label],
                    descripcion=descripcion,
                    usuario=usuario,
                )
            except Exception as exc:
                st.error(f"No se pudo crear la agrupación: {exc}")
            else:
                st.success(f"Agrupación creada: {resultado.get('nombre', nombre)}")
                _rerun()


def _mostrar_gestion_agrupaciones(
    empresa_id: int,
    usuario: str,
    actividades_todas: pd.DataFrame,
) -> None:
    actividades_usuario = _solo_agrupaciones_usuario(actividades_todas)

    if actividades_usuario.empty:
        with st.expander("Agrupaciones disponibles", expanded=True):
            st.info(
                "Todavía no hay agrupaciones comerciales creadas por el usuario. "
                "Cree una agrupación como CUBIERTAS, MOVIMIENTO DE SUELO o SERVICIOS PROFESIONALES."
            )
        return

    with st.expander("Agrupaciones disponibles", expanded=True):
        columnas = _columnas_agrupaciones(actividades_usuario)
        vista = actividades_usuario[columnas].copy() if columnas else actividades_usuario.copy()
        vista = vista.rename(
            columns={
                "codigo": "Código",
                "nombre": "Agrupación",
                "tipo_venta": "Tipo fiscal/contable",
                "tratamiento_iva": "Tratamiento IVA",
                "activo": "Activa",
                "descripcion": "Descripción",
            }
        )
        st.dataframe(vista, use_container_width=True, hide_index=True)

    with st.expander("Editar / activar / desactivar agrupación", expanded=False):
        opciones = _opciones_actividades(actividades_usuario)
        if not opciones:
            st.info("No hay agrupaciones para editar.")
            return

        etiqueta = st.selectbox(
            "Agrupación a editar",
            options=list(opciones.keys()),
            key=f"venta_agrupacion_editar_sel_{empresa_id}",
        )
        actividad_id = opciones[etiqueta]
        fila = actividades_usuario[actividades_usuario["id"].astype(int) == int(actividad_id)].iloc[0].to_dict()

        tipo_labels = _labels_tipo()
        tratamiento_labels = _labels_tratamiento()

        col1, col2 = st.columns(2)
        nuevo_codigo = col1.text_input(
            "Código",
            value=str(fila.get("codigo", "")),
            key=f"venta_agrupacion_editar_codigo_{empresa_id}_{actividad_id}",
        )
        nuevo_nombre = col2.text_input(
            "Agrupación",
            value=str(fila.get("nombre", "")),
            key=f"venta_agrupacion_editar_nombre_{empresa_id}_{actividad_id}",
        )

        col3, col4 = st.columns(2)
        tipo_actual = _label_actual(tipo_labels, str(fila.get("tipo_venta", "")))
        tratamiento_actual = _label_actual(tratamiento_labels, str(fila.get("tratamiento_iva", "")))

        nuevo_tipo_label = col3.selectbox(
            "Tipo fiscal/contable base",
            options=list(tipo_labels.keys()),
            index=list(tipo_labels.keys()).index(tipo_actual),
            key=f"venta_agrupacion_editar_tipo_{empresa_id}_{actividad_id}",
        )
        nuevo_trat_label = col4.selectbox(
            "Tratamiento IVA",
            options=list(tratamiento_labels.keys()),
            index=list(tratamiento_labels.keys()).index(tratamiento_actual),
            key=f"venta_agrupacion_editar_trat_{empresa_id}_{actividad_id}",
        )

        nueva_descripcion = st.text_area(
            "Descripción / criterio de uso",
            value=str(fila.get("descripcion", "") or ""),
            key=f"venta_agrupacion_editar_desc_{empresa_id}_{actividad_id}",
        )

        st.caption(
            "Cambiar código o nombre actualiza el reporte de las ventas asociadas. "
            "Cambiar tipo fiscal/tratamiento IVA puede afectar propuestas futuras; si hay propuestas ya generadas, "
            "el sistema bloquea solo esos comprobantes puntuales."
        )

        col_btn1, col_btn2, col_btn3 = st.columns(3)

        with col_btn1:
            if st.button(
                "Guardar cambios",
                type="primary",
                use_container_width=True,
                key=f"venta_agrupacion_editar_guardar_{empresa_id}_{actividad_id}",
            ):
                try:
                    resultado = editar_agrupacion_venta(
                        empresa_id=empresa_id,
                        actividad_id=actividad_id,
                        codigo=nuevo_codigo,
                        nombre=nuevo_nombre,
                        tipo_venta=tipo_labels[nuevo_tipo_label],
                        tratamiento_iva=tratamiento_labels[nuevo_trat_label],
                        descripcion=nueva_descripcion,
                        usuario=usuario,
                    )
                    _mostrar_resultado_operacion(resultado)
                    if resultado.get("ok"):
                        _rerun()
                except Exception as exc:
                    st.error(f"No se pudo editar la agrupación: {exc}")

        activo = int(fila.get("activo", 1) or 0) == 1

        with col_btn2:
            if activo and st.button(
                "Desactivar",
                use_container_width=True,
                key=f"venta_agrupacion_desactivar_{empresa_id}_{actividad_id}",
            ):
                resultado = desactivar_agrupacion_venta(
                    empresa_id=empresa_id,
                    actividad_id=actividad_id,
                    usuario=usuario,
                )
                _mostrar_resultado_operacion(resultado)
                _rerun()

        with col_btn3:
            if not activo and st.button(
                "Reactivar",
                use_container_width=True,
                key=f"venta_agrupacion_reactivar_{empresa_id}_{actividad_id}",
            ):
                resultado = reactivar_agrupacion_venta(
                    empresa_id=empresa_id,
                    actividad_id=actividad_id,
                    usuario=usuario,
                )
                _mostrar_resultado_operacion(resultado)
                _rerun()


def _mostrar_asignacion_pendientes(
    empresa_id: int,
    usuario: str,
    actividades_activas: pd.DataFrame,
) -> None:
    actividades_usuario_activas = _solo_agrupaciones_usuario(actividades_activas)
    archivos = ["Todas las ventas sin agrupación"] + listar_archivos_ventas_importadas(empresa_id=empresa_id)
    archivo_opcion = st.selectbox(
        "Alcance para asignar agrupación",
        options=archivos,
        key=f"venta_agrupacion_archivo_{empresa_id}",
    )
    archivo = "" if archivo_opcion == "Todas las ventas sin agrupación" else archivo_opcion

    try:
        pendientes = listar_ventas_sin_actividad(
            empresa_id=empresa_id,
            archivo=archivo or None,
        )
    except Exception as exc:
        st.error(f"No se pudieron leer ventas sin agrupación: {exc}")
        return

    with st.expander("Asignar agrupación a ventas sin agrupación", expanded=not pendientes.empty):
        if pendientes.empty:
            st.success("No hay ventas pendientes de agrupación para el alcance seleccionado.")
            return

        st.warning(
            "Antes de generar asientos de Ventas, asigne una agrupación interna. "
            "La agrupación ayuda a reportar ventas/IVA por actividad comercial del usuario."
        )

        columnas = _columnas_ventas(pendientes)
        st.dataframe(pendientes[columnas] if columnas else pendientes, use_container_width=True, hide_index=True)

        if actividades_usuario_activas.empty:
            st.info("Primero cree una agrupación comercial propia para poder asignarla.")
            return

        opciones = _opciones_actividades(actividades_usuario_activas)
        actividad_label = st.selectbox(
            "Agrupación a asignar",
            options=list(opciones.keys()),
            key=f"venta_agrupacion_asignar_{empresa_id}",
        )
        actividad_id = opciones[actividad_label]

        modo = st.radio(
            "Ventas a actualizar",
            options=["Todas las pendientes del alcance", "Seleccionar por ID"],
            horizontal=True,
            key=f"venta_agrupacion_modo_{empresa_id}",
        )

        ids_seleccionados: list[int] = []
        if modo == "Seleccionar por ID":
            ids_disponibles = [int(v) for v in pendientes["id"].tolist()]
            ids_seleccionados = st.multiselect(
                "IDs de ventas",
                options=ids_disponibles,
                key=f"venta_agrupacion_ids_{empresa_id}",
            )
            if not ids_seleccionados:
                st.info("Seleccione al menos una venta.")
                return

        confirmar = st.checkbox(
            "Confirmo que esta agrupación corresponde a las ventas seleccionadas",
            key=f"venta_agrupacion_confirmar_{empresa_id}",
        )
        if not confirmar:
            st.info("Marque la confirmación para habilitar la asignación.")
            return

        if st.button(
            "Asignar agrupación a ventas",
            type="primary",
            use_container_width=True,
            key=f"venta_agrupacion_aplicar_{empresa_id}",
        ):
            try:
                if modo == "Seleccionar por ID":
                    resultado = asignar_actividad_a_ventas(
                        empresa_id=empresa_id,
                        venta_ids=ids_seleccionados,
                        actividad_id=actividad_id,
                        usuario=usuario,
                    )
                else:
                    resultado = asignar_actividad_a_ventas_pendientes(
                        empresa_id=empresa_id,
                        actividad_id=actividad_id,
                        archivo=archivo or None,
                        usuario=usuario,
                    )
            except Exception as exc:
                st.error(f"No se pudo asignar la agrupación: {exc}")
                return

            _mostrar_resultado_operacion(resultado)
            if resultado.get("ok"):
                _rerun()


def _mostrar_correccion_asignaciones(
    empresa_id: int,
    usuario: str,
    actividades_todas: pd.DataFrame,
    actividades_activas: pd.DataFrame,
) -> None:
    actividades_usuario_todas = _solo_agrupaciones_usuario(actividades_todas)
    actividades_usuario_activas = _solo_agrupaciones_usuario(actividades_activas)

    with st.expander("Corregir asignaciones por comprobante", expanded=False):
        st.caption(
            "Use esta sección si el usuario agrupó mal uno o varios comprobantes. "
            "La corrección es por venta seleccionada; no afecta toda la importación salvo que usted seleccione masivamente ese alcance."
        )

        col1, col2, col3 = st.columns([1.4, 1.4, 2])

        opciones_filtro = {"Todas": None, "Sin agrupación": 0}
        opciones_filtro.update(_opciones_actividades(actividades_usuario_todas))

        filtro_label = col1.selectbox(
            "Agrupación actual",
            options=list(opciones_filtro.keys()),
            key=f"venta_agrupacion_correccion_filtro_{empresa_id}",
        )
        filtro_id = opciones_filtro[filtro_label]

        archivos = ["Todos"] + listar_archivos_ventas_importadas(empresa_id=empresa_id)
        archivo_label = col2.selectbox(
            "Archivo",
            options=archivos,
            key=f"venta_agrupacion_correccion_archivo_{empresa_id}",
        )
        archivo = "" if archivo_label == "Todos" else archivo_label

        busqueda = col3.text_input(
            "Buscar cliente, CUIT, comprobante o archivo",
            key=f"venta_agrupacion_correccion_busqueda_{empresa_id}",
        )

        try:
            ventas = listar_ventas_por_agrupacion(
                empresa_id=empresa_id,
                actividad_id=filtro_id,
                archivo=archivo or None,
                busqueda=busqueda,
                incluir_sin_agrupacion=True,
            )
        except Exception as exc:
            st.error(f"No se pudieron listar ventas para corregir: {exc}")
            return

        if ventas.empty:
            st.info("No hay ventas para los filtros seleccionados.")
            return

        st.caption(
            "Seleccione comprobantes desde la grilla. "
            "La pantalla no muestra chips por ID para evitar sobrecarga visual en importaciones grandes."
        )

        editor_base = _preparar_editor_seleccion_ventas(ventas)
        columnas_bloqueadas = [col for col in editor_base.columns if col != "Seleccionar"]

        editor = st.data_editor(
            editor_base,
            use_container_width=True,
            hide_index=True,
            height=320,
            disabled=columnas_bloqueadas,
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn(
                    "Seleccionar",
                    help="Marque solo los comprobantes que desea corregir.",
                    default=False,
                )
            },
            key=f"venta_agrupacion_correccion_editor_{empresa_id}",
        )

        ids_seleccionados = _ids_seleccionados_editor(editor)

        if not ids_seleccionados:
            st.info("Seleccione uno o más comprobantes desde la grilla para corregir.")
            return

        st.caption(f"Comprobantes seleccionados para corregir: {len(ids_seleccionados)}")

        seleccionadas = ventas[ventas["id"].astype(int).isin(ids_seleccionados)].copy()
        bloqueadas = seleccionadas[
            seleccionadas.get("tiene_asiento_propuesto", False).astype(bool)
        ] if "tiene_asiento_propuesto" in seleccionadas.columns else pd.DataFrame()

        if not bloqueadas.empty:
            st.warning(
                "Algunas ventas seleccionadas tienen propuesta contable en Bandeja. "
                "El sistema bloqueará solo esos comprobantes puntuales; las demás ventas seleccionadas pueden corregirse."
            )
            st.dataframe(
                bloqueadas[_columnas_ventas(bloqueadas)],
                use_container_width=True,
                hide_index=True,
            )

        accion = st.radio(
            "Acción",
            options=["Reasignar a otra agrupación", "Dejar sin agrupación"],
            horizontal=True,
            key=f"venta_agrupacion_correccion_accion_{empresa_id}",
        )

        actividad_destino_id: int | None = None
        if accion == "Reasignar a otra agrupación":
            if actividades_usuario_activas.empty:
                st.info("No hay agrupaciones comerciales activas disponibles para reasignar.")
                return
            opciones_destino = _opciones_actividades(actividades_usuario_activas)
            destino_label = st.selectbox(
                "Nueva agrupación",
                options=list(opciones_destino.keys()),
                key=f"venta_agrupacion_correccion_destino_{empresa_id}",
            )
            actividad_destino_id = opciones_destino[destino_label]

        confirmar = st.checkbox(
            "Confirmo la corrección de los comprobantes seleccionados",
            key=f"venta_agrupacion_correccion_confirmar_{empresa_id}",
        )
        if not confirmar:
            st.info("Marque la confirmación para habilitar la corrección.")
            return

        if st.button(
            "Aplicar corrección",
            type="primary",
            use_container_width=True,
            key=f"venta_agrupacion_correccion_aplicar_{empresa_id}",
        ):
            try:
                if accion == "Reasignar a otra agrupación":
                    resultado = reasignar_agrupacion_ventas(
                        empresa_id=empresa_id,
                        venta_ids=ids_seleccionados,
                        actividad_id=int(actividad_destino_id),
                        usuario=usuario,
                    )
                else:
                    resultado = desasignar_agrupacion_ventas(
                        empresa_id=empresa_id,
                        venta_ids=ids_seleccionados,
                        usuario=usuario,
                    )
            except Exception as exc:
                st.error(f"No se pudo corregir la asignación: {exc}")
                return

            _mostrar_resultado_operacion(resultado)
            if resultado.get("ventas_actualizadas", 0) > 0:
                _rerun()


def mostrar_actividades_ventas_ui(
    empresa_id: int | None = None,
    usuario: str | None = None,
) -> None:
    empresa_id_final = _empresa_id_actual(empresa_id)
    usuario_final = _usuario_actual(usuario)

    st.divider()
    st.subheader("🏷️ Agrupaciones internas de venta")

    st.caption(
        "Estas agrupaciones las crea el usuario para identificar sus ventas y luego analizarlas en reportes de Ventas/IVA. "
        "No son cuentas contables y no obligan a crear una cuenta por cada agrupación."
    )

    try:
        resumen = obtener_resumen_actividades_ventas(empresa_id=empresa_id_final)
        actividades_activas = listar_actividades_venta(empresa_id=empresa_id_final, solo_activas=True)
        actividades_todas = listar_actividades_venta(empresa_id=empresa_id_final, solo_activas=False)
    except Exception as exc:
        st.error(f"No se pudieron cargar agrupaciones de venta: {exc}")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Ventas cargadas", resumen.get("total", 0))
    col2.metric("Con agrupación", resumen.get("con_actividad", 0))
    col3.metric("Sin agrupación", resumen.get("sin_actividad", 0))

    _mostrar_resumen_por_agrupacion(empresa_id_final)
    _mostrar_crear_agrupacion(empresa_id_final, usuario_final, actividades_activas.empty)
    _mostrar_gestion_agrupaciones(empresa_id_final, usuario_final, actividades_todas)
    _mostrar_asignacion_pendientes(empresa_id_final, usuario_final, actividades_activas)
    _mostrar_correccion_asignaciones(empresa_id_final, usuario_final, actividades_todas, actividades_activas)