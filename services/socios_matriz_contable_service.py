from __future__ import annotations

from datetime import datetime
import re
import sqlite3
import unicodedata
from typing import Any

import pandas as pd

from database import conectar


MATRIZ_VINCULOS_SOCIOS: list[dict[str, Any]] = [
    {
        "tipo_vinculo": "CAPITAL_SUSCRIPTO",
        "nombre": "Capital suscripto",
        "grupo": "Capital",
        "descripcion": "Compromiso societario asumido por el socio o accionista. No representa ingreso ni préstamo.",
        "naturaleza_economica": "Aporte comprometido por el socio pendiente de integración total o parcial.",
        "tratamiento_contable": "Debe vincularse con cuentas de patrimonio neto y, cuando corresponda, con socios/accionistas por integración.",
        "cuenta_principal_esperada": "Capital social / capital suscripto",
        "cuenta_contrapartida_esperada": "Socios o accionistas por integración",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "INICIO_SOCIETARIO",
        "impacto_esperado": "Preparar asiento propuesto de suscripción sin mover Caja/Banco.",
        "palabras_clave": ["capital social", "capital suscripto", "socios por integracion", "accionistas por integracion"],
    },
    {
        "tipo_vinculo": "INTEGRACION_CAPITAL",
        "nombre": "Integración de capital",
        "grupo": "Capital",
        "descripcion": "Cancelación real, total o parcial, del capital suscripto pendiente de integración.",
        "naturaleza_economica": "Ingreso de un activo contra disminución del crédito por integración pendiente.",
        "tratamiento_contable": "Debe cancelar socios/accionistas por integración contra el activo recibido desde Caja/Banco/Tesorería en una etapa futura.",
        "cuenta_principal_esperada": "Socios o accionistas por integración",
        "cuenta_contrapartida_esperada": "Activo recibido por Caja/Banco/Tesorería",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "CAJA_BANCO_FUTURO",
        "impacto_esperado": "Preparar la clasificación; no registrar el movimiento real en esta etapa.",
        "palabras_clave": ["socios por integracion", "accionistas por integracion", "capital pendiente"],
    },
    {
        "tipo_vinculo": "PRESTAMO_SOCIO_EMPRESA",
        "nombre": "Préstamo de socio a la empresa",
        "grupo": "Cuenta particular",
        "descripcion": "Fondos, valores o créditos entregados por el socio a la empresa con obligación de devolución.",
        "naturaleza_economica": "Financiación de tercero relacionado. No es capital salvo decisión societaria formal.",
        "tratamiento_contable": "Debe tratarse como pasivo con socio o cuenta particular acreedora, no como patrimonio neto automático.",
        "cuenta_principal_esperada": "Préstamos de socios / deudas con socios",
        "cuenta_contrapartida_esperada": "Activo recibido por Caja/Banco/Tesorería",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "CAJA_BANCO_FUTURO",
        "impacto_esperado": "Preparar clasificación de pasivo relacionado; no registrar fondos en esta etapa.",
        "palabras_clave": ["prestamo socio", "prestamos de socios", "deudas con socios", "cuenta particular socios"],
    },
    {
        "tipo_vinculo": "DEVOLUCION_PRESTAMO_SOCIO",
        "nombre": "Devolución de préstamo de socio",
        "grupo": "Cuenta particular",
        "descripcion": "Cancelación total o parcial de un préstamo otorgado previamente por el socio a la empresa.",
        "naturaleza_economica": "Disminución de pasivo con socio contra salida de activo.",
        "tratamiento_contable": "Debe cancelar el pasivo con socio cuando el pago real se registre desde Caja/Banco/Tesorería.",
        "cuenta_principal_esperada": "Préstamos de socios / deudas con socios",
        "cuenta_contrapartida_esperada": "Activo entregado por Caja/Banco/Tesorería",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "CAJA_BANCO_FUTURO",
        "impacto_esperado": "Preparar clasificación de cancelación de pasivo; no pagar ni registrar fondos en esta etapa.",
        "palabras_clave": ["prestamo socio", "prestamos de socios", "deudas con socios", "cuenta particular socios"],
    },
    {
        "tipo_vinculo": "RETIRO_SOCIO",
        "nombre": "Retiro de socio",
        "grupo": "Cuenta particular",
        "descripcion": "Salida de fondos o bienes a favor del socio que requiere clasificación antes de contabilizarse definitivamente.",
        "naturaleza_economica": "Movimiento con socio no necesariamente deducible ni distribuible hasta analizar respaldo.",
        "tratamiento_contable": "Debe ir a cuenta particular/retiros a clasificar, no a gasto automático.",
        "cuenta_principal_esperada": "Cuenta particular de socios / retiros de socios",
        "cuenta_contrapartida_esperada": "Activo entregado por Caja/Banco/Tesorería",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "CAJA_BANCO_FUTURO",
        "impacto_esperado": "Preparar control auxiliar por socio; no ejecutar egresos en esta etapa.",
        "palabras_clave": ["cuenta particular socios", "retiro socio", "retiros de socios", "directores cuenta particular"],
    },
    {
        "tipo_vinculo": "REINTEGRO_SOCIO",
        "nombre": "Reintegro al socio",
        "grupo": "Cuenta particular",
        "descripcion": "Devolución al socio de importes adelantados o gastos pagados por cuenta de la empresa.",
        "naturaleza_economica": "Puede representar gasto, crédito, anticipo, reintegro documentado o cuenta particular según respaldo.",
        "tratamiento_contable": "Debe clasificarse con documentación; no debe imputarse automáticamente a gasto sin respaldo.",
        "cuenta_principal_esperada": "Cuenta particular de socios / gastos a rendir / acreedores varios",
        "cuenta_contrapartida_esperada": "Activo entregado por Caja/Banco/Tesorería",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "CAJA_BANCO_FUTURO",
        "impacto_esperado": "Preparar criterio de clasificación; no registrar reintegros en esta etapa.",
        "palabras_clave": ["cuenta particular socios", "gastos a rendir", "reintegros", "acreedores varios"],
    },
    {
        "tipo_vinculo": "HONORARIOS_SERVICIOS_SOCIO",
        "nombre": "Honorarios o servicios facturados por socio",
        "grupo": "Proveedor vinculado",
        "descripcion": "Servicios prestados por el socio en su actividad particular o profesional.",
        "naturaleza_economica": "Relación comercial/profesional con tercero relacionado, distinta del aporte societario.",
        "tratamiento_contable": "Debe tratarse como proveedor vinculado, gasto o servicio según comprobante y normativa aplicable.",
        "cuenta_principal_esperada": "Honorarios / servicios / gastos",
        "cuenta_contrapartida_esperada": "Proveedor vinculado / cuenta a pagar",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "COMPRAS_PAGOS_FUTURO",
        "impacto_esperado": "Preparar clasificación; no cargar compras, IVA ni pagos en esta etapa.",
        "palabras_clave": ["honorarios", "servicios", "proveedores", "acreedores comerciales"],
    },
    {
        "tipo_vinculo": "FACTURA_PROVEEDOR_SOCIO",
        "nombre": "Factura de proveedor vinculada al socio",
        "grupo": "Proveedor vinculado",
        "descripcion": "Comprobante de compra o gasto emitido por el socio o por un proveedor relacionado con el socio.",
        "naturaleza_economica": "Compra/gasto con parte relacionada que requiere identificación auxiliar.",
        "tratamiento_contable": "Debe vincularse a proveedor, compras/gastos y auxiliar de socio cuando corresponda.",
        "cuenta_principal_esperada": "Compras / gastos",
        "cuenta_contrapartida_esperada": "Proveedor vinculado / cuenta a pagar",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 1,
        "modulo_origen_futuro": "COMPRAS_PAGOS_FUTURO",
        "impacto_esperado": "Preparar vínculo auxiliar; no modificar Compras, IVA ni Pagos en esta etapa.",
        "palabras_clave": ["proveedores", "acreedores comerciales", "compras", "gastos"],
    },
    {
        "tipo_vinculo": "CUENTA_PARTICULAR_SOCIO",
        "nombre": "Cuenta particular del socio",
        "grupo": "Cuenta particular",
        "descripcion": "Referencia auxiliar para controlar movimientos económicos del socio no capitalizables.",
        "naturaleza_economica": "Auxiliar de control por tercero relacionado; no reemplaza el Plan de Cuentas.",
        "tratamiento_contable": "Debe usarse como control auxiliar. La cuenta contable base debe surgir del Plan Maestro FF/cuenta empresa.",
        "cuenta_principal_esperada": "Cuenta particular de socios",
        "cuenta_contrapartida_esperada": "Según naturaleza del movimiento futuro",
        "requiere_auxiliar_socio": 1,
        "requiere_documento_respaldo": 0,
        "modulo_origen_futuro": "SOCIOS_AUXILIAR",
        "impacto_esperado": "Preparar control auxiliar; no generar movimientos ni cuentas contables automáticas.",
        "palabras_clave": ["cuenta particular socios", "cuenta particular directores", "socios cuenta particular"],
    },
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar_codigo(valor: Any) -> str:
    return _texto(valor).upper().replace(" ", "_")


def _normalizar_busqueda(valor: Any) -> str:
    texto = _texto(valor).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _bool_int(valor: Any, default: int = 0) -> int:
    if valor is None or valor == "":
        return default
    if isinstance(valor, str):
        return 1 if valor.strip().upper() in {"1", "S", "SI", "SÍ", "TRUE", "VERDADERO", "YES"} else 0
    return 1 if bool(valor) else 0


def _conectar(conn: sqlite3.Connection | None = None) -> tuple[sqlite3.Connection, bool]:
    if conn is None:
        conn = conectar()
        propia = True
    else:
        propia = False
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row
    return conn, propia


def _table_exists(conn: sqlite3.Connection, tabla: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (_texto(tabla),),
    ).fetchone() is not None


def _fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    filas = cursor.fetchall()
    if not filas:
        return []
    if isinstance(filas[0], sqlite3.Row):
        return [dict(fila) for fila in filas]
    columnas = [col[0] for col in cursor.description]
    return [dict(zip(columnas, fila)) for fila in filas]


def _registrar_evento(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    tipo_vinculo: str,
    evento: str,
    detalle: str,
    valor_anterior: Any = "",
    valor_nuevo: Any = "",
    usuario: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO socios_matriz_contable_eventos
        (
            empresa_id, tipo_vinculo, evento, detalle, valor_anterior, valor_nuevo,
            usuario, fecha_evento
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            _normalizar_codigo(tipo_vinculo),
            _normalizar_codigo(evento),
            _texto(detalle),
            "" if valor_anterior is None else str(valor_anterior),
            "" if valor_nuevo is None else str(valor_nuevo),
            _texto(usuario) or "sistema",
            _now(),
        ),
    )


def asegurar_estructura_matriz_contable_socios(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> None:
    conn, propia = _conectar(conn)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS socios_matriz_contable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                tipo_vinculo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                grupo TEXT NOT NULL,
                descripcion TEXT,
                naturaleza_economica TEXT,
                tratamiento_contable TEXT,
                cuenta_principal_esperada TEXT,
                cuenta_contrapartida_esperada TEXT,
                cuenta_maestro_principal_codigo TEXT,
                cuenta_maestro_principal_nombre TEXT,
                cuenta_empresa_principal_codigo TEXT,
                cuenta_empresa_principal_nombre TEXT,
                cuenta_maestro_contrapartida_codigo TEXT,
                cuenta_maestro_contrapartida_nombre TEXT,
                cuenta_empresa_contrapartida_codigo TEXT,
                cuenta_empresa_contrapartida_nombre TEXT,
                requiere_auxiliar_socio INTEGER NOT NULL DEFAULT 1,
                requiere_documento_respaldo INTEGER NOT NULL DEFAULT 1,
                modulo_origen_futuro TEXT,
                impacto_esperado TEXT,
                estado_configuracion TEXT NOT NULL DEFAULT 'PENDIENTE',
                observaciones TEXT,
                estado TEXT NOT NULL DEFAULT 'ACTIVO',
                usuario_actualizacion TEXT,
                fecha_actualizacion TEXT,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (empresa_id, tipo_vinculo)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS socios_matriz_contable_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                tipo_vinculo TEXT NOT NULL,
                evento TEXT NOT NULL,
                detalle TEXT,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                usuario TEXT,
                fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_socios_matriz_contable_empresa
            ON socios_matriz_contable (empresa_id, estado, grupo, tipo_vinculo)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_socios_matriz_contable_eventos
            ON socios_matriz_contable_eventos (empresa_id, tipo_vinculo, fecha_evento)
            """
        )

        for item in MATRIZ_VINCULOS_SOCIOS:
            tipo = item["tipo_vinculo"]
            existente = conn.execute(
                """
                SELECT id
                FROM socios_matriz_contable
                WHERE empresa_id = ?
                  AND tipo_vinculo = ?
                LIMIT 1
                """,
                (int(empresa_id), tipo),
            ).fetchone()

            if existente:
                conn.execute(
                    """
                    UPDATE socios_matriz_contable
                    SET
                        nombre = ?,
                        grupo = ?,
                        descripcion = ?,
                        naturaleza_economica = ?,
                        tratamiento_contable = ?,
                        cuenta_principal_esperada = ?,
                        cuenta_contrapartida_esperada = ?,
                        requiere_auxiliar_socio = ?,
                        requiere_documento_respaldo = ?,
                        modulo_origen_futuro = ?,
                        impacto_esperado = ?
                    WHERE empresa_id = ?
                      AND tipo_vinculo = ?
                    """,
                    (
                        item["nombre"],
                        item["grupo"],
                        item["descripcion"],
                        item["naturaleza_economica"],
                        item["tratamiento_contable"],
                        item["cuenta_principal_esperada"],
                        item["cuenta_contrapartida_esperada"],
                        int(item["requiere_auxiliar_socio"]),
                        int(item["requiere_documento_respaldo"]),
                        item["modulo_origen_futuro"],
                        item["impacto_esperado"],
                        int(empresa_id),
                        tipo,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO socios_matriz_contable
                    (
                        empresa_id, tipo_vinculo, nombre, grupo, descripcion, naturaleza_economica,
                        tratamiento_contable, cuenta_principal_esperada, cuenta_contrapartida_esperada,
                        requiere_auxiliar_socio, requiere_documento_respaldo, modulo_origen_futuro,
                        impacto_esperado, estado_configuracion, estado, creado_en
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', 'ACTIVO', ?)
                    """,
                    (
                        int(empresa_id),
                        tipo,
                        item["nombre"],
                        item["grupo"],
                        item["descripcion"],
                        item["naturaleza_economica"],
                        item["tratamiento_contable"],
                        item["cuenta_principal_esperada"],
                        item["cuenta_contrapartida_esperada"],
                        int(item["requiere_auxiliar_socio"]),
                        int(item["requiere_documento_respaldo"]),
                        item["modulo_origen_futuro"],
                        item["impacto_esperado"],
                        _now(),
                    ),
                )
                _registrar_evento(
                    conn,
                    empresa_id=int(empresa_id),
                    tipo_vinculo=tipo,
                    evento="MATRIZ_SEMBRADA",
                    detalle="Se creó el vínculo base de la matriz contable de socios.",
                    valor_nuevo=item,
                    usuario="sistema",
                )

        if propia:
            conn.commit()
    except Exception:
        if propia:
            conn.rollback()
        raise
    finally:
        if propia:
            conn.close()


def _obtener_cuenta_maestra(
    conn: sqlite3.Connection,
    codigo: str,
) -> dict[str, Any] | None:
    codigo = _texto(codigo)
    if not codigo or not _table_exists(conn, "plan_cuentas_maestro"):
        return None
    filas = _fetch_dicts(
        conn,
        """
        SELECT
            p.codigo,
            p.nombre,
            p.elemento,
            p.rubro,
            p.cuenta,
            p.subcuenta,
            p.imputable,
            p.estado,
            p.saldo_normal,
            p.uso_operativo_sistema
        FROM plan_cuentas_maestro p
        WHERE p.codigo = ?
        ORDER BY p.version_plan_id DESC, p.orden, p.id
        LIMIT 1
        """,
        (codigo,),
    )
    return filas[0] if filas else None


def _obtener_cuenta_empresa(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    codigo: str,
) -> dict[str, Any] | None:
    codigo = _texto(codigo)
    if not codigo:
        return None

    if _table_exists(conn, "plan_cuentas_empresa"):
        filas = _fetch_dicts(
            conn,
            """
            SELECT
                codigo,
                nombre,
                imputable,
                estado,
                uso_operativo_sistema,
                cuenta_maestro_id
            FROM plan_cuentas_empresa
            WHERE empresa_id = ?
              AND codigo = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(empresa_id), codigo),
        )
        if filas:
            return filas[0]

    if _table_exists(conn, "plan_cuentas"):
        filas = _fetch_dicts(
            conn,
            """
            SELECT
                codigo,
                nombre,
                1 AS imputable,
                'ACTIVA' AS estado,
                comportamiento_contable AS uso_operativo_sistema,
                NULL AS cuenta_maestro_id
            FROM plan_cuentas
            WHERE COALESCE(empresa_id, 1) = ?
              AND codigo = ?
            LIMIT 1
            """,
            (int(empresa_id), codigo),
        )
        if filas:
            return filas[0]

    return None


def _resolver_estado_configuracion(row: dict[str, Any], conn: sqlite3.Connection, empresa_id: int) -> str:
    if _texto(row.get("estado")).upper() != "ACTIVO":
        return "INACTIVA"

    principal_empresa = _texto(row.get("cuenta_empresa_principal_codigo"))
    principal_maestro = _texto(row.get("cuenta_maestro_principal_codigo"))

    if principal_empresa and _obtener_cuenta_empresa(conn, empresa_id=empresa_id, codigo=principal_empresa):
        return "CONFIGURADA_CON_CUENTA_EMPRESA"

    if principal_maestro and _obtener_cuenta_maestra(conn, principal_maestro):
        return "CONFIGURADA_CON_PLAN_MAESTRO"

    return "PENDIENTE_CUENTA_CONTABLE"


def _normalizar_fila_matriz(row: dict[str, Any], conn: sqlite3.Connection, empresa_id: int) -> dict[str, Any]:
    item = dict(row)
    estado_calculado = _resolver_estado_configuracion(item, conn, empresa_id)
    item["estado_configuracion_calculado"] = estado_calculado
    item["configurada"] = estado_calculado in {"CONFIGURADA_CON_CUENTA_EMPRESA", "CONFIGURADA_CON_PLAN_MAESTRO"}

    cuenta_principal = _texto(item.get("cuenta_empresa_principal_codigo")) or _texto(item.get("cuenta_maestro_principal_codigo"))
    nombre_principal = _texto(item.get("cuenta_empresa_principal_nombre")) or _texto(item.get("cuenta_maestro_principal_nombre"))
    item["cuenta_principal_referencia"] = f"{cuenta_principal} - {nombre_principal}".strip(" -")

    cuenta_contrapartida = _texto(item.get("cuenta_empresa_contrapartida_codigo")) or _texto(item.get("cuenta_maestro_contrapartida_codigo"))
    nombre_contrapartida = _texto(item.get("cuenta_empresa_contrapartida_nombre")) or _texto(item.get("cuenta_maestro_contrapartida_nombre"))
    item["cuenta_contrapartida_referencia"] = f"{cuenta_contrapartida} - {nombre_contrapartida}".strip(" -")

    return item


def listar_matriz_contable_socios(
    empresa_id: int = 1,
    incluir_inactivas: bool = False,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=empresa_id, conn=conn)
        filtro = "" if incluir_inactivas else "AND estado = 'ACTIVO'"
        filas = _fetch_dicts(
            conn,
            f"""
            SELECT *
            FROM socios_matriz_contable
            WHERE empresa_id = ?
              {filtro}
            ORDER BY
                CASE grupo
                    WHEN 'Capital' THEN 1
                    WHEN 'Cuenta particular' THEN 2
                    WHEN 'Proveedor vinculado' THEN 3
                    ELSE 9
                END,
                id
            """,
            (int(empresa_id),),
        )
        normalizadas = [_normalizar_fila_matriz(fila, conn, int(empresa_id)) for fila in filas]
        return pd.DataFrame(normalizadas)
    finally:
        if propia:
            conn.close()


def listar_eventos_matriz_contable_socios(
    empresa_id: int = 1,
    limite: int = 200,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=empresa_id, conn=conn)
        filas = _fetch_dicts(
            conn,
            """
            SELECT tipo_vinculo, evento, detalle, valor_anterior, valor_nuevo, usuario, fecha_evento
            FROM socios_matriz_contable_eventos
            WHERE empresa_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(empresa_id), int(limite)),
        )
        return pd.DataFrame(filas)
    finally:
        if propia:
            conn.close()


