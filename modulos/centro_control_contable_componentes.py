"""
Componentes UI del Centro de Control Contable PRO.

Vista central de control profesional:
- estado integral por modulo;
- diagnosticos consolidados;
- parametrizaciones sugeridas;
- decisiones auditadas ya registradas;
- historial disponible.

Esta UI no aplica parametrizaciones sobre modulos operativos, no genera asientos,
no registra movimientos y no modifica Libro Diario ni Bandeja.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st

try:
    from core.ui import preparar_vista
except Exception:  # pragma: no cover - fallback defensivo para tests aislados
    def preparar_vista(df):  # type: ignore
        return df

try:
    from services import centro_control_contable_service as centro_service
except Exception:  # pragma: no cover
    centro_service = None  # type: ignore

try:
    from services import parametrizaciones_asistidas_control_service as control_service
except Exception:  # pragma: no cover
    control_service = None  # type: ignore


FUNCIONES_CENTRO_CONTROL = [
    "generar_centro_control_contable",
    "obtener_centro_control_contable",
    "construir_centro_control_contable",
    "diagnosticar_centro_control_contable",
    "generar_centro_control_integral",
    "obtener_centro_control_integral",
    "diagnosticar_centro_control_integral",
    "obtener_panel_centro_control",
    "obtener_resumen_integral",
]

FUNCIONES_DECISIONES = [
    "listar_decisiones_parametrizaciones",
    "listar_decisiones_parametrizacion",
    "listar_parametrizaciones_asistidas_control",
    "listar_parametrizaciones_control",
    "obtener_decisiones_parametrizacion",
    "obtener_decisiones_parametrizaciones",
    "listar_decisiones",
]

FUNCIONES_EVENTOS = [
    "listar_eventos_parametrizaciones",
    "listar_eventos_parametrizacion",
    "listar_eventos_parametrizaciones_asistidas",
    "listar_eventos_parametrizacion_asistida",
    "obtener_historial_parametrizaciones",
    "obtener_historial_parametrizacion",
    "listar_historial",
]


def _texto(valor: Any, default: str = "") -> str:
    if valor is None:
        return default
    return str(valor).strip()


def _normalizar_estado(valor: Any) -> str:
    texto = _texto(valor, "SIN_ESTADO").upper()
    reemplazos = {
        "OK": "OK",
        "CORRECTO": "OK",
        "COMPLETO": "OK",
        "LISTO": "OK",
        "REQUIERE_REVISION": "REQUIERE_REVISION",
        "ADVERTENCIA": "REQUIERE_REVISION",
        "PENDIENTE": "REQUIERE_REVISION",
        "INCOMPLETO": "INCOMPLETO",
        "CRITICO": "CRITICO",
        "CRÍTICO": "CRITICO",
        "ERROR": "CRITICO",
    }
    return reemplazos.get(texto, texto or "SIN_ESTADO")


def _llamar_funcion_disponible(modulo: Any, nombres: Iterable[str], **kwargs: Any) -> Any:
    if modulo is None:
        return {
            "ok": False,
            "error": "No se pudo importar el servicio requerido.",
        }

    errores: List[str] = []

    for nombre in nombres:
        funcion = getattr(modulo, nombre, None)
        if not callable(funcion):
            continue

        try:
            firma = inspect.signature(funcion)
            parametros = firma.parameters
            argumentos = {
                clave: valor
                for clave, valor in kwargs.items()
                if clave in parametros
            }

            if "empresa_id" in parametros and "empresa_id" not in argumentos:
                argumentos["empresa_id"] = kwargs.get("empresa_id", 1)

            return funcion(**argumentos)

        except TypeError as exc:
            errores.append(f"{nombre}: {exc}")
            try:
                return funcion(kwargs.get("empresa_id", 1))
            except Exception as exc_posicional:
                errores.append(f"{nombre} posicional: {exc_posicional}")
        except Exception as exc:
            errores.append(f"{nombre}: {exc}")

    return {
        "ok": False,
        "error": "No se encontro una funcion compatible.",
        "funciones_probadas": list(nombres),
        "errores": errores,
    }


def _obtener_centro_control(empresa_id: int) -> Dict[str, Any]:
    resultado = _llamar_funcion_disponible(
        centro_service,
        FUNCIONES_CENTRO_CONTROL,
        empresa_id=empresa_id,
    )
    if isinstance(resultado, dict):
        return resultado
    return {"ok": True, "resultado": resultado}


def _obtener_decisiones(empresa_id: int) -> Any:
    return _llamar_funcion_disponible(
        control_service,
        FUNCIONES_DECISIONES,
        empresa_id=empresa_id,
    )


def _obtener_eventos(empresa_id: int) -> Any:
    return _llamar_funcion_disponible(
        control_service,
        FUNCIONES_EVENTOS,
        empresa_id=empresa_id,
    )


def _como_lista(valor: Any) -> List[Any]:
    if valor is None:
        return []
    if isinstance(valor, list):
        return valor
    if isinstance(valor, tuple):
        return list(valor)
    if isinstance(valor, dict):
        for clave in ("items", "registros", "filas", "datos", "decisiones", "eventos", "modulos", "alertas"):
            contenido = valor.get(clave)
            if isinstance(contenido, list):
                return contenido
        return [valor]
    if isinstance(valor, pd.DataFrame):
        return valor.to_dict("records")
    return [valor]


def _dataframe_seguro(valor: Any) -> pd.DataFrame:
    if isinstance(valor, pd.DataFrame):
        return valor.copy()

    filas = _como_lista(valor)
    normalizadas = []
    for fila in filas:
        if isinstance(fila, dict):
            normalizadas.append(fila)
        else:
            normalizadas.append({"valor": fila})

    if not normalizadas:
        return pd.DataFrame()

    return pd.DataFrame(normalizadas)


def _mostrar_tabla(valor: Any, mensaje_vacio: str) -> None:
    df = _dataframe_seguro(valor)
    if df.empty:
        st.info(mensaje_vacio)
        return

    st.dataframe(
        preparar_vista(df),
        use_container_width=True,
        hide_index=True,
    )


def _extraer_modulos(centro: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidatos = [
        centro.get("modulos"),
        centro.get("estado_modulos"),
        centro.get("diagnosticos"),
        centro.get("detalle_modulos"),
        centro.get("resultado", {}).get("modulos") if isinstance(centro.get("resultado"), dict) else None,
    ]

    for candidato in candidatos:
        if isinstance(candidato, dict):
            filas = []
            for modulo, datos in candidato.items():
                if isinstance(datos, dict):
                    fila = {"modulo": modulo}
                    fila.update(datos)
                    filas.append(fila)
                else:
                    filas.append({"modulo": modulo, "valor": datos})
            if filas:
                return filas
        if isinstance(candidato, list):
            return [x if isinstance(x, dict) else {"valor": x} for x in candidato]

    return []


def _extraer_resumen(centro: Dict[str, Any], modulos: List[Dict[str, Any]]) -> Dict[str, Any]:
    resumen = centro.get("resumen") or centro.get("resumen_general") or centro.get("totales")
    if isinstance(resumen, dict):
        base = dict(resumen)
    else:
        base = {}

    if modulos:
        estados = [_normalizar_estado(m.get("estado") or m.get("estado_general") or m.get("semaforo")) for m in modulos]
        base.setdefault("modulos", len(modulos))
        base.setdefault("ok", sum(1 for e in estados if e == "OK"))
        base.setdefault("requieren_revision", sum(1 for e in estados if e in {"REQUIERE_REVISION", "INCOMPLETO"}))
        base.setdefault("criticos", sum(1 for e in estados if e == "CRITICO"))

    for clave in ("estado", "estado_general", "semaforo"):
        if clave in centro and "estado_general" not in base:
            base["estado_general"] = centro.get(clave)

    return base


def _extraer_alertas(centro: Dict[str, Any]) -> List[Dict[str, Any]]:
    alertas: List[Dict[str, Any]] = []

    def agregar(origen: str, valor: Any) -> None:
        for item in _como_lista(valor):
            if isinstance(item, dict):
                fila = {"origen": origen}
                fila.update(item)
                alertas.append(fila)
            elif item not in (None, ""):
                alertas.append({"origen": origen, "detalle": item})

    for clave in ("alertas", "advertencias", "criticos", "errores", "pendientes"):
        if clave in centro:
            agregar(clave, centro.get(clave))

    for modulo in _extraer_modulos(centro):
        nombre = modulo.get("modulo") or modulo.get("nombre") or modulo.get("codigo") or "Modulo"
        for clave in ("alertas", "advertencias", "criticos", "errores", "pendientes"):
            if clave in modulo:
                agregar(str(nombre), modulo.get(clave))

    return alertas


def _extraer_parametrizaciones(centro: Dict[str, Any]) -> List[Dict[str, Any]]:
    parametrizaciones: List[Dict[str, Any]] = []

    def agregar(origen: str, valor: Any) -> None:
        for item in _como_lista(valor):
            if isinstance(item, dict):
                fila = {"origen": origen}
                fila.update(item)
                parametrizaciones.append(fila)
            elif item not in (None, ""):
                parametrizaciones.append({"origen": origen, "detalle": item})

    for clave in (
        "parametrizaciones",
        "parametrizaciones_sugeridas",
        "sugerencias",
        "acciones_sugeridas",
        "matriz_parametrizacion",
    ):
        if clave in centro:
            agregar(clave, centro.get(clave))

    for modulo in _extraer_modulos(centro):
        nombre = modulo.get("modulo") or modulo.get("nombre") or modulo.get("codigo") or "Modulo"
        for clave in ("parametrizaciones", "sugerencias", "acciones_sugeridas", "matriz_parametrizacion"):
            if clave in modulo:
                agregar(str(nombre), modulo.get(clave))

    return parametrizaciones


def _mostrar_metricas_resumen(resumen: Dict[str, Any]) -> None:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Módulos", resumen.get("modulos", resumen.get("total_modulos", 0)))

    with col2:
        st.metric("Correctos", resumen.get("ok", resumen.get("correctos", 0)))

    with col3:
        st.metric(
            "A revisar",
            resumen.get("requieren_revision", resumen.get("advertencias", resumen.get("pendientes", 0))),
        )

    with col4:
        st.metric("Críticos", resumen.get("criticos", resumen.get("errores", 0)))


def _mostrar_estado_general(resumen: Dict[str, Any]) -> None:
    estado = _normalizar_estado(resumen.get("estado_general") or resumen.get("estado") or resumen.get("semaforo"))

    if estado == "OK":
        st.success("Estado general: correcto.")
    elif estado == "CRITICO":
        st.error("Estado general: requiere atención crítica.")
    elif estado in {"REQUIERE_REVISION", "INCOMPLETO"}:
        st.warning("Estado general: requiere revisión profesional.")
    else:
        st.info(f"Estado general: {estado}")


def mostrar_centro_control_contable_ui(
    empresa_id: Optional[int] = None,
    usuario: Optional[str] = None,
    administrador: bool = False,
) -> None:
    """
    Muestra el Centro de Control Contable PRO.

    Es una pantalla de consulta/control. No aplica parametrizaciones, no modifica
    módulos operativos y no genera asientos.
    """

    empresa_id = int(empresa_id or 1)

    st.subheader("🧭 Centro de Control Contable")
    st.caption(
        "Vista integral de diagnósticos, parametrizaciones sugeridas y decisiones auditadas. "
        "Esta pantalla no modifica la operatoria ni genera asientos."
    )

    centro = _obtener_centro_control(empresa_id)
    modulos = _extraer_modulos(centro)
    resumen = _extraer_resumen(centro, modulos)
    alertas = _extraer_alertas(centro)
    parametrizaciones = _extraer_parametrizaciones(centro)

    _mostrar_estado_general(resumen)
    _mostrar_metricas_resumen(resumen)

    if centro.get("ok") is False and centro.get("error"):
        st.warning(f"Centro de Control: {centro.get('error')}")

    tab_resumen, tab_modulos, tab_alertas, tab_param, tab_decisiones, tab_historial = st.tabs(
        [
            "Resumen",
            "Módulos",
            "Alertas",
            "Parametrizaciones",
            "Decisiones auditadas",
            "Historial",
        ]
    )

    with tab_resumen:
        st.markdown("### Resumen integral")
        _mostrar_tabla([resumen], "No hay resumen disponible.")

        recomendaciones = centro.get("recomendaciones") or centro.get("acciones_recomendadas")
        st.markdown("### Recomendaciones")
        _mostrar_tabla(recomendaciones, "No hay recomendaciones registradas.")

    with tab_modulos:
        st.markdown("### Estado por módulo")
        _mostrar_tabla(modulos, "No hay módulos informados por el Centro de Control.")

    with tab_alertas:
        st.markdown("### Alertas consolidadas")
        _mostrar_tabla(alertas, "No hay alertas consolidadas.")

    with tab_param:
        st.markdown("### Parametrizaciones sugeridas")
        st.info(
            "Esta pestaña muestra sugerencias. La aceptación, edición o desactivación "
            "se registra por el núcleo auditado, pero no se aplica todavía a módulos operativos."
        )
        _mostrar_tabla(parametrizaciones, "No hay parametrizaciones sugeridas para mostrar.")

    with tab_decisiones:
        st.markdown("### Decisiones auditadas")
        decisiones = _obtener_decisiones(empresa_id)
        if isinstance(decisiones, dict) and decisiones.get("ok") is False and decisiones.get("error"):
            st.info(decisiones.get("error"))
        _mostrar_tabla(decisiones, "No hay decisiones auditadas registradas.")

    with tab_historial:
        st.markdown("### Historial de parametrizaciones")
        eventos = _obtener_eventos(empresa_id)
        if isinstance(eventos, dict) and eventos.get("ok") is False and eventos.get("error"):
            st.info(eventos.get("error"))
        _mostrar_tabla(eventos, "No hay historial de parametrizaciones registrado.")

    if administrador:
        st.caption(
            f"Usuario: {usuario or 'sin identificar'} · Empresa ID: {empresa_id} · "
            "Modo consulta/auditoría."
        )
