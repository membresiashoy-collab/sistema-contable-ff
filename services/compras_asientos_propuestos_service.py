from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import re
import sqlite3

import pandas as pd

from database import conectar
from services.asientos_origen_service import crear_asiento_origen


ORIGEN_COMPRA = "COMPRA_ARCA"
TABLA_COMPRAS = "compras_comprobantes"

USOS_PROVEEDORES = (
    "PROVEEDORES_CC",
    "PROVEEDORES",
    "DEUDAS_COMERCIALES_PROVEEDORES",
    "DEUDAS_COMERCIALES",
)

USOS_FISCALES_COMPRA = {
    "IVA_CREDITO_FISCAL": ("IVA_CREDITO_FISCAL", "IVA_CREDITO"),
    "PERCEPCION_IVA": ("PERCEPCION_IVA", "PERCEPCIONES_IVA"),
    "PERCEPCION_IIBB": ("PERCEPCION_IIBB", "PERCEPCIONES_IIBB"),
    "PERCEPCION_GANANCIAS": ("PERCEPCION_GANANCIAS", "PERCEPCIONES_GANANCIAS"),
    "PERCEPCION_OTROS_NACIONALES": (
        "PERCEPCION_OTROS_NACIONALES",
        "PERCEPCION_OTROS_IMP_NAC",
        "PERCEPCIONES_OTROS_NACIONALES",
    ),
    "PERCEPCION_MUNICIPAL": ("PERCEPCION_MUNICIPAL", "PERCEPCIONES_MUNICIPALES"),
    "IVA_NO_COMPUTABLE_MAYOR_COSTO": (
        "IVA_NO_COMPUTABLE_MAYOR_COSTO",
        "IVA_NO_COMPUTABLE",
    ),
    "TRIBUTOS_NO_RECUPERABLES": (
        "TRIBUTOS_NO_RECUPERABLES",
        "IMPUESTOS_TASAS_CONTRIBUCIONES",
    ),
}


@dataclass(frozen=True)
class CuentaContable:
    codigo: str
    nombre: str
    origen_resolucion: str = ""


class ErrorContableCompras(Exception):
    """Error controlado al preparar asientos de compras importadas."""


def _conexion(conn: Optional[sqlite3.Connection] = None) -> Tuple[sqlite3.Connection, bool]:
    if conn is not None:
        return conn, False
    return conectar(), True


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    fila = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (tabla,),
    ).fetchone()
    return fila is not None


