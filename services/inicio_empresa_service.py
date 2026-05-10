from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from database import conectar, ejecutar_query
from services.ejercicios_contables_service import (
    migrar_ejercicios_contables,
    obtener_ejercicio_actual,
    obtener_ejercicio_por_id,
    validar_fecha_operativa_contable,
)
from services.asientos_origen_service import (
    anular_asiento_origen,
    crear_asiento_origen,
    migrar_asientos_origen,
)


TOLERANCIA = 0.01

ORIGEN_TESORERIA = "TESORERIA"
TABLA_TESORERIA_OPERACIONES = "tesoreria_operaciones"
TABLA_CAPITAL_ORIGENES = "capital_integraciones_origenes"


def _resultado(ok: bool, mensaje: str, **extras) -> Dict[str, Any]:
    data = {"ok": ok, "mensaje": mensaje}
    data.update(extras)
    return data


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    return str(valor).strip()


def _texto_upper(valor: Any) -> str:
    return _texto(valor).upper()


def _numero(valor: Any) -> float:
    try:
        if valor is None or pd.isna(valor):
            return 0.0
        return round(float(valor), 2)
    except Exception:
        return 0.0


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


def _df_a_dict(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if df is None or df.empty:
        return None
    fila = df.iloc[0].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in fila.items()}


def _tabla_existe(conn, tabla: str) -> bool:
    try:
        fila = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            LIMIT 1
            """,
            (tabla,),
        ).fetchone()
        return fila is not None
    except Exception:
        return False


def _columnas_tabla(conn, tabla: str) -> set:
    try:
        return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    except Exception:
        return set()


def _agregar_columna_si_no_existe(conn, tabla: str, columna: str, definicion: str) -> None:
    if not _tabla_existe(conn, tabla):
        return
    if columna not in _columnas_tabla(conn, tabla):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _leer_sql_migracion(ruta_relativa: str, fallback: str = "") -> str:
    ruta = Path(__file__).resolve().parents[1] / ruta_relativa
    if ruta.exists():
        return ruta.read_text(encoding="utf-8")
    return fallback


def _sql_migracion_capital() -> str:
    return _leer_sql_migracion(
        "migrations/016_asientos_origen.sql",
        """
        CREATE TABLE IF NOT EXISTS socios_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            nombre TEXT NOT NULL,
            cuit TEXT,
            tipo_socio TEXT NOT NULL DEFAULT 'SOCIO',
            porcentaje_participacion REAL NOT NULL DEFAULT 0,
            observaciones TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            usuario_creacion TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_actualizacion TEXT,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_baja TEXT,
            fecha_baja TIMESTAMP,
            motivo_baja TEXT
        );
        CREATE TABLE IF NOT EXISTS capital_social_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            ejercicio_id INTEGER,
            fecha_instrumento TEXT NOT NULL,
            tipo_instrumento TEXT NOT NULL DEFAULT 'INICIO_CONTABLE',
            referencia TEXT,
            descripcion TEXT NOT NULL DEFAULT 'Capital social inicial',
            capital_social_total REAL NOT NULL DEFAULT 0,
            total_suscripto REAL NOT NULL DEFAULT 0,
            total_integrado REAL NOT NULL DEFAULT 0,
            total_pendiente_integracion REAL NOT NULL DEFAULT 0,
            cuenta_socios_integracion_codigo TEXT,
            cuenta_socios_integracion_nombre TEXT,
            cuenta_capital_codigo TEXT,
            cuenta_capital_nombre TEXT,
            estado TEXT NOT NULL DEFAULT 'PROPUESTO',
            asiento_suscripcion_origen_id INTEGER,
            asiento_suscripcion_propuesto_id INTEGER,
            asiento_integracion_origen_id INTEGER,
            asiento_integracion_propuesto_id INTEGER,
            usuario_creacion TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_anulacion TEXT,
            fecha_anulacion TIMESTAMP,
            motivo_anulacion TEXT,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS capital_suscripciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capital_id INTEGER NOT NULL,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            socio_id INTEGER NOT NULL,
            porcentaje REAL NOT NULL DEFAULT 0,
            importe_suscripto REAL NOT NULL DEFAULT 0,
            importe_integrado REAL NOT NULL DEFAULT 0,
            importe_pendiente REAL NOT NULL DEFAULT 0,
            observaciones TEXT,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS capital_integraciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capital_id INTEGER NOT NULL,
            suscripcion_id INTEGER,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            socio_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            importe REAL NOT NULL DEFAULT 0,
            medio_integracion TEXT NOT NULL DEFAULT 'NO_INTEGRADO',
            cuenta_destino_codigo TEXT,
            cuenta_destino_nombre TEXT,
            referencia TEXT,
            observaciones TEXT,
            asiento_origen_id INTEGER,
            asiento_propuesto_id INTEGER,
            estado TEXT NOT NULL DEFAULT 'PROPUESTO',
            usuario_creacion TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_anulacion TEXT,
            fecha_anulacion TIMESTAMP,
            motivo_anulacion TEXT
        );
        CREATE TABLE IF NOT EXISTS capital_social_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capital_id INTEGER,
            socio_id INTEGER,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            evento TEXT NOT NULL,
            detalle TEXT,
            usuario TEXT,
            fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
    )


def _sql_migracion_inicio_societario_pro() -> str:
    return _leer_sql_migracion(
        "migrations/022_inicio_societario_integraciones_reales.sql",
        f"""
        CREATE TABLE IF NOT EXISTS {TABLA_CAPITAL_ORIGENES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capital_integracion_id INTEGER NOT NULL,
            capital_id INTEGER NOT NULL,
            suscripcion_id INTEGER,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            socio_id INTEGER NOT NULL,
            origen_modulo TEXT NOT NULL,
            origen_tabla TEXT NOT NULL,
            origen_id INTEGER NOT NULL,
            cuenta_tesoreria_id INTEGER,
            tesoreria_operacion_id INTEGER,
            movimiento_caja_id INTEGER,
            movimiento_banco_id INTEGER,
            estado TEXT NOT NULL DEFAULT 'ACTIVO',
            usuario_vinculacion TEXT,
            fecha_vinculacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario_anulacion TEXT,
            fecha_anulacion TIMESTAMP,
            motivo_anulacion TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_capital_integraciones_origenes_activo
        ON {TABLA_CAPITAL_ORIGENES} (empresa_id, origen_modulo, origen_tabla, origen_id)
        WHERE estado = 'ACTIVO';
        """,
    )


