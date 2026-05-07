import os
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd

from database import conectar, ejecutar_query


# ======================================================
# CONSTANTES
# ======================================================

ESTADOS_EJERCICIO = {"ABIERTO", "CERRADO", "REABIERTO", "ANULADO"}

_SQL_MIGRACION = """
CREATE TABLE IF NOT EXISTS ejercicios_contables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    empresa_id INTEGER NOT NULL DEFAULT 1,

    nombre TEXT NOT NULL,
    fecha_inicio TEXT NOT NULL,
    fecha_cierre TEXT NOT NULL,

    anio_inicio INTEGER,
    anio_cierre INTEGER,

    estado TEXT NOT NULL DEFAULT 'ABIERTO',
    es_actual INTEGER NOT NULL DEFAULT 0,

    bloqueo_hasta TEXT,
    fecha_bloqueo TIMESTAMP,

    observaciones TEXT,

    usuario_creacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    usuario_cierre TEXT,
    fecha_cierre_operativo TIMESTAMP,
    motivo_cierre TEXT,

    usuario_reapertura TEXT,
    fecha_reapertura TIMESTAMP,
    motivo_reapertura TEXT,

    usuario_anulacion TEXT,
    fecha_anulacion TIMESTAMP,
    motivo_anulacion TEXT,

    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (empresa_id, fecha_inicio, fecha_cierre)
);

CREATE INDEX IF NOT EXISTS idx_ejercicios_empresa_estado
ON ejercicios_contables (empresa_id, estado);

CREATE INDEX IF NOT EXISTS idx_ejercicios_empresa_fechas
ON ejercicios_contables (empresa_id, fecha_inicio, fecha_cierre);

CREATE INDEX IF NOT EXISTS idx_ejercicios_empresa_actual
ON ejercicios_contables (empresa_id, es_actual);

CREATE INDEX IF NOT EXISTS idx_ejercicios_bloqueo
ON ejercicios_contables (empresa_id, bloqueo_hasta);

CREATE TABLE IF NOT EXISTS ejercicios_contables_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    ejercicio_id INTEGER,
    empresa_id INTEGER NOT NULL DEFAULT 1,

    evento TEXT NOT NULL,
    detalle TEXT,
    usuario TEXT,

    fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ejercicios_eventos_ejercicio
ON ejercicios_contables_eventos (ejercicio_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_ejercicios_eventos_empresa
ON ejercicios_contables_eventos (empresa_id, fecha_evento);
"""


# ======================================================
# UTILIDADES INTERNAS
# ======================================================

def migrar_ejercicios_contables() -> None:
    """
    Crea las tablas de ejercicios contables si no existen.

    Es idempotente:
    - puede ejecutarse desde tests;
    - puede ejecutarse desde Streamlit;
    - no borra datos.
    """
    conn = conectar()
    try:
        conn.executescript(_SQL_MIGRACION)
        conn.commit()
    finally:
        conn.close()


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalizar_fecha(valor: Any, nombre_campo: str = "fecha") -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()

    if isinstance(valor, date):
        return valor.isoformat()

    if isinstance(valor, str):
        limpio = valor.strip()
        try:
            return date.fromisoformat(limpio).isoformat()
        except Exception as exc:
            raise ValueError(f"{nombre_campo} debe tener formato YYYY-MM-DD.") from exc

    raise ValueError(f"{nombre_campo} debe tener formato YYYY-MM-DD.")


def _fecha(valor: Any, nombre_campo: str = "fecha") -> date:
    return date.fromisoformat(_normalizar_fecha(valor, nombre_campo))


def _resultado(ok: bool, mensaje: str, **extras) -> Dict[str, Any]:
    data = {"ok": ok, "mensaje": mensaje}
    data.update(extras)
    return data