def obtener_vinculo_matriz_contable(
    tipo_vinculo: str,
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    tipo = _normalizar_codigo(tipo_vinculo)
    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=empresa_id, conn=conn)
        filas = _fetch_dicts(
            conn,
            """
            SELECT *
            FROM socios_matriz_contable
            WHERE empresa_id = ?
              AND tipo_vinculo = ?
            LIMIT 1
            """,
            (int(empresa_id), tipo),
        )
        if not filas:
            return {}
        return _normalizar_fila_matriz(filas[0], conn, int(empresa_id))
    finally:
        if propia:
            conn.close()


def _cuentas_maestras_candidatas(
    conn: sqlite3.Connection,
    palabras_clave: list[str],
    limite: int,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "plan_cuentas_maestro"):
        return []

    filas = _fetch_dicts(
        conn,
        """
        SELECT
            p.codigo,
            p.nombre,
            p.elemento,
            p.rubro,
            p.cuenta,
            p.subcuenta,
            p.imputable,
            p.estado,
            p.saldo_normal,
            p.uso_operativo_sistema,
            p.modulo_sugerido,
            p.orden,
            p.version_plan_id
        FROM plan_cuentas_maestro p
        WHERE COALESCE(p.estado, 'ACTIVA') = 'ACTIVA'
          AND COALESCE(p.imputable, 0) = 1
        ORDER BY p.version_plan_id DESC, p.orden, p.codigo
        """
    )

    salida: list[dict[str, Any]] = []
    claves = [_normalizar_busqueda(p) for p in palabras_clave if _texto(p)]
    for fila in filas:
        texto = _normalizar_busqueda(
            " ".join(
                [
                    fila.get("codigo", ""),
                    fila.get("nombre", ""),
                    fila.get("elemento", ""),
                    fila.get("rubro", ""),
                    fila.get("cuenta", ""),
                    fila.get("subcuenta", ""),
                    fila.get("uso_operativo_sistema", ""),
                ]
            )
        )
        puntaje = sum(1 for clave in claves if clave and clave in texto)
        if puntaje <= 0:
            continue
        fila["origen"] = "PLAN_MAESTRO"
        fila["puntaje"] = puntaje
        salida.append(fila)

    salida.sort(key=lambda x: (-int(x.get("puntaje") or 0), _texto(x.get("codigo"))))
    return salida[:limite]


