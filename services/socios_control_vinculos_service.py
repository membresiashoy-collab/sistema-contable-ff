from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from database import conectar
from services.socios_matriz_contable_service import (
    asegurar_estructura_matriz_contable_socios,
    diagnosticar_matriz_contable_socios,
    listar_matriz_contable_socios,
)


TIPOS_MATRIZ_REQUERIDOS_SOCIEDAD = {
    "CAPITAL_SUSCRIPTO": "Capital suscripto",
    "INTEGRACION_CAPITAL": "Integración de capital",
}

REQUISITOS_POR_OPERACION = {
    "admite_prestamos": [
        ("PRESTAMO_SOCIO_EMPRESA", "Préstamo de socio a empresa"),
        ("DEVOLUCION_PRESTAMO_SOCIO", "Devolución de préstamo de socio"),
    ],
    "admite_retiros": [
        ("RETIRO_SOCIO", "Retiro de socio"),
    ],
    "admite_reintegros": [
        ("REINTEGRO_SOCIO", "Reintegro al socio"),
    ],
    "admite_honorarios": [
        ("HONORARIOS_SERVICIOS_SOCIO", "Honorarios o servicios facturados por socio"),
    ],
    "admite_facturas_proveedor": [
        ("FACTURA_PROVEEDOR_SOCIO", "Factura de proveedor vinculada al socio"),
    ],
}

COLUMNAS_BOOLEANAS_SOCIO = {
    "cuenta_particular_habilitada",
    "admite_prestamos",
    "admite_retiros",
    "admite_reintegros",
    "admite_honorarios",
    "admite_facturas_proveedor",
}


def _conectar(conn: sqlite3.Connection | None = None) -> tuple[sqlite3.Connection, bool]:
    if conn is not None:
        if conn.row_factory is None:
            conn.row_factory = sqlite3.Row
        return conn, False

    nueva = conectar()
    if nueva.row_factory is None:
        nueva.row_factory = sqlite3.Row
    return nueva, True


def _table_exists(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (_texto(tabla),),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, tabla: str) -> set[str]:
    if not _table_exists(conn, tabla):
        return set()
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar_codigo(valor: Any) -> str:
    return _texto(valor).upper().replace(" ", "_")


def _bool_int(valor: Any, default: int = 0) -> int:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return 1 if valor else 0
    if isinstance(valor, (int, float)):
        return 1 if valor else 0

    texto = _texto(valor).upper()
    if texto in {"1", "S", "SI", "SÍ", "TRUE", "VERDADERO", "YES"}:
        return 1
    if texto in {"0", "N", "NO", "FALSE", "FALSO"}:
        return 0
    return default