def _df_a_dict(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if df is None or df.empty:
        return None

    fila = df.iloc[0].to_dict()

    limpio = {}
    for clave, valor in fila.items():
        if pd.isna(valor):
            limpio[clave] = None
        else:
            limpio[clave] = valor

    return limpio


def _registrar_evento(
    ejercicio_id: Optional[int],
    empresa_id: int,
    evento: str,
    detalle: str = "",
    usuario: Optional[str] = None,
    conn=None,
) -> None:
    sql = """
        INSERT INTO ejercicios_contables_eventos
        (ejercicio_id, empresa_id, evento, detalle, usuario)
        VALUES (?, ?, ?, ?, ?)
    """
    params = (ejercicio_id, empresa_id, evento, detalle, usuario)

    if conn is not None:
        conn.execute(sql, params)
        return

    ejecutar_query(sql, params)


def _hay_solapamiento(
    empresa_id: int,
    fecha_inicio: str,
    fecha_cierre: str,
    ejercicio_id_excluir: Optional[int] = None,
) -> bool:
    migrar_ejercicios_contables()

    params = [empresa_id, fecha_cierre, fecha_inicio]
    filtro_excluir = ""

    if ejercicio_id_excluir is not None:
        filtro_excluir = "AND id <> ?"
        params.append(ejercicio_id_excluir)

    df = ejecutar_query(
        f"""
        SELECT id
        FROM ejercicios_contables
        WHERE empresa_id = ?
          AND estado <> 'ANULADO'
          AND fecha_inicio <= ?
          AND fecha_cierre >= ?
          {filtro_excluir}
        LIMIT 1
        """,
        tuple(params),
        fetch=True,
    )

    return not df.empty


def _contar_movimientos_libro_en_rango(
    empresa_id: int,
    fecha_inicio: str,
    fecha_cierre: str,
) -> int:
    df = ejecutar_query(
        """
        SELECT COUNT(*) AS cantidad
        FROM libro_diario
        WHERE COALESCE(empresa_id, 1) = ?
          AND fecha >= ?
          AND fecha <= ?
        """,
        (empresa_id, fecha_inicio, fecha_cierre),
        fetch=True,
    )

    if df.empty:
        return 0

    return int(df.iloc[0]["cantidad"] or 0)


# ======================================================
# CONSULTAS
# ======================================================

def listar_ejercicios_contables(
    empresa_id: int = 1,
    incluir_anulados: bool = False,
) -> pd.DataFrame:
    migrar_ejercicios_contables()

    where_anulados = "" if incluir_anulados else "AND estado <> 'ANULADO'"

    return ejecutar_query(
        f"""
        SELECT
            id,
            empresa_id,
            nombre,
            fecha_inicio,
            fecha_cierre,
            anio_inicio,
            anio_cierre,
            estado,
            es_actual,
            bloqueo_hasta,
            fecha_bloqueo,
            observaciones,
            usuario_creacion,
            fecha_creacion,
            usuario_cierre,
            fecha_cierre_operativo,
            motivo_cierre,
            usuario_reapertura,
            fecha_reapertura,
            motivo_reapertura,
            usuario_anulacion,
            fecha_anulacion,
            motivo_anulacion,
            fecha_actualizacion
        FROM ejercicios_contables
        WHERE empresa_id = ?
        {where_anulados}
        ORDER BY fecha_inicio DESC, id DESC
        """,
        (empresa_id,),
        fetch=True,
    )


def obtener_ejercicio_por_id(ejercicio_id: int) -> Optional[Dict[str, Any]]:
    migrar_ejercicios_contables()

    df = ejecutar_query(
        """
        SELECT *
        FROM ejercicios_contables
        WHERE id = ?
        """,
        (ejercicio_id,),
        fetch=True,
    )

    return _df_a_dict(df)


def obtener_ejercicio_actual(empresa_id: int = 1) -> Optional[Dict[str, Any]]:
    migrar_ejercicios_contables()

    df = ejecutar_query(
        """
        SELECT *
        FROM ejercicios_contables
        WHERE empresa_id = ?
          AND estado <> 'ANULADO'
          AND es_actual = 1
        ORDER BY fecha_inicio DESC, id DESC
        LIMIT 1
        """,
        (empresa_id,),
        fetch=True,
    )

    actual = _df_a_dict(df)

    if actual:
        return actual

    df = ejecutar_query(
        """
        SELECT *
        FROM ejercicios_contables
        WHERE empresa_id = ?
          AND estado <> 'ANULADO'
        ORDER BY fecha_inicio DESC, id DESC
        LIMIT 1
        """,
        (empresa_id,),
        fetch=True,
    )

    return _df_a_dict(df)


def obtener_ejercicio_para_fecha(
    empresa_id: int,
    fecha_movimiento: Any,
    incluir_anulados: bool = False,
) -> Optional[Dict[str, Any]]:
    migrar_ejercicios_contables()

    fecha_norm = _normalizar_fecha(fecha_movimiento, "fecha_movimiento")
    where_anulados = "" if incluir_anulados else "AND estado <> 'ANULADO'"

    df = ejecutar_query(
        f"""
        SELECT *
        FROM ejercicios_contables
        WHERE empresa_id = ?
          AND fecha_inicio <= ?
          AND fecha_cierre >= ?
          {where_anulados}
        ORDER BY fecha_inicio DESC, id DESC
        LIMIT 1
        """,
        (empresa_id, fecha_norm, fecha_norm),
        fetch=True,
    )

    return _df_a_dict(df)


def listar_eventos_ejercicio(ejercicio_id: int) -> pd.DataFrame:
    migrar_ejercicios_contables()

    return ejecutar_query(
        """
        SELECT
            id,
            ejercicio_id,
            empresa_id,
            evento,
            detalle,
            usuario,
            fecha_evento
        FROM ejercicios_contables_eventos
        WHERE ejercicio_id = ?
        ORDER BY fecha_evento DESC, id DESC
        """,
        (ejercicio_id,),
        fetch=True,
    )


# ======================================================
# VALIDACIONES CONTABLES
# ======================================================

def validar_fecha_operativa_contable(
    empresa_id: int,
    fecha_movimiento: Any,
    permitir_periodo_cerrado: bool = False,
) -> Dict[str, Any]:
    """
    Valida si una fecha puede recibir movimientos contables operativos.

    Regla:
    - si no existe ejercicio, se bloquea;
    - si el ejercicio está CERRADO y la fecha cae dentro del bloqueo, se bloquea;
    - si permitir_periodo_cerrado=True, informa advertencia pero permite.
    """
    migrar_ejercicios_contables()

    try:
        fecha_norm = _normalizar_fecha(fecha_movimiento, "fecha_movimiento")
    except ValueError as exc:
        return _resultado(False, str(exc))

    ejercicio = obtener_ejercicio_para_fecha(empresa_id, fecha_norm)

    if not ejercicio:
        return _resultado(
            False,
            "No existe un ejercicio contable activo para esa fecha. "
            "Primero cargá el ejercicio contable de la empresa.",
            fecha=fecha_norm,
            ejercicio=None,
            bloqueada=True,
        )

    estado = str(ejercicio.get("estado") or "").upper()
    bloqueo_hasta = ejercicio.get("bloqueo_hasta")

    bloqueada = (
        estado == "CERRADO"
        and bloqueo_hasta is not None
        and fecha_norm <= str(bloqueo_hasta)
    )

    if bloqueada and not permitir_periodo_cerrado:
        return _resultado(
            False,
            f"La fecha {fecha_norm} pertenece al ejercicio cerrado "
            f"{ejercicio.get('nombre')}. Para modificarla se requiere reapertura controlada.",
            fecha=fecha_norm,
            ejercicio=ejercicio,
            bloqueada=True,
        )

    if bloqueada and permitir_periodo_cerrado:
        return _resultado(
            True,
            f"La fecha {fecha_norm} pertenece a un ejercicio cerrado, "
            "pero fue permitida por parámetro explícito.",
            fecha=fecha_norm,
            ejercicio=ejercicio,
            bloqueada=True,
            advertencia=True,
        )

    return _resultado(
        True,
        "Fecha contable habilitada.",
        fecha=fecha_norm,
        ejercicio=ejercicio,
        bloqueada=False,
    )


def obtener_rango_filtro_periodo(
    empresa_id: int,
    modo: str = "TODOS",
    ejercicio_id: Optional[int] = None,
    fecha_desde: Optional[Any] = None,
    fecha_hasta: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Devuelve un rango listo para usar en reportes.

    Modos:
    - TODOS
    - EJERCICIO
    - HASTA_CIERRE
    - RANGO_MANUAL
    """
    migrar_ejercicios_contables()

    modo_norm = str(modo or "TODOS").strip().upper()

    if modo_norm == "TODOS":
        return _resultado(
            True,
            "Todos los movimientos.",
            modo="TODOS",
            fecha_desde=None,
            fecha_hasta=None,
            ejercicio=None,
        )

    if modo_norm in {"EJERCICIO", "HASTA_CIERRE"}:
        ejercicio = None

        if ejercicio_id:
            ejercicio = obtener_ejercicio_por_id(int(ejercicio_id))
        else:
            ejercicio = obtener_ejercicio_actual(empresa_id)

        if not ejercicio or int(ejercicio.get("empresa_id") or 0) != int(empresa_id):
            return _resultado(False, "No se encontró el ejercicio contable seleccionado.")

        return _resultado(
            True,
            "Rango de ejercicio contable.",
            modo=modo_norm,
            fecha_desde=ejercicio.get("fecha_inicio"),
            fecha_hasta=ejercicio.get("fecha_cierre"),
            ejercicio=ejercicio,
        )

    if modo_norm == "RANGO_MANUAL":
        if not fecha_desde or not fecha_hasta:
            return _resultado(False, "Para rango manual se requieren fecha desde y fecha hasta.")

        desde = _normalizar_fecha(fecha_desde, "fecha_desde")
        hasta = _normalizar_fecha(fecha_hasta, "fecha_hasta")

        if desde > hasta:
            return _resultado(False, "La fecha desde no puede ser posterior a la fecha hasta.")

        return _resultado(
            True,
            "Rango manual.",
            modo="RANGO_MANUAL",
            fecha_desde=desde,
            fecha_hasta=hasta,
            ejercicio=None,
        )

    return _resultado(False, f"Modo de filtro no válido: {modo}")


# ======================================================
# OPERACIONES PRINCIPALES
# ======================================================

def crear_ejercicio_contable(
    empresa_id: int,
    fecha_inicio: Any,
    fecha_cierre: Any,
    nombre: Optional[str] = None,
    observaciones: Optional[str] = None,
    usuario: Optional[str] = None,
    marcar_actual: bool = True,
) -> Dict[str, Any]:
    migrar_ejercicios_contables()

    try:
        inicio = _normalizar_fecha(fecha_inicio, "fecha_inicio")
        cierre = _normalizar_fecha(fecha_cierre, "fecha_cierre")
    except ValueError as exc:
        return _resultado(False, str(exc))

    if inicio > cierre:
        return _resultado(False, "La fecha de inicio no puede ser posterior a la fecha de cierre.")

    if _hay_solapamiento(empresa_id, inicio, cierre):
        return _resultado(
            False,
            "El ejercicio se superpone con otro ejercicio activo de la misma empresa.",
        )

    fecha_inicio_date = date.fromisoformat(inicio)
    fecha_cierre_date = date.fromisoformat(cierre)

    nombre_final = (nombre or "").strip()
    if not nombre_final:
        nombre_final = f"Ejercicio {fecha_inicio_date.year}-{fecha_cierre_date.year}"

    conn = conectar()

    try:
        cur = conn.cursor()

        if marcar_actual:
            cur.execute(
                """
                UPDATE ejercicios_contables
                SET es_actual = 0,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE empresa_id = ?
                  AND estado <> 'ANULADO'
                """,
                (empresa_id,),
            )

        cur.execute(
            """
            INSERT INTO ejercicios_contables
            (
                empresa_id,
                nombre,
                fecha_inicio,
                fecha_cierre,
                anio_inicio,
                anio_cierre,
                estado,
                es_actual,
                observaciones,
                usuario_creacion
            )
            VALUES (?, ?, ?, ?, ?, ?, 'ABIERTO', ?, ?, ?)
            """,
            (
                empresa_id,
                nombre_final,
                inicio,
                cierre,
                fecha_inicio_date.year,
                fecha_cierre_date.year,
                1 if marcar_actual else 0,
                observaciones,
                usuario,
            ),
        )

        ejercicio_id = int(cur.lastrowid)

        _registrar_evento(
            ejercicio_id=ejercicio_id,
            empresa_id=empresa_id,
            evento="CREACION",
            detalle=f"Ejercicio creado: {nombre_final} ({inicio} al {cierre}).",
            usuario=usuario,
            conn=conn,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo crear el ejercicio: {exc}")

    finally:
        conn.close()

    return _resultado(
        True,
        "Ejercicio contable creado correctamente.",
        ejercicio_id=ejercicio_id,
        ejercicio=obtener_ejercicio_por_id(ejercicio_id),
    )


def marcar_ejercicio_actual(
    ejercicio_id: int,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    migrar_ejercicios_contables()

    ejercicio = obtener_ejercicio_por_id(ejercicio_id)

    if not ejercicio:
        return _resultado(False, "No se encontró el ejercicio contable.")

    if ejercicio.get("estado") == "ANULADO":
        return _resultado(False, "No se puede marcar como actual un ejercicio anulado.")

    empresa_id = int(ejercicio["empresa_id"])

    conn = conectar()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE ejercicios_contables
            SET es_actual = 0,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE empresa_id = ?
            """,
            (empresa_id,),
        )

        cur.execute(
            """
            UPDATE ejercicios_contables
            SET es_actual = 1,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (ejercicio_id,),
        )

        _registrar_evento(
            ejercicio_id=ejercicio_id,
            empresa_id=empresa_id,
            evento="MARCAR_ACTUAL",
            detalle="Ejercicio marcado como actual.",
            usuario=usuario,
            conn=conn,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo marcar el ejercicio como actual: {exc}")

    finally:
        conn.close()

    return _resultado(True, "Ejercicio marcado como actual.", ejercicio=obtener_ejercicio_por_id(ejercicio_id))


def cerrar_ejercicio_contable(
    ejercicio_id: int,
    motivo: str,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    migrar_ejercicios_contables()

    motivo_limpio = (motivo or "").strip()

    if not motivo_limpio:
        return _resultado(False, "Para cerrar un ejercicio se requiere motivo/observación.")

    ejercicio = obtener_ejercicio_por_id(ejercicio_id)

    if not ejercicio:
        return _resultado(False, "No se encontró el ejercicio contable.")

    estado = str(ejercicio.get("estado") or "").upper()

    if estado == "ANULADO":
        return _resultado(False, "No se puede cerrar un ejercicio anulado.")

    if estado == "CERRADO":
        return _resultado(False, "El ejercicio ya está cerrado.")

    empresa_id = int(ejercicio["empresa_id"])
    fecha_cierre = str(ejercicio["fecha_cierre"])

    conn = conectar()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE ejercicios_contables
            SET estado = 'CERRADO',
                bloqueo_hasta = ?,
                fecha_bloqueo = CURRENT_TIMESTAMP,
                usuario_cierre = ?,
                fecha_cierre_operativo = CURRENT_TIMESTAMP,
                motivo_cierre = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (fecha_cierre, usuario, motivo_limpio, ejercicio_id),
        )

        _registrar_evento(
            ejercicio_id=ejercicio_id,
            empresa_id=empresa_id,
            evento="CIERRE",
            detalle=f"Ejercicio cerrado. Bloqueo hasta {fecha_cierre}. Motivo: {motivo_limpio}",
            usuario=usuario,
            conn=conn,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo cerrar el ejercicio: {exc}")

    finally:
        conn.close()

    return _resultado(
        True,
        "Ejercicio cerrado correctamente. Las fechas del ejercicio quedan bloqueadas.",
        ejercicio=obtener_ejercicio_por_id(ejercicio_id),
    )


def reabrir_ejercicio_contable(
    ejercicio_id: int,
    motivo: str,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    migrar_ejercicios_contables()

    motivo_limpio = (motivo or "").strip()

    if not motivo_limpio:
        return _resultado(False, "Para reabrir un ejercicio se requiere motivo.")

    ejercicio = obtener_ejercicio_por_id(ejercicio_id)

    if not ejercicio:
        return _resultado(False, "No se encontró el ejercicio contable.")

    estado = str(ejercicio.get("estado") or "").upper()

    if estado == "ANULADO":
        return _resultado(False, "No se puede reabrir un ejercicio anulado.")

    if estado != "CERRADO":
        return _resultado(False, "Solo se puede reabrir un ejercicio cerrado.")

    empresa_id = int(ejercicio["empresa_id"])

    conn = conectar()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE ejercicios_contables
            SET estado = 'REABIERTO',
                bloqueo_hasta = NULL,
                fecha_bloqueo = NULL,
                usuario_reapertura = ?,
                fecha_reapertura = CURRENT_TIMESTAMP,
                motivo_reapertura = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (usuario, motivo_limpio, ejercicio_id),
        )

        _registrar_evento(
            ejercicio_id=ejercicio_id,
            empresa_id=empresa_id,
            evento="REAPERTURA",
            detalle=f"Ejercicio reabierto. Motivo: {motivo_limpio}",
            usuario=usuario,
            conn=conn,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo reabrir el ejercicio: {exc}")

    finally:
        conn.close()

    return _resultado(
        True,
        "Ejercicio reabierto correctamente.",
        ejercicio=obtener_ejercicio_por_id(ejercicio_id),
    )


def anular_ejercicio_contable(
    ejercicio_id: int,
    motivo: str,
    usuario: Optional[str] = None,
    forzar: bool = False,
) -> Dict[str, Any]:
    migrar_ejercicios_contables()

    motivo_limpio = (motivo or "").strip()

    if not motivo_limpio:
        return _resultado(False, "Para anular un ejercicio se requiere motivo.")

    ejercicio = obtener_ejercicio_por_id(ejercicio_id)

    if not ejercicio:
        return _resultado(False, "No se encontró el ejercicio contable.")

    if ejercicio.get("estado") == "ANULADO":
        return _resultado(False, "El ejercicio ya está anulado.")

    empresa_id = int(ejercicio["empresa_id"])
    fecha_inicio = str(ejercicio["fecha_inicio"])
    fecha_cierre = str(ejercicio["fecha_cierre"])

    movimientos = _contar_movimientos_libro_en_rango(empresa_id, fecha_inicio, fecha_cierre)

    if movimientos > 0 and not forzar:
        return _resultado(
            False,
            "No se puede anular el ejercicio porque tiene movimientos en Libro Diario. "
            "Usá reapertura o una acción administrativa controlada.",
            movimientos=movimientos,
        )

    conn = conectar()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE ejercicios_contables
            SET estado = 'ANULADO',
                es_actual = 0,
                bloqueo_hasta = NULL,
                fecha_bloqueo = NULL,
                usuario_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?,
                fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (usuario, motivo_limpio, ejercicio_id),
        )

        _registrar_evento(
            ejercicio_id=ejercicio_id,
            empresa_id=empresa_id,
            evento="ANULACION",
            detalle=f"Ejercicio anulado. Motivo: {motivo_limpio}",
            usuario=usuario,
            conn=conn,
        )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo anular el ejercicio: {exc}")

    finally:
        conn.close()

    return _resultado(True, "Ejercicio anulado correctamente.", ejercicio=obtener_ejercicio_por_id(ejercicio_id))


def obtener_resumen_ejercicios(empresa_id: int = 1) -> Dict[str, Any]:
    migrar_ejercicios_contables()

    df = listar_ejercicios_contables(empresa_id=empresa_id, incluir_anulados=True)

    if df.empty:
        return {
            "empresa_id": empresa_id,
            "total": 0,
            "abiertos": 0,
            "cerrados": 0,
            "reabiertos": 0,
            "anulados": 0,
            "actual": None,
        }

    estados = df["estado"].fillna("").astype(str).str.upper()

    return {
        "empresa_id": empresa_id,
        "total": int(len(df)),
        "abiertos": int((estados == "ABIERTO").sum()),
        "cerrados": int((estados == "CERRADO").sum()),
        "reabiertos": int((estados == "REABIERTO").sum()),
        "anulados": int((estados == "ANULADO").sum()),
        "actual": obtener_ejercicio_actual(empresa_id),
    }