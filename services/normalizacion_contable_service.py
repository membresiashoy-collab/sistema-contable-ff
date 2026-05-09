from __future__ import annotations

from datetime import datetime
import re
import sqlite3
import unicodedata
from typing import Any

from core.contabilidad_coherencia import (
    COMPORTAMIENTOS_CONTABLES,
    COMPORTAMIENTOS_CRITICOS,
    describir_comportamiento,
    normalizar_codigo,
    validar_comportamiento_contable,
)
from services.comportamientos_contables_service import (
    guardar_comportamiento_cuenta,
    listar_cuentas_plan,
    listar_eventos_comportamientos,
    listar_mapeos_comportamientos,
    migrar_configuracion_comportamientos,
)


CONFIANZA_ALTA = "Alta"
CONFIANZA_MEDIA = "Media"
CONFIANZA_BAJA = "Baja"

ESTADO_ACTIVO = "ACTIVO"
ESTADO_INACTIVO = "INACTIVO"
ESTADO_ANULADO = "ANULADO"


def _conectar_default() -> sqlite3.Connection:
    from database import conectar

    return conectar()


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row


def _fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _agregar_columna_si_falta(conn: sqlite3.Connection, tabla: str, columna: str, definicion: str) -> None:
    if columna not in _columns(conn, tabla):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _contiene(texto: str, *patrones: str) -> bool:
    return any(_normalizar_texto(patron) in texto for patron in patrones)


def _todos(texto: str, *patrones: str) -> bool:
    return all(_normalizar_texto(patron) in texto for patron in patrones)