def _cuentas_empresa_candidatas(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    palabras_clave: list[str],
    limite: int,
) -> list[dict[str, Any]]:
    claves = [_normalizar_busqueda(p) for p in palabras_clave if _texto(p)]
    filas: list[dict[str, Any]] = []

    if _table_exists(conn, "plan_cuentas_empresa"):
        filas = _fetch_dicts(
            conn,
            """
            SELECT
                codigo,
                nombre,
                imputable,
                estado,
                uso_operativo_sistema,
                orden
            FROM plan_cuentas_empresa
            WHERE empresa_id = ?
              AND COALESCE(estado, 'ACTIVA') = 'ACTIVA'
              AND COALESCE(imputable, 0) = 1
            ORDER BY orden, codigo
            """,
            (int(empresa_id),),
        )
    elif _table_exists(conn, "plan_cuentas"):
        filas = _fetch_dicts(
            conn,
            """
            SELECT
                codigo,
                nombre,
                1 AS imputable,
                'ACTIVA' AS estado,
                comportamiento_contable AS uso_operativo_sistema,
                0 AS orden
            FROM plan_cuentas
            WHERE COALESCE(empresa_id, 1) = ?
            ORDER BY codigo
            """,
            (int(empresa_id),),
        )

    salida: list[dict[str, Any]] = []
    for fila in filas:
        texto = _normalizar_busqueda(
            " ".join(
                [
                    fila.get("codigo", ""),
                    fila.get("nombre", ""),
                    fila.get("uso_operativo_sistema", ""),
                ]
            )
        )
        puntaje = sum(1 for clave in claves if clave and clave in texto)
        if puntaje <= 0:
            continue
        fila["origen"] = "PLAN_EMPRESA"
        fila["puntaje"] = puntaje
        salida.append(fila)

    salida.sort(key=lambda x: (-int(x.get("puntaje") or 0), _texto(x.get("codigo"))))
    return salida[:limite]


