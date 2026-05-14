from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional, Tuple
import re
import sqlite3

import pandas as pd

from database import conectar
from services.asientos_origen_service import crear_asiento_origen
from services.ventas_actividades_service import (
    TABLA_ACTIVIDADES,
    TABLA_VENTAS,
    asegurar_estructura_ventas_actividades,
)


ORIGEN_VENTA = "VENTA_ARCA"

TRATAMIENTOS_SIN_IVA_DEBITO = {"EXENTO", "NO_GRAVADO", "EXPORTACION"}

USOS_CLIENTES = (
    "CLIENTES_CC",
    "DEUDORES_POR_VENTAS",
    "DEUDORES_VENTAS",
    "CUENTAS_A_COBRAR_CLIENTES",
)

USOS_IVA_DEBITO = (
    "IVA_DEBITO_FISCAL",
    "IVA_DEBITO",
    "IVA_A_PAGAR",
)

USOS_POR_TIPO_VENTA = {
    "VENTA_MERCADERIAS": (
        "VENTAS_MERCADERIAS",
        "VENTA_MERCADERIAS",
        "VENTAS_PRODUCTOS",
        "VENTAS_BIENES",
        "INGRESOS_VENTAS",
        "INGRESOS_OPERATIVOS",
    ),
    "VENTA_SERVICIOS": (
        "VENTAS_SERVICIOS",
        "INGRESOS_SERVICIOS",
        "SERVICIOS_PRESTADOS",
        "INGRESOS_OPERATIVOS",
    ),
    "EXPORTACION_BIENES": (
        "EXPORTACION_BIENES",
        "VENTAS_EXPORTACION",
        "INGRESOS_EXPORTACION",
        "INGRESOS_OPERATIVOS",
    ),
    "EXPORTACION_SERVICIOS": (
        "EXPORTACION_SERVICIOS",
        "VENTAS_EXPORTACION",
        "INGRESOS_EXPORTACION",
        "INGRESOS_OPERATIVOS",
    ),
    "VENTA_EXENTA": (
        "VENTAS_EXENTAS",
        "INGRESOS_EXENTOS",
        "INGRESOS_OPERATIVOS",
    ),
    "VENTA_NO_GRAVADA": (
        "VENTAS_NO_GRAVADAS",
        "INGRESOS_NO_GRAVADOS",
        "INGRESOS_OPERATIVOS",
    ),
    "OTRA_ACTIVIDAD": (
        "INGRESOS_OPERATIVOS",
        "VENTAS",
        "INGRESOS_VENTAS",
    ),
}

CRITERIO_POR_TIPO_VENTA = {
    "VENTA_MERCADERIAS": "VENTAS MERCADERIAS BIENES",
    "VENTA_SERVICIOS": "VENTAS SERVICIOS",
    "EXPORTACION_BIENES": "EXPORTACION BIENES",
    "EXPORTACION_SERVICIOS": "EXPORTACION SERVICIOS",
    "VENTA_EXENTA": "VENTAS EXENTAS",
    "VENTA_NO_GRAVADA": "VENTAS NO GRAVADAS",
    "OTRA_ACTIVIDAD": "INGRESOS OPERATIVOS VENTAS",
}


@dataclass(frozen=True)
class CuentaContable:
    codigo: str
    nombre: str
    origen_resolucion: str = ""


class ErrorContableVentas(Exception):
    """Error controlado al preparar asientos de ventas importadas."""


def _conexion(conn: Optional[sqlite3.Connection] = None) -> Tuple[sqlite3.Connection, bool]:
    if conn is not None:
        return conn, False
    return conectar(), True


def _tabla_existe(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (tabla,),
    ).fetchone() is not None


def _columnas(conn: sqlite3.Connection, tabla: str) -> set[str]:
    if not _tabla_existe(conn, tabla):
        return set()
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


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


