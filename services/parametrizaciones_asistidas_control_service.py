"""
Parametrizacion PRO v2B - nucleo auditado de decisiones.

Este servicio guarda decisiones sobre parametrizaciones asistidas sin modificar
modulos operativos, sin generar asientos, sin impactar Libro Diario/Bandeja y
sin ejecutar acciones contables. Su responsabilidad es conservar la decision
profesional del usuario con trazabilidad.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

ACCION_ACEPTAR = "ACEPTAR"
ACCION_EDITAR = "EDITAR"
ACCION_DESACTIVAR = "DESACTIVAR"
ACCION_REACTIVAR = "REACTIVAR"

ESTADO_ACTIVA = "ACTIVA"
ESTADO_DESACTIVADA = "DESACTIVADA"

ACCIONES_VALIDAS = {
    ACCION_ACEPTAR,
    ACCION_EDITAR,
    ACCION_DESACTIVAR,
    ACCION_REACTIVAR,
}

MIGRACION_SQL = """
CREATE TABLE IF NOT EXISTS parametrizaciones_asistidas_decisiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL,
    modulo TEXT NOT NULL,
    tipo_parametrizacion TEXT NOT NULL DEFAULT 'GENERAL',
    clave_parametrizacion TEXT NOT NULL,
    origen_sugerencia TEXT NOT NULL DEFAULT 'PARAMETRIZACION_ASISTIDA',
    estado_decision TEXT NOT NULL DEFAULT 'ACTIVA',
    accion_ultima TEXT NOT NULL DEFAULT 'ACEPTAR',
    cuenta_codigo TEXT,
    cuenta_nombre TEXT,
    valor_sugerido_json TEXT,
    valor_decidido_json TEXT,
    confianza TEXT,
    requiere_revision INTEGER NOT NULL DEFAULT 0,
    motivo TEXT,
    observacion TEXT,
    usuario_id INTEGER,
    fecha_decision TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_desactivacion TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (empresa_id, modulo, clave_parametrizacion)
);

CREATE INDEX IF NOT EXISTS idx_param_decisiones_empresa_modulo
ON parametrizaciones_asistidas_decisiones (empresa_id, modulo);

CREATE INDEX IF NOT EXISTS idx_param_decisiones_estado
ON parametrizaciones_asistidas_decisiones (empresa_id, estado_decision, activo);

CREATE TABLE IF NOT EXISTS parametrizaciones_asistidas_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    empresa_id INTEGER NOT NULL,
    modulo TEXT NOT NULL,
    clave_parametrizacion TEXT NOT NULL,
    accion TEXT NOT NULL,
    estado_anterior TEXT,
    estado_nuevo TEXT NOT NULL,
    valor_anterior_json TEXT,
    valor_nuevo_json TEXT,
    motivo TEXT,
    usuario_id INTEGER,
    fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (decision_id) REFERENCES parametrizaciones_asistidas_decisiones(id)
);

CREATE INDEX IF NOT EXISTS idx_param_eventos_decision
ON parametrizaciones_asistidas_eventos (decision_id, fecha_evento);

CREATE INDEX IF NOT EXISTS idx_param_eventos_empresa_modulo
ON parametrizaciones_asistidas_eventos (empresa_id, modulo, clave_parametrizacion);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _texto(valor: Any, default: str = "") -> str:
    if valor is None:
        return default
    return str(valor).strip()


def _normalizar_modulo(modulo: str) -> str:
    texto = _texto(modulo).upper().replace(" ", "_").replace("/", "_")
    if not texto:
        raise ValueError("El modulo de la parametrizacion es obligatorio.")
    return texto


def _normalizar_clave(clave: str) -> str:
    texto = _texto(clave)
    if not texto:
        raise ValueError("La clave de parametrizacion es obligatoria.")
    return texto


def _normalizar_accion(accion: str) -> str:
    texto = _texto(accion).upper()
    if texto not in ACCIONES_VALIDAS:
        raise ValueError(f"Accion de parametrizacion invalida: {accion!r}.")
    return texto


def _validar_empresa_id(empresa_id: int) -> int:
    try:
        valor = int(empresa_id)
    except Exception as exc:
        raise ValueError("empresa_id debe ser numerico.") from exc
    if valor <= 0:
        raise ValueError("empresa_id debe ser mayor a cero.")
    return valor


def _json(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)


def _json_leer(valor: Optional[str]) -> Any:
    if valor in (None, ""):
        return None
    try:
        return json.loads(valor)
    except Exception:
        return valor


