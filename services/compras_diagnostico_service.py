from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from database import conectar


SEVERIDAD_CRITICO = "CRITICO"
SEVERIDAD_ADVERTENCIA = "ADVERTENCIA"
SEVERIDAD_INFORMATIVO = "INFORMATIVO"

PALABRAS_BIENES_CAMBIO = (
    "MERCADERIA",
    "MERCADERÍAS",
    "MERCADERIAS",
    "BIENES DE CAMBIO",
    "REVENTA",
    "INVENTARIO",
    "STOCK",
)

PALABRAS_CMV = (
    "CMV",
    "COSTO DE MERCADERIA VENDIDA",
    "COSTO DE MERCADERÍA VENDIDA",
    "COSTO MERCADERIA VENDIDA",
    "COSTO MERCADERÍA VENDIDA",
    "COSTO DE VENTAS",
)

CONCEPTOS_FISCALES_ESPERADOS = {
    "IVA_CREDITO_FISCAL",
    "IVA CRÉDITO FISCAL",
    "IVA CREDITO FISCAL",
    "PERCEPCION_IVA",
    "PERCEPCIÓN IVA",
    "PERCEPCION IVA",
    "PERCEPCION_IIBB",
    "PERCEPCIÓN IIBB",
    "PERCEPCION IIBB",
    "IVA_NO_COMPUTABLE",
    "IVA NO COMPUTABLE",
    "OTROS_TRIBUTOS",
    "OTROS TRIBUTOS",
}

PATRON_CODIGO_CUENTA_LEGACY = re.compile(r"['\"]([0-9]{7,})['\"]")


# ======================================================
# Utilidades internas
# ======================================================


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar(valor: Any) -> str:
    texto = _texto(valor).upper()
    reemplazos = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _to_int(valor: Any, default: int = 0) -> int:
    try:
        if valor is None or valor == "":
            return default
        return int(valor)
    except Exception:
        return default


def _to_float(valor: Any, default: float = 0.0) -> float:
    try:
        if valor is None or valor == "":
            return default
        return float(valor)
    except Exception:
        return default


def _fila_a_dict(cursor, fila: Any) -> dict[str, Any]:
    """
    Convierte filas sqlite a dict sin modificar conn.row_factory.

    Esta función es deliberadamente local a cada cursor para que el diagnóstico
    no altere conexiones recibidas desde tests, otros servicios o Streamlit.
    """
    if fila is None:
        return {}

    if isinstance(fila, dict):
        return dict(fila)

    if hasattr(fila, "keys"):
        try:
            return {str(clave): fila[clave] for clave in fila.keys()}
        except Exception:
            pass

    columnas = [str(col[0]) for col in (cursor.description or [])]
    return {columnas[idx]: fila[idx] for idx in range(min(len(columnas), len(fila)))}


def _table_exists(conn, tabla: str) -> bool:
    fila = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (tabla,),
    ).fetchone()
    return bool(fila)


def _columns(conn, tabla: str) -> set[str]:
    if not _table_exists(conn, tabla):
        return set()
    filas = conn.execute(f"PRAGMA table_info({tabla})").fetchall()
    return {str(fila.get("name") if isinstance(fila, dict) else fila[1]) for fila in filas}


def _rows(conn, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, tuple(params))
    filas = cursor.fetchall()
    return [_fila_a_dict(cursor, fila) for fila in filas]