def listar_candidatas_matriz_contable(
    tipo_vinculo: str,
    empresa_id: int = 1,
    limite: int = 12,
    conn: sqlite3.Connection | None = None,
) -> dict[str, pd.DataFrame]:
    tipo = _normalizar_codigo(tipo_vinculo)
    definicion = next((item for item in MATRIZ_VINCULOS_SOCIOS if item["tipo_vinculo"] == tipo), None)
    palabras = list(definicion.get("palabras_clave", [])) if definicion else [_texto(tipo_vinculo)]

    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=empresa_id, conn=conn)
        empresa = _cuentas_empresa_candidatas(conn, empresa_id=int(empresa_id), palabras_clave=palabras, limite=int(limite))
        maestro = _cuentas_maestras_candidatas(conn, palabras_clave=palabras, limite=int(limite))
        return {
            "empresa": pd.DataFrame(empresa),
            "maestro": pd.DataFrame(maestro),
        }
    finally:
        if propia:
            conn.close()


def actualizar_vinculo_matriz_contable(
    *,
    empresa_id: int = 1,
    tipo_vinculo: str,
    cuenta_maestro_principal_codigo: str = "",
    cuenta_empresa_principal_codigo: str = "",
    cuenta_maestro_contrapartida_codigo: str = "",
    cuenta_empresa_contrapartida_codigo: str = "",
    observaciones: str = "",
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    tipo = _normalizar_codigo(tipo_vinculo)
    if not tipo:
        return {"ok": False, "mensaje": "Debe indicar el tipo de vínculo."}

    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=empresa_id, conn=conn)
        actual = obtener_vinculo_matriz_contable(tipo, empresa_id=empresa_id, conn=conn)
        if not actual:
            return {"ok": False, "mensaje": "No se encontró el vínculo en la matriz."}

        cm_principal = _texto(cuenta_maestro_principal_codigo)
        ce_principal = _texto(cuenta_empresa_principal_codigo)
        cm_contrapartida = _texto(cuenta_maestro_contrapartida_codigo)
        ce_contrapartida = _texto(cuenta_empresa_contrapartida_codigo)

        cuenta_maestro_principal = _obtener_cuenta_maestra(conn, cm_principal) if cm_principal else None
        cuenta_empresa_principal = _obtener_cuenta_empresa(conn, empresa_id=int(empresa_id), codigo=ce_principal) if ce_principal else None
        cuenta_maestro_contrapartida = _obtener_cuenta_maestra(conn, cm_contrapartida) if cm_contrapartida else None
        cuenta_empresa_contrapartida = _obtener_cuenta_empresa(conn, empresa_id=int(empresa_id), codigo=ce_contrapartida) if ce_contrapartida else None

        errores: list[str] = []
        if cm_principal and not cuenta_maestro_principal:
            errores.append("La cuenta principal del Plan Maestro no existe o no está disponible.")
        if ce_principal and not cuenta_empresa_principal:
            errores.append("La cuenta principal de empresa no existe o no está disponible.")
        if cm_contrapartida and not cuenta_maestro_contrapartida:
            errores.append("La cuenta contrapartida del Plan Maestro no existe o no está disponible.")
        if ce_contrapartida and not cuenta_empresa_contrapartida:
            errores.append("La cuenta contrapartida de empresa no existe o no está disponible.")
        if errores:
            return {"ok": False, "mensaje": " ".join(errores), "errores": errores}

        estado_configuracion = "PENDIENTE"
        if ce_principal:
            estado_configuracion = "CONFIGURADA_CON_CUENTA_EMPRESA"
        elif cm_principal:
            estado_configuracion = "CONFIGURADA_CON_PLAN_MAESTRO"

        nuevo = {
            "cuenta_maestro_principal_codigo": cm_principal,
            "cuenta_maestro_principal_nombre": _texto((cuenta_maestro_principal or {}).get("nombre")),
            "cuenta_empresa_principal_codigo": ce_principal,
            "cuenta_empresa_principal_nombre": _texto((cuenta_empresa_principal or {}).get("nombre")),
            "cuenta_maestro_contrapartida_codigo": cm_contrapartida,
            "cuenta_maestro_contrapartida_nombre": _texto((cuenta_maestro_contrapartida or {}).get("nombre")),
            "cuenta_empresa_contrapartida_codigo": ce_contrapartida,
            "cuenta_empresa_contrapartida_nombre": _texto((cuenta_empresa_contrapartida or {}).get("nombre")),
            "estado_configuracion": estado_configuracion,
            "observaciones": _texto(observaciones),
        }

        conn.execute(
            """
            UPDATE socios_matriz_contable
            SET
                cuenta_maestro_principal_codigo = ?,
                cuenta_maestro_principal_nombre = ?,
                cuenta_empresa_principal_codigo = ?,
                cuenta_empresa_principal_nombre = ?,
                cuenta_maestro_contrapartida_codigo = ?,
                cuenta_maestro_contrapartida_nombre = ?,
                cuenta_empresa_contrapartida_codigo = ?,
                cuenta_empresa_contrapartida_nombre = ?,
                estado_configuracion = ?,
                observaciones = ?,
                usuario_actualizacion = ?,
                fecha_actualizacion = ?
            WHERE empresa_id = ?
              AND tipo_vinculo = ?
            """,
            (
                nuevo["cuenta_maestro_principal_codigo"],
                nuevo["cuenta_maestro_principal_nombre"],
                nuevo["cuenta_empresa_principal_codigo"],
                nuevo["cuenta_empresa_principal_nombre"],
                nuevo["cuenta_maestro_contrapartida_codigo"],
                nuevo["cuenta_maestro_contrapartida_nombre"],
                nuevo["cuenta_empresa_contrapartida_codigo"],
                nuevo["cuenta_empresa_contrapartida_nombre"],
                nuevo["estado_configuracion"],
                nuevo["observaciones"],
                _texto(usuario) or "sistema",
                _now(),
                int(empresa_id),
                tipo,
            ),
        )
        _registrar_evento(
            conn,
            empresa_id=int(empresa_id),
            tipo_vinculo=tipo,
            evento="MATRIZ_ACTUALIZADA",
            detalle="Se actualizó la vinculación contable preparatoria del vínculo con socios.",
            valor_anterior=actual,
            valor_nuevo=nuevo,
            usuario=usuario,
        )

        if propia:
            conn.commit()
        return {
            "ok": True,
            "mensaje": "Matriz contable actualizada correctamente.",
            "tipo_vinculo": tipo,
            "estado_configuracion": estado_configuracion,
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "mensaje": str(exc)}
    finally:
        if propia:
            conn.close()


