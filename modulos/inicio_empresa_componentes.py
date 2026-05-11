import streamlit as st
import pandas as pd

from services.inicio_empresa_service import (
    documentacion_respaldo_listar,
    etiqueta_tipo_sujeto,
    obtener_estado_onboarding_empresa,
    obtener_perfil_inicio_empresa,
    obtener_requisitos_inicio_empresa,
)


from modulos.inicio_societario_componentes import mostrar_panel_inicio_societario
def _texto(valor, default=""):
    if valor is None:
        return default
    texto = str(valor).strip()
    return texto if texto else default


def _estado_legible(valor):
    return _texto(valor, "PENDIENTE").replace("_", " ").title()


def _preparar_vista_default(df):
    df_vista = df.copy()
    df_vista.index = range(1, len(df_vista) + 1)
    df_vista.index.name = "N°"
    return df_vista


def _contar_requisitos(requisitos):
    pendientes = 0
    bloqueantes = 0
    recomendados = 0

    for requisito in requisitos or []:
        ok = bool(requisito.get("ok"))
        bloqueante = bool(requisito.get("bloqueante", True))
        recomendado = bool(requisito.get("recomendado", False))

        if not ok:
            pendientes += 1
            if bloqueante:
                bloqueantes += 1
            if recomendado or not bloqueante:
                recomendados += 1

    return {
        "pendientes": pendientes,
        "bloqueantes": bloqueantes,
        "recomendados": recomendados,
    }


def _filtrar_requisitos(requisitos, codigos):
    codigos_set = {str(codigo).strip().upper() for codigo in codigos}
    return [
        requisito
        for requisito in requisitos or []
        if str(requisito.get("codigo", "")).strip().upper() in codigos_set
    ]


def _requisitos_a_dataframe(requisitos):
    filas = []
    for requisito in requisitos or []:
        filas.append(
            {
                "Código": requisito.get("codigo", ""),
                "Requisito": requisito.get("nombre", ""),
                "Estado": "OK" if requisito.get("ok") else "Pendiente",
                "Tipo": "Bloqueante" if requisito.get("bloqueante", True) else "Recomendado",
                "Detalle": requisito.get("detalle", ""),
            }
        )
    return pd.DataFrame(filas)


def _mostrar_requisitos(requisitos, preparar_vista, titulo="Requisitos"):
    st.markdown(f"#### {titulo}")

    if not requisitos:
        st.info("No hay requisitos para mostrar en esta sección.")
        return

    df = _requisitos_a_dataframe(requisitos)
    st.dataframe(
        preparar_vista(df),
        use_container_width=True,
        hide_index=False,
    )


def _mostrar_tarjeta_persona_humana(perfil, requisitos, preparar_vista):
    st.success("Inicio simplificado para persona humana.")

    st.caption(
        "No se exige carga de socios, capital social, suscripción ni integración societaria. "
        "El sistema solo controla datos fiscales y operativos mínimos."
    )

    campos_no_aplican = perfil.get("campos_no_aplican") or []
    if campos_no_aplican:
        st.markdown("**No aplica para este tipo de sujeto:**")
        st.write(", ".join(campos_no_aplican))

    requisitos_persona_humana = _filtrar_requisitos(
        requisitos,
        ["DATOS_BASICOS", "TIPO_SUJETO", "INICIO_PERSONA_HUMANA", "DOCUMENTACION_RESPALDO"],
    )
    _mostrar_requisitos(requisitos_persona_humana, preparar_vista, "Checklist de inicio")


def _mostrar_tarjeta_sociedad(perfil, requisitos, preparar_vista):
    st.warning("Inicio societario requerido.")

    st.caption(
        "Para sociedades/personas jurídicas corresponde controlar socios o accionistas, "
        "tipo societario, capital suscripto e integración real. La documentación sigue siendo "
        "opcional/recomendada y no bloquea la creación básica de la empresa."
    )

    requisitos_sociedad = _filtrar_requisitos(
        requisitos,
        [
            "DATOS_BASICOS",
            "TIPO_SUJETO",
            "TIPO_SOCIETARIO",
            "SOCIOS",
            "CAPITAL_SOCIAL",
            "INTEGRACION_PENDIENTE",
            "DOCUMENTACION_RESPALDO",
        ],
    )
    _mostrar_requisitos(requisitos_sociedad, preparar_vista, "Checklist societario")

    st.info(
        "Las integraciones reales de capital deben vincularse desde Tesorería mediante el flujo "
        "ya existente. Esta pantalla no registra movimientos ni toca Banco/Caja."
    )

    mostrar_panel_inicio_societario(perfil=perfil, preparar_vista=preparar_vista)