def _leer_socios_activos(conn: sqlite3.Connection, empresa_id: int) -> pd.DataFrame:
    if not _table_exists(conn, "socios_empresa"):
        return pd.DataFrame()

    columnas = _columns(conn, "socios_empresa")
    if not columnas:
        return pd.DataFrame()

    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM socios_empresa
            WHERE empresa_id = ?
              AND COALESCE(estado, 'ACTIVO') = 'ACTIVO'
            ORDER BY nombre COLLATE NOCASE ASC, id ASC
            """,
            conn,
            params=(int(empresa_id),),
        )
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    for columna in COLUMNAS_BOOLEANAS_SOCIO:
        if columna in df.columns:
            df[columna] = df[columna].apply(lambda valor: _bool_int(valor, 0)).astype(int)

    for columna in [
        "nombre",
        "cuit",
        "tipo_socio",
        "rol_relacion",
        "condicion_fiscal",
        "proveedor_vinculado_referencia",
        "cuenta_particular_codigo",
        "cuenta_particular_nombre",
    ]:
        if columna in df.columns:
            df[columna] = df[columna].fillna("").astype(str)

    return df


def _leer_empresa(conn: sqlite3.Connection, empresa_id: int) -> dict[str, Any]:
    if not _table_exists(conn, "empresas"):
        return {}

    columnas = _columns(conn, "empresas")
    if "id" not in columnas:
        return {}

    columnas_preferidas = [
        col
        for col in [
            "id",
            "nombre",
            "razon_social",
            "tipo_sujeto",
            "tipo_persona",
            "tipo_societario",
            "cuit",
            "estado",
        ]
        if col in columnas
    ]
    if not columnas_preferidas:
        return {}

    sql = f"""
        SELECT {", ".join(columnas_preferidas)}
        FROM empresas
        WHERE id = ?
        LIMIT 1
    """
    fila = conn.execute(sql, (int(empresa_id),)).fetchone()
    if not fila:
        return {}

    if isinstance(fila, sqlite3.Row):
        return dict(fila)
    return dict(zip(columnas_preferidas, fila))


def _empresa_es_sociedad(empresa: dict[str, Any], socios: pd.DataFrame) -> bool:
    texto = " ".join(
        [
            _texto(empresa.get("tipo_sujeto")),
            _texto(empresa.get("tipo_persona")),
            _texto(empresa.get("tipo_societario")),
            _texto(empresa.get("razon_social")),
            _texto(empresa.get("nombre")),
        ]
    ).upper()

    claves_sociedad = [
        "SOCIEDAD",
        "PERSONA_JURIDICA",
        "PERSONA JURIDICA",
        "PERSONA_JURÍDICA",
        "PERSONA JURÍDICA",
        "S.A.",
        "SA",
        "SAS",
        "S.A.S.",
        "SRL",
        "S.R.L.",
    ]

    if any(clave in texto for clave in claves_sociedad):
        return True

    if not socios.empty and "rol_relacion" in socios.columns:
        roles = {_normalizar_codigo(valor) for valor in socios["rol_relacion"].tolist()}
        if roles.intersection({"SOCIO", "ACCIONISTA", "ASOCIADO", "COOPERATIVISTA"}):
            return True

    if not socios.empty and "tipo_socio" in socios.columns:
        tipos = {_normalizar_codigo(valor) for valor in socios["tipo_socio"].tolist()}
        if tipos.intersection({"SOCIO", "ACCIONISTA", "ASOCIADO", "COOPERATIVISTA"}):
            return True

    return False


def _matriz_configurada(matriz: pd.DataFrame, tipo_vinculo: str) -> bool:
    if matriz.empty or "tipo_vinculo" not in matriz.columns:
        return False

    tipo = _normalizar_codigo(tipo_vinculo)
    filas = matriz[matriz["tipo_vinculo"].astype(str).str.upper() == tipo]
    if filas.empty:
        return False

    fila = filas.iloc[0].to_dict()
    if _bool_int(fila.get("configurada"), 0):
        return True

    estado = _normalizar_codigo(fila.get("estado_configuracion_calculado") or fila.get("estado_configuracion"))
    return estado in {"CONFIGURADA_CON_CUENTA_EMPRESA", "CONFIGURADA_CON_PLAN_MAESTRO", "CONFIGURADA"}


def _estado_matriz(matriz: pd.DataFrame, tipo_vinculo: str) -> str:
    if matriz.empty or "tipo_vinculo" not in matriz.columns:
        return "SIN_MATRIZ"

    tipo = _normalizar_codigo(tipo_vinculo)
    filas = matriz[matriz["tipo_vinculo"].astype(str).str.upper() == tipo]
    if filas.empty:
        return "SIN_VINCULO"

    fila = filas.iloc[0].to_dict()
    return _texto(fila.get("estado_configuracion_calculado") or fila.get("estado_configuracion")) or "PENDIENTE"


def _agregar_alerta(
    alertas: list[dict[str, Any]],
    *,
    nivel: str,
    area: str,
    codigo: str,
    mensaje: str,
    recomendacion: str,
    socio_id: Any = "",
    socio_nombre: str = "",
    tipo_vinculo: str = "",
    bloqueante: int = 0,
) -> None:
    alertas.append(
        {
            "nivel": _normalizar_codigo(nivel) or "INFORMATIVO",
            "area": _texto(area),
            "codigo": _normalizar_codigo(codigo),
            "socio_id": _texto(socio_id),
            "socio_nombre": _texto(socio_nombre),
            "tipo_vinculo": _normalizar_codigo(tipo_vinculo),
            "mensaje": _texto(mensaje),
            "recomendacion": _texto(recomendacion),
            "bloqueante": _bool_int(bloqueante, 0),
        }
    )


def controlar_vinculos_socios(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Control normativo y operativo de vínculos con socios.

    No registra movimientos.
    No genera asientos.
    No toca Caja/Banco, Compras, Ventas, IVA, Pagos, Cobranzas ni Conciliación.
    """
    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=int(empresa_id), conn=conn)

        empresa = _leer_empresa(conn, int(empresa_id))
        socios = _leer_socios_activos(conn, int(empresa_id))
        matriz = listar_matriz_contable_socios(empresa_id=int(empresa_id), incluir_inactivas=False, conn=conn)
        diagnostico_matriz = diagnosticar_matriz_contable_socios(empresa_id=int(empresa_id), conn=conn)

        alertas: list[dict[str, Any]] = []

        if socios.empty:
            _agregar_alerta(
                alertas,
                nivel="INFORMATIVO",
                area="Socios",
                codigo="SOCIOS_SIN_SOCIOS_ACTIVOS",
                mensaje="No hay socios/accionistas activos para controlar.",
                recomendacion="Cargue socios o accionistas si la empresa requiere control societario.",
                bloqueante=0,
            )

        es_sociedad = _empresa_es_sociedad(empresa, socios)
        if es_sociedad:
            for tipo, nombre in TIPOS_MATRIZ_REQUERIDOS_SOCIEDAD.items():
                if not _matriz_configurada(matriz, tipo):
                    _agregar_alerta(
                        alertas,
                        nivel="CRITICO",
                        area="Capital",
                        codigo="SOCIEDAD_MATRIZ_CAPITAL_INCOMPLETA",
                        tipo_vinculo=tipo,
                        mensaje=f"La empresa tiene perfil societario y la matriz no está configurada para {nombre}.",
                        recomendacion="Vincule la cuenta principal y la cuenta relacionada desde la Matriz contable de vínculos con socios.",
                        bloqueante=1,
                    )

        if not _matriz_configurada(matriz, "CUENTA_PARTICULAR_SOCIO"):
            socios_con_cuenta_particular = (
                socios[socios.get("cuenta_particular_habilitada", pd.Series(dtype=int)) == 1]
                if not socios.empty and "cuenta_particular_habilitada" in socios.columns
                else pd.DataFrame()
            )
            if not socios_con_cuenta_particular.empty:
                _agregar_alerta(
                    alertas,
                    nivel="ADVERTENCIA",
                    area="Cuenta particular",
                    codigo="CUENTAS_PARTICULARES_SIN_MATRIZ_CONFIGURADA",
                    tipo_vinculo="CUENTA_PARTICULAR_SOCIO",
                    mensaje="Hay socios con cuenta particular habilitada, pero la matriz de cuenta particular no está configurada.",
                    recomendacion="Configure el vínculo CUENTA_PARTICULAR_SOCIO antes de usar la cuenta particular como auxiliar de control.",
                    bloqueante=0,
                )

        for _, socio_row in socios.iterrows():
            socio = socio_row.to_dict()
            socio_id = socio.get("id", "")
            socio_nombre = _texto(socio.get("nombre")) or f"Socio #{socio_id}"

            operaciones_habilitadas = [
                campo
                for campo in REQUISITOS_POR_OPERACION
                if _bool_int(socio.get(campo), 0) == 1
            ]

            if operaciones_habilitadas and not _bool_int(socio.get("cuenta_particular_habilitada"), 0):
                _agregar_alerta(
                    alertas,
                    nivel="ADVERTENCIA",
                    area="Socio",
                    codigo="SOCIO_OPERA_SIN_CUENTA_PARTICULAR",
                    socio_id=socio_id,
                    socio_nombre=socio_nombre,
                    tipo_vinculo="CUENTA_PARTICULAR_SOCIO",
                    mensaje="El socio tiene vínculos económicos habilitados, pero no tiene cuenta particular preparada.",
                    recomendacion="Prepare la cuenta particular interna del socio para conservar trazabilidad auxiliar antes de movimientos futuros.",
                    bloqueante=0,
                )

            for campo, requisitos in REQUISITOS_POR_OPERACION.items():
                if _bool_int(socio.get(campo), 0) != 1:
                    continue

                for tipo_vinculo, nombre_vinculo in requisitos:
                    if not _matriz_configurada(matriz, tipo_vinculo):
                        _agregar_alerta(
                            alertas,
                            nivel="ADVERTENCIA",
                            area="Matriz contable",
                            codigo=f"SOCIO_{tipo_vinculo}_SIN_MATRIZ_CONFIGURADA",
                            socio_id=socio_id,
                            socio_nombre=socio_nombre,
                            tipo_vinculo=tipo_vinculo,
                            mensaje=f"El socio tiene habilitado el vínculo '{nombre_vinculo}', pero la matriz no tiene cuenta configurada.",
                            recomendacion="Configure la cuenta del Plan Maestro FF y/o la cuenta empresa para ese vínculo antes de permitir movimientos reales.",
                            bloqueante=0,
                        )

            if _bool_int(socio.get("admite_honorarios"), 0) == 1:
                if not _texto(socio.get("proveedor_vinculado_referencia")):
                    _agregar_alerta(
                        alertas,
                        nivel="ADVERTENCIA",
                        area="Proveedor vinculado",
                        codigo="SOCIO_HONORARIOS_SIN_PROVEEDOR_VINCULADO",
                        socio_id=socio_id,
                        socio_nombre=socio_nombre,
                        tipo_vinculo="HONORARIOS_SERVICIOS_SOCIO",
                        mensaje="El socio admite honorarios/servicios, pero no tiene referencia de proveedor vinculado.",
                        recomendacion="Complete la referencia del proveedor vinculado o deje documentado que se cargará al registrar el comprobante.",
                        bloqueante=0,
                    )

            if _bool_int(socio.get("admite_facturas_proveedor"), 0) == 1:
                condicion = _normalizar_codigo(socio.get("condicion_fiscal"))
                if not condicion or condicion == "NO_INFORMADA":
                    _agregar_alerta(
                        alertas,
                        nivel="INFORMATIVO",
                        area="Proveedor vinculado",
                        codigo="SOCIO_FACTURA_PROVEEDOR_SIN_CONDICION_FISCAL",
                        socio_id=socio_id,
                        socio_nombre=socio_nombre,
                        tipo_vinculo="FACTURA_PROVEEDOR_SOCIO",
                        mensaje="El socio admite facturas de proveedor, pero su condición fiscal no está informada.",
                        recomendacion="Complete la condición fiscal del socio para facilitar validaciones futuras en compras/pagos.",
                        bloqueante=0,
                    )

            if _bool_int(socio.get("cuenta_particular_habilitada"), 0) == 1:
                if not _texto(socio.get("cuenta_particular_codigo")):
                    _agregar_alerta(
                        alertas,
                        nivel="ADVERTENCIA",
                        area="Cuenta particular",
                        codigo="SOCIO_CUENTA_PARTICULAR_SIN_CODIGO",
                        socio_id=socio_id,
                        socio_nombre=socio_nombre,
                        tipo_vinculo="CUENTA_PARTICULAR_SOCIO",
                        mensaje="El socio tiene cuenta particular habilitada, pero no tiene código interno preparado.",
                        recomendacion="Use la acción Preparar cuenta particular desde la ficha integral del socio.",
                        bloqueante=0,
                    )

        alertas_criticas = [a for a in alertas if a["nivel"] == "CRITICO"]
        advertencias = [a for a in alertas if a["nivel"] == "ADVERTENCIA"]
        informativas = [a for a in alertas if a["nivel"] == "INFORMATIVO"]

        socios_con_alertas = {
            a["socio_id"]
            for a in alertas
            if _texto(a.get("socio_id"))
        }

        detalle_por_socio: list[dict[str, Any]] = []
        for _, socio_row in socios.iterrows():
            socio = socio_row.to_dict()
            sid = _texto(socio.get("id"))
            alertas_socio = [a for a in alertas if _texto(a.get("socio_id")) == sid]
            detalle_por_socio.append(
                {
                    "socio_id": sid,
                    "socio_nombre": _texto(socio.get("nombre")) or f"Socio #{sid}",
                    "rol_relacion": _texto(socio.get("rol_relacion") or socio.get("tipo_socio")),
                    "condicion_fiscal": _texto(socio.get("condicion_fiscal")),
                    "cuenta_particular_habilitada": _bool_int(socio.get("cuenta_particular_habilitada"), 0),
                    "proveedor_vinculado_referencia": _texto(socio.get("proveedor_vinculado_referencia")),
                    "alertas": len(alertas_socio),
                    "criticas": sum(1 for a in alertas_socio if a["nivel"] == "CRITICO"),
                    "advertencias": sum(1 for a in alertas_socio if a["nivel"] == "ADVERTENCIA"),
                    "informativas": sum(1 for a in alertas_socio if a["nivel"] == "INFORMATIVO"),
                }
            )

        return {
            "ok": True,
            "empresa_id": int(empresa_id),
            "empresa_es_sociedad": es_sociedad,
            "registra_movimientos": False,
            "genera_asientos": False,
            "total_socios": int(len(socios)),
            "socios_con_alertas": int(len(socios_con_alertas)),
            "total_alertas": int(len(alertas)),
            "criticas": int(len(alertas_criticas)),
            "advertencias": int(len(advertencias)),
            "informativas": int(len(informativas)),
            "alertas": alertas,
            "detalle_por_socio": detalle_por_socio,
            "matriz": {
                "total": int(diagnostico_matriz.get("total") or 0),
                "configuradas": int(diagnostico_matriz.get("configuradas") or 0),
                "pendientes": int(diagnostico_matriz.get("pendientes") or 0),
                "porcentaje_configurado": float(diagnostico_matriz.get("porcentaje_configurado") or 0),
            },
            "estados_matriz_relevantes": {
                tipo: _estado_matriz(matriz, tipo)
                for tipo in [
                    "CAPITAL_SUSCRIPTO",
                    "INTEGRACION_CAPITAL",
                    "PRESTAMO_SOCIO_EMPRESA",
                    "DEVOLUCION_PRESTAMO_SOCIO",
                    "RETIRO_SOCIO",
                    "REINTEGRO_SOCIO",
                    "HONORARIOS_SERVICIOS_SOCIO",
                    "FACTURA_PROVEEDOR_SOCIO",
                    "CUENTA_PARTICULAR_SOCIO",
                ]
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "empresa_id": int(empresa_id),
            "error": str(exc),
            "registra_movimientos": False,
            "genera_asientos": False,
            "total_socios": 0,
            "socios_con_alertas": 0,
            "total_alertas": 1,
            "criticas": 0,
            "advertencias": 1,
            "informativas": 0,
            "alertas": [
                {
                    "nivel": "ADVERTENCIA",
                    "area": "Control de socios",
                    "codigo": "CONTROL_VINCULOS_SOCIOS_NO_DISPONIBLE",
                    "socio_id": "",
                    "socio_nombre": "",
                    "tipo_vinculo": "",
                    "mensaje": "No se pudo ejecutar el control normativo y operativo de vínculos con socios.",
                    "recomendacion": "Revisar el detalle técnico sin bloquear el resto de Configuración.",
                    "bloqueante": 0,
                }
            ],
            "detalle_por_socio": [],
            "matriz": {},
            "estados_matriz_relevantes": {},
        }
    finally:
        if propia:
            conn.close()


def listar_alertas_control_vinculos_socios(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    resultado = controlar_vinculos_socios(empresa_id=empresa_id, conn=conn)
    return pd.DataFrame(resultado.get("alertas") or [])


def listar_detalle_control_vinculos_por_socio(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    resultado = controlar_vinculos_socios(empresa_id=empresa_id, conn=conn)
    return pd.DataFrame(resultado.get("detalle_por_socio") or [])


def resumir_control_vinculos_socios(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    resultado = controlar_vinculos_socios(empresa_id=empresa_id, conn=conn)
    return {
        "ok": resultado.get("ok", False),
        "total_socios": resultado.get("total_socios", 0),
        "socios_con_alertas": resultado.get("socios_con_alertas", 0),
        "total_alertas": resultado.get("total_alertas", 0),
        "criticas": resultado.get("criticas", 0),
        "advertencias": resultado.get("advertencias", 0),
        "informativas": resultado.get("informativas", 0),
        "matriz": resultado.get("matriz", {}),
        "registra_movimientos": False,
        "genera_asientos": False,
    }