def _asegurar_extensiones_inicio_societario_conn(conn) -> None:
    """
    Extiende la estructura histórica de capital social sin romper la migración 016.

    SQLite no permite ADD COLUMN IF NOT EXISTS en forma portable para todos
    los entornos del proyecto, por eso las columnas se agregan desde Python
    de manera idempotente.
    """
    conn.executescript(_sql_migracion_inicio_societario_pro())

    _agregar_columna_si_no_existe(conn, "capital_integraciones", "origen_modulo", "TEXT")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "origen_tabla", "TEXT")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "origen_id", "INTEGER")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "cuenta_tesoreria_id", "INTEGER")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "tesoreria_operacion_id", "INTEGER")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "movimiento_caja_id", "INTEGER")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "movimiento_banco_id", "INTEGER")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "es_integracion_real", "INTEGER NOT NULL DEFAULT 0")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "fecha_vinculacion", "TIMESTAMP")
    _agregar_columna_si_no_existe(conn, "capital_integraciones", "usuario_vinculacion", "TEXT")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_capital_integraciones_origen_real
        ON capital_integraciones (empresa_id, origen_modulo, origen_tabla, origen_id, estado)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_capital_integraciones_tesoreria
        ON capital_integraciones (empresa_id, tesoreria_operacion_id, estado)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_capital_integraciones_origen_real_activo
        ON capital_integraciones (empresa_id, origen_modulo, origen_tabla, origen_id)
        WHERE es_integracion_real = 1
          AND estado <> 'ANULADO'
          AND origen_modulo IS NOT NULL
          AND origen_tabla IS NOT NULL
          AND origen_id IS NOT NULL
        """
    )


def migrar_capital_social() -> None:
    migrar_ejercicios_contables()
    migrar_asientos_origen()
    conn = conectar()
    try:
        conn.executescript(_sql_migracion_capital())
        _asegurar_extensiones_inicio_societario_conn(conn)
        conn.commit()
    finally:
        conn.close()


def asegurar_estructura_inicio_societario_pro() -> None:
    migrar_capital_social()


def _registrar_evento(capital_id=None, socio_id=None, empresa_id=1, evento="", detalle="", usuario=None, conn=None):
    sql = """
        INSERT INTO capital_social_eventos
        (capital_id, socio_id, empresa_id, evento, detalle, usuario)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (capital_id, socio_id, empresa_id, evento, detalle, usuario)
    if conn is not None:
        conn.execute(sql, params)
    else:
        ejecutar_query(sql, params)


def _asegurar_tesoreria_si_disponible() -> None:
    try:
        from services.tesoreria_service import inicializar_tesoreria

        inicializar_tesoreria()
    except Exception:
        # La etapa actual solo consulta Tesorería si está disponible.
        # Si no lo está, las funciones de integración devolverán error controlado.
        pass


def listar_socios_empresa(empresa_id: int = 1, incluir_bajas: bool = False) -> pd.DataFrame:
    migrar_capital_social()
    where_bajas = "" if incluir_bajas else "AND estado = 'ACTIVO'"
    return ejecutar_query(
        f"""
        SELECT *
        FROM socios_empresa
        WHERE empresa_id = ?
        {where_bajas}
        ORDER BY nombre
        """,
        (empresa_id,),
        fetch=True,
    )


def crear_socio_empresa(
    empresa_id: int,
    nombre: str,
    cuit: Optional[str] = None,
    tipo_socio: str = "SOCIO",
    porcentaje_participacion: float = 0,
    observaciones: Optional[str] = None,
    usuario: Optional[str] = None,
    conn=None,
) -> Dict[str, Any]:
    migrar_capital_social()
    nombre_limpio = _texto(nombre)
    if not nombre_limpio:
        return _resultado(False, "El nombre del socio es obligatorio.")

    porcentaje = _numero(porcentaje_participacion)
    if porcentaje < 0 or porcentaje > 100:
        return _resultado(False, "El porcentaje de participación debe estar entre 0 y 100.")

    close_conn = False
    if conn is None:
        conn = conectar()
        close_conn = True

    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO socios_empresa
            (empresa_id, nombre, cuit, tipo_socio, porcentaje_participacion, observaciones, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (empresa_id, nombre_limpio, _texto(cuit) or None, _texto(tipo_socio).upper() or "SOCIO", porcentaje, observaciones, usuario),
        )
        socio_id = int(cur.lastrowid)
        _registrar_evento(None, socio_id, empresa_id, "ALTA_SOCIO", f"Socio creado: {nombre_limpio}.", usuario, conn)
        if close_conn:
            conn.commit()
    except Exception as exc:
        if close_conn:
            conn.rollback()
        return _resultado(False, f"No se pudo crear el socio: {exc}")
    finally:
        if close_conn:
            conn.close()

    return _resultado(True, "Socio creado correctamente.", socio_id=socio_id)


def listar_capital_social_empresa(empresa_id: int = 1, incluir_anulados: bool = False) -> pd.DataFrame:
    migrar_capital_social()
    where_anulados = "" if incluir_anulados else "AND estado <> 'ANULADO'"
    return ejecutar_query(
        f"""
        SELECT *
        FROM capital_social_empresa
        WHERE empresa_id = ?
        {where_anulados}
        ORDER BY fecha_instrumento DESC, id DESC
        """,
        (empresa_id,),
        fetch=True,
    )


def obtener_capital_social(capital_id: int) -> Optional[Dict[str, Any]]:
    migrar_capital_social()
    cabecera = _df_a_dict(ejecutar_query("SELECT * FROM capital_social_empresa WHERE id = ?", (capital_id,), fetch=True))
    if not cabecera:
        return None
    suscripciones = ejecutar_query(
        """
        SELECT cs.*, se.nombre AS socio_nombre, se.cuit AS socio_cuit
        FROM capital_suscripciones cs
        LEFT JOIN socios_empresa se ON se.id = cs.socio_id
        WHERE cs.capital_id = ?
        ORDER BY se.nombre
        """,
        (capital_id,),
        fetch=True,
    )
    integraciones = ejecutar_query(
        """
        SELECT ci.*, se.nombre AS socio_nombre, se.cuit AS socio_cuit
        FROM capital_integraciones ci
        LEFT JOIN socios_empresa se ON se.id = ci.socio_id
        WHERE ci.capital_id = ?
        ORDER BY ci.fecha, ci.id
        """,
        (capital_id,),
        fetch=True,
    )
    cabecera["suscripciones"] = suscripciones.to_dict("records") if not suscripciones.empty else []
    cabecera["integraciones"] = integraciones.to_dict("records") if not integraciones.empty else []
    return cabecera


def listar_eventos_capital(capital_id: int) -> pd.DataFrame:
    migrar_capital_social()
    return ejecutar_query(
        """
        SELECT *
        FROM capital_social_eventos
        WHERE capital_id = ?
        ORDER BY fecha_evento DESC, id DESC
        """,
        (capital_id,),
        fetch=True,
    )