def _mostrar_tarjeta_otro_ente(perfil, requisitos, preparar_vista):
    st.info("Inicio adaptativo para otro ente.")

    st.caption(
        "No se fuerza el flujo societario estándar. El sistema controla datos mínimos, tipo de sujeto "
        "y documentación opcional. Los requisitos especiales podrán incorporarse como reglas separadas."
    )

    requisitos_otro = _filtrar_requisitos(
        requisitos,
        ["DATOS_BASICOS", "TIPO_SUJETO", "DOCUMENTACION_RESPALDO"],
    )
    _mostrar_requisitos(requisitos_otro, preparar_vista, "Checklist adaptativo")


def _mostrar_tarjeta_tipo_no_definido(requisitos, preparar_vista):
    st.warning("El tipo de sujeto todavía no está definido.")

    st.caption(
        "Primero definí si la empresa corresponde a Persona humana, Persona jurídica/sociedad u Otro ente. "
        "Esa decisión evita exigir socios o capital social cuando no corresponde."
    )

    requisitos_base = _filtrar_requisitos(
        requisitos,
        ["DATOS_BASICOS", "TIPO_SUJETO", "DOCUMENTACION_RESPALDO"],
    )
    _mostrar_requisitos(requisitos_base, preparar_vista, "Checklist mínimo")


def _mostrar_asistente_adaptativo(perfil, requisitos, preparar_vista):
    st.markdown("### Asistente operativo adaptativo")

    if perfil.get("es_persona_humana"):
        _mostrar_tarjeta_persona_humana(perfil, requisitos, preparar_vista)
        return

    if perfil.get("es_sociedad"):
        _mostrar_tarjeta_sociedad(perfil, requisitos, preparar_vista)
        return

    if perfil.get("es_otro_ente"):
        _mostrar_tarjeta_otro_ente(perfil, requisitos, preparar_vista)
        return

    _mostrar_tarjeta_tipo_no_definido(requisitos, preparar_vista)


def _mostrar_documentacion_opcional(documentacion_inicio, preparar_vista):
    with st.expander("Documentación respaldatoria opcional", expanded=False):
        st.caption(
            "La documentación respaldatoria es recomendada para auditoría y control interno, "
            "pero no bloquea la creación ni el inicio operativo básico de la empresa."
        )

        if isinstance(documentacion_inicio, pd.DataFrame) and not documentacion_inicio.empty:
            st.dataframe(
                preparar_vista(documentacion_inicio),
                use_container_width=True,
            )
        else:
            st.info("No hay documentación respaldatoria registrada. Podés continuar operando y cargarla luego.")


def _mostrar_controles_generales(controles, preparar_vista):
    st.markdown("### Controles de preparación")

    if controles is None or controles.empty:
        st.info("No hay controles para mostrar.")
        return

    st.dataframe(
        preparar_vista(controles),
        use_container_width=True,
    )


def _mostrar_recomendaciones(recomendaciones):
    st.markdown("### Recomendaciones")

    if not recomendaciones:
        st.success("No hay recomendaciones pendientes.")
        return

    for recomendacion in recomendaciones:
        st.write(f"- {recomendacion}")