def _fecha_bandeja(valor: Any) -> str:
    """
    Normaliza fecha para uso interno de Bandeja.

    Regla:
    - En pantalla se muestra dd/mm/aaaa.
    - Para crear asiento propuesto se envía YYYY-MM-DD.
    """
    texto = _texto(valor)
    if not texto:
        return ""

    texto = texto.strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        return texto

    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).strftime("%Y-%m-%d")
        except Exception:
            pass

    try:
        fecha = pd.to_datetime(texto, errors="coerce", dayfirst=True)
        if pd.notna(fecha):
            return fecha.strftime("%Y-%m-%d")
    except Exception:
        pass

    return texto



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
          AND UPPER(COALESCE(CAST(estado AS TEXT), 'ACTIVA')) IN ('ACTIVA', 'ACTIVO', 'A', '1', 'S', 'SI', 'TRUE')
          AND UPPER(COALESCE(CAST(imputable AS TEXT), '1')) IN ('1', 'S', 'SI', 'TRUE')
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
          AND UPPER(COALESCE(CAST(estado AS TEXT), 'ACTIVA')) IN ('ACTIVA', 'ACTIVO', 'A', '1', 'S', 'SI', 'TRUE')
          AND UPPER(COALESCE(CAST(imputable AS TEXT), '1')) IN ('1', 'S', 'SI', 'TRUE')
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
          AND UPPER(COALESCE(CAST(estado AS TEXT), 'ACTIVA')) IN ('ACTIVA', 'ACTIVO', 'A', '1', 'S', 'SI', 'TRUE')
          AND UPPER(COALESCE(CAST(imputable AS TEXT), '1')) IN ('1', 'S', 'SI', 'TRUE')
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


def _score_cuenta(criterio: str, cuenta: CuentaContable) -> int:
    criterio_n = _normalizar(criterio)
    cuenta_n = _normalizar(cuenta.nombre)
    if not cuenta_n:
        return 0

    score = 0
    if criterio_n and criterio_n == cuenta_n:
        score += 100
    if criterio_n and (criterio_n in cuenta_n or cuenta_n in criterio_n):
        score += 50

    for token in [t for t in criterio_n.split() if len(t) >= 4]:
        if token in cuenta_n:
            score += 10

    if "SERVICIO" in criterio_n and "SERVICIO" in cuenta_n:
        score += 30
    if any(t in criterio_n for t in ("MERCADERIA", "PRODUCTO", "BIEN")) and any(
        t in cuenta_n for t in ("MERCADERIA", "PRODUCTO", "BIEN")
    ):
        score += 30
    if any(t in criterio_n for t in ("EXENTA", "EXENTO")) and any(t in cuenta_n for t in ("EXENTA", "EXENTO")):
        score += 30
    if any(t in criterio_n for t in ("EXPORTACION", "EXPORTACIONES")) and any(
        t in cuenta_n for t in ("EXPORTACION", "EXPORTACIONES")
    ):
        score += 30
    if any(t in cuenta_n for t in ("CLIENTE", "DEUDOR", "IVA", "CAJA", "BANCO", "PROVEEDOR")):
        score -= 50

    return score


def _elegir_mejor_cuenta(criterio: str, cuentas: list[CuentaContable]) -> Optional[CuentaContable]:
    if not cuentas:
        return None
    if len(cuentas) == 1:
        return cuentas[0]

    ordenadas = sorted(cuentas, key=lambda cuenta: (_score_cuenta(criterio, cuenta), cuenta.codigo), reverse=True)
    mejor = ordenadas[0]
    segundo = ordenadas[1]
    if _score_cuenta(criterio, mejor) <= 0:
        return None
    if _score_cuenta(criterio, mejor) == _score_cuenta(criterio, segundo):
        return None
    return mejor


def _actividad_venta(
    conn: sqlite3.Connection,
    venta: dict[str, Any],
    empresa_id: int,
) -> dict[str, Any]:
    """
    Devuelve la agrupación interna/comercial asignada a la venta.

    Regla de raíz:
    - Una venta no puede generar asiento propuesto en Bandeja si no tiene agrupación interna asignada.
    - No alcanza con tener tipo_venta o tratamiento_iva_venta cargados.
    - La agrupación no define cuenta contable, pero sí es obligatoria como clasificación operativa previa.
    """
    actividad_id = int(_numero(venta.get("actividad_venta_id")))

    if actividad_id <= 0:
        raise ErrorContableVentas(
            "La venta no tiene agrupación interna asignada. "
            "Asigne una agrupación comercial antes de generar el asiento propuesto en Bandeja."
        )

    if not _tabla_existe(conn, TABLA_ACTIVIDADES):
        raise ErrorContableVentas(
            "No existe la tabla de agrupaciones internas de venta. "
            "Configure las agrupaciones antes de generar asientos propuestos."
        )

    fila = _query_uno(
        conn,
        f"""
        SELECT *
        FROM {TABLA_ACTIVIDADES}
        WHERE id = ?
          AND COALESCE(empresa_id, 1) = ?
          AND COALESCE(activo, 1) = 1
        LIMIT 1
        """,
        (actividad_id, int(empresa_id)),
    )

    if not fila:
        raise ErrorContableVentas(
            "La agrupación interna asignada a la venta no existe o está inactiva. "
            "Corrija la agrupación antes de generar el asiento propuesto en Bandeja."
        )

    return fila

