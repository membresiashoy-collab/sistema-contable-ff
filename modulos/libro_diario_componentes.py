from __future__ import annotations

from datetime import date
from typing import Any, Dict

import pandas as pd
import streamlit as st

from core.exportadores import exportar_excel
from core.numeros import moneda
from core.ui import preparar_vista
from services.libro_diario_trazabilidad_service import (
    TIPO_CONTROLADO_BANDEJA,
    TIPO_DIRECTO_HISTORICO,
    TIPO_DIRECTO_TECNICO,
    TIPO_REVERSO_BANDEJA,
    listar_opciones_origen_funcional,
    listar_opciones_tipo_trazabilidad,
    listar_trazabilidad_libro_diario,
    obtener_detalle_asiento_libro_diario,
    obtener_resumen_trazabilidad_libro_diario,
)


# ======================================================
# CONTABILIDAD PRO - COMPONENTE UI TRAZABILIDAD DIARIO
# ======================================================


def _texto(valor: Any) -> str:
    try:
        if valor is None:
            return ""
        if isinstance(valor, float) and pd.isna(valor):
            return ""
        return str(valor).strip()
    except Exception:
        return ""


def _fecha_mostrar(valor: Any) -> str:
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    try:
        fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
        if pd.isna(fecha):
            return str(valor)
        return fecha.strftime("%d/%m/%Y")
    except Exception:
        return str(valor)


def _fecha_iso(valor: Any) -> str:
    if valor is None:
        return ""
    try:
        fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
        if pd.isna(fecha):
            return ""
        return fecha.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _date_input_argentino(*args, **kwargs):
    kwargs.setdefault("format", "DD/MM/YYYY")
    try:
        return st.date_input(*args, **kwargs)
    except TypeError:
        kwargs.pop("format", None)
        return st.date_input(*args, **kwargs)


def _mostrar_metricas_resumen(resumen: Dict[str, Any]) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asientos", resumen.get("total_asientos", 0))
    c2.metric("Controlados por Bandeja", resumen.get("controlados_bandeja", 0))
    c3.metric("Directos / históricos", resumen.get("directos_historicos", 0))
    c4.metric("Reversos", resumen.get("reversos_bandeja", 0))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Líneas", resumen.get("total_lineas", 0))
    c6.metric("Debe", moneda(resumen.get("total_debe", 0)))
    c7.metric("Haber", moneda(resumen.get("total_haber", 0)))
    c8.metric("Descuadrados", resumen.get("descuadrados", 0))

    diferencia = round(float(resumen.get("diferencia") or 0), 2)
    if diferencia == 0:
        st.success("El Libro Diario está cuadrado para la empresa actual.")
    else:
        st.error(f"El Libro Diario tiene diferencia global: {moneda(diferencia)}")