def _normalizar_socios_capital(socios: List[Dict[str, Any]], capital_total: float) -> Dict[str, Any]:
    if not socios:
        return _resultado(False, "Debe cargarse al menos un socio.")

    normalizados = []
    for idx, socio in enumerate(socios, start=1):
        nombre = _texto(socio.get("nombre") or socio.get("socio_nombre"))
        socio_id = socio.get("socio_id")
        if not nombre and not socio_id:
            return _resultado(False, f"El socio {idx} no tiene nombre.")

        porcentaje = _numero(socio.get("porcentaje"))
        suscripto = _numero(socio.get("importe_suscripto"))
        integrado = _numero(socio.get("importe_integrado"))

        if porcentaje <= 0:
            return _resultado(False, f"El socio {idx} debe tener porcentaje mayor a cero.")
        if suscripto <= 0:
            return _resultado(False, f"El socio {idx} debe tener capital suscripto mayor a cero.")
        if integrado < 0:
            return _resultado(False, f"El socio {idx} no puede tener integración negativa.")
        if integrado - suscripto > TOLERANCIA:
            return _resultado(False, f"El socio {idx} no puede integrar más de lo suscripto.")

        normalizados.append({
            "socio_id": int(socio_id) if socio_id else None,
            "nombre": nombre,
            "cuit": _texto(socio.get("cuit")) or None,
            "tipo_socio": _texto(socio.get("tipo_socio")) or "SOCIO",
            "porcentaje": porcentaje,
            "importe_suscripto": suscripto,
            "importe_integrado": integrado,
            "importe_pendiente": round(suscripto - integrado, 2),
            "medio_integracion": _texto(socio.get("medio_integracion")) or "NO_INTEGRADO",
            "cuenta_destino_codigo": _texto(socio.get("cuenta_destino_codigo")),
            "cuenta_destino_nombre": _texto(socio.get("cuenta_destino_nombre")) or "Caja/Banco/Bienes aportados",
            "referencia": _texto(socio.get("referencia")),
            "observaciones": _texto(socio.get("observaciones")),
        })

    total_porcentaje = round(sum(s["porcentaje"] for s in normalizados), 2)
    total_suscripto = round(sum(s["importe_suscripto"] for s in normalizados), 2)
    total_integrado = round(sum(s["importe_integrado"] for s in normalizados), 2)

    if abs(total_porcentaje - 100) > TOLERANCIA:
        return _resultado(False, "La suma de participaciones debe ser 100%.", total_porcentaje=total_porcentaje)
    if abs(total_suscripto - capital_total) > TOLERANCIA:
        return _resultado(False, "La suma del capital suscripto debe coincidir con el capital social total.", total_suscripto=total_suscripto, capital_total=capital_total)

    return _resultado(
        True,
        "Socios validados.",
        socios=normalizados,
        total_porcentaje=total_porcentaje,
        total_suscripto=total_suscripto,
        total_integrado=total_integrado,
        total_pendiente=round(total_suscripto - total_integrado, 2),
    )