def resolver_cuenta_cliente(
    conn: sqlite3.Connection,
    venta: dict[str, Any],
    empresa_id: int,
) -> CuentaContable:
    for codigo in (venta.get("cuenta_cliente_codigo"), venta.get("cuenta_deudor_codigo")):
        cuenta = _limpiar_cuenta(_cuenta_por_codigo(conn, codigo, empresa_id))
        if cuenta:
            return cuenta

    candidatos = _cuentas_por_uso(conn, empresa_id, USOS_CLIENTES)
    cuenta = _elegir_mejor_cuenta("CLIENTES", candidatos)
    if cuenta:
        return cuenta

    for nombre in (venta.get("cuenta_cliente_nombre"), venta.get("cuenta_deudor_nombre"), "Deudores por Ventas", "Clientes"):
        cuenta = _limpiar_cuenta(_cuenta_por_nombre(conn, nombre, empresa_id))
        if cuenta:
            return cuenta

    raise ErrorContableVentas("No se pudo resolver la cuenta de clientes/deudores por ventas en el Plan Empresa.")


def resolver_cuenta_iva_debito(
    conn: sqlite3.Connection,
    empresa_id: int,
) -> CuentaContable:
    candidatos = _cuentas_por_uso(conn, empresa_id, USOS_IVA_DEBITO)
    cuenta = _elegir_mejor_cuenta("IVA DEBITO FISCAL", candidatos)
    if cuenta:
        return cuenta

    for nombre in ("IVA Débito Fiscal", "IVA Debito Fiscal", "IVA débito fiscal", "IVA a pagar"):
        cuenta = _limpiar_cuenta(_cuenta_por_nombre(conn, nombre, empresa_id))
        if cuenta:
            return cuenta

    raise ErrorContableVentas("No se pudo resolver la cuenta de IVA débito fiscal en el Plan Empresa.")


def resolver_cuenta_ventas(
    conn: sqlite3.Connection,
    venta: dict[str, Any],
    empresa_id: int,
) -> CuentaContable:
    actividad = _actividad_venta(conn, venta, empresa_id)
    tipo_venta = _texto(actividad.get("tipo_venta")) or _texto(venta.get("tipo_venta")) or "OTRA_ACTIVIDAD"

    usos = USOS_POR_TIPO_VENTA.get(tipo_venta, USOS_POR_TIPO_VENTA["OTRA_ACTIVIDAD"])
    criterio = CRITERIO_POR_TIPO_VENTA.get(tipo_venta, "INGRESOS OPERATIVOS VENTAS")

    cuenta = _elegir_mejor_cuenta(criterio, _cuentas_por_uso(conn, empresa_id, usos))
    if cuenta:
        return cuenta

    # Fallback por nombre solo fiscal/contable. No usa el nombre comercial de la agrupación.
    nombres_fallback = {
        "VENTA_MERCADERIAS": ("Ventas de Mercaderías", "Ventas de Mercaderias", "Ventas de Bienes", "Ventas"),
        "VENTA_SERVICIOS": ("Ventas de Servicios", "Servicios Prestados", "Ingresos por Servicios", "Ventas"),
        "EXPORTACION_BIENES": ("Exportaciones", "Ventas de Exportación", "Ingresos por Exportación"),
        "EXPORTACION_SERVICIOS": ("Exportaciones", "Ventas de Exportación", "Ingresos por Exportación"),
        "VENTA_EXENTA": ("Ventas Exentas", "Ingresos Exentos", "Ventas"),
        "VENTA_NO_GRAVADA": ("Ventas No Gravadas", "Ingresos No Gravados", "Ventas"),
        "OTRA_ACTIVIDAD": ("Ingresos Operativos", "Ingresos por Ventas", "Ventas"),
    }

    for nombre in nombres_fallback.get(tipo_venta, nombres_fallback["OTRA_ACTIVIDAD"]):
        cuenta = _limpiar_cuenta(_cuenta_por_nombre(conn, nombre, empresa_id))
        if cuenta:
            return cuenta

    raise ErrorContableVentas(
        "No se pudo resolver la cuenta de ventas/ingresos en el Plan Empresa. "
        "Configure una cuenta activa/imputable con uso operativo compatible con el tipo fiscal de venta; "
        "la agrupación comercial no define la cuenta contable."
    )


