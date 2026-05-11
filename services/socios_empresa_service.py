from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from database import conectar
from services.capital_social_service import asegurar_estructura_inicio_societario_pro


COLUMNAS_FICHA_SOCIO = {
    "rol_relacion": "TEXT",
    "condicion_fiscal": "TEXT",
    "documento": "TEXT",
    "email": "TEXT",
    "telefono": "TEXT",
    "domicilio": "TEXT",
    "actividad_vinculada": "TEXT",
    "proveedor_vinculado_referencia": "TEXT",
    "cuenta_particular_habilitada": "INTEGER",
    "cuenta_particular_codigo": "TEXT",
    "cuenta_particular_nombre": "TEXT",
    "cuenta_particular_significado": "TEXT",
    "admite_prestamos": "INTEGER",
    "admite_retiros": "INTEGER",
    "admite_reintegros": "INTEGER",
    "admite_honorarios": "INTEGER",
    "admite_facturas_proveedor": "INTEGER",
    "observaciones_ficha": "TEXT",
    "usuario_actualizacion_ficha": "TEXT",
    "fecha_actualizacion_ficha": "TIMESTAMP",
}

CAMPOS_EDITABLES_FICHA = tuple(COLUMNAS_FICHA_SOCIO.keys())

CAMPOS_BOOLEANOS = {
    "cuenta_particular_habilitada",
    "admite_prestamos",
    "admite_retiros",
    "admite_reintegros",
    "admite_honorarios",
    "admite_facturas_proveedor",
}

TIPOS_RELACION_VALIDOS = {
    "SOCIO",
    "ACCIONISTA",
    "ASOCIADO",
    "COOPERATIVISTA",
    "TITULAR",
    "TERCERO_RELACIONADO",
}

CONDICIONES_FISCALES_VALIDAS = {
    "NO_INFORMADA",
    "RESPONSABLE_INSCRIPTO",
    "MONOTRIBUTO",
    "EXENTO",
    "CONSUMIDOR_FINAL",
    "SUJETO_NO_CATEGORIZADO",
}

CONCEPTOS_RELACION_SOCIO = [
    {
        "codigo": "CAPITAL_SUSCRIPTO",
        "nombre": "Capital suscripto",
        "grupo": "Capital",
        "descripcion": "Compromiso societario asumido por el socio. No representa por sí mismo ingreso ni préstamo.",
        "naturaleza_contable": "PATRIMONIO_NETO / CREDITO_POR_INTEGRACION",
        "movimiento_real": "NO",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "NO",
    },
    {
        "codigo": "INTEGRACION_CAPITAL",
        "nombre": "Integración de capital",
        "grupo": "Capital",
        "descripcion": "Cancelación real, total o parcial, del capital suscripto pendiente de integración.",
        "naturaleza_contable": "ACTIVO_CONTRA_CREDITO_POR_INTEGRACION",
        "movimiento_real": "SI",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "SI",
    },
    {
        "codigo": "PRESTAMO_SOCIO_EMPRESA",
        "nombre": "Préstamo de socio a la empresa",
        "grupo": "Cuenta particular",
        "descripcion": "Fondos o valores entregados por el socio a la empresa que deben tratarse como pasivo con socio, no como capital.",
        "naturaleza_contable": "PASIVO_CON_SOCIO",
        "movimiento_real": "SI",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "SI",
    },
    {
        "codigo": "RETIRO_SOCIO",
        "nombre": "Retiro de socio",
        "grupo": "Cuenta particular",
        "descripcion": "Salida de fondos o bienes a favor del socio. Debe clasificarse antes de afectar contabilidad definitiva.",
        "naturaleza_contable": "CUENTA_PARTICULAR_SOCIO",
        "movimiento_real": "SI",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "SI",
    },
    {
        "codigo": "REINTEGRO_SOCIO",
        "nombre": "Reintegro al socio",
        "grupo": "Cuenta particular",
        "descripcion": "Devolución de importes adelantados o gastos soportados por el socio por cuenta de la empresa.",
        "naturaleza_contable": "CUENTA_PARTICULAR_SOCIO / GASTO_A_CLASIFICAR",
        "movimiento_real": "SI",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "SI",
    },
    {
        "codigo": "HONORARIOS_SERVICIOS_SOCIO",
        "nombre": "Honorarios o servicios facturados por socio",
        "grupo": "Proveedor vinculado",
        "descripcion": "Servicios prestados por el socio en su actividad particular. Deben tratarse como proveedor vinculado si corresponde.",
        "naturaleza_contable": "GASTO / PASIVO_PROVEEDOR_VINCULADO",
        "movimiento_real": "SI",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "NO",
    },
    {
        "codigo": "FACTURA_PROVEEDOR_SOCIO",
        "nombre": "Factura de proveedor vinculada al socio",
        "grupo": "Proveedor vinculado",
        "descripcion": "Comprobante de compra o gasto emitido por un proveedor relacionado con el socio.",
        "naturaleza_contable": "COMPRAS_GASTOS / PASIVO_PROVEEDOR",
        "movimiento_real": "SI",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "NO",
    },
    {
        "codigo": "CUENTA_PARTICULAR_SOCIO",
        "nombre": "Cuenta particular del socio",
        "grupo": "Cuenta particular",
        "descripcion": "Cuenta de control económico por socio para futuros movimientos no capitalizables.",
        "naturaleza_contable": "CONTROL_A_CLASIFICAR",
        "movimiento_real": "NO",
        "genera_asiento_directo": "NO",
        "impacta_caja_banco": "NO",
    },
]


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar_bool(valor: Any) -> int:
    if isinstance(valor, str):
        return 1 if valor.strip().upper() in {"1", "SI", "SÍ", "TRUE", "VERDADERO", "YES"} else 0
    return 1 if bool(valor) else 0