def _scalar(conn, sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
    try:
        cursor = conn.execute(sql, tuple(params))
        fila = cursor.fetchone()
        if not fila:
            return default

        if isinstance(fila, dict):
            return next(iter(fila.values()), default)

        if hasattr(fila, "keys"):
            try:
                claves = list(fila.keys())
                return fila[claves[0]] if claves else default
            except Exception:
                pass

        return fila[0]
    except Exception:
        return default


def _nueva_alerta(
    alertas: list[dict[str, Any]],
    *,
    severidad: str,
    area: str,
    codigo: str,
    objeto: str = "",
    mensaje: str,
    recomendacion: str = "",
    detalle: Optional[dict[str, Any]] = None,
) -> None:
    alertas.append(
        {
            "severidad": severidad,
            "area": area,
            "codigo": codigo,
            "objeto": objeto,
            "mensaje": mensaje,
            "recomendacion": recomendacion,
            "detalle": detalle or {},
        }
    )


def _buscar_cuenta_empresa(conn, cuenta_id: Any = None, codigo: Any = None, empresa_id: int = 1) -> dict[str, Any] | None:
    if not _table_exists(conn, "plan_cuentas_empresa"):
        return None

    if cuenta_id not in (None, ""):
        filas = _rows(
            conn,
            """
            SELECT id, empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema, cuenta_maestro_id
            FROM plan_cuentas_empresa
            WHERE id = ?
              AND empresa_id = ?
            LIMIT 1
            """,
            (int(cuenta_id), int(empresa_id)),
        )
        return filas[0] if filas else None

    codigo_txt = _texto(codigo)
    if codigo_txt:
        filas = _rows(
            conn,
            """
            SELECT id, empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema, cuenta_maestro_id
            FROM plan_cuentas_empresa
            WHERE codigo = ?
              AND empresa_id = ?
            LIMIT 1
            """,
            (codigo_txt, int(empresa_id)),
        )
        return filas[0] if filas else None

    return None


def _es_bienes_de_cambio(registro: dict[str, Any]) -> bool:
    texto = " ".join(
        [
            _normalizar(registro.get("categoria")),
            _normalizar(registro.get("descripcion")),
            _normalizar(registro.get("tipo_categoria")),
            _normalizar(registro.get("tratamiento_contable")),
        ]
    )
    return any(palabra in texto for palabra in PALABRAS_BIENES_CAMBIO) or _to_int(registro.get("afecta_inventario")) == 1


def _parece_cmv(registro: dict[str, Any]) -> bool:
    texto = " ".join(
        [
            _normalizar(registro.get("categoria")),
            _normalizar(registro.get("descripcion")),
            _normalizar(registro.get("tipo_categoria")),
            _normalizar(registro.get("tratamiento_contable")),
        ]
    )
    return any(palabra in texto for palabra in PALABRAS_CMV)


# ======================================================
# Lecturas de configuración
# ======================================================


def _leer_categorias_legacy(conn, empresa_id: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "categorias_compra"):
        return []
    columnas = _columns(conn, "categorias_compra")
    filtro_empresa = "AND COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas else ""
    params = (int(empresa_id),) if filtro_empresa else ()
    return _rows(
        conn,
        f"""
        SELECT *
        FROM categorias_compra
        WHERE COALESCE(activo, 1) = 1
        {filtro_empresa}
        ORDER BY categoria
        """,
        params,
    )


def _leer_categorias_config(conn, empresa_id: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "categorias_compra_config"):
        return []
    return _rows(
        conn,
        """
        SELECT *
        FROM categorias_compra_config
        WHERE empresa_id = ?
          AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
        ORDER BY categoria
        """,
        (int(empresa_id),),
    )


def _leer_conceptos_legacy(conn, empresa_id: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "conceptos_fiscales_compra"):
        return []
    columnas = _columns(conn, "conceptos_fiscales_compra")
    filtro_empresa = "AND COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas else ""
    params = (int(empresa_id),) if filtro_empresa else ()
    return _rows(
        conn,
        f"""
        SELECT *
        FROM conceptos_fiscales_compra
        WHERE COALESCE(activo, 1) = 1
        {filtro_empresa}
        ORDER BY concepto
        """,
        params,
    )


def _leer_conceptos_config(conn, empresa_id: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "conceptos_fiscales_compra_config"):
        return []
    return _rows(
        conn,
        """
        SELECT *
        FROM conceptos_fiscales_compra_config
        WHERE empresa_id = ?
          AND COALESCE(estado, 'ACTIVO') = 'ACTIVO'
        ORDER BY concepto
        """,
        (int(empresa_id),),
    )


def detectar_codigos_legacy_en_compras_service(
    ruta_compras_service: str | Path = "services/compras_service.py",
) -> list[dict[str, Any]]:
    ruta = Path(ruta_compras_service)
    if not ruta.exists():
        return []

    resultados: list[dict[str, Any]] = []
    for nro_linea, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        for match in PATRON_CODIGO_CUENTA_LEGACY.finditer(linea):
            resultados.append(
                {
                    "codigo": match.group(1),
                    "linea": nro_linea,
                    "texto": linea.strip()[:240],
                }
            )

    unicos: dict[tuple[str, int], dict[str, Any]] = {}
    for item in resultados:
        unicos[(str(item["codigo"]), int(item["linea"]))] = item
    return list(unicos.values())


# ======================================================
# Diagnósticos específicos
# ======================================================


def _diagnosticar_categorias(
    conn,
    *,
    empresa_id: int,
    alertas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    legacy = _leer_categorias_legacy(conn, empresa_id)
    config = _leer_categorias_config(conn, empresa_id)

    legacy_por_nombre = {_normalizar(c.get("categoria")): c for c in legacy if _texto(c.get("categoria"))}
    config_por_nombre = {_normalizar(c.get("categoria")): c for c in config if _texto(c.get("categoria"))}

    for clave, categoria_legacy in legacy_por_nombre.items():
        if clave not in config_por_nombre:
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_ADVERTENCIA,
                area="Compras / Categorías",
                codigo="COMPRA_CATEGORIA_LEGACY_SIN_CONFIG_FF",
                objeto=_texto(categoria_legacy.get("categoria")),
                mensaje="La categoría existe en la tabla legacy de compras pero no tiene configuración FF activa.",
                recomendacion="Migrar o vincular la categoría a categorias_compra_config antes de usarla para imputación contable profesional.",
            )

    diagnostico: list[dict[str, Any]] = []

    for categoria in config:
        nombre = _texto(categoria.get("categoria"))
        cuenta = _buscar_cuenta_empresa(conn, categoria.get("cuenta_sugerida_id"), empresa_id=empresa_id)
        cuenta_contrapartida = _buscar_cuenta_empresa(
            conn,
            categoria.get("cuenta_contrapartida_sugerida_id"),
            empresa_id=empresa_id,
        )
        es_inventario = _es_bienes_de_cambio(categoria)
        parece_cmv = _parece_cmv(categoria)

        estado_cuenta = "OK" if cuenta and _texto(cuenta.get("estado")).upper() == "ACTIVA" else "SIN_CUENTA_ACTIVA"

        item = {
            "categoria": nombre,
            "tratamiento_contable": _texto(categoria.get("tratamiento_contable")),
            "tipo_categoria": _texto(categoria.get("tipo_categoria")),
            "afecta_inventario": _to_int(categoria.get("afecta_inventario")),
            "afecta_bienes_uso": _to_int(categoria.get("afecta_bienes_uso")),
            "afecta_resultado": _to_int(categoria.get("afecta_resultado")),
            "afecta_iva": _to_int(categoria.get("afecta_iva")),
            "cuenta_sugerida_id": categoria.get("cuenta_sugerida_id"),
            "cuenta_sugerida_codigo": cuenta.get("codigo") if cuenta else "",
            "cuenta_sugerida_nombre": cuenta.get("nombre") if cuenta else "",
            "cuenta_contrapartida_sugerida_id": categoria.get("cuenta_contrapartida_sugerida_id"),
            "cuenta_contrapartida_codigo": cuenta_contrapartida.get("codigo") if cuenta_contrapartida else "",
            "cuenta_contrapartida_nombre": cuenta_contrapartida.get("nombre") if cuenta_contrapartida else "",
            "es_bienes_de_cambio": 1 if es_inventario else 0,
            "parece_cmv": 1 if parece_cmv else 0,
            "estado_diagnostico": estado_cuenta,
        }
        diagnostico.append(item)

        if not cuenta:
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_ADVERTENCIA,
                area="Compras / Categorías",
                codigo="COMPRA_CATEGORIA_CONFIG_SIN_CUENTA_PLAN_EMPRESA",
                objeto=nombre,
                mensaje="La categoría de compra no tiene cuenta sugerida activa del Plan de Cuentas Empresa.",
                recomendacion="Vincular la categoría con una cuenta imputable del Plan Empresa basada en el Plan Maestro FF.",
            )

        if cuenta and _texto(cuenta.get("estado")).upper() != "ACTIVA":
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_ADVERTENCIA,
                area="Compras / Categorías",
                codigo="COMPRA_CATEGORIA_CUENTA_INACTIVA",
                objeto=nombre,
                mensaje="La categoría apunta a una cuenta de empresa que no está activa.",
                recomendacion="Elegir una cuenta activa o corregir la configuración con auditoría.",
                detalle={"cuenta": cuenta},
            )

        if es_inventario:
            if _to_int(categoria.get("afecta_inventario")) != 1:
                _nueva_alerta(
                    alertas,
                    severidad=SEVERIDAD_ADVERTENCIA,
                    area="Compras / Bienes de cambio",
                    codigo="COMPRA_BIENES_CAMBIO_NO_AFECTA_INVENTARIO",
                    objeto=nombre,
                    mensaje="La categoría parece mercadería para reventa o bienes de cambio, pero no está marcada como inventario.",
                    recomendacion="Marcar afecta_inventario=1 y usar cuenta de Bienes de cambio/Mercaderías, no resultado directo.",
                )
            if _to_int(categoria.get("afecta_resultado")) == 1:
                _nueva_alerta(
                    alertas,
                    severidad=SEVERIDAD_ADVERTENCIA,
                    area="Compras / CMV",
                    codigo="COMPRA_BIENES_CAMBIO_IMPUTA_RESULTADO_DIRECTO",
                    objeto=nombre,
                    mensaje="La categoría de bienes de cambio está marcada como resultado al momento de compra.",
                    recomendacion="La compra de mercadería debería ir primero a Bienes de cambio; el CMV se reconoce al vender o al cierre de inventario.",
                )
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_INFORMATIVO,
                area="Compras / CMV",
                codigo="COMPRA_BIENES_CAMBIO_REQUIERE_CMV_FUTURO",
                objeto=nombre,
                mensaje="La categoría de bienes de cambio requiere política futura de CMV.",
                recomendacion="Definir si el CMV se calculará por inventario permanente, inventario periódico o ajuste manual de cierre.",
            )

        if parece_cmv:
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_INFORMATIVO,
                area="Compras / CMV",
                codigo="COMPRA_CATEGORIA_CMV_DEBE_USARSE_EN_CIERRE_O_VENTA",
                objeto=nombre,
                mensaje="La categoría parece referirse a Costo de Mercadería Vendida.",
                recomendacion="No usar CMV como imputación automática de la factura de compra salvo casos específicos; preparar su uso para venta, stock o cierre.",
            )

    return diagnostico