def _es_nota_credito(venta: dict[str, Any]) -> bool:
    texto = _normalizar(" ".join([
        _texto(venta.get("codigo")),
        _texto(venta.get("tipo")),
        _texto(venta.get("tipo_comprobante")),
    ]))
    if any(token in texto for token in ("NOTA CREDITO", "NOTA DE CREDITO", "CREDITO")):
        return True

    codigo = _texto(venta.get("codigo")).zfill(3)
    return codigo in {"003", "008", "013", "203", "208", "213"}


def _agregar_linea(
    lineas: list[dict[str, Any]],
    cuenta: CuentaContable,
    importe: float,
    glosa: str,
    naturaleza_deudora: bool,
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


def _clave_venta(venta: dict[str, Any], empresa_id: int) -> str:
    venta_id = int(_numero(venta.get("id")))
    return f"VENTA:{empresa_id}:{venta_id}"


def _asiento_existente(conn: sqlite3.Connection, venta: dict[str, Any], empresa_id: int) -> Optional[dict[str, Any]]:
    referencia = _clave_venta(venta, empresa_id)
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
            (empresa_id, ORIGEN_VENTA, referencia),
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
            (empresa_id, ORIGEN_VENTA, referencia),
        )
        if fila:
            return {"asiento_propuesto_id": fila["id"], "estado": fila.get("estado")}

    return None


def _leer_venta(conn: sqlite3.Connection, venta_id: int, empresa_id: int) -> dict[str, Any]:
    if not _tabla_existe(conn, TABLA_VENTAS):
        raise ErrorContableVentas("No existe la tabla ventas_comprobantes.")

    asegurar_estructura_ventas_actividades(conn)

    fila = _query_uno(
        conn,
        f"""
        SELECT *
        FROM {TABLA_VENTAS}
        WHERE id = ?
          AND COALESCE(empresa_id, 1) = ?
        LIMIT 1
        """,
        (int(venta_id), int(empresa_id)),
    )
    if not fila:
        raise ErrorContableVentas(f"No existe la venta id={venta_id} para empresa_id={empresa_id}.")
    return fila


