from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from database import conectar, ejecutar_query
from services.ejercicios_contables_service import (
    migrar_ejercicios_contables,
    obtener_ejercicio_para_fecha,
    obtener_ejercicio_por_id,
    validar_fecha_operativa_contable,
)


TIPOS_ORIGEN_PERMITIDOS = {
    "APERTURA",
    "CAPITAL_SOCIAL",
    "SUSCRIPCION_CAPITAL",
    "INTEGRACION_CAPITAL",
    "APORTE_SOCIO",
    "APORTE_IRREVOCABLE",
    "PRESTAMO_SOCIO",
    "AJUSTE_INICIAL",
}

TOLERANCIA_CUADRE = 0.01


def _sql_migracion() -> str:
    ruta = Path(__file__).resolve().parents[1] / "migrations" / "016_asientos_origen.sql"
    if ruta.exists():
        return ruta.read_text(encoding="utf-8")
    # Fallback mínimo para entornos de prueba/copias incompletas.
    return """
    CREATE TABLE IF NOT EXISTS asientos_origen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL DEFAULT 1,
        ejercicio_id INTEGER,
        fecha TEXT NOT NULL,
        tipo_origen TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        referencia TEXT,
        observaciones TEXT,
        estado TEXT NOT NULL DEFAULT 'PROPUESTO',
        total_debe REAL NOT NULL DEFAULT 0,
        total_haber REAL NOT NULL DEFAULT 0,
        diferencia REAL NOT NULL DEFAULT 0,
        asiento_propuesto_id INTEGER,
        usuario_creacion TEXT,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        usuario_anulacion TEXT,
        fecha_anulacion TIMESTAMP,
        motivo_anulacion TEXT,
        fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS asientos_origen_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asiento_origen_id INTEGER NOT NULL,
        renglon INTEGER NOT NULL,
        cuenta_codigo TEXT,
        cuenta_nombre TEXT NOT NULL,
        debe REAL NOT NULL DEFAULT 0,
        haber REAL NOT NULL DEFAULT 0,
        glosa TEXT
    );
    CREATE TABLE IF NOT EXISTS asientos_origen_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asiento_origen_id INTEGER,
        empresa_id INTEGER NOT NULL DEFAULT 1,
        evento TEXT NOT NULL,
        detalle TEXT,
        usuario TEXT,
        fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS asientos_propuestos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL DEFAULT 1,
        ejercicio_id INTEGER,
        fecha TEXT NOT NULL,
        origen TEXT NOT NULL,
        origen_tabla TEXT,
        origen_id INTEGER,
        tipo_asiento TEXT NOT NULL,
        referencia TEXT,
        descripcion TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'PROPUESTO',
        total_debe REAL NOT NULL DEFAULT 0,
        total_haber REAL NOT NULL DEFAULT 0,
        diferencia REAL NOT NULL DEFAULT 0,
        id_asiento_libro_diario INTEGER,
        fecha_contabilizacion TIMESTAMP,
        usuario_contabilizacion TEXT,
        usuario_creacion TEXT,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        usuario_anulacion TEXT,
        fecha_anulacion TIMESTAMP,
        motivo_anulacion TEXT,
        fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS asientos_propuestos_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asiento_propuesto_id INTEGER NOT NULL,
        renglon INTEGER NOT NULL,
        cuenta_codigo TEXT,
        cuenta_nombre TEXT NOT NULL,
        debe REAL NOT NULL DEFAULT 0,
        haber REAL NOT NULL DEFAULT 0,
        glosa TEXT
    );
    CREATE TABLE IF NOT EXISTS asientos_propuestos_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asiento_propuesto_id INTEGER,
        empresa_id INTEGER NOT NULL DEFAULT 1,
        evento TEXT NOT NULL,
        detalle TEXT,
        usuario TEXT,
        fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """


def migrar_asientos_origen() -> None:
    migrar_ejercicios_contables()
    conn = conectar()
    try:
        conn.executescript(_sql_migracion())
        conn.commit()
    finally:
        conn.close()


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


def _numero(valor: Any) -> float:
    try:
        if valor is None or pd.isna(valor):
            return 0.0
        return round(float(valor), 2)
    except Exception:
        return 0.0


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass
    return str(valor).strip()


def _resultado(ok: bool, mensaje: str, **extras) -> Dict[str, Any]:
    data = {"ok": ok, "mensaje": mensaje}
    data.update(extras)
    return data