def _diagnosticar_conceptos_fiscales(
    conn,
    *,
    empresa_id: int,
    alertas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    legacy = _leer_conceptos_legacy(conn, empresa_id)
    config = _leer_conceptos_config(conn, empresa_id)

    legacy_por_nombre = {_normalizar(c.get("concepto")): c for c in legacy if _texto(c.get("concepto"))}
    config_por_nombre = {_normalizar(c.get("concepto")): c for c in config if _texto(c.get("concepto"))}

    for clave, concepto_legacy in legacy_por_nombre.items():
        if clave not in config_por_nombre:
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_ADVERTENCIA,
                area="Compras / Conceptos fiscales",
                codigo="COMPRA_CONCEPTO_FISCAL_LEGACY_SIN_CONFIG_FF",
                objeto=_texto(concepto_legacy.get("concepto")),
                mensaje="El concepto fiscal existe en la tabla legacy pero no tiene configuración FF activa.",
                recomendacion="Migrar o vincular el concepto fiscal a conceptos_fiscales_compra_config.",
            )

    diagnostico: list[dict[str, Any]] = []

    for concepto in config:
        nombre = _texto(concepto.get("concepto"))
        cuenta = _buscar_cuenta_empresa(conn, concepto.get("cuenta_sugerida_id"), empresa_id=empresa_id)
        afecta_iva = _to_int(concepto.get("afecta_iva"))
        computable = _to_int(concepto.get("computable"))
        mayor_costo = _to_int(concepto.get("mayor_costo"))
        informativo = _to_int(concepto.get("informativo"))

        item = {
            "concepto": nombre,
            "tratamiento_fiscal": _texto(concepto.get("tratamiento_fiscal")),
            "afecta_iva": afecta_iva,
            "afecta_iibb": _to_int(concepto.get("afecta_iibb")),
            "afecta_ganancias": _to_int(concepto.get("afecta_ganancias")),
            "computable": computable,
            "mayor_costo": mayor_costo,
            "informativo": informativo,
            "cuenta_sugerida_id": concepto.get("cuenta_sugerida_id"),
            "cuenta_sugerida_codigo": cuenta.get("codigo") if cuenta else "",
            "cuenta_sugerida_nombre": cuenta.get("nombre") if cuenta else "",
            "estado_diagnostico": "OK" if cuenta or informativo == 1 else "SIN_CUENTA_ACTIVA",
        }
        diagnostico.append(item)

        if not cuenta and informativo != 1:
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_ADVERTENCIA,
                area="Compras / Conceptos fiscales",
                codigo="COMPRA_CONCEPTO_FISCAL_CONFIG_SIN_CUENTA_PLAN_EMPRESA",
                objeto=nombre,
                mensaje="El concepto fiscal no tiene cuenta sugerida activa del Plan de Cuentas Empresa.",
                recomendacion="Vincular IVA crédito, percepciones o tributos no recuperables con una cuenta activa del Plan Empresa.",
            )

        if afecta_iva == 1 and computable == 0 and mayor_costo == 0 and informativo == 0:
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_ADVERTENCIA,
                area="Compras / IVA",
                codigo="COMPRA_CONCEPTO_IVA_SIN_DESTINO_CLARO",
                objeto=nombre,
                mensaje="El concepto afecta IVA pero no está marcado como computable, mayor costo ni informativo.",
                recomendacion="Definir si impacta posición IVA, si es no computable/mayor costo o si solo es informativo.",
            )

    conceptos_norm = {_normalizar(c.get("concepto")) for c in config}
    for esperado in CONCEPTOS_FISCALES_ESPERADOS:
        esperado_norm = _normalizar(esperado)
        if not any(esperado_norm in existente or existente in esperado_norm for existente in conceptos_norm):
            _nueva_alerta(
                alertas,
                severidad=SEVERIDAD_INFORMATIVO,
                area="Compras / Conceptos fiscales",
                codigo="COMPRA_CONCEPTO_FISCAL_ESPERADO_NO_DETECTADO",
                objeto=esperado,
                mensaje="No se detectó un concepto fiscal esperado para compras en la configuración FF activa.",
                recomendacion="Revisar si corresponde incorporarlo según actividad y régimen fiscal de la empresa.",
            )

    return diagnostico