def _preparar_vista_trazabilidad(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    columnas = [
        "id_asiento",
        "fecha",
        "tipo_trazabilidad",
        "estado_trazabilidad",
        "origen_funcional",
        "origen_tecnico",
        "archivo",
        "comprobante_clave",
        "fuente_clave",
        "propuesta_estado",
        "lote_id",
        "movimientos",
        "cuentas",
        "debe",
        "haber",
        "diferencia",
        "alerta",
    ]
    columnas = [col for col in columnas if col in df.columns]

    vista = df[columnas].copy()

    if "fecha" in vista.columns:
        vista["fecha"] = vista["fecha"].apply(_fecha_mostrar)

    vista = vista.rename(columns={
        "id_asiento": "Asiento",
        "fecha": "Fecha",
        "tipo_trazabilidad": "Tipo de trazabilidad",
        "estado_trazabilidad": "Estado control",
        "origen_funcional": "Origen funcional",
        "origen_tecnico": "Origen técnico",
        "archivo": "Archivo",
        "comprobante_clave": "Clave comprobante",
        "fuente_clave": "Propuesta vinculada",
        "propuesta_estado": "Estado propuesta",
        "lote_id": "Lote",
        "movimientos": "Líneas",
        "cuentas": "Cuentas",
        "debe": "Debe",
        "haber": "Haber",
        "diferencia": "Diferencia",
        "alerta": "Observación",
    })

    return vista


def _preparar_detalle_lineas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    columnas = [
        "id",
        "id_asiento",
        "fecha",
        "cuenta",
        "debe",
        "haber",
        "glosa",
        "origen",
        "origen_tabla",
        "origen_id",
        "comprobante_clave",
        "archivo",
        "estado",
    ]
    columnas = [col for col in columnas if col in df.columns]

    vista = df[columnas].copy()

    if "fecha" in vista.columns:
        vista["fecha"] = vista["fecha"].apply(_fecha_mostrar)

    vista = vista.rename(columns={
        "id": "ID línea",
        "id_asiento": "Asiento",
        "fecha": "Fecha",
        "cuenta": "Cuenta",
        "debe": "Debe",
        "haber": "Haber",
        "glosa": "Glosa",
        "origen": "Origen",
        "origen_tabla": "Tabla origen",
        "origen_id": "ID origen",
        "comprobante_clave": "Clave comprobante",
        "archivo": "Archivo",
        "estado": "Estado",
    })

    return vista


def _mostrar_guia_trazabilidad() -> None:
    with st.expander("Cómo leer esta pantalla", expanded=False):
        st.markdown(
            """
Esta vista no reemplaza al Libro Diario ni a la Bandeja de asientos. Sirve para auditar el origen de lo que ya está contabilizado.

- **Controlado por Bandeja**: el asiento pasó por revisión previa y quedó vinculado a una propuesta.
- **Reverso de Bandeja**: el asiento es la reversión controlada de una propuesta contabilizada.
- **Directo con trazabilidad técnica**: el asiento no pasó por Bandeja, pero conserva origen técnico, comprobante o tabla de origen.
- **Directo / histórico**: asiento registrado en Libro Diario sin vínculo de Bandeja ni origen técnico suficiente.

En etapas futuras, Ventas, Compras, Cobranzas, Pagos, Banco y Caja deberían migrar gradualmente hacia la Bandeja para evitar escrituras directas al Libro Diario.
"""
        )


def _mostrar_detalle_asiento(empresa_id: int, id_asiento: int) -> None:
    detalle = obtener_detalle_asiento_libro_diario(
        empresa_id=empresa_id,
        id_asiento=id_asiento,
    )

    if not detalle.get("ok"):
        st.error(detalle.get("mensaje", "No se encontró el asiento."))
        return

    resumen = detalle.get("resumen") or {}
    lineas = detalle.get("detalle")
    eventos = detalle.get("eventos")

    st.markdown("### Detalle del asiento seleccionado")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asiento", resumen.get("id_asiento", id_asiento))
    c2.metric("Tipo", resumen.get("tipo_trazabilidad", ""))
    c3.metric("Debe", moneda(resumen.get("debe", 0)))
    c4.metric("Haber", moneda(resumen.get("haber", 0)))

    diferencia = round(float(resumen.get("diferencia") or 0), 2)
    if diferencia == 0:
        st.success("El asiento seleccionado está cuadrado.")
    else:
        st.error(f"El asiento seleccionado está descuadrado por {moneda(diferencia)}.")

    info1, info2, info3 = st.columns(3)
    info1.caption("Origen funcional")
    info1.write(resumen.get("origen_funcional") or "Sin origen funcional")
    info2.caption("Propuesta vinculada")
    info2.write(resumen.get("fuente_clave") or "Sin propuesta vinculada")
    info3.caption("Lote")
    info3.write(resumen.get("lote_id") or "Sin lote")

    if resumen.get("alerta"):
        st.warning(str(resumen.get("alerta")))

    st.markdown("#### Líneas del Libro Diario")
    if isinstance(lineas, pd.DataFrame) and not lineas.empty:
        st.dataframe(
            preparar_vista(_preparar_detalle_lineas(lineas)),
            use_container_width=True,
        )
    else:
        st.info("El asiento no tiene líneas para mostrar.")

    with st.expander("Información de Bandeja / propuesta vinculada", expanded=bool(resumen.get("fuente_clave"))):
        if not resumen.get("fuente_clave"):
            st.info("Este asiento no tiene propuesta de Bandeja vinculada.")
        else:
            datos = pd.DataFrame([{
                "Fuente": resumen.get("fuente_propuesta"),
                "Clave": resumen.get("fuente_clave"),
                "Estado propuesta": resumen.get("propuesta_estado"),
                "Tipo asiento": resumen.get("propuesta_tipo_asiento"),
                "Descripción": resumen.get("propuesta_descripcion"),
                "Referencia": resumen.get("propuesta_referencia"),
                "Lote": resumen.get("lote_id"),
                "Acción lote": resumen.get("lote_accion"),
                "Estado lote": resumen.get("lote_estado"),
                "Fecha lote": _fecha_mostrar(resumen.get("lote_fecha")),
                "Usuario lote": resumen.get("lote_usuario"),
                "Asiento referenciado": resumen.get("id_asiento_referenciado"),
            }])
            st.dataframe(preparar_vista(datos), use_container_width=True)

    with st.expander("Eventos de Bandeja", expanded=False):
        if isinstance(eventos, pd.DataFrame) and not eventos.empty:
            eventos_vista = eventos.copy()
            if "fecha_evento" in eventos_vista.columns:
                eventos_vista["fecha_evento"] = eventos_vista["fecha_evento"].apply(_fecha_mostrar)
            st.dataframe(preparar_vista(eventos_vista), use_container_width=True)
        else:
            st.info("Sin eventos de Bandeja para este asiento.")


def mostrar_trazabilidad_libro_diario_ui(
    empresa_id: int = 1,
    usuario: str | None = None,
    key_prefix: str = "trazabilidad_libro_diario",
) -> None:
    st.subheader("🔎 Trazabilidad del Libro Diario")
    st.caption(
        "Control para entender de dónde viene cada asiento definitivo: histórico/directo, "
        "pasado desde Bandeja, lote, propuesta vinculada y reversos."
    )

    _mostrar_guia_trazabilidad()

    resumen = obtener_resumen_trazabilidad_libro_diario(empresa_id=empresa_id)
    _mostrar_metricas_resumen(resumen)

    st.divider()

    st.markdown("### Filtros")

    opciones_origen = ["Todos"] + listar_opciones_origen_funcional(empresa_id=empresa_id)
    opciones_tipo = ["Todos"] + listar_opciones_tipo_trazabilidad(empresa_id=empresa_id)

    col1, col2, col3, col4 = st.columns([1.1, 1.1, 1.2, 1.3])

    with col1:
        usar_fechas = st.checkbox(
            "Filtrar por fechas",
            value=False,
            key=f"{key_prefix}_usar_fechas",
        )

    fecha_desde = None
    fecha_hasta = None

    with col2:
        if usar_fechas:
            fecha_desde = _date_input_argentino(
                "Desde",
                value=date(date.today().year, 1, 1),
                key=f"{key_prefix}_fecha_desde",
            )
        else:
            st.caption("Sin fecha desde")

    with col3:
        if usar_fechas:
            fecha_hasta = _date_input_argentino(
                "Hasta",
                value=date.today(),
                key=f"{key_prefix}_fecha_hasta",
            )
        else:
            st.caption("Sin fecha hasta")

    with col4:
        solo_descuadrados = st.checkbox(
            "Solo descuadrados",
            value=False,
            key=f"{key_prefix}_solo_descuadrados",
        )

    col5, col6, col7 = st.columns([1.2, 1.3, 1.6])

    with col5:
        origen = st.selectbox(
            "Origen funcional",
            opciones_origen,
            key=f"{key_prefix}_origen_funcional",
        )

    with col6:
        tipo = st.selectbox(
            "Tipo de trazabilidad",
            opciones_tipo,
            key=f"{key_prefix}_tipo_trazabilidad",
        )

    with col7:
        busqueda = st.text_input(
            "Buscar",
            key=f"{key_prefix}_busqueda",
            placeholder="Asiento, glosa, archivo, comprobante, propuesta...",
        )

    df = listar_trazabilidad_libro_diario(
        empresa_id=empresa_id,
        fecha_desde=fecha_desde if usar_fechas else None,
        fecha_hasta=fecha_hasta if usar_fechas else None,
        origen_funcional=None if origen == "Todos" else origen,
        tipo_trazabilidad=None if tipo == "Todos" else tipo,
        solo_descuadrados=solo_descuadrados,
        busqueda=busqueda,
    )

    st.divider()

    if df.empty:
        st.info("No hay asientos con los filtros seleccionados.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asientos filtrados", len(df))
    c2.metric("Controlados", int((df["tipo_trazabilidad"] == TIPO_CONTROLADO_BANDEJA).sum()))
    c3.metric("Directos", int(df["tipo_trazabilidad"].isin([TIPO_DIRECTO_HISTORICO, TIPO_DIRECTO_TECNICO]).sum()))
    c4.metric("Descuadrados", int((df["cuadrado"] == False).sum()))

    vista = _preparar_vista_trazabilidad(df)
    st.dataframe(
        preparar_vista(vista),
        use_container_width=True,
    )

    excel = exportar_excel({
        "Trazabilidad Diario": vista,
    })

    st.download_button(
        "Descargar trazabilidad Excel",
        data=excel,
        file_name="trazabilidad_libro_diario.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_descargar_excel",
    )

    st.divider()

    ids = df["id_asiento"].dropna().astype(int).drop_duplicates().tolist()
    if not ids:
        return

    id_asiento = st.selectbox(
        "Ver detalle de asiento",
        ids,
        format_func=lambda x: f"Asiento {x}",
        key=f"{key_prefix}_detalle_id_asiento",
    )

    _mostrar_detalle_asiento(empresa_id=empresa_id, id_asiento=int(id_asiento))