from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.exportadores import exportar_excel
from core.ui import preparar_vista
from services.comportamientos_contables_service import (
    aplicar_sugerencias_comportamientos,
    desactivar_comportamiento_cuenta,
    guardar_comportamiento_cuenta,
    listar_catalogo_comportamientos,
    listar_cuentas_plan,
    listar_eventos_comportamientos,
    listar_mapeos_comportamientos,
    listar_sugerencias_comportamientos,
    migrar_configuracion_comportamientos,
    obtener_resumen_configuracion_comportamientos,
)


COLUMNAS_CUENTAS = [
    "codigo_cuenta",
    "nombre_cuenta",
    "comportamientos_texto",
    "imputable",
    "requiere_auxiliar",
    "permite_imputacion_operativa",
]

COLUMNAS_MAPEOS = [
    "id",
    "codigo_cuenta",
    "cuenta_nombre",
    "comportamiento",
    "comportamiento_nombre",
    "naturaleza",
    "origen",
    "observaciones",
    "creado_en",
]

COLUMNAS_SUGERENCIAS = [
    "codigo_cuenta",
    "nombre_cuenta",
    "comportamiento",
    "comportamiento_nombre",
    "confianza",
    "motivo",
]


def _df(filas: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(filas or [])


def _cuentas_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_CUENTAS)
    for columna in COLUMNAS_CUENTAS:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_CUENTAS].copy()


def _mapeos_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_MAPEOS)
    for columna in COLUMNAS_MAPEOS:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_MAPEOS].copy()


def _sugerencias_dataframe(filas: list[dict[str, Any]]) -> pd.DataFrame:
    df = _df(filas)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_SUGERENCIAS)
    for columna in COLUMNAS_SUGERENCIAS:
        if columna not in df.columns:
            df[columna] = ""
    return df[COLUMNAS_SUGERENCIAS].copy()


def _vista_cuentas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Código", "Cuenta", "Comportamiento", "Imputable", "Auxiliar", "Imputación operativa"])
    vista = df.rename(
        columns={
            "codigo_cuenta": "Código",
            "nombre_cuenta": "Cuenta",
            "comportamientos_texto": "Comportamiento",
            "imputable": "Imputable",
            "requiere_auxiliar": "Auxiliar",
            "permite_imputacion_operativa": "Imputación operativa",
        }
    )
    return preparar_vista(vista)


def _vista_mapeos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["ID", "Código", "Cuenta", "Comportamiento", "Nombre", "Naturaleza", "Origen", "Observaciones"])
    vista = df.rename(
        columns={
            "id": "ID",
            "codigo_cuenta": "Código",
            "cuenta_nombre": "Cuenta",
            "comportamiento": "Comportamiento",
            "comportamiento_nombre": "Nombre",
            "naturaleza": "Naturaleza",
            "origen": "Origen",
            "observaciones": "Observaciones",
            "creado_en": "Creado",
        }
    )
    return preparar_vista(vista)