def _df_a_dict(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if df is None or df.empty:
        return None
    fila = df.iloc[0].to_dict()
    return {k: (None if pd.isna(v) else v) for k, v in fila.items()}


def _registrar_evento_origen(asiento_origen_id, empresa_id, evento, detalle="", usuario=None, conn=None):
    sql = """
        INSERT INTO asientos_origen_eventos
        (asiento_origen_id, empresa_id, evento, detalle, usuario)
        VALUES (?, ?, ?, ?, ?)
    """
    params = (asiento_origen_id, empresa_id, evento, detalle, usuario)
    if conn is not None:
        conn.execute(sql, params)
    else:
        ejecutar_query(sql, params)


def _registrar_evento_propuesto(asiento_propuesto_id, empresa_id, evento, detalle="", usuario=None, conn=None):
    sql = """
        INSERT INTO asientos_propuestos_eventos
        (asiento_propuesto_id, empresa_id, evento, detalle, usuario)
        VALUES (?, ?, ?, ?, ?)
    """
    params = (asiento_propuesto_id, empresa_id, evento, detalle, usuario)
    if conn is not None:
        conn.execute(sql, params)
    else:
        ejecutar_query(sql, params)


def _normalizar_lineas(lineas: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not lineas:
        return [], _resultado(False, "El asiento debe tener al menos dos líneas.")

    normalizadas = []
    for indice, linea in enumerate(lineas, start=1):
        cuenta_codigo = _texto(linea.get("cuenta_codigo") or linea.get("codigo") or linea.get("cuenta"))
        cuenta_nombre = _texto(linea.get("cuenta_nombre") or linea.get("nombre") or linea.get("detalle") or cuenta_codigo)
        debe = _numero(linea.get("debe", 0))
        haber = _numero(linea.get("haber", 0))
        glosa = _texto(linea.get("glosa") or linea.get("descripcion"))

        if not cuenta_nombre:
            return [], _resultado(False, f"La línea {indice} no tiene cuenta.")
        if debe < 0 or haber < 0:
            return [], _resultado(False, f"La línea {indice} no puede tener importes negativos.")
        if debe > 0 and haber > 0:
            return [], _resultado(False, f"La línea {indice} no puede tener Debe y Haber simultáneamente.")
        if debe == 0 and haber == 0:
            return [], _resultado(False, f"La línea {indice} debe tener importe en Debe o Haber.")

        normalizadas.append({
            "renglon": indice,
            "cuenta_codigo": cuenta_codigo,
            "cuenta_nombre": cuenta_nombre,
            "debe": debe,
            "haber": haber,
            "glosa": glosa,
        })

    if len(normalizadas) < 2:
        return [], _resultado(False, "El asiento debe tener al menos dos líneas.")

    total_debe = round(sum(item["debe"] for item in normalizadas), 2)
    total_haber = round(sum(item["haber"] for item in normalizadas), 2)
    diferencia = round(total_debe - total_haber, 2)

    if abs(diferencia) > TOLERANCIA_CUADRE:
        return [], _resultado(False, "El asiento no está cuadrado.", total_debe=total_debe, total_haber=total_haber, diferencia=diferencia)

    return normalizadas, _resultado(True, "Asiento cuadrado.", total_debe=total_debe, total_haber=total_haber, diferencia=diferencia)


def _obtener_ejercicio_para_asiento(empresa_id: int, fecha: str, ejercicio_id: Optional[int] = None) -> Dict[str, Any]:
    if ejercicio_id:
        ejercicio = obtener_ejercicio_por_id(int(ejercicio_id))
        if not ejercicio:
            return _resultado(False, "No se encontró el ejercicio contable informado.")
        if int(ejercicio.get("empresa_id") or 0) != int(empresa_id):
            return _resultado(False, "El ejercicio informado no pertenece a la empresa actual.")
        if not (str(ejercicio["fecha_inicio"]) <= fecha <= str(ejercicio["fecha_cierre"])):
            return _resultado(False, "La fecha del asiento no pertenece al ejercicio informado.")
        return _resultado(True, "Ejercicio válido.", ejercicio=ejercicio)

    ejercicio = obtener_ejercicio_para_fecha(empresa_id, fecha)
    if not ejercicio:
        return _resultado(False, "No existe ejercicio contable para la fecha del asiento. Primero cargá el ejercicio contable.")
    return _resultado(True, "Ejercicio válido.", ejercicio=ejercicio)


def _crear_asiento_propuesto_desde_origen(conn, *, empresa_id, ejercicio_id, fecha, tipo_origen, asiento_origen_id, descripcion, referencia, total_debe, total_haber, diferencia, lineas, usuario):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO asientos_propuestos
        (empresa_id, ejercicio_id, fecha, origen, origen_tabla, origen_id, tipo_asiento, referencia, descripcion, estado,
         total_debe, total_haber, diferencia, usuario_creacion)
        VALUES (?, ?, ?, ?, 'asientos_origen', ?, ?, ?, ?, 'PROPUESTO', ?, ?, ?, ?)
        """,
        (empresa_id, ejercicio_id, fecha, tipo_origen, asiento_origen_id, tipo_origen, referencia, descripcion, total_debe, total_haber, diferencia, usuario),
    )
    asiento_propuesto_id = int(cur.lastrowid)
    for linea in lineas:
        cur.execute(
            """
            INSERT INTO asientos_propuestos_detalle
            (asiento_propuesto_id, renglon, cuenta_codigo, cuenta_nombre, debe, haber, glosa)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (asiento_propuesto_id, linea["renglon"], linea["cuenta_codigo"], linea["cuenta_nombre"], linea["debe"], linea["haber"], linea["glosa"]),
        )
    _registrar_evento_propuesto(asiento_propuesto_id, empresa_id, "CREACION", f"Asiento propuesto generado desde {tipo_origen}.", usuario, conn)
    return asiento_propuesto_id


def _columnas_tabla(nombre_tabla: str) -> set:
    conn = conectar()
    try:
        filas = conn.execute(f"PRAGMA table_info({nombre_tabla})").fetchall()
        return {fila[1] for fila in filas}
    finally:
        conn.close()


def obtener_plan_cuentas_opciones(empresa_id: int = 1) -> pd.DataFrame:
    columnas_detalle = _columnas_tabla("plan_cuentas_detallado")
    if columnas_detalle:
        filtro_empresa = "WHERE COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas_detalle else ""
        params = (empresa_id,) if "empresa_id" in columnas_detalle else ()
        cuenta_col = "cuenta" if "cuenta" in columnas_detalle else ("cuenta_codigo" if "cuenta_codigo" in columnas_detalle else "codigo")
        nombre_col = "detalle" if "detalle" in columnas_detalle else ("cuenta_nombre" if "cuenta_nombre" in columnas_detalle else cuenta_col)
        extra_cols = [col if col in columnas_detalle else f"NULL AS {col}" for col in ["imputable", "tipo", "madre", "nivel", "orden"]]
        order_col = "orden, " if "orden" in columnas_detalle else ""
        df = ejecutar_query(
            f"""
            SELECT {cuenta_col} AS cuenta_codigo, COALESCE({nombre_col}, {cuenta_col}) AS cuenta_nombre, {', '.join(extra_cols)}
            FROM plan_cuentas_detallado
            {filtro_empresa}
            ORDER BY {order_col}{cuenta_col}
            """,
            params,
            fetch=True,
        )
        if df is not None and not df.empty:
            return df

    columnas_simple = _columnas_tabla("plan_cuentas")
    if columnas_simple:
        filtro_empresa = "WHERE COALESCE(empresa_id, 1) = ?" if "empresa_id" in columnas_simple else ""
        params = (empresa_id,) if "empresa_id" in columnas_simple else ()
        codigo_col = "codigo" if "codigo" in columnas_simple else ("cuenta" if "cuenta" in columnas_simple else "cuenta_codigo")
        nombre_col = "nombre" if "nombre" in columnas_simple else codigo_col
        return ejecutar_query(
            f"""
            SELECT {codigo_col} AS cuenta_codigo, COALESCE({nombre_col}, {codigo_col}) AS cuenta_nombre,
                   NULL AS imputable, NULL AS tipo, NULL AS madre, NULL AS nivel, NULL AS orden
            FROM plan_cuentas
            {filtro_empresa}
            ORDER BY {codigo_col}
            """,
            params,
            fetch=True,
        )
    return pd.DataFrame(columns=["cuenta_codigo", "cuenta_nombre", "imputable", "tipo", "madre", "nivel", "orden"])


def listar_asientos_origen(empresa_id: int = 1, estado: Optional[str] = None, tipo_origen: Optional[str] = None, ejercicio_id: Optional[int] = None, incluir_anulados: bool = False) -> pd.DataFrame:
    migrar_asientos_origen()
    condiciones = ["empresa_id = ?"]
    params: List[Any] = [empresa_id]
    if estado:
        condiciones.append("estado = ?")
        params.append(str(estado).strip().upper())
    elif not incluir_anulados:
        condiciones.append("estado <> 'ANULADO'")
    if tipo_origen:
        condiciones.append("tipo_origen = ?")
        params.append(str(tipo_origen).strip().upper())
    if ejercicio_id:
        condiciones.append("ejercicio_id = ?")
        params.append(int(ejercicio_id))
    return ejecutar_query(f"SELECT * FROM asientos_origen WHERE {' AND '.join(condiciones)} ORDER BY fecha DESC, id DESC", tuple(params), fetch=True)


def obtener_asiento_origen(asiento_origen_id: int) -> Optional[Dict[str, Any]]:
    migrar_asientos_origen()
    cabecera = _df_a_dict(ejecutar_query("SELECT * FROM asientos_origen WHERE id = ?", (asiento_origen_id,), fetch=True))
    if not cabecera:
        return None
    detalle = ejecutar_query("SELECT * FROM asientos_origen_detalle WHERE asiento_origen_id = ? ORDER BY renglon", (asiento_origen_id,), fetch=True)
    cabecera["detalle"] = detalle.to_dict("records") if not detalle.empty else []
    cabecera["asiento_propuesto"] = obtener_asiento_propuesto(int(cabecera["asiento_propuesto_id"])) if cabecera.get("asiento_propuesto_id") else None
    return cabecera


def listar_asientos_propuestos(empresa_id: int = 1, estado: Optional[str] = None, origen: Optional[str] = None, ejercicio_id: Optional[int] = None, incluir_anulados: bool = False) -> pd.DataFrame:
    migrar_asientos_origen()
    condiciones = ["empresa_id = ?"]
    params: List[Any] = [empresa_id]
    if estado:
        condiciones.append("estado = ?")
        params.append(str(estado).strip().upper())
    elif not incluir_anulados:
        condiciones.append("estado <> 'ANULADO'")
    if origen:
        condiciones.append("origen = ?")
        params.append(str(origen).strip().upper())
    if ejercicio_id:
        condiciones.append("ejercicio_id = ?")
        params.append(int(ejercicio_id))
    return ejecutar_query(f"SELECT * FROM asientos_propuestos WHERE {' AND '.join(condiciones)} ORDER BY fecha DESC, id DESC", tuple(params), fetch=True)


def obtener_asiento_propuesto(asiento_propuesto_id: int) -> Optional[Dict[str, Any]]:
    migrar_asientos_origen()
    cabecera = _df_a_dict(ejecutar_query("SELECT * FROM asientos_propuestos WHERE id = ?", (asiento_propuesto_id,), fetch=True))
    if not cabecera:
        return None
    detalle = ejecutar_query("SELECT * FROM asientos_propuestos_detalle WHERE asiento_propuesto_id = ? ORDER BY renglon", (asiento_propuesto_id,), fetch=True)
    cabecera["detalle"] = detalle.to_dict("records") if not detalle.empty else []
    return cabecera


def listar_eventos_asiento_origen(asiento_origen_id: int) -> pd.DataFrame:
    migrar_asientos_origen()
    return ejecutar_query("SELECT * FROM asientos_origen_eventos WHERE asiento_origen_id = ? ORDER BY fecha_evento DESC, id DESC", (asiento_origen_id,), fetch=True)


def listar_eventos_asiento_propuesto(asiento_propuesto_id: int) -> pd.DataFrame:
    migrar_asientos_origen()
    return ejecutar_query("SELECT * FROM asientos_propuestos_eventos WHERE asiento_propuesto_id = ? ORDER BY fecha_evento DESC, id DESC", (asiento_propuesto_id,), fetch=True)


def crear_asiento_origen(empresa_id: int, fecha: Any, tipo_origen: str, descripcion: str, lineas: List[Dict[str, Any]], ejercicio_id: Optional[int] = None, referencia: Optional[str] = None, observaciones: Optional[str] = None, usuario: Optional[str] = None, generar_propuesta: bool = True) -> Dict[str, Any]:
    migrar_asientos_origen()
    try:
        fecha_norm = _normalizar_fecha(fecha, "fecha")
    except ValueError as exc:
        return _resultado(False, str(exc))

    tipo_norm = str(tipo_origen or "").strip().upper()
    if tipo_norm not in TIPOS_ORIGEN_PERMITIDOS:
        return _resultado(False, f"Tipo de origen no válido: {tipo_origen}.", tipos_permitidos=sorted(TIPOS_ORIGEN_PERMITIDOS))

    descripcion_limpia = _texto(descripcion)
    if not descripcion_limpia:
        return _resultado(False, "La descripción del asiento es obligatoria.")

    ejercicio_resultado = _obtener_ejercicio_para_asiento(empresa_id, fecha_norm, ejercicio_id)
    if not ejercicio_resultado["ok"]:
        return ejercicio_resultado
    ejercicio_id_final = int(ejercicio_resultado["ejercicio"]["id"])

    validacion_fecha = validar_fecha_operativa_contable(empresa_id, fecha_norm, permitir_periodo_cerrado=False)
    if not validacion_fecha["ok"]:
        return validacion_fecha

    lineas_normalizadas, validacion_lineas = _normalizar_lineas(lineas)
    if not validacion_lineas["ok"]:
        return validacion_lineas

    total_debe = float(validacion_lineas["total_debe"])
    total_haber = float(validacion_lineas["total_haber"])
    diferencia = float(validacion_lineas["diferencia"])
    estado_inicial = "PROPUESTO" if generar_propuesta else "BORRADOR"

    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO asientos_origen
            (empresa_id, ejercicio_id, fecha, tipo_origen, descripcion, referencia, observaciones, estado,
             total_debe, total_haber, diferencia, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (empresa_id, ejercicio_id_final, fecha_norm, tipo_norm, descripcion_limpia, referencia, observaciones, estado_inicial, total_debe, total_haber, diferencia, usuario),
        )
        asiento_origen_id = int(cur.lastrowid)
        for linea in lineas_normalizadas:
            cur.execute(
                """
                INSERT INTO asientos_origen_detalle
                (asiento_origen_id, renglon, cuenta_codigo, cuenta_nombre, debe, haber, glosa)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (asiento_origen_id, linea["renglon"], linea["cuenta_codigo"], linea["cuenta_nombre"], linea["debe"], linea["haber"], linea["glosa"]),
            )
        asiento_propuesto_id = None
        if generar_propuesta:
            asiento_propuesto_id = _crear_asiento_propuesto_desde_origen(
                conn,
                empresa_id=empresa_id,
                ejercicio_id=ejercicio_id_final,
                fecha=fecha_norm,
                tipo_origen=tipo_norm,
                asiento_origen_id=asiento_origen_id,
                descripcion=descripcion_limpia,
                referencia=referencia,
                total_debe=total_debe,
                total_haber=total_haber,
                diferencia=diferencia,
                lineas=lineas_normalizadas,
                usuario=usuario,
            )
            cur.execute("UPDATE asientos_origen SET asiento_propuesto_id = ?, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ?", (asiento_propuesto_id, asiento_origen_id))
        _registrar_evento_origen(asiento_origen_id, empresa_id, "CREACION", f"Asiento de origen {tipo_norm} creado en estado {estado_inicial}.", usuario, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo crear el asiento de origen: {exc}")
    finally:
        conn.close()

    return _resultado(True, "Asiento de origen creado correctamente.", asiento_origen_id=asiento_origen_id, asiento_propuesto_id=asiento_propuesto_id, asiento=obtener_asiento_origen(asiento_origen_id))


def crear_asiento_apertura(empresa_id, fecha, descripcion, lineas, ejercicio_id=None, referencia=None, observaciones=None, usuario=None):
    return crear_asiento_origen(empresa_id, fecha, "APERTURA", descripcion, lineas, ejercicio_id, referencia, observaciones, usuario, True)


def crear_asiento_capital_social(empresa_id, fecha, descripcion, lineas, ejercicio_id=None, referencia=None, observaciones=None, usuario=None):
    return crear_asiento_origen(empresa_id, fecha, "CAPITAL_SOCIAL", descripcion, lineas, ejercicio_id, referencia, observaciones, usuario, True)


def crear_aporte_socio(empresa_id, fecha, descripcion, lineas, ejercicio_id=None, referencia=None, observaciones=None, usuario=None):
    return crear_asiento_origen(empresa_id, fecha, "APORTE_SOCIO", descripcion, lineas, ejercicio_id, referencia, observaciones, usuario, True)


def anular_asiento_origen(asiento_origen_id: int, motivo: str, usuario: Optional[str] = None) -> Dict[str, Any]:
    migrar_asientos_origen()
    motivo_limpio = _texto(motivo)
    if not motivo_limpio:
        return _resultado(False, "Para anular un asiento de origen se requiere motivo.")
    asiento = obtener_asiento_origen(asiento_origen_id)
    if not asiento:
        return _resultado(False, "No se encontró el asiento de origen.")
    estado = str(asiento.get("estado") or "").upper()
    if estado == "ANULADO":
        return _resultado(False, "El asiento ya está anulado.")
    if estado == "CONTABILIZADO":
        return _resultado(False, "El asiento ya fue contabilizado. La anulación deberá hacerse con reverso controlado desde la futura bandeja de asientos.")

    empresa_id = int(asiento["empresa_id"])
    asiento_propuesto_id = asiento.get("asiento_propuesto_id")
    conn = conectar()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE asientos_origen
            SET estado = 'ANULADO', usuario_anulacion = ?, fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (usuario, motivo_limpio, asiento_origen_id),
        )
        _registrar_evento_origen(asiento_origen_id, empresa_id, "ANULACION", f"Asiento de origen anulado. Motivo: {motivo_limpio}", usuario, conn)
        if asiento_propuesto_id:
            propuesta = obtener_asiento_propuesto(int(asiento_propuesto_id))
            if propuesta and propuesta.get("estado") == "PROPUESTO":
                cur.execute(
                    """
                    UPDATE asientos_propuestos
                    SET estado = 'ANULADO', usuario_anulacion = ?, fecha_anulacion = CURRENT_TIMESTAMP,
                        motivo_anulacion = ?, fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (usuario, motivo_limpio, int(asiento_propuesto_id)),
                )
                _registrar_evento_propuesto(int(asiento_propuesto_id), empresa_id, "ANULACION", f"Asiento propuesto anulado por anulación del origen. Motivo: {motivo_limpio}", usuario, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo anular el asiento de origen: {exc}")
    finally:
        conn.close()
    return _resultado(True, "Asiento de origen anulado correctamente.", asiento=obtener_asiento_origen(asiento_origen_id))


def rechazar_asiento_propuesto(asiento_propuesto_id: int, motivo: str, usuario: Optional[str] = None) -> Dict[str, Any]:
    migrar_asientos_origen()
    motivo_limpio = _texto(motivo)
    if not motivo_limpio:
        return _resultado(False, "Para rechazar un asiento propuesto se requiere motivo.")
    propuesta = obtener_asiento_propuesto(asiento_propuesto_id)
    if not propuesta:
        return _resultado(False, "No se encontró el asiento propuesto.")
    if propuesta.get("estado") != "PROPUESTO":
        return _resultado(False, "Solo se pueden rechazar asientos en estado PROPUESTO.")
    empresa_id = int(propuesta["empresa_id"])
    conn = conectar()
    try:
        conn.execute(
            """
            UPDATE asientos_propuestos
            SET estado = 'RECHAZADO', usuario_anulacion = ?, fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?, fecha_actualizacion = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (usuario, motivo_limpio, asiento_propuesto_id),
        )
        _registrar_evento_propuesto(asiento_propuesto_id, empresa_id, "RECHAZO", f"Asiento propuesto rechazado. Motivo: {motivo_limpio}", usuario, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo rechazar el asiento propuesto: {exc}")
    finally:
        conn.close()
    return _resultado(True, "Asiento propuesto rechazado correctamente.", asiento_propuesto=obtener_asiento_propuesto(asiento_propuesto_id))


def obtener_resumen_asientos_origen(empresa_id: int = 1) -> Dict[str, Any]:
    migrar_asientos_origen()
    origenes = listar_asientos_origen(empresa_id=empresa_id, incluir_anulados=True)
    propuestos = listar_asientos_propuestos(empresa_id=empresa_id, incluir_anulados=True)

    def contar(df: pd.DataFrame, estado: str) -> int:
        if df.empty:
            return 0
        return int((df["estado"].fillna("").astype(str).str.upper() == estado).sum())

    return {
        "empresa_id": empresa_id,
        "asientos_origen_total": int(len(origenes)) if not origenes.empty else 0,
        "asientos_origen_propuestos": contar(origenes, "PROPUESTO"),
        "asientos_origen_borrador": contar(origenes, "BORRADOR"),
        "asientos_origen_anulados": contar(origenes, "ANULADO"),
        "asientos_propuestos_total": int(len(propuestos)) if not propuestos.empty else 0,
        "asientos_propuestos_pendientes": contar(propuestos, "PROPUESTO"),
        "asientos_propuestos_contabilizados": contar(propuestos, "CONTABILIZADO"),
        "asientos_propuestos_anulados": contar(propuestos, "ANULADO"),
        "asientos_propuestos_rechazados": contar(propuestos, "RECHAZADO"),
    }