def _columnas(conn: sqlite3.Connection, tabla: str) -> set[str]:
    if not _tabla_existe(conn, tabla):
        return set()
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _valor(fila: Any, campo: str, default: Any = None) -> Any:
    if fila is None:
        return default
    if isinstance(fila, dict):
        return fila.get(campo, default)
    try:
        return fila[campo]
    except Exception:
        return default


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
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _numero(valor: Any) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    texto = str(valor).strip()
    if texto == "":
        return 0.0
    texto = texto.replace("$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return round(float(texto), 2)
    except Exception:
        return 0.0


def _fila_a_dict(cursor: sqlite3.Cursor, fila: Any) -> Optional[dict[str, Any]]:
    if fila is None:
        return None
    columnas = [col[0] for col in cursor.description]
    return dict(zip(columnas, fila))


def _query_uno(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[dict[str, Any]]:
    cur = conn.execute(sql, tuple(params))
    return _fila_a_dict(cur, cur.fetchone())


def _query_todos(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur = conn.execute(sql, tuple(params))
    columnas = [col[0] for col in cur.description]
    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def _limpiar_cuenta(cuenta: Optional[CuentaContable]) -> Optional[CuentaContable]:
    if cuenta is None:
        return None
    codigo = _texto(cuenta.codigo)
    nombre = _texto(cuenta.nombre)
    if not codigo or not nombre:
        return None
    return CuentaContable(codigo=codigo, nombre=nombre, origen_resolucion=cuenta.origen_resolucion)


def _cuenta_por_id(conn: sqlite3.Connection, cuenta_id: Any) -> Optional[CuentaContable]:
    cuenta_id_int = int(_numero(cuenta_id))
    if cuenta_id_int <= 0 or not _tabla_existe(conn, "plan_cuentas_empresa"):
        return None

    fila = _query_uno(
        conn,
        """
        SELECT codigo, nombre
        FROM plan_cuentas_empresa
        WHERE id = ?
          AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
          AND COALESCE(imputable, 0) = 1
        LIMIT 1
        """,
        (cuenta_id_int,),
    )
    if not fila:
        return None
    return CuentaContable(
        codigo=_texto(fila["codigo"]),
        nombre=_texto(fila["nombre"]),
        origen_resolucion="plan_cuentas_empresa.id",
    )


def _cuenta_por_codigo(conn: sqlite3.Connection, codigo: Any, empresa_id: int) -> Optional[CuentaContable]:
    codigo_txt = _texto(codigo)
    if not codigo_txt or not _tabla_existe(conn, "plan_cuentas_empresa"):
        return None

    fila = _query_uno(
        conn,
        """
        SELECT codigo, nombre
        FROM plan_cuentas_empresa
        WHERE COALESCE(empresa_id, 1) = ?
          AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
          AND COALESCE(imputable, 0) = 1
          AND codigo = ?
        LIMIT 1
        """,
        (empresa_id, codigo_txt),
    )
    if not fila:
        return None
    return CuentaContable(
        codigo=_texto(fila["codigo"]),
        nombre=_texto(fila["nombre"]),
        origen_resolucion="plan_cuentas_empresa.codigo",
    )


def _cuenta_por_nombre(conn: sqlite3.Connection, nombre: Any, empresa_id: int) -> Optional[CuentaContable]:
    nombre_n = _normalizar(nombre)
    if not nombre_n or not _tabla_existe(conn, "plan_cuentas_empresa"):
        return None

    filas = _query_todos(
        conn,
        """
        SELECT codigo, nombre
        FROM plan_cuentas_empresa
        WHERE COALESCE(empresa_id, 1) = ?
          AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
          AND COALESCE(imputable, 0) = 1
        """,
        (empresa_id,),
    )
    for fila in filas:
        if _normalizar(fila.get("nombre")) == nombre_n:
            return CuentaContable(
                codigo=_texto(fila["codigo"]),
                nombre=_texto(fila["nombre"]),
                origen_resolucion="plan_cuentas_empresa.nombre",
            )
    return None


def _cuentas_por_uso(
    conn: sqlite3.Connection,
    empresa_id: int,
    usos: Iterable[str],
) -> list[CuentaContable]:
    usos_n = [_texto(uso).upper() for uso in usos if _texto(uso)]
    if not usos_n or not _tabla_existe(conn, "plan_cuentas_empresa"):
        return []

    placeholders = ", ".join("?" for _ in usos_n)
    filas = _query_todos(
        conn,
        f"""
        SELECT codigo, nombre, uso_operativo_sistema
        FROM plan_cuentas_empresa
        WHERE COALESCE(empresa_id, 1) = ?
          AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
          AND COALESCE(imputable, 0) = 1
          AND UPPER(COALESCE(uso_operativo_sistema, '')) IN ({placeholders})
        ORDER BY codigo
        """,
        (empresa_id, *usos_n),
    )
    return [
        CuentaContable(
            codigo=_texto(fila["codigo"]),
            nombre=_texto(fila["nombre"]),
            origen_resolucion=f"uso_operativo_sistema:{_texto(fila.get('uso_operativo_sistema'))}",
        )
        for fila in filas
    ]


def _uso_por_id(conn: sqlite3.Connection, uso_id: Any) -> str:
    uso_id_int = int(_numero(uso_id))
    if uso_id_int <= 0 or not _tabla_existe(conn, "usos_operativos_contables"):
        return ""
    fila = _query_uno(
        conn,
        "SELECT codigo FROM usos_operativos_contables WHERE id = ? AND COALESCE(activo, 1) = 1",
        (uso_id_int,),
    )
    return _texto(fila.get("codigo")) if fila else ""


def _score_cuenta(categoria: str, cuenta: CuentaContable) -> int:
    categoria_n = _normalizar(categoria)
    cuenta_n = _normalizar(cuenta.nombre)
    if not categoria_n or not cuenta_n:
        return 0

    score = 0
    if categoria_n == cuenta_n:
        score += 100
    if categoria_n in cuenta_n or cuenta_n in categoria_n:
        score += 50

    tokens = [t for t in categoria_n.split() if len(t) >= 4]
    for token in tokens:
        if token in cuenta_n:
            score += 10

    penalizaciones = {
        "MERCADERIA": ["BANCO", "CAJA", "IVA", "PROVEEDOR"],
        "ALQUILER": ["BANCO", "CAJA", "IVA", "PROVEEDOR"],
        "COMBUSTIBLE": ["BANCO", "CAJA", "IVA", "PROVEEDOR"],
        "LIBRERIA": ["BANCO", "CAJA", "IVA", "PROVEEDOR"],
        "HONORARIO": ["BANCO", "CAJA", "IVA", "PROVEEDOR"],
    }
    for token, prohibidos in penalizaciones.items():
        if token in categoria_n and any(p in cuenta_n for p in prohibidos):
            score -= 50

    return score


def _elegir_mejor_cuenta(categoria: str, cuentas: list[CuentaContable]) -> Optional[CuentaContable]:
    if not cuentas:
        return None
    if len(cuentas) == 1:
        return cuentas[0]

    ordenadas = sorted(cuentas, key=lambda cuenta: (_score_cuenta(categoria, cuenta), cuenta.codigo), reverse=True)
    mejor = ordenadas[0]
    segundo = ordenadas[1]
    if _score_cuenta(categoria, mejor) <= 0:
        return None
    if _score_cuenta(categoria, mejor) == _score_cuenta(categoria, segundo):
        return None
    return mejor


def _categoria_config(conn: sqlite3.Connection, empresa_id: int, categoria: str) -> Optional[dict[str, Any]]:
    if not categoria or not _tabla_existe(conn, "categorias_compra_config"):
        return None
    return _query_uno(
        conn,
        """
        SELECT *
        FROM categorias_compra_config
        WHERE COALESCE(empresa_id, 1) = ?
          AND UPPER(TRIM(categoria)) = UPPER(TRIM(?))
          AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
        LIMIT 1
        """,
        (empresa_id, categoria),
    )


def _categoria_legacy(conn: sqlite3.Connection, empresa_id: int, categoria: str) -> Optional[dict[str, Any]]:
    if not categoria or not _tabla_existe(conn, "categorias_compra"):
        return None
    return _query_uno(
        conn,
        """
        SELECT *
        FROM categorias_compra
        WHERE COALESCE(empresa_id, 1) = ?
          AND UPPER(TRIM(categoria)) = UPPER(TRIM(?))
          AND COALESCE(activo, 1) = 1
        LIMIT 1
        """,
        (empresa_id, categoria),
    )


def resolver_cuenta_principal_compra(
    conn: sqlite3.Connection,
    compra: dict[str, Any],
    empresa_id: int,
) -> CuentaContable:
    categoria = _texto(compra.get("categoria_compra"))
    if not categoria:
        raise ErrorContableCompras("La compra no tiene categoria_compra definida.")

    config = _categoria_config(conn, empresa_id, categoria)
    legacy = _categoria_legacy(conn, empresa_id, categoria)

    if config:
        cuenta = _limpiar_cuenta(_cuenta_por_id(conn, config.get("cuenta_sugerida_id")))
        if cuenta:
            return CuentaContable(cuenta.codigo, cuenta.nombre, "categorias_compra_config.cuenta_sugerida_id")

    for codigo in (
        compra.get("cuenta_principal_codigo"),
        legacy.get("cuenta_codigo") if legacy else None,
    ):
        cuenta = _limpiar_cuenta(_cuenta_por_codigo(conn, codigo, empresa_id))
        if cuenta:
            return cuenta

    if config:
        uso_codigo = _uso_por_id(conn, config.get("uso_operativo_principal_id"))
        if uso_codigo:
            candidatos = _cuentas_por_uso(conn, empresa_id, (uso_codigo,))
            cuenta = _elegir_mejor_cuenta(categoria, candidatos)
            if cuenta:
                return cuenta

    for nombre in (
        compra.get("cuenta_principal_nombre"),
        legacy.get("cuenta_nombre") if legacy else None,
    ):
        cuenta = _limpiar_cuenta(_cuenta_por_nombre(conn, nombre, empresa_id))
        if cuenta:
            return cuenta

    raise ErrorContableCompras(
        f"No se pudo resolver una cuenta imputable activa del Plan Empresa para la categoría de compra '{categoria}'."
    )


def resolver_cuenta_proveedor(
    conn: sqlite3.Connection,
    compra: dict[str, Any],
    empresa_id: int,
) -> CuentaContable:
    categoria = _texto(compra.get("categoria_compra"))
    legacy = _categoria_legacy(conn, empresa_id, categoria) if categoria else None

    candidatos = _cuentas_por_uso(conn, empresa_id, USOS_PROVEEDORES)
    cuenta = _elegir_mejor_cuenta("PROVEEDORES", candidatos)
    if cuenta:
        return cuenta

    for codigo in (
        compra.get("cuenta_proveedor_codigo"),
        legacy.get("cuenta_proveedor_codigo") if legacy else None,
    ):
        cuenta = _limpiar_cuenta(_cuenta_por_codigo(conn, codigo, empresa_id))
        if cuenta:
            return cuenta

    for nombre in (
        compra.get("cuenta_proveedor_nombre"),
        legacy.get("cuenta_proveedor_nombre") if legacy else None,
        "Proveedores",
    ):
        cuenta = _limpiar_cuenta(_cuenta_por_nombre(conn, nombre, empresa_id))
        if cuenta:
            return cuenta

    raise ErrorContableCompras("No se pudo resolver la cuenta de proveedores en el Plan Empresa.")


def resolver_cuenta_fiscal(
    conn: sqlite3.Connection,
    empresa_id: int,
    concepto: str,
) -> CuentaContable:
    usos = USOS_FISCALES_COMPRA.get(concepto, (concepto,))
    candidatos = _cuentas_por_uso(conn, empresa_id, usos)
    cuenta = _elegir_mejor_cuenta(concepto, candidatos)
    if cuenta:
        return cuenta

    cuenta = _cuenta_por_nombre(conn, concepto.replace("_", " "), empresa_id)
    if cuenta:
        return cuenta

    raise ErrorContableCompras(f"No se pudo resolver la cuenta fiscal '{concepto}' en el Plan Empresa.")


def _agregar_linea(
    lineas: list[dict[str, Any]],
    cuenta: CuentaContable,
    importe: float,
    glosa: str,
    naturaleza_deudora: bool = True,
) -> None:
    importe = round(float(importe or 0), 2)
    if abs(importe) < 0.01:
        return

    debe = 0.0
    haber = 0.0

    if naturaleza_deudora:
        if importe > 0:
            debe = importe
        else:
            haber = abs(importe)
    else:
        if importe > 0:
            haber = importe
        else:
            debe = abs(importe)

    lineas.append(
        {
            "cuenta_codigo": cuenta.codigo,
            "cuenta_nombre": cuenta.nombre,
            "debe": round(debe, 2),
            "haber": round(haber, 2),
            "glosa": glosa,
        }
    )


def _sumar_lineas(lineas: list[dict[str, Any]]) -> tuple[float, float]:
    debe = round(sum(_numero(linea.get("debe")) for linea in lineas), 2)
    haber = round(sum(_numero(linea.get("haber")) for linea in lineas), 2)
    return debe, haber


def _clave_compra(compra: dict[str, Any], empresa_id: int) -> str:
    compra_id = int(_numero(compra.get("id")))
    return f"COMPRA:{empresa_id}:{compra_id}"


def _asiento_existente(conn: sqlite3.Connection, compra: dict[str, Any], empresa_id: int) -> Optional[dict[str, Any]]:
    referencia = _clave_compra(compra, empresa_id)
    if _tabla_existe(conn, "asientos_origen"):
        fila = _query_uno(
            conn,
            """
            SELECT id, asiento_propuesto_id, estado
            FROM asientos_origen
            WHERE COALESCE(empresa_id, 1) = ?
              AND tipo_origen = ?
              AND referencia = ?
              AND COALESCE(estado, '') <> 'ANULADO'
            ORDER BY id DESC
            LIMIT 1
            """,
            (empresa_id, ORIGEN_COMPRA, referencia),
        )
        if fila:
            return fila

    if _tabla_existe(conn, "asientos_propuestos"):
        fila = _query_uno(
            conn,
            """
            SELECT id, estado
            FROM asientos_propuestos
            WHERE COALESCE(empresa_id, 1) = ?
              AND origen = ?
              AND referencia = ?
              AND COALESCE(estado, '') <> 'ANULADO'
            ORDER BY id DESC
            LIMIT 1
            """,
            (empresa_id, ORIGEN_COMPRA, referencia),
        )
        if fila:
            return {"asiento_propuesto_id": fila["id"], "estado": fila.get("estado")}

    return None


def _leer_compra(conn: sqlite3.Connection, compra_id: int, empresa_id: int) -> dict[str, Any]:
    if not _tabla_existe(conn, TABLA_COMPRAS):
        raise ErrorContableCompras("No existe la tabla compras_comprobantes.")

    fila = _query_uno(
        conn,
        f"""
        SELECT *
        FROM {TABLA_COMPRAS}
        WHERE id = ?
          AND COALESCE(empresa_id, 1) = ?
        LIMIT 1
        """,
        (int(compra_id), int(empresa_id)),
    )
    if not fila:
        raise ErrorContableCompras(f"No existe la compra id={compra_id} para empresa_id={empresa_id}.")
    return fila


def preparar_lineas_asiento_compra(
    compra: dict[str, Any],
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        cuenta_principal = resolver_cuenta_principal_compra(conexion, compra, empresa_id)
        cuenta_proveedor = resolver_cuenta_proveedor(conexion, compra, empresa_id)

        neto = _numero(compra.get("neto"))
        importe_no_gravado = _numero(compra.get("importe_no_gravado"))
        importe_exento = _numero(compra.get("importe_exento"))

        iva_total = _numero(compra.get("iva_total"))
        if abs(iva_total) < 0.01:
            iva_total = _numero(compra.get("iva"))

        iva_computable = _numero(compra.get("iva_computable_sistema"))
        if abs(iva_computable) < 0.01:
            iva_computable = _numero(compra.get("credito_fiscal_computable"))
        if abs(iva_computable) < 0.01:
            iva_computable = iva_total

        iva_no_computable = _numero(compra.get("iva_no_computable_sistema"))
        if abs(iva_no_computable) < 0.01:
            iva_no_computable = _numero(compra.get("iva_no_computable"))
        if abs(iva_no_computable) < 0.01:
            iva_no_computable = round(iva_total - iva_computable, 2)

        percepcion_iva = _numero(compra.get("percepcion_iva"))
        percepcion_iibb = _numero(compra.get("percepcion_iibb"))
        percepcion_otros = _numero(compra.get("percepcion_otros_imp_nac"))
        impuestos_municipales = _numero(compra.get("impuestos_municipales"))
        impuestos_internos = _numero(compra.get("impuestos_internos"))
        otros_tributos = _numero(compra.get("otros_tributos"))

        categoria = _texto(compra.get("categoria_compra"))
        comprobante = f"{_texto(compra.get('tipo'))} {_texto(compra.get('punto_venta'))}-{_texto(compra.get('numero'))}".strip()
        proveedor = _texto(compra.get("proveedor")) or _texto(compra.get("cuit"))
        glosa_base = f"Compra {comprobante} {proveedor}".strip()

        lineas: list[dict[str, Any]] = []

        principal_importe = round(
            neto
            + importe_no_gravado
            + importe_exento
            + max(iva_no_computable, 0)
            + impuestos_municipales
            + impuestos_internos
            + otros_tributos,
            2,
        )
        _agregar_linea(
            lineas,
            cuenta_principal,
            principal_importe,
            f"{glosa_base} - {categoria}",
            naturaleza_deudora=True,
        )

        if abs(iva_computable) >= 0.01:
            cuenta_iva = resolver_cuenta_fiscal(conexion, empresa_id, "IVA_CREDITO_FISCAL")
            _agregar_linea(
                lineas,
                cuenta_iva,
                iva_computable,
                f"{glosa_base} - IVA crédito fiscal computable",
                naturaleza_deudora=True,
            )

        for concepto, importe, glosa in (
            ("PERCEPCION_IVA", percepcion_iva, "Percepción IVA"),
            ("PERCEPCION_IIBB", percepcion_iibb, "Percepción IIBB"),
            ("PERCEPCION_OTROS_NACIONALES", percepcion_otros, "Percepción otros impuestos nacionales"),
        ):
            if abs(importe) >= 0.01:
                cuenta = resolver_cuenta_fiscal(conexion, empresa_id, concepto)
                _agregar_linea(
                    lineas,
                    cuenta,
                    importe,
                    f"{glosa_base} - {glosa}",
                    naturaleza_deudora=True,
                )

        total_debe, total_haber_sin_proveedor = _sumar_lineas(lineas)
        saldo_a_proveedor = round(total_debe - total_haber_sin_proveedor, 2)
        if abs(saldo_a_proveedor) < 0.01:
            raise ErrorContableCompras("La compra no genera saldo contable a proveedor.")

        total_comprobante = _numero(compra.get("total"))
        diferencia_total = round(abs(abs(saldo_a_proveedor) - abs(total_comprobante)), 2)
        advertencias: list[str] = []
        if abs(total_comprobante) >= 0.01 and diferencia_total > 0.05:
            advertencias.append(
                f"El total del comprobante ({total_comprobante}) difiere del total contable calculado ({saldo_a_proveedor})."
            )

        _agregar_linea(
            lineas,
            cuenta_proveedor,
            saldo_a_proveedor,
            f"{glosa_base} - Proveedor",
            naturaleza_deudora=False,
        )

        total_debe, total_haber = _sumar_lineas(lineas)
        diferencia = round(total_debe - total_haber, 2)
        if abs(diferencia) > 0.01:
            raise ErrorContableCompras(f"El asiento preparado queda desbalanceado por {diferencia}.")

        return {
            "ok": True,
            "compra_id": int(_numero(compra.get("id"))),
            "referencia": _clave_compra(compra, empresa_id),
            "descripcion": f"Compra importada ARCA {comprobante} - {proveedor}".strip(),
            "lineas": lineas,
            "total_debe": total_debe,
            "total_haber": total_haber,
            "diferencia": diferencia,
            "advertencias": advertencias,
        }
    finally:
        if cerrar:
            conexion.close()


def generar_asiento_propuesto_compra(
    compra_id: int,
    empresa_id: int = 1,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        compra = _leer_compra(conexion, int(compra_id), int(empresa_id))

        existente = _asiento_existente(conexion, compra, int(empresa_id))
        if existente:
            return {
                "ok": True,
                "estado": "YA_EXISTE",
                "compra_id": int(compra_id),
                "asiento_propuesto_id": existente.get("asiento_propuesto_id"),
                "mensaje": "La compra ya tiene un asiento propuesto no anulado.",
            }

        preparado = preparar_lineas_asiento_compra(compra, empresa_id=int(empresa_id), conn=conexion)

        resultado = crear_asiento_origen(
            empresa_id=int(empresa_id),
            fecha=_texto(compra.get("fecha")),
            tipo_origen=ORIGEN_COMPRA,
            descripcion=preparado["descripcion"],
            lineas=preparado["lineas"],
            ejercicio_id=None,
            referencia=preparado["referencia"],
            observaciones=(
                f"Origen real: {TABLA_COMPRAS}.id={compra_id}. "
                "Generado desde comprobante de compra importado/clasificado."
            ),
            usuario=usuario,
            generar_propuesta=True,
        )

        if not resultado or not resultado.get("ok", False):
            return {
                "ok": False,
                "estado": "ERROR",
                "compra_id": int(compra_id),
                "mensaje": (resultado or {}).get("mensaje", "No se pudo crear el asiento propuesto."),
                "detalle": resultado,
            }

        return {
            "ok": True,
            "estado": "GENERADO",
            "compra_id": int(compra_id),
            "asiento_origen_id": resultado.get("asiento_origen_id") or resultado.get("id"),
            "asiento_propuesto_id": resultado.get("asiento_propuesto_id"),
            "total_debe": preparado["total_debe"],
            "total_haber": preparado["total_haber"],
            "advertencias": preparado.get("advertencias", []),
            "mensaje": "Asiento propuesto de compra generado en Bandeja.",
        }
    except ErrorContableCompras as exc:
        return {"ok": False, "estado": "ERROR_VALIDACION", "compra_id": int(compra_id), "mensaje": str(exc)}
    except Exception as exc:
        return {"ok": False, "estado": "ERROR_TECNICO", "compra_id": int(compra_id), "mensaje": str(exc)}
    finally:
        if cerrar:
            conexion.close()


def listar_compras_pendientes_asiento(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        if not _tabla_existe(conexion, TABLA_COMPRAS):
            return pd.DataFrame()

        sql = f"""
            SELECT c.*
            FROM {TABLA_COMPRAS} c
            WHERE COALESCE(c.empresa_id, 1) = ?
              AND COALESCE(TRIM(c.categoria_compra), '') <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM asientos_origen ao
                  WHERE COALESCE(ao.empresa_id, 1) = COALESCE(c.empresa_id, 1)
                    AND ao.tipo_origen = ?
                    AND ao.referencia = ('COMPRA:' || COALESCE(c.empresa_id, 1) || ':' || c.id)
                    AND COALESCE(ao.estado, '') <> 'ANULADO'
              )
            ORDER BY c.fecha, c.id
        """
        return pd.read_sql_query(sql, conexion, params=(int(empresa_id), ORIGEN_COMPRA))
    finally:
        if cerrar:
            conexion.close()


def generar_asientos_propuestos_compras_importadas(
    empresa_id: int = 1,
    usuario: str = "sistema",
    limite: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        pendientes = listar_compras_pendientes_asiento(empresa_id=int(empresa_id), conn=conexion)
        if limite is not None and int(limite) > 0:
            pendientes = pendientes.head(int(limite))

        resultados: list[dict[str, Any]] = []
        for _, fila in pendientes.iterrows():
            compra_id = int(fila["id"])
            resultados.append(
                generar_asiento_propuesto_compra(
                    compra_id=compra_id,
                    empresa_id=int(empresa_id),
                    usuario=usuario,
                    conn=conexion,
                )
            )

        generados = sum(1 for r in resultados if r.get("estado") == "GENERADO")
        existentes = sum(1 for r in resultados if r.get("estado") == "YA_EXISTE")
        errores = [r for r in resultados if not r.get("ok", False)]

        return {
            "ok": not errores,
            "empresa_id": int(empresa_id),
            "pendientes_detectadas": int(len(pendientes)),
            "generados": generados,
            "ya_existentes": existentes,
            "errores": len(errores),
            "resultados": resultados,
        }
    finally:
        if cerrar:
            conexion.close()


def simular_asiento_compra(
    compra_id: int,
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        compra = _leer_compra(conexion, int(compra_id), int(empresa_id))
        return preparar_lineas_asiento_compra(compra, empresa_id=int(empresa_id), conn=conexion)
    except ErrorContableCompras as exc:
        return {"ok": False, "estado": "ERROR_VALIDACION", "compra_id": int(compra_id), "mensaje": str(exc)}
    except Exception as exc:
        return {"ok": False, "estado": "ERROR_TECNICO", "compra_id": int(compra_id), "mensaje": str(exc)}
    finally:
        if cerrar:
            conexion.close()


__all__ = [
    "ORIGEN_COMPRA",
    "generar_asiento_propuesto_compra",
    "generar_asientos_propuestos_compras_importadas",
    "listar_compras_pendientes_asiento",
    "preparar_lineas_asiento_compra",
    "resolver_cuenta_principal_compra",
    "resolver_cuenta_proveedor",
    "simular_asiento_compra",
]