def _mostrar_inicializacion_segura(
    empresa_id,
    inicializar_empresa_operativa,
    crear_backup_sqlite,
    mostrar_pasos_inicializacion,
):
    st.markdown("### Inicialización segura de empresa")

    st.warning(
        "Esta acción completa catálogos y configuraciones base faltantes. "
        "No borra datos, no elimina movimientos, no imputa comprobantes y no concilia bancos."
    )

    incluir_tesoreria = st.checkbox(
        "Incluir inicialización de Tesorería / Banco recomendada",
        value=True,
        help=(
            "Usa servicios existentes para asegurar medios de pago, cuentas bancarias recomendadas "
            "y configuración contable bancaria default cuando corresponda."
        ),
        key="config_estado_empresa_incluir_tesoreria",
    )

    if "confirmar_inicializar_empresa_operativa" not in st.session_state:
        st.session_state["confirmar_inicializar_empresa_operativa"] = False

    if st.button(
        "Inicializar / completar base operativa de esta empresa",
        type="primary",
        use_container_width=True,
        key="btn_inicializar_empresa_operativa",
    ):
        st.session_state["confirmar_inicializar_empresa_operativa"] = True

    if not st.session_state["confirmar_inicializar_empresa_operativa"]:
        return

    st.warning(
        "¿Confirmás inicializar datos base de la empresa activa? "
        "Se creará un backup antes de ejecutar."
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button(
            "Sí, inicializar empresa",
            type="primary",
            use_container_width=True,
            key="confirmar_si_inicializar_empresa",
        ):
            crear_backup_sqlite("antes_inicializar_empresa_operativa")

            resultado = inicializar_empresa_operativa(
                empresa_id=empresa_id,
                incluir_tesoreria=bool(incluir_tesoreria),
            )

            if resultado.get("ok"):
                st.success(resultado.get("mensaje", "Empresa inicializada correctamente."))
            else:
                st.warning(resultado.get("mensaje", "Inicialización parcial. Revisar detalle."))

            mostrar_pasos_inicializacion(resultado.get("pasos", []))

            st.session_state["confirmar_inicializar_empresa_operativa"] = False
            st.rerun()

    with c2:
        if st.button(
            "Cancelar",
            use_container_width=True,
            key="cancelar_inicializar_empresa",
        ):
            st.session_state["confirmar_inicializar_empresa_operativa"] = False
            st.rerun()


def mostrar_estado_empresa_operativa_adaptativo(
    empresa_actual_id,
    obtener_resumen_empresa_operativa,
    preparar_controles_empresa_para_vista,
    obtener_recomendaciones_empresa,
    inicializar_empresa_operativa,
    crear_backup_sqlite,
    preparar_vista=None,
    mostrar_pasos_inicializacion=None,
):
    preparar_vista = preparar_vista or _preparar_vista_default

    if mostrar_pasos_inicializacion is None:
        def mostrar_pasos_inicializacion(pasos):
            for paso in pasos or []:
                st.write(f"- {paso}")

    st.subheader("Estado operativo de la empresa")

    st.info(
        "Esta vista controla si la empresa activa tiene la base mínima para operar. "
        "El asistente adapta los requisitos según el tipo de sujeto y evita exigir flujo societario "
        "cuando no corresponde."
    )

    empresa_id = empresa_actual_id()

    if empresa_id is None:
        st.warning("No hay empresa activa seleccionada. Revisá Seguridad o el selector de empresa.")
        return

    try:
        resumen = obtener_resumen_empresa_operativa(empresa_id)
        controles = preparar_controles_empresa_para_vista(empresa_id)
        recomendaciones = obtener_recomendaciones_empresa(empresa_id)
    except Exception as exc:
        st.error("No se pudo obtener el diagnóstico operativo de la empresa.")
        st.exception(exc)
        return

    try:
        perfil_inicio = obtener_perfil_inicio_empresa(empresa_id)
        estado_inicio = obtener_estado_onboarding_empresa(empresa_id)
        requisitos_inicio = obtener_requisitos_inicio_empresa(empresa_id)
        documentacion_inicio = documentacion_respaldo_listar(empresa_id)
    except Exception as exc:
        perfil_inicio = {}
        estado_inicio = {}
        requisitos_inicio = []
        documentacion_inicio = pd.DataFrame()
        st.warning("No se pudo cargar el detalle de inicio de empresa. El diagnóstico operativo general sigue disponible.")
        st.caption(str(exc))

    tipo_sujeto = (
        perfil_inicio.get("tipo_sujeto")
        or perfil_inicio.get("empresa", {}).get("tipo_sujeto")
        or resumen.get("tipo_sujeto")
        or "NO_DEFINIDO"
    )

    estado_onboarding = (
        estado_inicio.get("estado")
        or estado_inicio.get("estado_onboarding")
        or perfil_inicio.get("estado_onboarding")
        or "PENDIENTE"
    )

    conteo_requisitos = _contar_requisitos(requisitos_inicio)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Empresa", resumen.get("nombre") or "Sin nombre")
    col2.metric("CUIT", resumen.get("cuit") or "Sin CUIT")
    col3.metric("Preparación", f"{resumen.get('porcentaje_preparacion', 0)}%")
    col4.metric("Faltantes críticos", int(resumen.get("faltantes_criticos", 0) or 0))

    if resumen.get("lista_para_operar"):
        st.success(resumen.get("mensaje", "La empresa tiene la base crítica para operar."))
    else:
        st.warning(resumen.get("mensaje", "La empresa todavía tiene faltantes críticos antes de operar."))

    st.divider()

    st.markdown("### Inicio de empresa")
    st.caption(
        "Asistente operativo adaptativo según tipo de sujeto: persona humana, "
        "persona jurídica/sociedad u otro ente. La documentación respaldatoria es opcional."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tipo de sujeto", etiqueta_tipo_sujeto(tipo_sujeto))
    c2.metric("Onboarding", _estado_legible(estado_onboarding))
    c3.metric("Requisitos pendientes", int(conteo_requisitos["pendientes"]))
    c4.metric("Bloqueantes", int(conteo_requisitos["bloqueantes"]))

    _mostrar_asistente_adaptativo(perfil_inicio, requisitos_inicio, preparar_vista)

    st.divider()
    _mostrar_documentacion_opcional(documentacion_inicio, preparar_vista)

    st.divider()
    _mostrar_controles_generales(controles, preparar_vista)

    st.divider()
    _mostrar_recomendaciones(recomendaciones)

    st.divider()
    _mostrar_inicializacion_segura(
        empresa_id=empresa_id,
        inicializar_empresa_operativa=inicializar_empresa_operativa,
        crear_backup_sqlite=crear_backup_sqlite,
        mostrar_pasos_inicializacion=mostrar_pasos_inicializacion,
    )


__all__ = [
    "mostrar_estado_empresa_operativa_adaptativo",
]