def preparar_lineas_asiento_venta(
    venta: dict[str, Any],
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        asegurar_estructura_ventas_actividades(conexion)

        actividad = _actividad_venta(conexion, venta, empresa_id)
        tratamiento_iva = _texto(actividad.get("tratamiento_iva") or venta.get("tratamiento_iva_venta") or "A_REVISAR").upper()

        cuenta_cliente = resolver_cuenta_cliente(conexion, venta, empresa_id)
        cuenta_ventas = resolver_cuenta_ventas(conexion, venta, empresa_id)

        neto = _numero(venta.get("neto"))
        iva = _numero(venta.get("iva"))
        total = _numero(venta.get("total"))
        if abs(total) < 0.01:
            total = round(neto + iva, 2)

        signo = -1 if _es_nota_credito(venta) else 1
        if neto < 0 or iva < 0 or total < 0:
            signo = -1

        neto_abs = abs(neto)
        iva_abs = abs(iva)
        total_abs = abs(total)

        genera_iva_debito = tratamiento_iva not in TRATAMIENTOS_SIN_IVA_DEBITO and iva_abs >= 0.01

        if genera_iva_debito:
            ingreso_abs = neto_abs if neto_abs >= 0.01 else round(total_abs - iva_abs, 2)
        else:
            ingreso_abs = total_abs if total_abs >= 0.01 else neto_abs

        if ingreso_abs < 0.01:
            raise ErrorContableVentas("La venta no tiene importe de ingreso válido.")

        if total_abs < 0.01:
            total_abs = round(ingreso_abs + (iva_abs if genera_iva_debito else 0), 2)

        tipo = _texto(venta.get("tipo"))
        comprobante = f"{tipo} {_texto(venta.get('punto_venta'))}-{_texto(venta.get('numero'))}".strip()
        cliente = _texto(venta.get("cliente")) or _texto(venta.get("cuit"))
        agrupacion_nombre = _texto(actividad.get("nombre")) or _texto(venta.get("actividad_venta_nombre")) or "Sin agrupación"
        tipo_venta = _texto(actividad.get("tipo_venta")) or _texto(venta.get("tipo_venta")) or "OTRA_ACTIVIDAD"
        glosa_base = f"Venta {comprobante} {cliente}".strip()

        advertencias: list[str] = []
        if tratamiento_iva in TRATAMIENTOS_SIN_IVA_DEBITO and iva_abs >= 0.01:
            advertencias.append(
                "La venta tiene IVA informado pero el tratamiento indica sin débito fiscal; "
                "el importe se incluye en la cuenta de ingresos para mantener el asiento balanceado."
            )

        if genera_iva_debito and abs(total_abs - (ingreso_abs + iva_abs)) > 0.05:
            advertencias.append(
                f"El total ({total_abs}) no coincide con ingreso + IVA ({round(ingreso_abs + iva_abs, 2)})."
            )
            total_abs = round(ingreso_abs + iva_abs, 2)

        lineas: list[dict[str, Any]] = []

        _agregar_linea(
            lineas,
            cuenta_cliente,
            signo * total_abs,
            f"{glosa_base} - Cliente",
            naturaleza_deudora=True,
        )

        _agregar_linea(
            lineas,
            cuenta_ventas,
            signo * ingreso_abs,
            f"{glosa_base} - {tipo_venta} / {agrupacion_nombre}",
            naturaleza_deudora=False,
        )

        if genera_iva_debito:
            cuenta_iva = resolver_cuenta_iva_debito(conexion, empresa_id)
            _agregar_linea(
                lineas,
                cuenta_iva,
                signo * iva_abs,
                f"{glosa_base} - IVA débito fiscal",
                naturaleza_deudora=False,
            )

        total_debe, total_haber = _sumar_lineas(lineas)
        diferencia = round(total_debe - total_haber, 2)
        if abs(diferencia) > 0.01:
            raise ErrorContableVentas(f"El asiento preparado queda desbalanceado por {diferencia}.")

        return {
            "ok": True,
            "venta_id": int(_numero(venta.get("id"))),
            "referencia": _clave_venta(venta, empresa_id),
            "descripcion": f"Venta importada ARCA {comprobante} - {cliente}".strip(),
            "lineas": lineas,
            "total_debe": total_debe,
            "total_haber": total_haber,
            "diferencia": diferencia,
            "es_nota_credito": signo < 0,
            "actividad_venta": actividad,
            "agrupacion_venta": actividad,
            "tipo_venta": tipo_venta,
            "tratamiento_iva": tratamiento_iva,
            "cuenta_ventas_resuelta": {
                "codigo": cuenta_ventas.codigo,
                "nombre": cuenta_ventas.nombre,
                "origen_resolucion": cuenta_ventas.origen_resolucion,
            },
            "advertencias": advertencias,
        }
    finally:
        if cerrar:
            conexion.close()


def generar_asiento_propuesto_venta(
    venta_id: int,
    empresa_id: int = 1,
    usuario: str = "sistema",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        venta = _leer_venta(conexion, int(venta_id), int(empresa_id))

        existente = _asiento_existente(conexion, venta, int(empresa_id))
        if existente:
            return {
                "ok": True,
                "estado": "YA_EXISTE",
                "venta_id": int(venta_id),
                "asiento_propuesto_id": existente.get("asiento_propuesto_id"),
                "mensaje": "La venta ya tiene un asiento propuesto no anulado.",
            }

        preparado = preparar_lineas_asiento_venta(venta, empresa_id=int(empresa_id), conn=conexion)

        resultado = crear_asiento_origen(
            empresa_id=int(empresa_id),
            fecha=_fecha_bandeja(venta.get("fecha")),
            tipo_origen=ORIGEN_VENTA,
            descripcion=preparado["descripcion"],
            lineas=preparado["lineas"],
            ejercicio_id=None,
            referencia=preparado["referencia"],
            observaciones=(
                f"Origen real: {TABLA_VENTAS}.id={venta_id}. "
                "Generado desde comprobante de venta importado/manual con agrupación interna y tipo fiscal asignados. "
                "La agrupación comercial no define la cuenta contable."
            ),
            usuario=usuario,
            generar_propuesta=True,
        )

        if not resultado or not resultado.get("ok", False):
            return {
                "ok": False,
                "estado": "ERROR",
                "venta_id": int(venta_id),
                "mensaje": (resultado or {}).get("mensaje", "No se pudo crear el asiento propuesto."),
                "detalle": resultado,
            }

        return {
            "ok": True,
            "estado": "GENERADO",
            "venta_id": int(venta_id),
            "asiento_origen_id": resultado.get("asiento_origen_id") or resultado.get("id"),
            "asiento_propuesto_id": resultado.get("asiento_propuesto_id"),
            "total_debe": preparado["total_debe"],
            "total_haber": preparado["total_haber"],
            "advertencias": preparado.get("advertencias", []),
            "mensaje": "Asiento propuesto de venta generado en Bandeja.",
        }
    except ErrorContableVentas as exc:
        return {"ok": False, "estado": "ERROR_VALIDACION", "venta_id": int(venta_id), "mensaje": str(exc)}
    except Exception as exc:
        return {"ok": False, "estado": "ERROR_TECNICO", "venta_id": int(venta_id), "mensaje": str(exc)}
    finally:
        if cerrar:
            conexion.close()


def listar_ventas_pendientes_asiento(
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    conexion, cerrar = _conexion(conn)
    try:
        if not _tabla_existe(conexion, TABLA_VENTAS):
            return pd.DataFrame()

        asegurar_estructura_ventas_actividades(conexion)

        sql = f"""
            SELECT v.*
            FROM {TABLA_VENTAS} v
            WHERE COALESCE(v.empresa_id, 1) = ?
              AND COALESCE(v.actividad_venta_id, 0) > 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM asientos_origen ao
                  WHERE COALESCE(ao.empresa_id, 1) = COALESCE(v.empresa_id, 1)
                    AND ao.tipo_origen = ?
                    AND ao.referencia = ('VENTA:' || COALESCE(v.empresa_id, 1) || ':' || v.id)
                    AND COALESCE(ao.estado, '') <> 'ANULADO'
              )
            ORDER BY v.fecha, v.id
        """
        return pd.read_sql_query(sql, conexion, params=(int(empresa_id), ORIGEN_VENTA))
    finally:
        if cerrar:
            conexion.close()


def generar_asientos_propuestos_ventas_importadas(
    empresa_id: int = 1,
    usuario: str = "sistema",
    limite: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        pendientes = listar_ventas_pendientes_asiento(empresa_id=int(empresa_id), conn=conexion)
        if limite is not None and int(limite) > 0:
            pendientes = pendientes.head(int(limite))

        resultados: list[dict[str, Any]] = []
        for _, fila in pendientes.iterrows():
            venta_id = int(fila["id"])
            resultados.append(
                generar_asiento_propuesto_venta(
                    venta_id=venta_id,
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


def simular_asiento_venta(
    venta_id: int,
    empresa_id: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    conexion, cerrar = _conexion(conn)
    try:
        venta = _leer_venta(conexion, int(venta_id), int(empresa_id))
        return preparar_lineas_asiento_venta(venta, empresa_id=int(empresa_id), conn=conexion)
    except ErrorContableVentas as exc:
        return {"ok": False, "estado": "ERROR_VALIDACION", "venta_id": int(venta_id), "mensaje": str(exc)}
    except Exception as exc:
        return {"ok": False, "estado": "ERROR_TECNICO", "venta_id": int(venta_id), "mensaje": str(exc)}
    finally:
        if cerrar:
            conexion.close()


__all__ = [
    "ORIGEN_VENTA",
    "generar_asiento_propuesto_venta",
    "generar_asientos_propuestos_ventas_importadas",
    "listar_ventas_pendientes_asiento",
    "preparar_lineas_asiento_venta",
    "resolver_cuenta_cliente",
    "resolver_cuenta_iva_debito",
    "resolver_cuenta_ventas",
    "simular_asiento_venta",
]