def _vista_sugerencias(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Código", "Cuenta", "Comportamiento", "Nombre", "Confianza", "Motivo"])
    vista = df.rename(
        columns={
            "codigo_cuenta": "Código",
            "nombre_cuenta": "Cuenta",
            "comportamiento": "Comportamiento",
            "comportamiento_nombre": "Nombre",
            "confianza": "Confianza",
            "motivo": "Motivo",
        }
    )
    return preparar_vista(vista)


def _opcion_cuenta(cuenta: dict[str, Any]) -> str:
    codigo = str(cuenta.get("codigo_cuenta") or "").strip()
    nombre = str(cuenta.get("nombre_cuenta") or "").strip()
    comportamiento = str(cuenta.get("comportamientos_texto") or "Sin comportamiento").strip()
    return f"{codigo} — {nombre} ({comportamiento})"


def _opcion_comportamiento(item: dict[str, Any]) -> str:
    return f"{item['codigo']} — {item['nombre']}"


def _codigo_desde_opcion(opcion: str) -> str:
    return str(opcion or "").split("—", 1)[0].strip()


def _render_resumen(resumen: dict[str, Any]) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Cuentas", resumen.get("total_cuentas", 0))
    c2.metric("Con comportamiento", resumen.get("cuentas_con_mapeo", 0))
    c3.metric("Sin comportamiento", resumen.get("cuentas_sin_mapeo", 0))
    c4.metric("Críticos cubiertos", f"{resumen.get('criticos_cubiertos', 0)}/{resumen.get('criticos_total', 0)}")
    c5.metric("Mapeos activos", resumen.get("mapeos_activos", 0))

    faltantes = resumen.get("criticos_faltantes") or []
    if faltantes:
        st.warning(
            "Faltan comportamientos críticos por mapear: " + ", ".join(faltantes) + ". "
            "Esto no bloquea la operatoria actual, pero limita la coherencia contable automática."
        )
    else:
        st.success("Los comportamientos críticos del núcleo están cubiertos para esta empresa.")


def _render_mapa_actual(empresa_id: int | None, usuario: str | None, key_prefix: str) -> None:
    st.markdown("### Mapa actual del plan de cuentas")
    st.caption("Esta vista muestra qué cuentas ya tienen una función contable operativa reconocible por el sistema.")

    filtro = st.text_input("Buscar cuenta", key=f"{key_prefix}_filtro_cuentas")
    cuentas = listar_cuentas_plan(empresa_id=empresa_id, filtro=filtro)
    df_cuentas = _cuentas_dataframe(cuentas)

    col1, col2 = st.columns([2, 1])
    with col1:
        solo_sin_mapeo = st.checkbox("Mostrar solo cuentas sin comportamiento", value=False, key=f"{key_prefix}_solo_sin_mapeo")
    with col2:
        st.caption("Usá esta lista para detectar cuentas que todavía necesitan mapeo.")

    if solo_sin_mapeo and not df_cuentas.empty:
        df_cuentas = df_cuentas[df_cuentas["comportamientos_texto"].fillna("").eq("")]

    if df_cuentas.empty:
        st.info("No se encontraron cuentas para los filtros actuales.")
    else:
        st.dataframe(_vista_cuentas(df_cuentas), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Comportamientos activos")
    mapeos = listar_mapeos_comportamientos(empresa_id=empresa_id)
    df_mapeos = _mapeos_dataframe(mapeos)
    if df_mapeos.empty:
        st.info("Todavía no hay comportamientos configurados para esta empresa.")
        return

    comportamientos = sorted(df_mapeos["comportamiento"].dropna().unique().tolist())
    seleccion = st.multiselect(
        "Filtrar por comportamiento",
        options=comportamientos,
        default=comportamientos,
        key=f"{key_prefix}_filtro_mapeos",
    )
    if seleccion:
        df_mapeos = df_mapeos[df_mapeos["comportamiento"].isin(seleccion)]
    st.dataframe(_vista_mapeos(df_mapeos), use_container_width=True, hide_index=True)

    with st.expander("Desactivar un comportamiento configurado", expanded=False):
        opciones = [f"{int(row['id'])} — {row['codigo_cuenta']} — {row['comportamiento']}" for _, row in df_mapeos.iterrows()]
        if not opciones:
            st.info("No hay comportamientos visibles para desactivar.")
            return
        opcion = st.selectbox("Comportamiento a desactivar", options=opciones, key=f"{key_prefix}_desactivar_opcion")
        motivo = st.text_area("Motivo", key=f"{key_prefix}_desactivar_motivo")
        if st.button("Desactivar comportamiento", key=f"{key_prefix}_desactivar_btn", use_container_width=True):
            mapeo_id = int(_codigo_desde_opcion(opcion))
            resultado = desactivar_comportamiento_cuenta(
                empresa_id=empresa_id,
                mapeo_id=mapeo_id,
                usuario=usuario,
                motivo=motivo or "Baja manual desde configuración contable.",
            )
            if resultado.get("ok"):
                st.success(resultado.get("mensaje"))
                st.rerun()
            else:
                st.error(resultado.get("mensaje"))


def _render_asignacion_manual(empresa_id: int | None, usuario: str | None, key_prefix: str) -> None:
    st.markdown("### Asignar comportamiento a una cuenta")
    st.caption(
        "Una cuenta puede tener más de un comportamiento cuando sea necesario, pero conviene mantenerlo simple. "
        "Ejemplo: una cuenta bancaria debe marcarse como BANCO; una caja chica como CAJA."
    )

    cuentas = listar_cuentas_plan(empresa_id=empresa_id)
    if not cuentas:
        st.warning("No hay plan de cuentas disponible para configurar.")
        return

    catalogo = listar_catalogo_comportamientos()
    opciones_cuentas = [_opcion_cuenta(cuenta) for cuenta in cuentas]
    opciones_comportamientos = [_opcion_comportamiento(item) for item in catalogo]

    cuenta_opcion = st.selectbox("Cuenta", options=opciones_cuentas, key=f"{key_prefix}_cuenta_manual")
    comportamiento_opcion = st.selectbox("Comportamiento", options=opciones_comportamientos, key=f"{key_prefix}_comportamiento_manual")
    observaciones = st.text_area(
        "Observaciones",
        value="",
        key=f"{key_prefix}_observaciones_manual",
        placeholder="Ejemplo: cuenta bancaria principal del Banco Nación.",
    )

    codigo_cuenta = _codigo_desde_opcion(cuenta_opcion)
    comportamiento = _codigo_desde_opcion(comportamiento_opcion)

    if comportamiento:
        elegido = next((item for item in catalogo if item["codigo"] == comportamiento), None)
        if elegido:
            st.info(f"{elegido['nombre']} · Naturaleza: {elegido['naturaleza']} · {elegido['descripcion']}")

    if st.button("Guardar comportamiento", type="primary", use_container_width=True, key=f"{key_prefix}_guardar_manual"):
        resultado = guardar_comportamiento_cuenta(
            empresa_id=empresa_id,
            codigo_cuenta=codigo_cuenta,
            comportamiento=comportamiento,
            usuario=usuario,
            observaciones=observaciones,
            origen="MANUAL",
        )
        if resultado.get("ok"):
            st.success(resultado.get("mensaje"))
            st.rerun()
        else:
            st.error(resultado.get("mensaje"))


def _render_sugerencias(empresa_id: int | None, usuario: str | None, key_prefix: str) -> None:
    st.markdown("### Sugerencias automáticas")
    st.caption(
        "El sistema propone comportamientos por nombre/código de cuenta. "
        "La aplicación siempre requiere confirmación del usuario."
    )

    incluir_ya = st.checkbox("Mostrar también cuentas ya mapeadas", value=False, key=f"{key_prefix}_sug_incluir_ya")
    sugerencias = listar_sugerencias_comportamientos(empresa_id=empresa_id, incluir_ya_mapeadas=incluir_ya)
    df_sugerencias = _sugerencias_dataframe(sugerencias)
    if df_sugerencias.empty:
        st.success("No hay sugerencias pendientes para aplicar.")
        return

    st.dataframe(_vista_sugerencias(df_sugerencias), use_container_width=True, hide_index=True)

    opciones = [
        f"{fila['codigo_cuenta']} — {fila['nombre_cuenta']} — {fila['comportamiento']}"
        for _, fila in df_sugerencias.iterrows()
    ]
    seleccionadas = st.multiselect(
        "Sugerencias a aplicar",
        options=opciones,
        key=f"{key_prefix}_sugerencias_seleccionadas",
    )
    if not seleccionadas:
        st.info("Seleccioná una o más sugerencias para aplicarlas.")
        return

    seleccion_codigos = {_codigo_desde_opcion(opcion) for opcion in seleccionadas}
    sugerencias_a_aplicar = [s for s in sugerencias if str(s.get("codigo_cuenta")) in seleccion_codigos]

    if st.button("Aplicar sugerencias seleccionadas", type="primary", use_container_width=True, key=f"{key_prefix}_aplicar_sugerencias"):
        resultado = aplicar_sugerencias_comportamientos(
            empresa_id=empresa_id,
            sugerencias=sugerencias_a_aplicar,
            usuario=usuario,
        )
        if resultado.get("ok"):
            st.success(f"Se aplicaron {resultado.get('procesadas', 0)} sugerencia(s).")
            st.rerun()
        else:
            st.warning(f"Procesadas: {resultado.get('procesadas', 0)}. Errores: {resultado.get('errores')}")


def _render_catalogo_y_eventos(empresa_id: int | None, key_prefix: str) -> None:
    tab1, tab2 = st.tabs(["Catálogo", "Eventos"])

    with tab1:
        catalogo = pd.DataFrame(listar_catalogo_comportamientos())
        if catalogo.empty:
            st.info("No hay catálogo de comportamientos disponible.")
        else:
            vista = catalogo.rename(
                columns={
                    "codigo": "Código",
                    "nombre": "Nombre",
                    "naturaleza": "Naturaleza",
                    "descripcion": "Descripción",
                }
            )
            st.dataframe(preparar_vista(vista), use_container_width=True, hide_index=True)

    with tab2:
        eventos = listar_eventos_comportamientos(empresa_id=empresa_id, limite=100)
        df_eventos = pd.DataFrame(eventos)
        if df_eventos.empty:
            st.info("Todavía no hay eventos de configuración.")
        else:
            vista = df_eventos.rename(
                columns={
                    "fecha_evento": "Fecha",
                    "codigo_cuenta": "Cuenta",
                    "comportamiento": "Comportamiento",
                    "evento": "Evento",
                    "detalle": "Detalle",
                    "usuario": "Usuario",
                }
            )
            st.dataframe(preparar_vista(vista), use_container_width=True, hide_index=True)


def _render_descarga_excel(empresa_id: int | None) -> None:
    cuentas = _vista_cuentas(_cuentas_dataframe(listar_cuentas_plan(empresa_id=empresa_id)))
    mapeos = _vista_mapeos(_mapeos_dataframe(listar_mapeos_comportamientos(empresa_id=empresa_id, incluir_inactivos=True)))
    sugerencias = _vista_sugerencias(_sugerencias_dataframe(listar_sugerencias_comportamientos(empresa_id=empresa_id)))
    catalogo = pd.DataFrame(listar_catalogo_comportamientos())

    archivo = exportar_excel(
        {
            "Plan de cuentas": cuentas,
            "Mapeos": mapeos,
            "Sugerencias": sugerencias,
            "Catalogo": catalogo,
        }
    )
    st.download_button(
        "Descargar configuración en Excel",
        data=archivo,
        file_name="configuracion_comportamientos_contables.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def mostrar_configuracion_comportamientos_contables_ui(
    empresa_id: int | None = None,
    usuario: str | None = None,
    key_prefix: str = "comportamientos_contables",
) -> None:
    st.subheader("⚙️ Comportamientos contables del plan de cuentas")
    st.caption(
        "Configuración central para que el sistema entienda qué cuentas representan Caja, Banco, IVA, Capital, "
        "Socios, Sueldos y otros comportamientos críticos. Esta pantalla no genera asientos; solo clasifica cuentas."
    )

    migrar_configuracion_comportamientos()
    resumen = obtener_resumen_configuracion_comportamientos(empresa_id=empresa_id)
    _render_resumen(resumen)

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs([
        "Mapa actual",
        "Asignar manualmente",
        "Sugerencias",
        "Catálogo y auditoría",
    ])

    with tab1:
        _render_mapa_actual(empresa_id, usuario, key_prefix)

    with tab2:
        _render_asignacion_manual(empresa_id, usuario, key_prefix)

    with tab3:
        _render_sugerencias(empresa_id, usuario, key_prefix)

    with tab4:
        _render_catalogo_y_eventos(empresa_id, key_prefix)

    st.divider()
    with st.expander("Exportar configuración", expanded=False):
        _render_descarga_excel(empresa_id)


# Alias corto para mantener la misma convención que otros componentes.
def mostrar_configuracion_comportamientos_contables(
    empresa_id: int | None = None,
    usuario: str | None = None,
    key_prefix: str = "comportamientos_contables",
) -> None:
    mostrar_configuracion_comportamientos_contables_ui(
        empresa_id=empresa_id,
        usuario=usuario,
        key_prefix=key_prefix,
    )