def diagnosticar_matriz_contable_socios(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    conn, propia = _conectar(conn)
    try:
        df = listar_matriz_contable_socios(empresa_id=empresa_id, incluir_inactivas=False, conn=conn)
        if df.empty:
            return {
                "ok": True,
                "total": 0,
                "configuradas": 0,
                "pendientes": 0,
                "porcentaje_configurado": 0.0,
                "pendientes_detalle": [],
                "advertencias": ["La matriz contable de socios no tiene vínculos activos."],
            }

        configuradas = df[df["configurada"] == True] if "configurada" in df.columns else pd.DataFrame()
        pendientes = df[df["configurada"] != True] if "configurada" in df.columns else df
        advertencias: list[str] = []
        if not _table_exists(conn, "plan_cuentas_maestro"):
            advertencias.append("No se detectó la tabla plan_cuentas_maestro.")
        if not _table_exists(conn, "plan_cuentas_empresa") and not _table_exists(conn, "plan_cuentas"):
            advertencias.append("No se detectaron cuentas de empresa disponibles.")

        return {
            "ok": True,
            "total": int(len(df)),
            "configuradas": int(len(configuradas)),
            "pendientes": int(len(pendientes)),
            "porcentaje_configurado": round((len(configuradas) / len(df)) * 100, 2) if len(df) else 0.0,
            "pendientes_detalle": pendientes[
                ["tipo_vinculo", "nombre", "grupo", "cuenta_principal_esperada", "cuenta_contrapartida_esperada"]
            ].to_dict("records") if not pendientes.empty else [],
            "advertencias": advertencias,
        }
    finally:
        if propia:
            conn.close()


def restaurar_vinculo_matriz_contable(
    *,
    empresa_id: int = 1,
    tipo_vinculo: str,
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    tipo = _normalizar_codigo(tipo_vinculo)
    conn, propia = _conectar(conn)
    try:
        asegurar_estructura_matriz_contable_socios(empresa_id=empresa_id, conn=conn)
        actual = obtener_vinculo_matriz_contable(tipo, empresa_id=empresa_id, conn=conn)
        if not actual:
            return {"ok": False, "mensaje": "No se encontró el vínculo indicado."}

        conn.execute(
            """
            UPDATE socios_matriz_contable
            SET
                cuenta_maestro_principal_codigo = NULL,
                cuenta_maestro_principal_nombre = NULL,
                cuenta_empresa_principal_codigo = NULL,
                cuenta_empresa_principal_nombre = NULL,
                cuenta_maestro_contrapartida_codigo = NULL,
                cuenta_maestro_contrapartida_nombre = NULL,
                cuenta_empresa_contrapartida_codigo = NULL,
                cuenta_empresa_contrapartida_nombre = NULL,
                estado_configuracion = 'PENDIENTE',
                observaciones = NULL,
                usuario_actualizacion = ?,
                fecha_actualizacion = ?
            WHERE empresa_id = ?
              AND tipo_vinculo = ?
            """,
            (_texto(usuario) or "sistema", _now(), int(empresa_id), tipo),
        )
        _registrar_evento(
            conn,
            empresa_id=int(empresa_id),
            tipo_vinculo=tipo,
            evento="MATRIZ_RESTAURADA",
            detalle="Se limpiaron las cuentas configuradas para volver el vínculo a estado pendiente.",
            valor_anterior=actual,
            valor_nuevo={"estado_configuracion": "PENDIENTE"},
            usuario=usuario,
        )

        if propia:
            conn.commit()
        return {"ok": True, "mensaje": "Vínculo restaurado a pendiente correctamente."}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "mensaje": str(exc)}
    finally:
        if propia:
            conn.close()