def _diagnosticar_compras_cargadas(conn, empresa_id: int, alertas: list[dict[str, Any]]) -> dict[str, Any]:
    if not _table_exists(conn, "compras_comprobantes"):
        _nueva_alerta(
            alertas,
            severidad=SEVERIDAD_CRITICO,
            area="Compras / Estructura",
            codigo="COMPRAS_COMPROBANTES_NO_EXISTE",
            mensaje="No existe la tabla compras_comprobantes.",
            recomendacion="Ejecutar la inicialización estructural de Compras antes de operar el módulo.",
        )
        return {
            "compras_cargadas": 0,
            "compras_sin_categoria": 0,
            "compras_sin_cuenta_principal": 0,
            "compras_sin_cuenta_proveedor": 0,
        }

    total = _to_int(
        _scalar(
            conn,
            "SELECT COUNT(*) FROM compras_comprobantes WHERE COALESCE(empresa_id, 1)=?",
            (int(empresa_id),),
            0,
        )
    )
    sin_categoria = _to_int(
        _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM compras_comprobantes
            WHERE COALESCE(empresa_id, 1)=?
              AND COALESCE(TRIM(categoria_compra), '') = ''
            """,
            (int(empresa_id),),
            0,
        )
    )
    sin_cuenta_principal = _to_int(
        _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM compras_comprobantes
            WHERE COALESCE(empresa_id, 1)=?
              AND COALESCE(TRIM(cuenta_principal_codigo), '') = ''
            """,
            (int(empresa_id),),
            0,
        )
    )
    sin_cuenta_proveedor = _to_int(
        _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM compras_comprobantes
            WHERE COALESCE(empresa_id, 1)=?
              AND COALESCE(TRIM(cuenta_proveedor_codigo), '') = ''
            """,
            (int(empresa_id),),
            0,
        )
    )

    if total > 0 and sin_categoria > 0:
        _nueva_alerta(
            alertas,
            severidad=SEVERIDAD_ADVERTENCIA,
            area="Compras / Comprobantes",
            codigo="COMPRA_COMPROBANTES_SIN_CATEGORIA",
            mensaje="Hay comprobantes de compra sin categoría.",
            recomendacion="Clasificar antes de generar imputaciones contables o diagnósticos fiscales definitivos.",
            detalle={"cantidad": sin_categoria},
        )

    if total > 0 and sin_cuenta_principal > 0:
        _nueva_alerta(
            alertas,
            severidad=SEVERIDAD_ADVERTENCIA,
            area="Compras / Comprobantes",
            codigo="COMPRA_COMPROBANTES_SIN_CUENTA_PRINCIPAL",
            mensaje="Hay comprobantes de compra sin cuenta principal registrada.",
            recomendacion="Reprocesar o sanear la imputación de compras contra categorías FF y Plan Empresa.",
            detalle={"cantidad": sin_cuenta_principal},
        )

    return {
        "compras_cargadas": total,
        "compras_sin_categoria": sin_categoria,
        "compras_sin_cuenta_principal": sin_cuenta_principal,
        "compras_sin_cuenta_proveedor": sin_cuenta_proveedor,
    }


# ======================================================
# API pública
# ======================================================


def diagnosticar_configuracion_compras(
    empresa_id: int = 1,
    *,
    conn=None,
    ruta_compras_service: str | Path | None = "services/compras_service.py",
) -> dict[str, Any]:
    """
    Diagnóstico contable-fiscal de Compras PRO.

    No modifica datos.
    No procesa comprobantes.
    No genera asientos.
    No toca pagos, caja, banco ni cuenta corriente.
    """
    propia = conn is None
    conn = conn or conectar()

    try:
        alertas: list[dict[str, Any]] = []

        tablas_requeridas = [
            "compras_comprobantes",
            "categorias_compra",
            "categorias_compra_config",
            "conceptos_fiscales_compra",
            "conceptos_fiscales_compra_config",
            "plan_cuentas_empresa",
        ]

        tablas_estado = {tabla: _table_exists(conn, tabla) for tabla in tablas_requeridas}
        for tabla, existe in tablas_estado.items():
            if not existe:
                _nueva_alerta(
                    alertas,
                    severidad=SEVERIDAD_CRITICO,
                    area="Compras / Estructura",
                    codigo="COMPRA_TABLA_REQUERIDA_NO_EXISTE",
                    objeto=tabla,
                    mensaje=f"No existe la tabla requerida {tabla}.",
                    recomendacion="Ejecutar migraciones/estructura antes de avanzar con Compras PRO.",
                )

        categorias = _diagnosticar_categorias(conn, empresa_id=int(empresa_id), alertas=alertas)
        conceptos = _diagnosticar_conceptos_fiscales(conn, empresa_id=int(empresa_id), alertas=alertas)
        compras_estado = _diagnosticar_compras_cargadas(conn, int(empresa_id), alertas)

        codigos_legacy: list[dict[str, Any]] = []
        if ruta_compras_service is not None:
            codigos_legacy = detectar_codigos_legacy_en_compras_service(ruta_compras_service)
            if codigos_legacy:
                _nueva_alerta(
                    alertas,
                    severidad=SEVERIDAD_ADVERTENCIA,
                    area="Compras / Código",
                    codigo="COMPRA_SERVICE_TIENE_CODIGOS_CUENTA_HARDCODEADOS",
                    mensaje="Se detectaron posibles códigos de cuenta hardcodeados en services/compras_service.py.",
                    recomendacion="Reemplazar defaults por configuraciones FF basadas en Plan Empresa antes de generar asientos profesionales.",
                    detalle={"cantidad": len(codigos_legacy), "muestras": codigos_legacy[:10]},
                )

        criticas = [a for a in alertas if a["severidad"] == SEVERIDAD_CRITICO]
        advertencias = [a for a in alertas if a["severidad"] == SEVERIDAD_ADVERTENCIA]
        informativos = [a for a in alertas if a["severidad"] == SEVERIDAD_INFORMATIVO]

        categorias_inventario = [c for c in categorias if _to_int(c.get("es_bienes_de_cambio")) == 1]
        categorias_cmv = [c for c in categorias if _to_int(c.get("parece_cmv")) == 1]
        categorias_sin_cuenta = [c for c in categorias if c.get("estado_diagnostico") != "OK"]
        conceptos_sin_cuenta = [c for c in conceptos if c.get("estado_diagnostico") != "OK"]

        estado_general = "OK"
        if criticas:
            estado_general = "CRITICO"
        elif advertencias:
            estado_general = "REQUIERE_REVISION"

        return {
            "ok": True,
            "empresa_id": int(empresa_id),
            "estado_general": estado_general,
            "resumen": {
                "tablas_requeridas_ok": all(tablas_estado.values()),
                "categorias_config_activas": len(categorias),
                "categorias_sin_cuenta_plan_empresa": len(categorias_sin_cuenta),
                "categorias_bienes_de_cambio": len(categorias_inventario),
                "categorias_cmv_detectadas": len(categorias_cmv),
                "conceptos_fiscales_config_activos": len(conceptos),
                "conceptos_fiscales_sin_cuenta_plan_empresa": len(conceptos_sin_cuenta),
                "codigos_legacy_en_compras_service": len(codigos_legacy),
                **compras_estado,
                "criticas": len(criticas),
                "advertencias": len(advertencias),
                "informativos": len(informativos),
                "total_alertas": len(alertas),
            },
            "alertas": alertas,
            "categorias": categorias,
            "conceptos_fiscales": conceptos,
            "codigos_legacy": codigos_legacy,
            "recomendacion_siguiente_etapa": _recomendacion_siguiente_etapa(estado_general, categorias_sin_cuenta, conceptos_sin_cuenta, codigos_legacy),
        }
    except Exception as exc:
        return {"ok": False, "estado_general": "ERROR", "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def diagnosticar_compras_pro(
    empresa_id: int = 1,
    *,
    conn=None,
    ruta_compras_service: str | Path | None = "services/compras_service.py",
) -> dict[str, Any]:
    return diagnosticar_configuracion_compras(
        empresa_id=empresa_id,
        conn=conn,
        ruta_compras_service=ruta_compras_service,
    )


def _recomendacion_siguiente_etapa(
    estado_general: str,
    categorias_sin_cuenta: list[dict[str, Any]],
    conceptos_sin_cuenta: list[dict[str, Any]],
    codigos_legacy: list[dict[str, Any]],
) -> str:
    if estado_general == "CRITICO":
        return "Primero completar estructura/migraciones de Compras antes de rediseñar el circuito operativo."

    if categorias_sin_cuenta or conceptos_sin_cuenta:
        return "Avanzar con saneamiento controlado de categorías y conceptos fiscales contra Plan Empresa."

    if codigos_legacy:
        return "Reemplazar defaults hardcodeados de Compras por configuración FF antes de asientos propuestos."

    return "La configuración base está lista para iniciar imputación contable controlada de compras."