def configurar_capital_social_inicial(
    empresa_id: int,
    ejercicio_id: int,
    fecha_instrumento: Any,
    capital_social_total: float,
    socios: List[Dict[str, Any]],
    descripcion: str = "Capital social inicial",
    referencia: Optional[str] = None,
    tipo_instrumento: str = "INICIO_CONTABLE",
    cuenta_socios_integracion_codigo: str = "",
    cuenta_socios_integracion_nombre: str = "Socios / Accionistas por integración",
    cuenta_capital_codigo: str = "",
    cuenta_capital_nombre: str = "Capital social",
    usuario: Optional[str] = None,
    generar_asientos: bool = True,
) -> Dict[str, Any]:
    migrar_capital_social()

    try:
        fecha_norm = _normalizar_fecha(fecha_instrumento, "fecha_instrumento")
    except ValueError as exc:
        return _resultado(False, str(exc))

    capital_total = _numero(capital_social_total)
    if capital_total <= 0:
        return _resultado(False, "El capital social total debe ser mayor a cero.")

    ejercicio = obtener_ejercicio_por_id(int(ejercicio_id))
    if not ejercicio or int(ejercicio.get("empresa_id") or 0) != int(empresa_id):
        return _resultado(False, "No se encontró el ejercicio contable informado para la empresa.")

    validacion_fecha = validar_fecha_operativa_contable(empresa_id, fecha_norm, permitir_periodo_cerrado=False)
    if not validacion_fecha.get("ok"):
        return validacion_fecha

    validacion_socios = _normalizar_socios_capital(socios, capital_total)
    if not validacion_socios["ok"]:
        return validacion_socios

    socios_norm = validacion_socios["socios"]
    total_suscripto = float(validacion_socios["total_suscripto"])
    total_integrado = float(validacion_socios["total_integrado"])
    total_pendiente = float(validacion_socios["total_pendiente"])

    descripcion_limpia = _texto(descripcion) or "Capital social inicial"
    cuenta_socios_nombre = _texto(cuenta_socios_integracion_nombre) or "Socios / Accionistas por integración"
    cuenta_capital_nombre_final = _texto(cuenta_capital_nombre) or "Capital social"

    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO capital_social_empresa
            (empresa_id, ejercicio_id, fecha_instrumento, tipo_instrumento, referencia, descripcion,
             capital_social_total, total_suscripto, total_integrado, total_pendiente_integracion,
             cuenta_socios_integracion_codigo, cuenta_socios_integracion_nombre,
             cuenta_capital_codigo, cuenta_capital_nombre, estado, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?)
            """,
            (
                empresa_id, ejercicio_id, fecha_norm, _texto(tipo_instrumento) or "INICIO_CONTABLE", referencia, descripcion_limpia,
                capital_total, total_suscripto, total_integrado, total_pendiente,
                _texto(cuenta_socios_integracion_codigo), cuenta_socios_nombre,
                _texto(cuenta_capital_codigo), cuenta_capital_nombre_final, usuario,
            ),
        )
        capital_id = int(cur.lastrowid)

        for socio in socios_norm:
            socio_id = socio["socio_id"]
            if not socio_id:
                res_socio = crear_socio_empresa(
                    empresa_id=empresa_id,
                    nombre=socio["nombre"],
                    cuit=socio["cuit"],
                    tipo_socio=socio["tipo_socio"],
                    porcentaje_participacion=socio["porcentaje"],
                    observaciones=socio["observaciones"],
                    usuario=usuario,
                    conn=conn,
                )
                if not res_socio["ok"]:
                    raise RuntimeError(res_socio["mensaje"])
                socio_id = int(res_socio["socio_id"])
            else:
                cur.execute(
                    """
                    UPDATE socios_empresa
                    SET porcentaje_participacion = ?, fecha_actualizacion = CURRENT_TIMESTAMP, usuario_actualizacion = ?
                    WHERE id = ? AND empresa_id = ?
                    """,
                    (socio["porcentaje"], usuario, socio_id, empresa_id),
                )

            cur.execute(
                """
                INSERT INTO capital_suscripciones
                (capital_id, empresa_id, socio_id, porcentaje, importe_suscripto, importe_integrado, importe_pendiente, observaciones)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (capital_id, empresa_id, socio_id, socio["porcentaje"], socio["importe_suscripto"], socio["importe_integrado"], socio["importe_pendiente"], socio["observaciones"]),
            )
            suscripcion_id = int(cur.lastrowid)
            socio["socio_id"] = socio_id
            socio["suscripcion_id"] = suscripcion_id

            if socio["importe_integrado"] > 0:
                cur.execute(
                    """
                    INSERT INTO capital_integraciones
                    (capital_id, suscripcion_id, empresa_id, socio_id, fecha, importe, medio_integracion,
                     cuenta_destino_codigo, cuenta_destino_nombre, referencia, observaciones, estado, usuario_creacion,
                     es_integracion_real)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?, 0)
                    """,
                    (
                        capital_id, suscripcion_id, empresa_id, socio_id, fecha_norm, socio["importe_integrado"], socio["medio_integracion"],
                        socio["cuenta_destino_codigo"], socio["cuenta_destino_nombre"], socio["referencia"] or referencia, socio["observaciones"], usuario,
                    ),
                )
        _registrar_evento(capital_id, None, empresa_id, "CREACION_CAPITAL", "Configuración inicial de capital social cargada.", usuario, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        return _resultado(False, f"No se pudo configurar el capital social: {exc}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    asiento_suscripcion = None
    asiento_integracion = None
    if generar_asientos:
        asiento_suscripcion = crear_asiento_origen(
            empresa_id=empresa_id,
            fecha=fecha_norm,
            tipo_origen="CAPITAL_SOCIAL",
            descripcion=f"Suscripción de capital social - {descripcion_limpia}",
            lineas=[
                {"cuenta_codigo": _texto(cuenta_socios_integracion_codigo), "cuenta_nombre": cuenta_socios_nombre, "debe": total_suscripto, "haber": 0, "glosa": "Capital suscripto por socios/accionistas"},
                {"cuenta_codigo": _texto(cuenta_capital_codigo), "cuenta_nombre": cuenta_capital_nombre_final, "debe": 0, "haber": total_suscripto, "glosa": "Capital social suscripto"},
            ],
            ejercicio_id=ejercicio_id,
            referencia=referencia,
            observaciones=f"Generado desde Inicio contable. Capital ID {capital_id}.",
            usuario=usuario,
            generar_propuesta=True,
        )
        if not asiento_suscripcion.get("ok"):
            return _resultado(False, f"Capital cargado, pero no se pudo generar asiento de suscripción: {asiento_suscripcion.get('mensaje')}", capital_id=capital_id)

        if total_integrado > 0:
            agrupado = {}
            for socio in socios_norm:
                importe = _numero(socio["importe_integrado"])
                if importe <= 0:
                    continue
                clave = (socio["cuenta_destino_codigo"], socio["cuenta_destino_nombre"])
                agrupado[clave] = round(agrupado.get(clave, 0) + importe, 2)

            lineas_integracion = [
                {"cuenta_codigo": codigo, "cuenta_nombre": nombre or "Caja/Banco/Bienes aportados", "debe": importe, "haber": 0, "glosa": "Integración de capital por socios/accionistas"}
                for (codigo, nombre), importe in agrupado.items()
            ]
            lineas_integracion.append({"cuenta_codigo": _texto(cuenta_socios_integracion_codigo), "cuenta_nombre": cuenta_socios_nombre, "debe": 0, "haber": total_integrado, "glosa": "Cancelación parcial/total de integración pendiente"})

            asiento_integracion = crear_asiento_origen(
                empresa_id=empresa_id,
                fecha=fecha_norm,
                tipo_origen="CAPITAL_SOCIAL",
                descripcion=f"Integración de capital social - {descripcion_limpia}",
                lineas=lineas_integracion,
                ejercicio_id=ejercicio_id,
                referencia=referencia,
                observaciones=f"Generado desde Inicio contable. Capital ID {capital_id}.",
                usuario=usuario,
                generar_propuesta=True,
            )
            if not asiento_integracion.get("ok"):
                return _resultado(False, f"Capital cargado, pero no se pudo generar asiento de integración: {asiento_integracion.get('mensaje')}", capital_id=capital_id)

        conn = conectar()
        try:
            conn.execute(
                """
                UPDATE capital_social_empresa
                SET asiento_suscripcion_origen_id = ?, asiento_suscripcion_propuesto_id = ?,
                    asiento_integracion_origen_id = ?, asiento_integracion_propuesto_id = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    asiento_suscripcion.get("asiento_origen_id") if asiento_suscripcion else None,
                    asiento_suscripcion.get("asiento_propuesto_id") if asiento_suscripcion else None,
                    asiento_integracion.get("asiento_origen_id") if asiento_integracion else None,
                    asiento_integracion.get("asiento_propuesto_id") if asiento_integracion else None,
                    capital_id,
                ),
            )
            _registrar_evento(capital_id, None, empresa_id, "ASIENTOS_PROPUESTOS", "Asientos propuestos de capital generados.", usuario, conn)
            conn.commit()
        finally:
            conn.close()

    return _resultado(
        True,
        "Inicio de capital social configurado correctamente. Los asientos quedaron como propuestas; todavía no impactan en Libro Diario.",
        capital_id=capital_id,
        asiento_suscripcion_origen_id=asiento_suscripcion.get("asiento_origen_id") if asiento_suscripcion else None,
        asiento_suscripcion_propuesto_id=asiento_suscripcion.get("asiento_propuesto_id") if asiento_suscripcion else None,
        asiento_integracion_origen_id=asiento_integracion.get("asiento_origen_id") if asiento_integracion else None,
        asiento_integracion_propuesto_id=asiento_integracion.get("asiento_propuesto_id") if asiento_integracion else None,
        capital=obtener_capital_social(capital_id),
    )


def _obtener_capital_conn(conn, capital_id: int) -> Optional[Dict[str, Any]]:
    cur = conn.execute("SELECT * FROM capital_social_empresa WHERE id = ? LIMIT 1", (int(capital_id),))
    fila = cur.fetchone()
    if not fila:
        return None
    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _obtener_suscripcion_conn(conn, capital_id: int, socio_id: int) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT cs.*, se.nombre AS socio_nombre, se.cuit AS socio_cuit
        FROM capital_suscripciones cs
        LEFT JOIN socios_empresa se ON se.id = cs.socio_id
        WHERE cs.capital_id = ?
          AND cs.socio_id = ?
          AND cs.estado = 'ACTIVO'
        LIMIT 1
        """,
        (int(capital_id), int(socio_id)),
    )
    fila = cur.fetchone()
    if not fila:
        return None
    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _obtener_integracion_conn(conn, integracion_id: int) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT ci.*, cse.cuenta_socios_integracion_codigo, cse.cuenta_socios_integracion_nombre,
               cse.ejercicio_id, se.nombre AS socio_nombre
        FROM capital_integraciones ci
        LEFT JOIN capital_social_empresa cse ON cse.id = ci.capital_id
        LEFT JOIN socios_empresa se ON se.id = ci.socio_id
        WHERE ci.id = ?
        LIMIT 1
        """,
        (int(integracion_id),),
    )
    fila = cur.fetchone()
    if not fila:
        return None
    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _obtener_operacion_tesoreria_conn(conn, empresa_id: int, operacion_id: int) -> Optional[Dict[str, Any]]:
    if not _tabla_existe(conn, "tesoreria_operaciones"):
        return None

    sql = """
        SELECT op.*,
               tc.tipo_cuenta AS cuenta_tesoreria_tipo,
               tc.nombre AS cuenta_tesoreria_nombre,
               tc.cuenta_contable_codigo AS cuenta_tesoreria_codigo,
               tc.cuenta_contable_nombre AS cuenta_tesoreria_cuenta_nombre
        FROM tesoreria_operaciones op
        LEFT JOIN tesoreria_cuentas tc
               ON tc.id = op.cuenta_tesoreria_id
              AND COALESCE(tc.empresa_id, 1) = COALESCE(op.empresa_id, 1)
        WHERE op.id = ?
          AND COALESCE(op.empresa_id, 1) = ?
        LIMIT 1
    """
    cur = conn.execute(sql, (int(operacion_id), int(empresa_id)))
    fila = cur.fetchone()
    if not fila:
        return None
    columnas = [col[0] for col in cur.description]
    return dict(zip(columnas, fila))


def _origen_real_usado_conn(conn, empresa_id: int, origen_modulo: str, origen_tabla: str, origen_id: int, excluir_integracion_id: Optional[int] = None) -> bool:
    params = [int(empresa_id), _texto_upper(origen_modulo), _texto(origen_tabla), int(origen_id)]
    filtro_exclusion = ""
    if excluir_integracion_id:
        filtro_exclusion = "AND id <> ?"
        params.append(int(excluir_integracion_id))

    fila = conn.execute(
        f"""
        SELECT id
        FROM capital_integraciones
        WHERE empresa_id = ?
          AND origen_modulo = ?
          AND origen_tabla = ?
          AND origen_id = ?
          AND COALESCE(es_integracion_real, 0) = 1
          AND estado <> 'ANULADO'
          {filtro_exclusion}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return fila is not None


def _actualizar_totales_capital_conn(conn, capital_id: int) -> None:
    fila = conn.execute(
        """
        SELECT
            ROUND(COALESCE(SUM(importe_suscripto), 0), 2) AS total_suscripto,
            ROUND(COALESCE(SUM(importe_integrado), 0), 2) AS total_integrado,
            ROUND(COALESCE(SUM(importe_pendiente), 0), 2) AS total_pendiente
        FROM capital_suscripciones
        WHERE capital_id = ?
          AND estado = 'ACTIVO'
        """,
        (int(capital_id),),
    ).fetchone()
    if not fila:
        return
    conn.execute(
        """
        UPDATE capital_social_empresa
        SET total_suscripto = ?,
            total_integrado = ?,
            total_pendiente_integracion = ?,
            fecha_actualizacion = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_numero(fila[0]), _numero(fila[1]), _numero(fila[2]), int(capital_id)),
    )


def _medio_desde_tipo_tesoreria(tipo_cuenta: str) -> str:
    tipo = _texto_upper(tipo_cuenta)
    if "CAJA" in tipo or tipo == "EFECTIVO":
        return "CAJA"
    if "BANCO" in tipo or "CBU" in tipo or "CUENTA" in tipo:
        return "BANCO"
    if "BILLETERA" in tipo:
        return "BILLETERA"
    if "TARJETA" in tipo:
        return "TARJETA"
    return "TESORERIA"


def listar_pendientes_integracion_por_socio(empresa_id: int = 1, capital_id: Optional[int] = None) -> pd.DataFrame:
    migrar_capital_social()
    filtros = ["cs.empresa_id = ?", "cs.estado = 'ACTIVO'", "cse.estado <> 'ANULADO'"]
    params: List[Any] = [int(empresa_id)]

    if capital_id is not None:
        filtros.append("cs.capital_id = ?")
        params.append(int(capital_id))

    return ejecutar_query(
        f"""
        SELECT
            cs.id AS suscripcion_id,
            cs.capital_id,
            cs.empresa_id,
            cs.socio_id,
            se.nombre AS socio_nombre,
            se.cuit AS socio_cuit,
            cs.porcentaje,
            cs.importe_suscripto,
            cs.importe_integrado,
            cs.importe_pendiente,
            cse.fecha_instrumento,
            cse.descripcion AS capital_descripcion,
            cse.cuenta_socios_integracion_codigo,
            cse.cuenta_socios_integracion_nombre,
            cse.cuenta_capital_codigo,
            cse.cuenta_capital_nombre
        FROM capital_suscripciones cs
        INNER JOIN capital_social_empresa cse ON cse.id = cs.capital_id
        LEFT JOIN socios_empresa se ON se.id = cs.socio_id
        WHERE {' AND '.join(filtros)}
        ORDER BY cse.fecha_instrumento DESC, se.nombre
        """,
        tuple(params),
        fetch=True,
    )


def listar_movimientos_tesoreria_disponibles_para_integracion(
    empresa_id: int = 1,
    cuenta_tesoreria_id: Optional[int] = None,
    desde: Optional[Any] = None,
    hasta: Optional[Any] = None,
    limite: int = 100,
) -> pd.DataFrame:
    migrar_capital_social()
    _asegurar_tesoreria_si_disponible()

    conn = conectar()
    try:
        if not _tabla_existe(conn, "tesoreria_operaciones"):
            return pd.DataFrame()

        filtros = [
            "COALESCE(op.empresa_id, 1) = ?",
            "COALESCE(op.importe, 0) > 0",
            "UPPER(COALESCE(op.estado, 'CONFIRMADA')) NOT IN ('ANULADA', 'ANULADO', 'CANCELADA')",
            """
            NOT EXISTS (
                SELECT 1
                FROM capital_integraciones ci
                WHERE ci.empresa_id = COALESCE(op.empresa_id, 1)
                  AND ci.origen_modulo = 'TESORERIA'
                  AND ci.origen_tabla = 'tesoreria_operaciones'
                  AND ci.origen_id = op.id
                  AND COALESCE(ci.es_integracion_real, 0) = 1
                  AND ci.estado <> 'ANULADO'
            )
            """,
        ]
        params: List[Any] = [int(empresa_id)]

        if cuenta_tesoreria_id is not None:
            filtros.append("op.cuenta_tesoreria_id = ?")
            params.append(int(cuenta_tesoreria_id))

        if desde is not None:
            filtros.append("COALESCE(op.fecha_contable, op.fecha_operacion) >= ?")
            params.append(_normalizar_fecha(desde, "desde"))

        if hasta is not None:
            filtros.append("COALESCE(op.fecha_contable, op.fecha_operacion) <= ?")
            params.append(_normalizar_fecha(hasta, "hasta"))

        params.append(max(1, int(limite or 100)))

        return pd.read_sql_query(
            f"""
            SELECT
                op.id AS tesoreria_operacion_id,
                op.empresa_id,
                op.tipo_operacion,
                op.subtipo,
                op.fecha_operacion,
                op.fecha_contable,
                COALESCE(op.fecha_contable, op.fecha_operacion) AS fecha,
                op.cuenta_tesoreria_id,
                tc.tipo_cuenta AS cuenta_tesoreria_tipo,
                tc.nombre AS cuenta_tesoreria_nombre,
                tc.cuenta_contable_codigo,
                tc.cuenta_contable_nombre,
                op.tercero_nombre,
                op.tercero_cuit,
                op.descripcion,
                op.referencia_externa,
                op.importe,
                op.estado
            FROM tesoreria_operaciones op
            LEFT JOIN tesoreria_cuentas tc
                   ON tc.id = op.cuenta_tesoreria_id
                  AND COALESCE(tc.empresa_id, 1) = COALESCE(op.empresa_id, 1)
            WHERE {' AND '.join(filtros)}
            ORDER BY COALESCE(op.fecha_contable, op.fecha_operacion) DESC, op.id DESC
            LIMIT ?
            """,
            conn,
            params=tuple(params),
        )
    finally:
        conn.close()


def registrar_integracion_capital_desde_tesoreria(
    empresa_id: int,
    capital_id: int,
    socio_id: int,
    tesoreria_operacion_id: int,
    importe: float,
    fecha_integracion: Optional[Any] = None,
    referencia: Optional[str] = None,
    observaciones: Optional[str] = None,
    usuario: Optional[str] = None,
    generar_asiento: bool = True,
) -> Dict[str, Any]:
    """
    Registra una integración de capital vinculada a un movimiento real de Tesorería.

    Esta función es el camino PRO para integrar capital por Caja/Banco/Tesorería:
    - valida que el socio tenga saldo pendiente;
    - valida que la operación de tesorería exista y no esté usada;
    - toma la cuenta contable real de la cuenta de tesorería;
    - genera asiento propuesto a Bandeja;
    - no impacta directo en Libro Diario.
    """
    migrar_capital_social()
    _asegurar_tesoreria_si_disponible()

    importe_norm = _numero(importe)
    if importe_norm <= 0:
        return _resultado(False, "El importe de integración debe ser mayor a cero.")

    conn = conectar()
    integracion_id = None
    try:
        capital = _obtener_capital_conn(conn, capital_id)
        if not capital:
            return _resultado(False, "No se encontró la configuración de capital social.")
        if int(capital.get("empresa_id") or 0) != int(empresa_id):
            return _resultado(False, "El capital informado no pertenece a la empresa.")
        if _texto_upper(capital.get("estado")) == "ANULADO":
            return _resultado(False, "No se puede integrar capital sobre una configuración anulada.")

        suscripcion = _obtener_suscripcion_conn(conn, capital_id, socio_id)
        if not suscripcion:
            return _resultado(False, "No se encontró suscripción activa para el socio informado.")

        pendiente = _numero(suscripcion.get("importe_pendiente"))
        if importe_norm - pendiente > TOLERANCIA:
            return _resultado(
                False,
                "La integración no puede superar el saldo pendiente del socio.",
                importe_solicitado=importe_norm,
                importe_pendiente=pendiente,
            )

        operacion = _obtener_operacion_tesoreria_conn(conn, empresa_id, tesoreria_operacion_id)
        if not operacion:
            return _resultado(False, "No se encontró la operación de Tesorería informada.")

        estado_operacion = _texto_upper(operacion.get("estado") or "CONFIRMADA")
        if estado_operacion in {"ANULADA", "ANULADO", "CANCELADA"}:
            return _resultado(False, "La operación de Tesorería está anulada o cancelada.")

        importe_operacion = _numero(operacion.get("importe"))
        if importe_operacion <= 0:
            return _resultado(False, "Solo se pueden aplicar movimientos positivos de Tesorería como integración de capital.")
        if importe_norm - importe_operacion > TOLERANCIA:
            return _resultado(False, "La integración no puede superar el importe del movimiento de Tesorería.")

        if _origen_real_usado_conn(
            conn,
            empresa_id=empresa_id,
            origen_modulo=ORIGEN_TESORERIA,
            origen_tabla=TABLA_TESORERIA_OPERACIONES,
            origen_id=tesoreria_operacion_id,
        ):
            return _resultado(False, "La operación de Tesorería ya fue aplicada como integración de capital.")

        cuenta_codigo = _texto(operacion.get("cuenta_tesoreria_codigo"))
        cuenta_nombre = _texto(operacion.get("cuenta_tesoreria_cuenta_nombre")) or _texto(operacion.get("cuenta_tesoreria_nombre"))
        if not cuenta_codigo or not cuenta_nombre:
            return _resultado(False, "La cuenta de Tesorería no tiene cuenta contable vinculada al Plan de Cuentas.")

        fecha_base = fecha_integracion or operacion.get("fecha_contable") or operacion.get("fecha_operacion") or date.today()
        try:
            fecha_norm = _normalizar_fecha(fecha_base, "fecha_integracion")
        except ValueError as exc:
            return _resultado(False, str(exc))

        validacion_fecha = validar_fecha_operativa_contable(int(empresa_id), fecha_norm, permitir_periodo_cerrado=False)
        if not validacion_fecha.get("ok"):
            return validacion_fecha

        nueva_integracion_socio = round(_numero(suscripcion.get("importe_integrado")) + importe_norm, 2)
        nuevo_pendiente = round(_numero(suscripcion.get("importe_pendiente")) - importe_norm, 2)
        if nuevo_pendiente < 0 and abs(nuevo_pendiente) <= TOLERANCIA:
            nuevo_pendiente = 0.0

        medio = _medio_desde_tipo_tesoreria(operacion.get("cuenta_tesoreria_tipo"))
        referencia_final = _texto(referencia) or _texto(operacion.get("referencia_externa")) or f"Tesorería operación {tesoreria_operacion_id}"
        observaciones_final = _texto(observaciones) or _texto(operacion.get("descripcion"))

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO capital_integraciones
            (capital_id, suscripcion_id, empresa_id, socio_id, fecha, importe, medio_integracion,
             cuenta_destino_codigo, cuenta_destino_nombre, referencia, observaciones,
             origen_modulo, origen_tabla, origen_id, cuenta_tesoreria_id, tesoreria_operacion_id,
             es_integracion_real, fecha_vinculacion, usuario_vinculacion,
             estado, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, ?, 'PROPUESTO', ?)
            """,
            (
                int(capital_id),
                int(suscripcion.get("id")),
                int(empresa_id),
                int(socio_id),
                fecha_norm,
                importe_norm,
                medio,
                cuenta_codigo,
                cuenta_nombre,
                referencia_final,
                observaciones_final,
                ORIGEN_TESORERIA,
                TABLA_TESORERIA_OPERACIONES,
                int(tesoreria_operacion_id),
                operacion.get("cuenta_tesoreria_id"),
                int(tesoreria_operacion_id),
                usuario,
                usuario,
            ),
        )
        integracion_id = int(cur.lastrowid)

        cur.execute(
            """
            INSERT INTO capital_integraciones_origenes
            (capital_integracion_id, capital_id, suscripcion_id, empresa_id, socio_id,
             origen_modulo, origen_tabla, origen_id, cuenta_tesoreria_id, tesoreria_operacion_id,
             estado, usuario_vinculacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?)
            """,
            (
                integracion_id,
                int(capital_id),
                int(suscripcion.get("id")),
                int(empresa_id),
                int(socio_id),
                ORIGEN_TESORERIA,
                TABLA_TESORERIA_OPERACIONES,
                int(tesoreria_operacion_id),
                operacion.get("cuenta_tesoreria_id"),
                int(tesoreria_operacion_id),
                usuario,
            ),
        )

        cur.execute(
            """
            UPDATE capital_suscripciones
            SET importe_integrado = ?,
                importe_pendiente = ?
            WHERE id = ?
            """,
            (nueva_integracion_socio, nuevo_pendiente, int(suscripcion.get("id"))),
        )
        _actualizar_totales_capital_conn(conn, capital_id)
        _registrar_evento(
            capital_id,
            socio_id,
            empresa_id,
            "INTEGRACION_REAL_TESORERIA",
            f"Integración real por Tesorería operación {tesoreria_operacion_id} por {importe_norm:.2f}.",
            usuario,
            conn,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo registrar la integración real de capital: {exc}")
    finally:
        conn.close()

    asiento = None
    if generar_asiento:
        cuenta_socios_codigo = _texto(capital.get("cuenta_socios_integracion_codigo"))
        cuenta_socios_nombre = _texto(capital.get("cuenta_socios_integracion_nombre")) or "Socios / Accionistas por integración"

        asiento = crear_asiento_origen(
            empresa_id=int(empresa_id),
            fecha=fecha_norm,
            tipo_origen="CAPITAL_SOCIAL",
            descripcion=f"Integración real de capital - {_texto(suscripcion.get('socio_nombre')) or 'Socio'}",
            lineas=[
                {
                    "cuenta_codigo": cuenta_codigo,
                    "cuenta_nombre": cuenta_nombre,
                    "debe": importe_norm,
                    "haber": 0,
                    "glosa": "Ingreso real por integración de capital",
                },
                {
                    "cuenta_codigo": cuenta_socios_codigo,
                    "cuenta_nombre": cuenta_socios_nombre,
                    "debe": 0,
                    "haber": importe_norm,
                    "glosa": "Cancelación de capital pendiente de integración",
                },
            ],
            ejercicio_id=capital.get("ejercicio_id"),
            referencia=referencia_final,
            observaciones=f"Generado desde Inicio societario PRO. Integración ID {integracion_id}. Tesorería operación {tesoreria_operacion_id}.",
            usuario=usuario,
            generar_propuesta=True,
        )
        if not asiento.get("ok"):
            # Se revierte la integración para no dejar capital integrado sin propuesta contable.
            anular_integracion_capital(
                integracion_id=integracion_id,
                motivo=f"No se pudo generar asiento propuesto: {asiento.get('mensaje')}",
                usuario=usuario,
                anular_asiento_vinculado=False,
            )
            return _resultado(
                False,
                f"No se pudo generar el asiento propuesto de integración: {asiento.get('mensaje')}",
                integracion_id=integracion_id,
            )

        conn = conectar()
        try:
            conn.execute(
                """
                UPDATE capital_integraciones
                SET asiento_origen_id = ?,
                    asiento_propuesto_id = ?
                WHERE id = ?
                """,
                (
                    asiento.get("asiento_origen_id"),
                    asiento.get("asiento_propuesto_id"),
                    integracion_id,
                ),
            )
            _registrar_evento(
                capital_id,
                socio_id,
                empresa_id,
                "ASIENTO_INTEGRACION_REAL_PROPUESTO",
                f"Asiento propuesto {asiento.get('asiento_propuesto_id')} generado para integración real {integracion_id}.",
                usuario,
                conn,
            )
            conn.commit()
        finally:
            conn.close()

    return _resultado(
        True,
        "Integración real de capital registrada correctamente. El asiento quedó propuesto para revisión; no impactó directo en Libro Diario.",
        integracion_id=integracion_id,
        asiento_origen_id=asiento.get("asiento_origen_id") if asiento else None,
        asiento_propuesto_id=asiento.get("asiento_propuesto_id") if asiento else None,
        capital=obtener_capital_social(capital_id),
    )


def anular_integracion_capital(
    integracion_id: int,
    motivo: str,
    usuario: Optional[str] = None,
    anular_asiento_vinculado: bool = True,
) -> Dict[str, Any]:
    migrar_capital_social()

    motivo_limpio = _texto(motivo)
    if not motivo_limpio:
        return _resultado(False, "Para anular la integración se requiere motivo.")

    conn = conectar()
    try:
        integracion = _obtener_integracion_conn(conn, integracion_id)
        if not integracion:
            return _resultado(False, "No se encontró la integración de capital.")
        if _texto_upper(integracion.get("estado")) == "ANULADO":
            return _resultado(False, "La integración ya está anulada.")

        asiento_propuesto_id = integracion.get("asiento_propuesto_id")
        if asiento_propuesto_id:
            fila_estado = conn.execute(
                "SELECT estado FROM asientos_propuestos WHERE id = ? LIMIT 1",
                (int(asiento_propuesto_id),),
            ).fetchone()
            estado_asiento = _texto_upper(fila_estado[0]) if fila_estado else ""
            if estado_asiento == "CONTABILIZADO":
                return _resultado(False, "No se puede anular la integración porque su asiento ya fue contabilizado. Use reverso controlado desde Bandeja.")

        cur_sus = conn.execute(
            """
            SELECT *
            FROM capital_suscripciones
            WHERE id = ?
              AND estado = 'ACTIVO'
            LIMIT 1
            """,
            (int(integracion.get("suscripcion_id")) if integracion.get("suscripcion_id") else 0,),
        )
        suscripcion = cur_sus.fetchone()
        if not suscripcion:
            return _resultado(False, "No se encontró la suscripción activa asociada a la integración.")

        columnas_sus = [col[0] for col in cur_sus.description]
        suscripcion_dict = dict(zip(columnas_sus, suscripcion))

        importe = _numero(integracion.get("importe"))
        nuevo_integrado = round(_numero(suscripcion_dict.get("importe_integrado")) - importe, 2)
        nuevo_pendiente = round(_numero(suscripcion_dict.get("importe_pendiente")) + importe, 2)
        if nuevo_integrado < 0 and abs(nuevo_integrado) <= TOLERANCIA:
            nuevo_integrado = 0.0

        conn.execute(
            """
            UPDATE capital_integraciones
            SET estado = 'ANULADO',
                usuario_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?
            WHERE id = ?
            """,
            (usuario, motivo_limpio, int(integracion_id)),
        )
        conn.execute(
            """
            UPDATE capital_integraciones_origenes
            SET estado = 'ANULADO',
                usuario_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?
            WHERE capital_integracion_id = ?
              AND estado = 'ACTIVO'
            """,
            (usuario, motivo_limpio, int(integracion_id)),
        )
        conn.execute(
            """
            UPDATE capital_suscripciones
            SET importe_integrado = ?,
                importe_pendiente = ?
            WHERE id = ?
            """,
            (nuevo_integrado, nuevo_pendiente, int(integracion.get("suscripcion_id"))),
        )
        _actualizar_totales_capital_conn(conn, int(integracion.get("capital_id")))
        _registrar_evento(
            integracion.get("capital_id"),
            integracion.get("socio_id"),
            integracion.get("empresa_id"),
            "ANULACION_INTEGRACION",
            f"Integración {integracion_id} anulada. Motivo: {motivo_limpio}",
            usuario,
            conn,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo anular la integración de capital: {exc}")
    finally:
        conn.close()

    if anular_asiento_vinculado and integracion.get("asiento_origen_id"):
        res_asiento = anular_asiento_origen(
            asiento_origen_id=int(integracion.get("asiento_origen_id")),
            motivo=f"Anulación de integración de capital {integracion_id}: {motivo_limpio}",
            usuario=usuario,
        )
        if not res_asiento.get("ok"):
            return _resultado(
                False,
                f"La integración fue anulada, pero no se pudo anular el asiento propuesto vinculado: {res_asiento.get('mensaje')}",
                integracion_id=integracion_id,
            )

    return _resultado(
        True,
        "Integración de capital anulada correctamente. El saldo pendiente del socio fue restaurado.",
        integracion_id=integracion_id,
        capital=obtener_capital_social(int(integracion.get("capital_id"))),
    )


def obtener_resumen_capital_socios(empresa_id: int = 1, capital_id: Optional[int] = None) -> Dict[str, Any]:
    migrar_capital_social()
    filtros = ["empresa_id = ?", "estado <> 'ANULADO'"]
    params: List[Any] = [int(empresa_id)]
    if capital_id is not None:
        filtros.append("id = ?")
        params.append(int(capital_id))

    capitales = ejecutar_query(
        f"""
        SELECT
            COUNT(*) AS cantidad_capitales,
            ROUND(COALESCE(SUM(capital_social_total), 0), 2) AS capital_social_total,
            ROUND(COALESCE(SUM(total_suscripto), 0), 2) AS total_suscripto,
            ROUND(COALESCE(SUM(total_integrado), 0), 2) AS total_integrado,
            ROUND(COALESCE(SUM(total_pendiente_integracion), 0), 2) AS total_pendiente_integracion
        FROM capital_social_empresa
        WHERE {' AND '.join(filtros)}
        """,
        tuple(params),
        fetch=True,
    )
    fila_cap = _df_a_dict(capitales) or {}

    socios = listar_socios_empresa(empresa_id=empresa_id, incluir_bajas=False)
    pendientes = listar_pendientes_integracion_por_socio(empresa_id=empresa_id, capital_id=capital_id)

    if pendientes.empty:
        socios_con_pendiente = 0
    else:
        socios_con_pendiente = int((pendientes["importe_pendiente"].astype(float) > TOLERANCIA).sum())

    return {
        "empresa_id": int(empresa_id),
        "capital_id": capital_id,
        "cantidad_capitales": int(fila_cap.get("cantidad_capitales") or 0),
        "cantidad_socios": int(len(socios)) if not socios.empty else 0,
        "capital_social_total": _numero(fila_cap.get("capital_social_total")),
        "total_suscripto": _numero(fila_cap.get("total_suscripto")),
        "total_integrado": _numero(fila_cap.get("total_integrado")),
        "total_pendiente_integracion": _numero(fila_cap.get("total_pendiente_integracion")),
        "socios_con_pendiente": socios_con_pendiente,
    }


def obtener_estado_inicio_contable(empresa_id: int = 1) -> Dict[str, Any]:
    migrar_capital_social()
    ejercicios = ejecutar_query(
        "SELECT COUNT(*) AS cantidad FROM ejercicios_contables WHERE empresa_id = ? AND estado <> 'ANULADO'",
        (empresa_id,),
        fetch=True,
    )
    capitales = listar_capital_social_empresa(empresa_id, incluir_anulados=False)
    socios = listar_socios_empresa(empresa_id, incluir_bajas=False)
    asientos_apertura = ejecutar_query(
        """
        SELECT COUNT(*) AS cantidad
        FROM asientos_origen
        WHERE empresa_id = ? AND tipo_origen = 'APERTURA' AND estado <> 'ANULADO'
        """,
        (empresa_id,),
        fetch=True,
    )
    libro = ejecutar_query(
        "SELECT COUNT(*) AS cantidad FROM libro_diario WHERE COALESCE(empresa_id, 1) = ?",
        (empresa_id,),
        fetch=True,
    )
    cant_ejercicios = int(ejercicios.iloc[0]["cantidad"] or 0) if not ejercicios.empty else 0
    cant_apertura = int(asientos_apertura.iloc[0]["cantidad"] or 0) if not asientos_apertura.empty else 0
    cant_libro = int(libro.iloc[0]["cantidad"] or 0) if not libro.empty else 0
    resumen = obtener_resumen_capital_socios(empresa_id=empresa_id)
    return {
        "empresa_id": empresa_id,
        "tiene_ejercicio": cant_ejercicios > 0,
        "cantidad_ejercicios": cant_ejercicios,
        "ejercicio_actual": obtener_ejercicio_actual(empresa_id),
        "tiene_capital_social": not capitales.empty,
        "cantidad_capitales": int(len(capitales)) if not capitales.empty else 0,
        "tiene_socios": not socios.empty,
        "cantidad_socios": int(len(socios)) if not socios.empty else 0,
        "tiene_asiento_apertura": cant_apertura > 0,
        "cantidad_asientos_apertura": cant_apertura,
        "cantidad_movimientos_libro_diario": cant_libro,
        "requiere_inicio_contable": cant_ejercicios == 0 or capitales.empty or cant_apertura == 0,
        "capital_social_total": resumen.get("capital_social_total", 0),
        "capital_total_integrado": resumen.get("total_integrado", 0),
        "capital_pendiente_integracion": resumen.get("total_pendiente_integracion", 0),
        "socios_con_pendiente_integracion": resumen.get("socios_con_pendiente", 0),
    }


def anular_capital_social(capital_id: int, motivo: str, usuario: Optional[str] = None) -> Dict[str, Any]:
    migrar_capital_social()
    motivo_limpio = _texto(motivo)
    if not motivo_limpio:
        return _resultado(False, "Para anular la configuración de capital se requiere motivo.")
    capital = obtener_capital_social(capital_id)
    if not capital:
        return _resultado(False, "No se encontró la configuración de capital.")
    if capital.get("estado") == "ANULADO":
        return _resultado(False, "La configuración de capital ya está anulada.")
    empresa_id = int(capital["empresa_id"])
    conn = conectar()
    try:
        conn.execute(
            """
            UPDATE capital_social_empresa
            SET estado = 'ANULADO', usuario_anulacion = ?, fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (usuario, motivo_limpio, capital_id),
        )
        conn.execute("UPDATE capital_suscripciones SET estado = 'ANULADO' WHERE capital_id = ?", (capital_id,))
        conn.execute("UPDATE capital_integraciones SET estado = 'ANULADO' WHERE capital_id = ?", (capital_id,))
        conn.execute(
            """
            UPDATE capital_integraciones_origenes
            SET estado = 'ANULADO',
                usuario_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?
            WHERE capital_id = ?
              AND estado = 'ACTIVO'
            """,
            (usuario, motivo_limpio, capital_id),
        )
        _registrar_evento(capital_id, None, empresa_id, "ANULACION", f"Capital anulado. Motivo: {motivo_limpio}", usuario, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo anular la configuración de capital: {exc}")
    finally:
        conn.close()
    return _resultado(True, "Configuración de capital anulada correctamente.", capital=obtener_capital_social(capital_id))