def _normalizar_opcion(valor: Any, opciones: Iterable[str], default: str) -> str:
    texto = _texto(valor).upper().replace(" ", "_")
    return texto if texto in set(opciones) else default


def _columnas_tabla(conn, tabla: str) -> set[str]:
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _agregar_columna_si_falta(conn, tabla: str, columna: str, definicion: str) -> None:
    columnas = _columnas_tabla(conn, tabla)
    if columna not in columnas:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _registrar_evento_ficha(
    conn,
    *,
    empresa_id: int,
    socio_id: int,
    tipo_evento: str,
    detalle: str,
    usuario: Optional[str],
) -> None:
    conn.execute(
        """
        INSERT INTO socios_empresa_ficha_eventos
            (empresa_id, socio_id, tipo_evento, detalle, usuario, fecha_evento)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            int(socio_id),
            _texto(tipo_evento),
            _texto(detalle),
            _texto(usuario) or "sistema",
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def _sembrar_conceptos_relacion(conn) -> None:
    for concepto in CONCEPTOS_RELACION_SOCIO:
        conn.execute(
            """
            INSERT INTO socios_conceptos_relacion
                (codigo, nombre, grupo, descripcion, naturaleza_contable, movimiento_real,
                 genera_asiento_directo, impacta_caja_banco, estado, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO', CURRENT_TIMESTAMP)
            ON CONFLICT(codigo) DO UPDATE SET
                nombre = excluded.nombre,
                grupo = excluded.grupo,
                descripcion = excluded.descripcion,
                naturaleza_contable = excluded.naturaleza_contable,
                movimiento_real = excluded.movimiento_real,
                genera_asiento_directo = excluded.genera_asiento_directo,
                impacta_caja_banco = excluded.impacta_caja_banco,
                estado = 'ACTIVO',
                fecha_actualizacion = CURRENT_TIMESTAMP
            """,
            (
                concepto["codigo"],
                concepto["nombre"],
                concepto["grupo"],
                concepto["descripcion"],
                concepto["naturaleza_contable"],
                concepto["movimiento_real"],
                concepto["genera_asiento_directo"],
                concepto["impacta_caja_banco"],
            ),
        )


def asegurar_estructura_socios_pro() -> None:
    asegurar_estructura_inicio_societario_pro()

    conn = conectar()
    try:
        for columna, definicion in COLUMNAS_FICHA_SOCIO.items():
            _agregar_columna_si_falta(conn, "socios_empresa", columna, definicion)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS socios_empresa_ficha_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                socio_id INTEGER NOT NULL,
                tipo_evento TEXT NOT NULL,
                detalle TEXT,
                usuario TEXT,
                fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS socios_conceptos_relacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                grupo TEXT NOT NULL,
                descripcion TEXT,
                naturaleza_contable TEXT NOT NULL,
                movimiento_real TEXT NOT NULL DEFAULT 'NO',
                genera_asiento_directo TEXT NOT NULL DEFAULT 'NO',
                impacta_caja_banco TEXT NOT NULL DEFAULT 'NO',
                estado TEXT NOT NULL DEFAULT 'ACTIVO',
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_socios_empresa_ficha_eventos_socio "
            "ON socios_empresa_ficha_eventos(empresa_id, socio_id, fecha_evento)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_socios_conceptos_relacion_estado "
            "ON socios_conceptos_relacion(estado, grupo)"
        )

        conn.execute(
            """
            UPDATE socios_empresa
            SET
                rol_relacion = COALESCE(NULLIF(TRIM(rol_relacion), ''), tipo_socio),
                condicion_fiscal = COALESCE(NULLIF(TRIM(condicion_fiscal), ''), 'NO_INFORMADA'),
                cuenta_particular_habilitada = COALESCE(cuenta_particular_habilitada, 0),
                admite_prestamos = COALESCE(admite_prestamos, 0),
                admite_retiros = COALESCE(admite_retiros, 0),
                admite_reintegros = COALESCE(admite_reintegros, 0),
                admite_honorarios = COALESCE(admite_honorarios, 0),
                admite_facturas_proveedor = COALESCE(admite_facturas_proveedor, 0)
            """
        )

        _sembrar_conceptos_relacion(conn)
        conn.commit()
    finally:
        conn.close()


def listar_fichas_socios_empresa(empresa_id: int = 1, incluir_bajas: bool = False) -> pd.DataFrame:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        where_estado = "" if incluir_bajas else "AND estado = 'ACTIVO'"
        df = pd.read_sql_query(
            f"""
            SELECT
                id, empresa_id, nombre, cuit, tipo_socio, porcentaje_participacion,
                rol_relacion, condicion_fiscal, documento, email, telefono, domicilio,
                actividad_vinculada, proveedor_vinculado_referencia,
                cuenta_particular_habilitada, cuenta_particular_codigo, cuenta_particular_nombre,
                cuenta_particular_significado,
                admite_prestamos, admite_retiros, admite_reintegros, admite_honorarios,
                admite_facturas_proveedor,
                observaciones, observaciones_ficha,
                estado, fecha_creacion, fecha_actualizacion, fecha_baja, motivo_baja
            FROM socios_empresa
            WHERE empresa_id = ?
            {where_estado}
            ORDER BY estado ASC, nombre COLLATE NOCASE ASC, id ASC
            """,
            conn,
            params=(int(empresa_id),),
        )

        if not df.empty:
            for campo in CAMPOS_BOOLEANOS:
                if campo in df.columns:
                    df[campo] = df[campo].fillna(0).astype(int)

        return df
    finally:
        conn.close()


def obtener_ficha_socio(socio_id: int, empresa_id: int = 1) -> Dict[str, Any]:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        fila = conn.execute(
            """
            SELECT *
            FROM socios_empresa
            WHERE id = ?
              AND empresa_id = ?
            """,
            (int(socio_id), int(empresa_id)),
        ).fetchone()

        if not fila:
            return {}

        columnas = [col[0] for col in conn.execute("SELECT * FROM socios_empresa LIMIT 0").description]
        return dict(zip(columnas, fila))
    finally:
        conn.close()


def _validar_socio_activo(conn, socio_id: int, empresa_id: int) -> Dict[str, Any]:
    fila = conn.execute(
        """
        SELECT id, empresa_id, nombre, cuit, tipo_socio, estado
        FROM socios_empresa
        WHERE id = ?
          AND empresa_id = ?
        """,
        (int(socio_id), int(empresa_id)),
    ).fetchone()

    if not fila:
        raise ValueError("No se encontró el socio indicado para la empresa activa.")

    socio = {
        "id": fila[0],
        "empresa_id": fila[1],
        "nombre": fila[2],
        "cuit": fila[3],
        "tipo_socio": fila[4],
        "estado": fila[5],
    }

    if _texto(socio["estado"]).upper() != "ACTIVO":
        raise ValueError("No se puede modificar la ficha integral de un socio dado de baja.")

    return socio


def _codigo_cuenta_particular_sugerido(socio_id: int) -> str:
    return f"SOCIO-{int(socio_id):04d}"


def _nombre_cuenta_particular_sugerido(nombre: str) -> str:
    nombre_limpio = _texto(nombre) or "Socio sin nombre"
    return f"Cuenta particular - {nombre_limpio}"


def actualizar_ficha_integral_socio(
    socio_id: int,
    empresa_id: int = 1,
    *,
    rol_relacion: str = "SOCIO",
    condicion_fiscal: str = "NO_INFORMADA",
    documento: str = "",
    email: str = "",
    telefono: str = "",
    domicilio: str = "",
    actividad_vinculada: str = "",
    proveedor_vinculado_referencia: str = "",
    cuenta_particular_habilitada: bool = False,
    cuenta_particular_codigo: str = "",
    cuenta_particular_nombre: str = "",
    cuenta_particular_significado: str = "",
    admite_prestamos: bool = False,
    admite_retiros: bool = False,
    admite_reintegros: bool = False,
    admite_honorarios: bool = False,
    admite_facturas_proveedor: bool = False,
    observaciones_ficha: str = "",
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        socio = _validar_socio_activo(conn, int(socio_id), int(empresa_id))

        rol = _normalizar_opcion(rol_relacion, TIPOS_RELACION_VALIDOS, "SOCIO")
        condicion = _normalizar_opcion(condicion_fiscal, CONDICIONES_FISCALES_VALIDAS, "NO_INFORMADA")

        cuenta_habilitada = _normalizar_bool(cuenta_particular_habilitada)
        cuenta_codigo = _texto(cuenta_particular_codigo)
        cuenta_nombre = _texto(cuenta_particular_nombre)

        if cuenta_habilitada:
            cuenta_codigo = cuenta_codigo or _codigo_cuenta_particular_sugerido(int(socio_id))
            cuenta_nombre = cuenta_nombre or _nombre_cuenta_particular_sugerido(socio["nombre"])

        cuenta_significado = _texto(cuenta_particular_significado)
        if cuenta_habilitada and not cuenta_significado:
            cuenta_significado = (
                "Control económico interno del socio para préstamos, retiros, reintegros, "
                "honorarios, facturas vinculadas u otros movimientos no capitalizables. "
                "No registra movimientos por sí sola."
            )

        conn.execute(
            """
            UPDATE socios_empresa
            SET
                rol_relacion = ?,
                condicion_fiscal = ?,
                documento = ?,
                email = ?,
                telefono = ?,
                domicilio = ?,
                actividad_vinculada = ?,
                proveedor_vinculado_referencia = ?,
                cuenta_particular_habilitada = ?,
                cuenta_particular_codigo = ?,
                cuenta_particular_nombre = ?,
                cuenta_particular_significado = ?,
                admite_prestamos = ?,
                admite_retiros = ?,
                admite_reintegros = ?,
                admite_honorarios = ?,
                admite_facturas_proveedor = ?,
                observaciones_ficha = ?,
                usuario_actualizacion_ficha = ?,
                fecha_actualizacion_ficha = CURRENT_TIMESTAMP,
                usuario_actualizacion = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
              AND empresa_id = ?
            """,
            (
                rol,
                condicion,
                _texto(documento),
                _texto(email),
                _texto(telefono),
                _texto(domicilio),
                _texto(actividad_vinculada),
                _texto(proveedor_vinculado_referencia),
                cuenta_habilitada,
                cuenta_codigo,
                cuenta_nombre,
                cuenta_significado,
                _normalizar_bool(admite_prestamos),
                _normalizar_bool(admite_retiros),
                _normalizar_bool(admite_reintegros),
                _normalizar_bool(admite_honorarios),
                _normalizar_bool(admite_facturas_proveedor),
                _texto(observaciones_ficha),
                _texto(usuario) or "sistema",
                _texto(usuario) or "sistema",
                int(socio_id),
                int(empresa_id),
            ),
        )

        _registrar_evento_ficha(
            conn,
            empresa_id=int(empresa_id),
            socio_id=int(socio_id),
            tipo_evento="ACTUALIZACION_FICHA_INTEGRAL",
            detalle="Se actualizó la ficha integral y datos de cuenta particular del socio.",
            usuario=usuario,
        )

        conn.commit()
        return {
            "ok": True,
            "socio_id": int(socio_id),
            "empresa_id": int(empresa_id),
            "mensaje": "Ficha integral del socio actualizada correctamente.",
        }
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "mensaje": str(exc)}
    finally:
        conn.close()


def preparar_cuenta_particular_socio(
    socio_id: int,
    empresa_id: int = 1,
    *,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        socio = _validar_socio_activo(conn, int(socio_id), int(empresa_id))
        cuenta_codigo = _codigo_cuenta_particular_sugerido(int(socio_id))
        cuenta_nombre = _nombre_cuenta_particular_sugerido(socio["nombre"])
        cuenta_significado = (
            "Control económico interno del socio para préstamos, retiros, reintegros, "
            "honorarios, facturas vinculadas u otros movimientos no capitalizables. "
            "No crea cuentas contables ni registra movimientos automáticamente."
        )

        conn.execute(
            """
            UPDATE socios_empresa
            SET
                cuenta_particular_habilitada = 1,
                cuenta_particular_codigo = COALESCE(NULLIF(TRIM(cuenta_particular_codigo), ''), ?),
                cuenta_particular_nombre = COALESCE(NULLIF(TRIM(cuenta_particular_nombre), ''), ?),
                cuenta_particular_significado = COALESCE(NULLIF(TRIM(cuenta_particular_significado), ''), ?),
                usuario_actualizacion_ficha = ?,
                fecha_actualizacion_ficha = CURRENT_TIMESTAMP,
                usuario_actualizacion = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
              AND empresa_id = ?
            """,
            (
                cuenta_codigo,
                cuenta_nombre,
                cuenta_significado,
                _texto(usuario) or "sistema",
                _texto(usuario) or "sistema",
                int(socio_id),
                int(empresa_id),
            ),
        )

        _registrar_evento_ficha(
            conn,
            empresa_id=int(empresa_id),
            socio_id=int(socio_id),
            tipo_evento="PREPARACION_CUENTA_PARTICULAR",
            detalle="Se preparó la cuenta particular interna del socio sin registrar movimientos.",
            usuario=usuario,
        )

        conn.commit()
        return {
            "ok": True,
            "socio_id": int(socio_id),
            "empresa_id": int(empresa_id),
            "cuenta_particular_codigo": cuenta_codigo,
            "cuenta_particular_nombre": cuenta_nombre,
            "mensaje": "Cuenta particular preparada correctamente.",
        }
    except Exception as exc:
        conn.rollback()
        return {"ok": False, "mensaje": str(exc)}
    finally:
        conn.close()


def obtener_resumen_socios_pro(empresa_id: int = 1) -> Dict[str, Any]:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        fila = conn.execute(
            """
            SELECT
                COUNT(*) AS total_socios,
                SUM(CASE WHEN estado = 'ACTIVO' THEN 1 ELSE 0 END) AS socios_activos,
                SUM(CASE WHEN estado = 'ACTIVO' AND COALESCE(cuenta_particular_habilitada, 0) = 1 THEN 1 ELSE 0 END) AS cuentas_preparadas,
                SUM(CASE WHEN estado = 'ACTIVO' AND COALESCE(admite_prestamos, 0) = 1 THEN 1 ELSE 0 END) AS admiten_prestamos,
                SUM(CASE WHEN estado = 'ACTIVO' AND COALESCE(admite_retiros, 0) = 1 THEN 1 ELSE 0 END) AS admiten_retiros
            FROM socios_empresa
            WHERE empresa_id = ?
            """,
            (int(empresa_id),),
        ).fetchone()

        return {
            "total_socios": int(fila[0] or 0),
            "socios_activos": int(fila[1] or 0),
            "cuentas_preparadas": int(fila[2] or 0),
            "admiten_prestamos": int(fila[3] or 0),
            "admiten_retiros": int(fila[4] or 0),
        }
    finally:
        conn.close()


def catalogo_conceptos_relacion_socios() -> pd.DataFrame:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        return pd.read_sql_query(
            """
            SELECT
                codigo, nombre, grupo, descripcion, naturaleza_contable,
                movimiento_real, genera_asiento_directo, impacta_caja_banco, estado
            FROM socios_conceptos_relacion
            WHERE estado = 'ACTIVO'
            ORDER BY grupo, codigo
            """,
            conn,
        )
    finally:
        conn.close()


def listar_eventos_ficha_socio(socio_id: int, empresa_id: int = 1) -> pd.DataFrame:
    asegurar_estructura_socios_pro()

    conn = conectar()
    try:
        return pd.read_sql_query(
            """
            SELECT tipo_evento, detalle, usuario, fecha_evento
            FROM socios_empresa_ficha_eventos
            WHERE empresa_id = ?
              AND socio_id = ?
            ORDER BY fecha_evento DESC, id DESC
            """,
            conn,
            params=(int(empresa_id), int(socio_id)),
        )
    finally:
        conn.close()