def _registrar_evento(
    conn: sqlite3.Connection,
    *,
    empresa_id: int | None,
    mapeo_id: int | None,
    codigo_cuenta: str,
    comportamiento: str,
    evento: str,
    detalle: str,
    usuario: str | None,
) -> None:
    migrar_normalizacion_contable(conn)
    conn.execute(
        """
        INSERT INTO contabilidad_cuentas_comportamiento_eventos
        (empresa_id, mapeo_id, codigo_cuenta, comportamiento, evento, detalle, usuario, fecha_evento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (empresa_id, mapeo_id, codigo_cuenta, comportamiento, evento, detalle, usuario, _now_iso()),
    )


def migrar_normalizacion_contable(conn: sqlite3.Connection | None = None) -> None:
    """Asegura columnas de corrección controlada sin borrar historia existente."""
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_configuracion_comportamientos(conn)
        if _table_exists(conn, "contabilidad_cuentas_comportamiento"):
            columnas = {
                "estado": "TEXT DEFAULT 'ACTIVO'",
                "usuario_anulacion": "TEXT",
                "fecha_anulacion": "TEXT",
                "motivo_anulacion": "TEXT",
                "usuario_edicion": "TEXT",
                "fecha_edicion": "TEXT",
                "motivo_edicion": "TEXT",
                "comportamiento_anterior": "TEXT",
            }
            for columna, definicion in columnas.items():
                _agregar_columna_si_falta(conn, "contabilidad_cuentas_comportamiento", columna, definicion)
            conn.execute(
                """
                UPDATE contabilidad_cuentas_comportamiento
                SET estado = CASE WHEN COALESCE(activo, 0) = 1 THEN 'ACTIVO' ELSE 'INACTIVO' END
                WHERE estado IS NULL OR TRIM(estado) = ''
                """
            )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def _sugerir_por_reglas(codigo_cuenta: Any, nombre_cuenta: Any) -> dict[str, Any] | None:
    codigo = str(codigo_cuenta or "").strip()
    nombre = str(nombre_cuenta or "").strip()
    texto = _normalizar_texto(f"{codigo} {nombre}")
    if not texto:
        return None

    reglas: list[dict[str, Any]] = [
        {
            "comportamiento": "IVA_CREDITO",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta contiene referencias a IVA crédito fiscal o crédito fiscal de compras.",
            "match": lambda t: _todos(t, "IVA", "CREDITO") or _contiene(t, "CREDITO FISCAL", "IVA COMPRAS", "IVA CF"),
        },
        {
            "comportamiento": "IVA_DEBITO",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta contiene referencias a IVA débito fiscal, IVA ventas o IVA a pagar.",
            "match": lambda t: _todos(t, "IVA", "DEBITO") or _contiene(t, "DEBITO FISCAL", "IVA VENTAS", "IVA DF", "IVA A PAGAR"),
        },
        {
            "comportamiento": "CAJA",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar efectivo, caja o fondo fijo.",
            "match": lambda t: _contiene(t, "CAJA", "EFECTIVO", "FONDO FIJO", "RECAUDACION"),
        },
        {
            "comportamiento": "BANCO",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar una cuenta bancaria operativa.",
            "match": lambda t: _contiene(
                t,
                "BANCO",
                "CUENTA CORRIENTE",
                "CUENTA BANCARIA",
                "CBU",
                "GALICIA",
                "NACION",
                "SANTANDER",
                "MACRO",
                "BBVA",
                "ICBC",
                "SUPERVIELLE",
            ),
        },
        {
            "comportamiento": "CLIENTES",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar clientes, deudores por ventas o cuentas a cobrar.",
            "match": lambda t: _contiene(t, "CLIENTES", "DEUDORES POR VENTAS", "CUENTAS A COBRAR", "CTA CTE CLIENTES"),
        },
        {
            "comportamiento": "PROVEEDORES",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar proveedores, acreedores comerciales o cuentas a pagar comerciales.",
            "match": lambda t: _contiene(t, "PROVEEDORES", "ACREEDORES COMERCIALES", "CTA CTE PROVEEDORES"),
        },
        {
            "comportamiento": "CAPITAL_SOCIAL",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta contiene referencias claras a capital social, acciones o cuotas sociales.",
            "match": lambda t: _contiene(t, "CAPITAL SOCIAL", "ACCIONES", "CUOTAS SOCIALES"),
        },
        {
            "comportamiento": "APORTE_IRREVOCABLE",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta contiene referencias a aportes irrevocables.",
            "match": lambda t: _contiene(t, "APORTE IRREVOCABLE", "APORTES IRREVOCABLES"),
        },
        {
            "comportamiento": "SOCIOS_INTEGRACION",
            "confianza": CONFIANZA_MEDIA,
            "motivo": "La cuenta parece vinculada a socios o accionistas por integración de capital.",
            "match": lambda t: _contiene(t, "SOCIOS POR INTEGRACION", "ACCIONISTAS POR INTEGRACION", "CAPITAL PENDIENTE DE INTEGRACION", "APORTE PENDIENTE"),
        },
        {
            "comportamiento": "CUENTA_PARTICULAR_SOCIO",
            "confianza": CONFIANZA_MEDIA,
            "motivo": "La cuenta parece representar una cuenta particular de socios.",
            "match": lambda t: _contiene(t, "CUENTA PARTICULAR SOCIOS", "SOCIOS CUENTA PARTICULAR", "CTA PARTICULAR SOCIOS"),
        },
        {
            "comportamiento": "PRESTAMO_SOCIO",
            "confianza": CONFIANZA_MEDIA,
            "motivo": "La cuenta parece representar préstamos de socios.",
            "match": lambda t: _contiene(t, "PRESTAMO SOCIO", "PRESTAMOS DE SOCIOS", "MUTUO SOCIO"),
        },
        {
            "comportamiento": "SUELDOS_A_PAGAR",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar remuneraciones a pagar.",
            "match": lambda t: _contiene(t, "SUELDOS A PAGAR", "HABERES A PAGAR", "REMUNERACIONES A PAGAR"),
        },
        {
            "comportamiento": "SUELDOS_GASTO",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar gasto por sueldos, jornales o remuneraciones.",
            "match": lambda t: _contiene(t, "SUELDOS", "JORNALES", "REMUNERACIONES", "HABERES"),
        },
        {
            "comportamiento": "ART_A_PAGAR",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar una obligación con ART.",
            "match": lambda t: _contiene(t, "ART A PAGAR", "ASEGURADORA DE RIESGOS"),
        },
        {
            "comportamiento": "OBRA_SOCIAL_A_PAGAR",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar obra social a pagar.",
            "match": lambda t: _contiene(t, "OBRA SOCIAL A PAGAR", "OBRAS SOCIALES A PAGAR"),
        },
        {
            "comportamiento": "SINDICATO_A_PAGAR",
            "confianza": CONFIANZA_ALTA,
            "motivo": "La cuenta parece representar sindicato a pagar.",
            "match": lambda t: _contiene(t, "SINDICATO A PAGAR", "APORTE SINDICAL", "CUOTA SINDICAL"),
        },
        {
            "comportamiento": "CARGAS_SOCIALES_A_PAGAR",
            "confianza": CONFIANZA_MEDIA,
            "motivo": "La cuenta parece representar cargas sociales o contribuciones a pagar.",
            "match": lambda t: _contiene(t, "CARGAS SOCIALES A PAGAR", "CONTRIBUCIONES A PAGAR", "SIPA A PAGAR", "931 A PAGAR"),
        },
        {
            "comportamiento": "CARGAS_SOCIALES_GASTO",
            "confianza": CONFIANZA_MEDIA,
            "motivo": "La cuenta parece representar gasto por cargas sociales o contribuciones patronales.",
            "match": lambda t: _contiene(t, "CARGAS SOCIALES", "CONTRIBUCIONES", "SEGURIDAD SOCIAL"),
        },
    ]

    for regla in reglas:
        comportamiento = normalizar_codigo(regla["comportamiento"])
        if not validar_comportamiento_contable(comportamiento):
            continue
        if regla["match"](texto):
            datos = describir_comportamiento(comportamiento) or {}
            return {
                "codigo_cuenta": codigo,
                "nombre_cuenta": nombre,
                "comportamiento": comportamiento,
                "comportamiento_nombre": datos.get("nombre", comportamiento),
                "naturaleza": datos.get("naturaleza", ""),
                "confianza": regla["confianza"],
                "motivo": regla["motivo"],
            }
    return None


def sugerir_normalizacion_para_cuenta(codigo_cuenta: Any, nombre_cuenta: Any) -> dict[str, Any] | None:
    return _sugerir_por_reglas(codigo_cuenta, nombre_cuenta)


def listar_sugerencias_normalizacion(
    empresa_id: int | None = None,
    *,
    incluir_conflictos: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        cuentas = listar_cuentas_plan(empresa_id=empresa_id, conn=conn)
        sugerencias: list[dict[str, Any]] = []
        for cuenta in cuentas:
            sugerencia = sugerir_normalizacion_para_cuenta(cuenta.get("codigo_cuenta"), cuenta.get("nombre_cuenta"))
            if not sugerencia:
                continue
            actuales = [normalizar_codigo(item) for item in cuenta.get("comportamientos") or []]
            if sugerencia["comportamiento"] in actuales:
                sugerencia["estado_sugerencia"] = "YA_CONFIGURADO"
                sugerencia["accion_recomendada"] = "Sin cambios"
                sugerencia["aplicable"] = False
            elif actuales:
                sugerencia["estado_sugerencia"] = "CONFLICTO"
                sugerencia["accion_recomendada"] = "Revisar asignación existente"
                sugerencia["aplicable"] = False
                sugerencia["comportamiento_actual"] = ",".join(actuales)
            else:
                sugerencia["estado_sugerencia"] = "PENDIENTE"
                sugerencia["accion_recomendada"] = "Aplicar sugerencia"
                sugerencia["aplicable"] = True
                sugerencia["comportamiento_actual"] = ""
            if sugerencia["estado_sugerencia"] == "CONFLICTO" and not incluir_conflictos:
                continue
            sugerencias.append(sugerencia)
        orden_confianza = {CONFIANZA_ALTA: 0, CONFIANZA_MEDIA: 1, CONFIANZA_BAJA: 2}
        return sorted(
            sugerencias,
            key=lambda item: (
                item.get("estado_sugerencia") != "PENDIENTE",
                orden_confianza.get(item.get("confianza"), 9),
                str(item.get("codigo_cuenta") or ""),
            ),
        )
    finally:
        if propia:
            conn.close()


def obtener_resumen_normalizacion(
    empresa_id: int | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        cuentas = listar_cuentas_plan(empresa_id=empresa_id, conn=conn)
        sugerencias = listar_sugerencias_normalizacion(empresa_id=empresa_id, conn=conn)
        mapeos_activos = listar_mapeos_comportamientos(empresa_id=empresa_id, conn=conn)
        comportamientos_cubiertos = {normalizar_codigo(item.get("comportamiento")) for item in mapeos_activos}
        return {
            "total_cuentas": len(cuentas),
            "cuentas_con_comportamiento": sum(1 for cuenta in cuentas if cuenta.get("cantidad_comportamientos", 0) > 0),
            "cuentas_sin_comportamiento": sum(1 for cuenta in cuentas if cuenta.get("cantidad_comportamientos", 0) == 0),
            "mapeos_activos": len(mapeos_activos),
            "sugerencias_total": len(sugerencias),
            "sugerencias_pendientes": sum(1 for item in sugerencias if item.get("estado_sugerencia") == "PENDIENTE"),
            "sugerencias_alta": sum(1 for item in sugerencias if item.get("estado_sugerencia") == "PENDIENTE" and item.get("confianza") == CONFIANZA_ALTA),
            "conflictos": sum(1 for item in sugerencias if item.get("estado_sugerencia") == "CONFLICTO"),
            "criticos_total": len(COMPORTAMIENTOS_CRITICOS),
            "criticos_cubiertos": sum(1 for codigo in COMPORTAMIENTOS_CRITICOS if codigo in comportamientos_cubiertos),
            "criticos_faltantes": [codigo for codigo in COMPORTAMIENTOS_CRITICOS if codigo not in comportamientos_cubiertos],
        }
    finally:
        if propia:
            conn.close()


def estimar_impacto_sugerencias(
    *,
    empresa_id: int | None,
    sugerencias: list[dict[str, Any]],
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        mapeos = listar_mapeos_comportamientos(empresa_id=empresa_id, conn=conn)
        cubiertos = {normalizar_codigo(item.get("comportamiento")) for item in mapeos}
        aplicables = [item for item in sugerencias if item.get("aplicable", True) and item.get("estado_sugerencia", "PENDIENTE") == "PENDIENTE"]
        nuevos = {normalizar_codigo(item.get("comportamiento")) for item in aplicables}
        despues = cubiertos | nuevos
        resolveria = [codigo for codigo in COMPORTAMIENTOS_CRITICOS if codigo not in cubiertos and codigo in despues]
        pendientes = [codigo for codigo in COMPORTAMIENTOS_CRITICOS if codigo not in despues]
        return {
            "aplicables": len(aplicables),
            "comportamientos_a_agregar": sorted(nuevos),
            "criticos_que_resolveria": resolveria,
            "criticos_que_seguirian_pendientes": pendientes,
        }
    finally:
        if propia:
            conn.close()


def aplicar_sugerencias_normalizacion(
    *,
    empresa_id: int | None,
    sugerencias: list[dict[str, Any]],
    usuario: str | None = None,
    motivo: str | None = None,
    solo_alta_confianza: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        procesadas = 0
        omitidas = 0
        errores: list[str] = []
        motivo_base = motivo or "Aplicado desde asistente de normalización contable."
        for sugerencia in sugerencias:
            if sugerencia.get("estado_sugerencia", "PENDIENTE") != "PENDIENTE" or not sugerencia.get("aplicable", True):
                omitidas += 1
                continue
            if solo_alta_confianza and sugerencia.get("confianza") != CONFIANZA_ALTA:
                omitidas += 1
                continue
            resultado = guardar_comportamiento_cuenta(
                empresa_id=empresa_id,
                codigo_cuenta=sugerencia.get("codigo_cuenta"),
                comportamiento=sugerencia.get("comportamiento"),
                usuario=usuario,
                observaciones=f"{motivo_base} Motivo sugerencia: {sugerencia.get('motivo', '')}",
                origen="ASISTENTE_NORMALIZACION",
                conn=conn,
            )
            if resultado.get("ok"):
                procesadas += 1
                _marcar_estado_activo(conn, resultado.get("mapeo_id"))
            else:
                errores.append(resultado.get("mensaje", "Error sin detalle."))
        if propia:
            conn.commit()
        return {"ok": not errores, "procesadas": procesadas, "omitidas": omitidas, "errores": errores}
    except Exception as exc:
        if propia:
            conn.rollback()
        raise exc
    finally:
        if propia:
            conn.close()


def _obtener_mapeo(conn: sqlite3.Connection, mapeo_id: int) -> dict[str, Any] | None:
    filas = _fetch_dicts(
        conn,
        "SELECT * FROM contabilidad_cuentas_comportamiento WHERE id = ? LIMIT 1",
        (mapeo_id,),
    )
    return filas[0] if filas else None


def _marcar_estado_activo(conn: sqlite3.Connection, mapeo_id: int | None) -> None:
    if not mapeo_id:
        return
    if "estado" in _columns(conn, "contabilidad_cuentas_comportamiento"):
        conn.execute(
            "UPDATE contabilidad_cuentas_comportamiento SET estado = 'ACTIVO' WHERE id = ?",
            (mapeo_id,),
        )


def editar_asignacion_comportamiento(
    *,
    empresa_id: int | None,
    mapeo_id: int,
    nuevo_comportamiento: str,
    usuario: str | None = None,
    motivo: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not str(motivo or "").strip():
        return {"ok": False, "mensaje": "El motivo es obligatorio para editar una asignación."}
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        nuevo = normalizar_codigo(nuevo_comportamiento)
        if not validar_comportamiento_contable(nuevo):
            return {"ok": False, "mensaje": f"Comportamiento no reconocido: {nuevo}."}
        mapeo = _obtener_mapeo(conn, mapeo_id)
        if not mapeo:
            return {"ok": False, "mensaje": "No se encontró la asignación a editar."}
        if empresa_id is not None and mapeo.get("empresa_id") not in (None, empresa_id):
            return {"ok": False, "mensaje": "La asignación no pertenece a la empresa seleccionada."}
        anterior = normalizar_codigo(mapeo.get("comportamiento"))
        if anterior == nuevo and mapeo.get("activo") == 1:
            return {"ok": True, "mensaje": "La asignación ya tenía ese comportamiento.", "sin_cambios": True}
        ahora = _now_iso()
        conn.execute(
            """
            UPDATE contabilidad_cuentas_comportamiento
            SET comportamiento = ?,
                comportamiento_anterior = ?,
                activo = 1,
                estado = 'ACTIVO',
                origen = 'MANUAL_CORRECCION',
                usuario_edicion = ?,
                fecha_edicion = ?,
                motivo_edicion = ?,
                usuario_actualizacion = ?,
                actualizado_en = ?,
                usuario_baja = NULL,
                fecha_baja = NULL,
                motivo_baja = NULL,
                usuario_anulacion = NULL,
                fecha_anulacion = NULL,
                motivo_anulacion = NULL
            WHERE id = ?
            """,
            (nuevo, anterior, usuario, ahora, motivo, usuario, ahora, mapeo_id),
        )
        _registrar_evento(
            conn,
            empresa_id=mapeo.get("empresa_id") if mapeo.get("empresa_id") is not None else empresa_id,
            mapeo_id=mapeo_id,
            codigo_cuenta=mapeo.get("codigo_cuenta"),
            comportamiento=nuevo,
            evento="EDITADO",
            detalle=f"Se corrigió la asignación de {anterior} a {nuevo}. Motivo: {motivo}",
            usuario=usuario,
        )
        if propia:
            conn.commit()
        return {"ok": True, "mensaje": f"Asignación corregida de {anterior} a {nuevo}.", "mapeo_id": mapeo_id}
    except Exception as exc:
        if propia:
            conn.rollback()
        raise exc
    finally:
        if propia:
            conn.close()


def desactivar_asignacion_comportamiento(
    *,
    empresa_id: int | None,
    mapeo_id: int,
    usuario: str | None = None,
    motivo: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not str(motivo or "").strip():
        return {"ok": False, "mensaje": "El motivo es obligatorio para desactivar una asignación."}
    return _cambiar_estado_asignacion(
        empresa_id=empresa_id,
        mapeo_id=mapeo_id,
        nuevo_estado=ESTADO_INACTIVO,
        evento="DESACTIVADO",
        usuario=usuario,
        motivo=motivo,
        conn=conn,
    )


def anular_asignacion_comportamiento(
    *,
    empresa_id: int | None,
    mapeo_id: int,
    usuario: str | None = None,
    motivo: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not str(motivo or "").strip():
        return {"ok": False, "mensaje": "El motivo es obligatorio para anular una asignación cargada por error."}
    return _cambiar_estado_asignacion(
        empresa_id=empresa_id,
        mapeo_id=mapeo_id,
        nuevo_estado=ESTADO_ANULADO,
        evento="ANULADO",
        usuario=usuario,
        motivo=motivo,
        conn=conn,
    )


def _cambiar_estado_asignacion(
    *,
    empresa_id: int | None,
    mapeo_id: int,
    nuevo_estado: str,
    evento: str,
    usuario: str | None,
    motivo: str | None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        mapeo = _obtener_mapeo(conn, mapeo_id)
        if not mapeo:
            return {"ok": False, "mensaje": "No se encontró la asignación indicada."}
        if empresa_id is not None and mapeo.get("empresa_id") not in (None, empresa_id):
            return {"ok": False, "mensaje": "La asignación no pertenece a la empresa seleccionada."}
        ahora = _now_iso()
        if nuevo_estado == ESTADO_ANULADO:
            conn.execute(
                """
                UPDATE contabilidad_cuentas_comportamiento
                SET activo = 0,
                    estado = 'ANULADO',
                    usuario_anulacion = ?,
                    fecha_anulacion = ?,
                    motivo_anulacion = ?,
                    usuario_baja = ?,
                    fecha_baja = ?,
                    motivo_baja = ?,
                    usuario_actualizacion = ?,
                    actualizado_en = ?
                WHERE id = ?
                """,
                (usuario, ahora, motivo, usuario, ahora, motivo, usuario, ahora, mapeo_id),
            )
        else:
            conn.execute(
                """
                UPDATE contabilidad_cuentas_comportamiento
                SET activo = 0,
                    estado = 'INACTIVO',
                    usuario_baja = ?,
                    fecha_baja = ?,
                    motivo_baja = ?,
                    usuario_actualizacion = ?,
                    actualizado_en = ?
                WHERE id = ?
                """,
                (usuario, ahora, motivo, usuario, ahora, mapeo_id),
            )
        _registrar_evento(
            conn,
            empresa_id=mapeo.get("empresa_id") if mapeo.get("empresa_id") is not None else empresa_id,
            mapeo_id=mapeo_id,
            codigo_cuenta=mapeo.get("codigo_cuenta"),
            comportamiento=mapeo.get("comportamiento"),
            evento=evento,
            detalle=motivo or evento,
            usuario=usuario,
        )
        if propia:
            conn.commit()
        return {"ok": True, "mensaje": f"Asignación {nuevo_estado.lower()} correctamente.", "mapeo_id": mapeo_id}
    except Exception as exc:
        if propia:
            conn.rollback()
        raise exc
    finally:
        if propia:
            conn.close()


def listar_historial_normalizacion(
    empresa_id: int | None = None,
    *,
    limite: int = 100,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    return listar_eventos_comportamientos(empresa_id=empresa_id, limite=limite, conn=conn)


def listar_asignaciones_normalizacion(
    empresa_id: int | None = None,
    *,
    incluir_inactivas: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    propia = conn is None
    conn = conn or _conectar_default()
    _asegurar_row_factory(conn)
    try:
        migrar_normalizacion_contable(conn)
        return listar_mapeos_comportamientos(
            empresa_id=empresa_id,
            incluir_inactivos=incluir_inactivas,
            conn=conn,
        )
    finally:
        if propia:
            conn.close()