def _motivo_requerido(accion: str, motivo: Optional[str]) -> None:
    if accion in {ACCION_EDITAR, ACCION_DESACTIVAR, ACCION_REACTIVAR} and not _texto(motivo):
        raise ValueError(f"La accion {accion} requiere motivo obligatorio.")


def _fila_a_dict(fila: Optional[sqlite3.Row | tuple], columnas: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    if fila is None:
        return None
    if isinstance(fila, sqlite3.Row):
        datos = dict(fila)
    else:
        if columnas is None:
            raise ValueError("columnas es obligatorio para convertir tuplas a dict.")
        datos = dict(zip(columnas, fila))

    for campo in ("valor_sugerido_json", "valor_decidido_json"):
        if campo in datos:
            datos[campo.replace("_json", "")] = _json_leer(datos.get(campo))
    return datos


def _fetchone_dict(conn: sqlite3.Connection, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    cur = conn.execute(query, params)
    fila = cur.fetchone()
    columnas = [d[0] for d in cur.description]
    return _fila_a_dict(fila, columnas)


def _fetchall_dicts(conn: sqlite3.Connection, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(query, params)
    columnas = [d[0] for d in cur.description]
    return [_fila_a_dict(fila, columnas) for fila in cur.fetchall()]


def inicializar_parametrizaciones_asistidas_control(conn: sqlite3.Connection) -> None:
    """Crea las tablas propias del nucleo auditado, de forma idempotente."""
    conn.executescript(MIGRACION_SQL)
    conn.commit()


def construir_clave_parametrizacion(modulo: str, tipo_parametrizacion: str, identificador: Any) -> str:
    """Construye una clave estable para decisiones por empresa/modulo."""
    modulo_norm = _normalizar_modulo(modulo)
    tipo_norm = _texto(tipo_parametrizacion, "GENERAL").upper().replace(" ", "_") or "GENERAL"
    ident = _normalizar_clave(str(identificador)).upper().replace(" ", "_")
    return f"{modulo_norm}:{tipo_norm}:{ident}"


def obtener_decision_parametrizacion(
    conn: sqlite3.Connection,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
) -> Optional[Dict[str, Any]]:
    inicializar_parametrizaciones_asistidas_control(conn)
    return _fetchone_dict(
        conn,
        """
        SELECT *
        FROM parametrizaciones_asistidas_decisiones
        WHERE empresa_id = ? AND modulo = ? AND clave_parametrizacion = ?
        """,
        (_validar_empresa_id(empresa_id), _normalizar_modulo(modulo), _normalizar_clave(clave_parametrizacion)),
    )


def _insertar_evento(
    conn: sqlite3.Connection,
    *,
    decision_id: int,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
    accion: str,
    estado_anterior: Optional[str],
    estado_nuevo: str,
    valor_anterior_json: Optional[str],
    valor_nuevo_json: Optional[str],
    motivo: Optional[str],
    usuario_id: Optional[int],
) -> None:
    conn.execute(
        """
        INSERT INTO parametrizaciones_asistidas_eventos (
            decision_id,
            empresa_id,
            modulo,
            clave_parametrizacion,
            accion,
            estado_anterior,
            estado_nuevo,
            valor_anterior_json,
            valor_nuevo_json,
            motivo,
            usuario_id,
            fecha_evento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            empresa_id,
            modulo,
            clave_parametrizacion,
            accion,
            estado_anterior,
            estado_nuevo,
            valor_anterior_json,
            valor_nuevo_json,
            _texto(motivo) or None,
            usuario_id,
            _ahora(),
        ),
    )


def registrar_decision_parametrizacion(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
    accion: str,
    tipo_parametrizacion: str = "GENERAL",
    origen_sugerencia: str = "PARAMETRIZACION_ASISTIDA",
    cuenta_codigo: Optional[str] = None,
    cuenta_nombre: Optional[str] = None,
    valor_sugerido: Any = None,
    valor_decidido: Any = None,
    confianza: Optional[str] = None,
    requiere_revision: bool = False,
    motivo: Optional[str] = None,
    observacion: Optional[str] = None,
    usuario_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Registra o actualiza la decision vigente para una parametrizacion asistida.

    No modifica la parametrizacion operativa original. Solo deja una decision
    auditada para que una etapa posterior pueda aplicar cambios con control.
    """
    inicializar_parametrizaciones_asistidas_control(conn)

    empresa_id = _validar_empresa_id(empresa_id)
    modulo_norm = _normalizar_modulo(modulo)
    clave_norm = _normalizar_clave(clave_parametrizacion)
    accion_norm = _normalizar_accion(accion)
    _motivo_requerido(accion_norm, motivo)

    if accion_norm == ACCION_DESACTIVAR:
        estado_nuevo = ESTADO_DESACTIVADA
        activo = 0
        fecha_desactivacion = _ahora()
    else:
        estado_nuevo = ESTADO_ACTIVA
        activo = 1
        fecha_desactivacion = None

    anterior = obtener_decision_parametrizacion(conn, empresa_id, modulo_norm, clave_norm)
    ahora = _ahora()
    valor_sugerido_json = _json(valor_sugerido)
    valor_decidido_json = _json(valor_decidido)

    if anterior:
        version = int(anterior.get("version") or 1) + 1
        valor_anterior_json = anterior.get("valor_decidido_json")
        conn.execute(
            """
            UPDATE parametrizaciones_asistidas_decisiones
            SET tipo_parametrizacion = ?,
                origen_sugerencia = ?,
                estado_decision = ?,
                accion_ultima = ?,
                cuenta_codigo = ?,
                cuenta_nombre = ?,
                valor_sugerido_json = ?,
                valor_decidido_json = ?,
                confianza = ?,
                requiere_revision = ?,
                motivo = ?,
                observacion = ?,
                usuario_id = ?,
                fecha_actualizacion = ?,
                fecha_desactivacion = ?,
                activo = ?,
                version = ?
            WHERE id = ?
            """,
            (
                _texto(tipo_parametrizacion, "GENERAL").upper() or "GENERAL",
                _texto(origen_sugerencia, "PARAMETRIZACION_ASISTIDA") or "PARAMETRIZACION_ASISTIDA",
                estado_nuevo,
                accion_norm,
                _texto(cuenta_codigo) or None,
                _texto(cuenta_nombre) or None,
                valor_sugerido_json,
                valor_decidido_json,
                _texto(confianza).upper() or None,
                1 if requiere_revision else 0,
                _texto(motivo) or None,
                _texto(observacion) or None,
                usuario_id,
                ahora,
                fecha_desactivacion,
                activo,
                version,
                anterior["id"],
            ),
        )
        decision_id = int(anterior["id"])
        estado_anterior = anterior.get("estado_decision")
    else:
        valor_anterior_json = None
        cur = conn.execute(
            """
            INSERT INTO parametrizaciones_asistidas_decisiones (
                empresa_id,
                modulo,
                tipo_parametrizacion,
                clave_parametrizacion,
                origen_sugerencia,
                estado_decision,
                accion_ultima,
                cuenta_codigo,
                cuenta_nombre,
                valor_sugerido_json,
                valor_decidido_json,
                confianza,
                requiere_revision,
                motivo,
                observacion,
                usuario_id,
                fecha_decision,
                fecha_actualizacion,
                fecha_desactivacion,
                activo,
                version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                modulo_norm,
                _texto(tipo_parametrizacion, "GENERAL").upper() or "GENERAL",
                clave_norm,
                _texto(origen_sugerencia, "PARAMETRIZACION_ASISTIDA") or "PARAMETRIZACION_ASISTIDA",
                estado_nuevo,
                accion_norm,
                _texto(cuenta_codigo) or None,
                _texto(cuenta_nombre) or None,
                valor_sugerido_json,
                valor_decidido_json,
                _texto(confianza).upper() or None,
                1 if requiere_revision else 0,
                _texto(motivo) or None,
                _texto(observacion) or None,
                usuario_id,
                ahora,
                ahora,
                fecha_desactivacion,
                activo,
                1,
            ),
        )
        decision_id = int(cur.lastrowid)
        estado_anterior = None

    _insertar_evento(
        conn,
        decision_id=decision_id,
        empresa_id=empresa_id,
        modulo=modulo_norm,
        clave_parametrizacion=clave_norm,
        accion=accion_norm,
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        valor_anterior_json=valor_anterior_json,
        valor_nuevo_json=valor_decidido_json,
        motivo=motivo,
        usuario_id=usuario_id,
    )
    conn.commit()

    decision = obtener_decision_parametrizacion(conn, empresa_id, modulo_norm, clave_norm)
    if decision is None:
        raise RuntimeError("No se pudo recuperar la decision registrada.")
    return decision


def aceptar_parametrizacion_asistida(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
    tipo_parametrizacion: str = "GENERAL",
    cuenta_codigo: Optional[str] = None,
    cuenta_nombre: Optional[str] = None,
    valor_sugerido: Any = None,
    valor_decidido: Any = None,
    confianza: Optional[str] = None,
    observacion: Optional[str] = None,
    usuario_id: Optional[int] = None,
) -> Dict[str, Any]:
    return registrar_decision_parametrizacion(
        conn,
        empresa_id=empresa_id,
        modulo=modulo,
        clave_parametrizacion=clave_parametrizacion,
        accion=ACCION_ACEPTAR,
        tipo_parametrizacion=tipo_parametrizacion,
        cuenta_codigo=cuenta_codigo,
        cuenta_nombre=cuenta_nombre,
        valor_sugerido=valor_sugerido,
        valor_decidido=valor_decidido if valor_decidido is not None else valor_sugerido,
        confianza=confianza,
        observacion=observacion,
        usuario_id=usuario_id,
    )


def editar_parametrizacion_asistida(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
    motivo: str,
    tipo_parametrizacion: str = "GENERAL",
    cuenta_codigo: Optional[str] = None,
    cuenta_nombre: Optional[str] = None,
    valor_sugerido: Any = None,
    valor_decidido: Any = None,
    confianza: Optional[str] = None,
    requiere_revision: bool = True,
    observacion: Optional[str] = None,
    usuario_id: Optional[int] = None,
) -> Dict[str, Any]:
    return registrar_decision_parametrizacion(
        conn,
        empresa_id=empresa_id,
        modulo=modulo,
        clave_parametrizacion=clave_parametrizacion,
        accion=ACCION_EDITAR,
        tipo_parametrizacion=tipo_parametrizacion,
        cuenta_codigo=cuenta_codigo,
        cuenta_nombre=cuenta_nombre,
        valor_sugerido=valor_sugerido,
        valor_decidido=valor_decidido,
        confianza=confianza,
        requiere_revision=requiere_revision,
        motivo=motivo,
        observacion=observacion,
        usuario_id=usuario_id,
    )


def desactivar_parametrizacion_asistida(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
    motivo: str,
    usuario_id: Optional[int] = None,
    observacion: Optional[str] = None,
) -> Dict[str, Any]:
    anterior = obtener_decision_parametrizacion(conn, empresa_id, modulo, clave_parametrizacion)
    return registrar_decision_parametrizacion(
        conn,
        empresa_id=empresa_id,
        modulo=modulo,
        clave_parametrizacion=clave_parametrizacion,
        accion=ACCION_DESACTIVAR,
        tipo_parametrizacion=(anterior or {}).get("tipo_parametrizacion") or "GENERAL",
        cuenta_codigo=(anterior or {}).get("cuenta_codigo"),
        cuenta_nombre=(anterior or {}).get("cuenta_nombre"),
        valor_sugerido=(anterior or {}).get("valor_sugerido"),
        valor_decidido=(anterior or {}).get("valor_decidido"),
        confianza=(anterior or {}).get("confianza"),
        requiere_revision=bool((anterior or {}).get("requiere_revision") or False),
        motivo=motivo,
        observacion=observacion,
        usuario_id=usuario_id,
    )


def reactivar_parametrizacion_asistida(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    modulo: str,
    clave_parametrizacion: str,
    motivo: str,
    usuario_id: Optional[int] = None,
    observacion: Optional[str] = None,
) -> Dict[str, Any]:
    anterior = obtener_decision_parametrizacion(conn, empresa_id, modulo, clave_parametrizacion)
    return registrar_decision_parametrizacion(
        conn,
        empresa_id=empresa_id,
        modulo=modulo,
        clave_parametrizacion=clave_parametrizacion,
        accion=ACCION_REACTIVAR,
        tipo_parametrizacion=(anterior or {}).get("tipo_parametrizacion") or "GENERAL",
        cuenta_codigo=(anterior or {}).get("cuenta_codigo"),
        cuenta_nombre=(anterior or {}).get("cuenta_nombre"),
        valor_sugerido=(anterior or {}).get("valor_sugerido"),
        valor_decidido=(anterior or {}).get("valor_decidido"),
        confianza=(anterior or {}).get("confianza"),
        requiere_revision=bool((anterior or {}).get("requiere_revision") or False),
        motivo=motivo,
        observacion=observacion,
        usuario_id=usuario_id,
    )


def listar_decisiones_parametrizacion(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    modulo: Optional[str] = None,
    estado_decision: Optional[str] = None,
    solo_activas: bool = False,
) -> List[Dict[str, Any]]:
    inicializar_parametrizaciones_asistidas_control(conn)
    empresa_id = _validar_empresa_id(empresa_id)

    condiciones = ["empresa_id = ?"]
    params: List[Any] = [empresa_id]

    if modulo:
        condiciones.append("modulo = ?")
        params.append(_normalizar_modulo(modulo))
    if estado_decision:
        condiciones.append("estado_decision = ?")
        params.append(_texto(estado_decision).upper())
    if solo_activas:
        condiciones.append("activo = 1")

    where = " AND ".join(condiciones)
    return _fetchall_dicts(
        conn,
        f"""
        SELECT *
        FROM parametrizaciones_asistidas_decisiones
        WHERE {where}
        ORDER BY modulo, tipo_parametrizacion, clave_parametrizacion
        """,
        tuple(params),
    )


def listar_eventos_decision(
    conn: sqlite3.Connection,
    *,
    decision_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    modulo: Optional[str] = None,
    clave_parametrizacion: Optional[str] = None,
) -> List[Dict[str, Any]]:
    inicializar_parametrizaciones_asistidas_control(conn)

    condiciones: List[str] = []
    params: List[Any] = []

    if decision_id is not None:
        condiciones.append("decision_id = ?")
        params.append(int(decision_id))
    if empresa_id is not None:
        condiciones.append("empresa_id = ?")
        params.append(_validar_empresa_id(empresa_id))
    if modulo:
        condiciones.append("modulo = ?")
        params.append(_normalizar_modulo(modulo))
    if clave_parametrizacion:
        condiciones.append("clave_parametrizacion = ?")
        params.append(_normalizar_clave(clave_parametrizacion))

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""
    return _fetchall_dicts(
        conn,
        f"""
        SELECT *
        FROM parametrizaciones_asistidas_eventos
        {where}
        ORDER BY id
        """,
        tuple(params),
    )


def obtener_resumen_decisiones_parametrizacion(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
) -> Dict[str, Any]:
    decisiones = listar_decisiones_parametrizacion(conn, empresa_id=empresa_id)

    resumen = {
        "empresa_id": _validar_empresa_id(empresa_id),
        "total_decisiones": len(decisiones),
        "activas": 0,
        "desactivadas": 0,
        "requieren_revision": 0,
        "por_modulo": {},
        "por_accion": {},
    }

    for decision in decisiones:
        modulo = decision.get("modulo") or "SIN_MODULO"
        accion = decision.get("accion_ultima") or "SIN_ACCION"
        estado = decision.get("estado_decision")
        activo = int(decision.get("activo") or 0)

        if activo and estado == ESTADO_ACTIVA:
            resumen["activas"] += 1
        if estado == ESTADO_DESACTIVADA:
            resumen["desactivadas"] += 1
        if int(decision.get("requiere_revision") or 0):
            resumen["requieren_revision"] += 1

        resumen["por_modulo"].setdefault(modulo, {"total": 0, "activas": 0, "desactivadas": 0})
        resumen["por_modulo"][modulo]["total"] += 1
        if activo and estado == ESTADO_ACTIVA:
            resumen["por_modulo"][modulo]["activas"] += 1
        if estado == ESTADO_DESACTIVADA:
            resumen["por_modulo"][modulo]["desactivadas"] += 1

        resumen["por_accion"][accion] = resumen["por_accion"].get(accion, 0) + 1

    return resumen


def exportar_decisiones_parametrizacion_como_texto(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
) -> str:
    resumen = obtener_resumen_decisiones_parametrizacion(conn, empresa_id=empresa_id)
    decisiones = listar_decisiones_parametrizacion(conn, empresa_id=empresa_id)

    lineas = [
        "PARAMETRIZACION PRO v2B - DECISIONES AUDITADAS",
        f"Empresa: {resumen['empresa_id']}",
        f"Total decisiones: {resumen['total_decisiones']}",
        f"Activas: {resumen['activas']}",
        f"Desactivadas: {resumen['desactivadas']}",
        f"Requieren revision: {resumen['requieren_revision']}",
        "",
        "Detalle:",
    ]

    for decision in decisiones:
        lineas.append(
            " - "
            f"{decision.get('modulo')} | "
            f"{decision.get('clave_parametrizacion')} | "
            f"{decision.get('estado_decision')} | "
            f"{decision.get('accion_ultima')} | "
            f"{decision.get('cuenta_codigo') or ''} {decision.get('cuenta_nombre') or ''}".strip()
        )

    return "\n".join(lineas)

