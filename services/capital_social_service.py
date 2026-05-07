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
from services.asientos_origen_service import crear_asiento_origen, migrar_asientos_origen


TOLERANCIA = 0.01


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


def _sql_migracion_capital() -> str:
    ruta = Path(__file__).resolve().parents[1] / "migrations" / "016_asientos_origen.sql"
    if ruta.exists():
        return ruta.read_text(encoding="utf-8")
    return """
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
    """


def migrar_capital_social() -> None:
    migrar_ejercicios_contables()
    migrar_asientos_origen()
    conn = conectar()
    try:
        conn.executescript(_sql_migracion_capital())
        conn.commit()
    finally:
        conn.close()


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
                     cuenta_destino_codigo, cuenta_destino_nombre, referencia, observaciones, estado, usuario_creacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROPUESTO', ?)
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
        _registrar_evento(capital_id, None, empresa_id, "ANULACION", f"Capital anulado. Motivo: {motivo_limpio}", usuario, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo anular la configuración de capital: {exc}")
    finally:
        conn.close()
    return _resultado(True, "Configuración de capital anulada correctamente.", capital=obtener_capital_social(capital_id))