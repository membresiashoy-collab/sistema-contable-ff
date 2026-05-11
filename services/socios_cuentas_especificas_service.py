from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from database import conectar
from services.plan_cuentas_service import crear_cuenta_empresa_desde_modelo


TIPOS_CUENTA_SOCIO: dict[str, dict[str, Any]] = {
    "CUENTA_PARTICULAR_SOCIO": {
        "nombre": "Cuenta particular del socio",
        "descripcion": "Control económico individual del socio para movimientos no capitalizables hasta su clasificación definitiva.",
        "tipo_vinculo": "CUENTA_PARTICULAR_SOCIO",
        "palabras_clave": [
            "cuenta particular socio",
            "cuenta particular socios",
            "cta particular",
            "socio x cuenta particular",
            "socio cuenta particular",
            "directores cuenta particular",
        ],
        "nombre_cuenta": "Cuenta particular - {socio}",
    },
    "PRESTAMO_SOCIO_EMPRESA": {
        "nombre": "Préstamo de socio a la empresa",
        "descripcion": "Pasivo o cuenta de control por fondos/créditos entregados por el socio a la empresa con obligación de devolución.",
        "tipo_vinculo": "PRESTAMO_SOCIO_EMPRESA",
        "palabras_clave": [
            "prestamo socio",
            "prestamos socio",
            "préstamo socio",
            "préstamos socio",
            "prestamos de socios",
            "préstamos de socios",
            "deudas con socios",
        ],
        "nombre_cuenta": "Préstamo socio - {socio}",
    },
    "SOCIOS_INTEGRACION": {
        "nombre": "Integración pendiente del socio",
        "descripcion": "Crédito contra el socio por capital suscripto pendiente de integración, cuando corresponda por el tipo societario.",
        "tipo_vinculo": "INTEGRACION_CAPITAL",
        "palabras_clave": [
            "socios por integracion",
            "socios por integración",
            "accionistas por integracion",
            "accionistas por integración",
            "capital pendiente",
            "cuenta suscripta",
            "cuenta aporte",
            "accionistas",
        ],
        "nombre_cuenta": "Socios por integración - {socio}",
    },
    "APORTE_IRREVOCABLE_SOCIO": {
        "nombre": "Aporte irrevocable del socio",
        "descripcion": "Cuenta específica para aportes irrevocables recibidos o comprometidos, pendiente de tratamiento societario/contable definitivo.",
        "tipo_vinculo": "APORTE_IRREVOCABLE_SOCIO",
        "palabras_clave": [
            "aporte irrevocable",
            "aportes irrevocables",
            "aportes de socios",
            "socio cuenta aporte",
            "cuenta aporte",
        ],
        "nombre_cuenta": "Aporte irrevocable socio - {socio}",
    },
    "RETIRO_REINTEGRO_SOCIO": {
        "nombre": "Retiros o reintegros a clasificar",
        "descripcion": "Cuenta auxiliar específica para clasificar retiros, reintegros o salidas a favor del socio antes de su registración definitiva.",
        "tipo_vinculo": "RETIRO_REINTEGRO_SOCIO",
        "palabras_clave": [
            "retiro socio",
            "retiros de socios",
            "reintegro socio",
            "reintegros socios",
            "cuenta particular socio",
            "cuenta particular socios",
        ],
        "nombre_cuenta": "Retiros/reintegros socio - {socio}",
    },
}

ESTADOS_VINCULO = {"SUGERIDA", "VINCULADA", "ANULADA"}
ORIGENES_VINCULO = {"SUGERIDA", "CREADA_DESDE_MODELO", "VINCULADA_EXISTENTE"}


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _normalizar_clave(valor: Any) -> str:
    texto = _texto(valor).upper()
    texto = texto.replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
    texto = texto.replace("Ñ", "N")
    texto = re.sub(r"[^A-Z0-9_]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto


def _texto_busqueda(valor: Any) -> str:
    texto = _texto(valor).lower()
    texto = texto.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    texto = texto.replace("ñ", "n")
    return texto


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _asegurar_row_factory(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row


def _table_exists(conn: sqlite3.Connection, tabla: str) -> bool:
    fila = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (_texto(tabla),),
    ).fetchone()
    return fila is not None


def _json(valor: Any) -> str:
    try:
        return json.dumps(valor, ensure_ascii=False, default=str)
    except Exception:
        return str(valor)


def _normalizar_tipo_cuenta(tipo_cuenta: str) -> str:
    tipo = _normalizar_clave(tipo_cuenta)
    if tipo not in TIPOS_CUENTA_SOCIO:
        raise ValueError("Tipo de cuenta de socio no reconocido.")
    return tipo


def _nombre_socio_limpio(nombre: str) -> str:
    nombre_limpio = re.sub(r"\s+", " ", _texto(nombre))
    return nombre_limpio or "Socio sin nombre"


def _sufijo_socio(socio: dict[str, Any]) -> str:
    cuit = re.sub(r"\D+", "", _texto(socio.get("cuit")))
    if len(cuit) >= 4:
        return cuit[-4:]
    return f"{int(socio.get('id') or 0):04d}"


def _codigo_candidato(base: str, socio: dict[str, Any], conn: sqlite3.Connection, empresa_id: int) -> str:
    base = _texto(base)
    if not base:
        base = "SOCIO"
    sufijo = _sufijo_socio(socio)
    candidato = f"{base}.{sufijo}"
    existe = conn.execute(
        """
        SELECT 1
        FROM plan_cuentas_empresa
        WHERE empresa_id = ?
          AND codigo = ?
        LIMIT 1
        """,
        (int(empresa_id), candidato),
    ).fetchone()
    if not existe:
        return candidato

    for numero in range(2, 100):
        candidato_num = f"{base}.{sufijo}.{numero:02d}"
        existe = conn.execute(
            """
            SELECT 1
            FROM plan_cuentas_empresa
            WHERE empresa_id = ?
              AND codigo = ?
            LIMIT 1
            """,
            (int(empresa_id), candidato_num),
        ).fetchone()
        if not existe:
            return candidato_num

    raise ValueError("No se pudo generar un código disponible para la cuenta específica del socio.")


def asegurar_estructura_socios_cuentas_especificas(conn: sqlite3.Connection | None = None) -> None:
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS socios_cuentas_especificas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                socio_id INTEGER NOT NULL,
                tipo_cuenta TEXT NOT NULL,
                tipo_vinculo TEXT,
                cuenta_modelo_id INTEGER,
                cuenta_modelo_codigo TEXT,
                cuenta_modelo_nombre TEXT,
                cuenta_empresa_id INTEGER,
                cuenta_empresa_codigo TEXT,
                cuenta_empresa_nombre TEXT,
                estado TEXT NOT NULL DEFAULT 'VINCULADA',
                origen TEXT NOT NULL DEFAULT 'VINCULADA_EXISTENTE',
                motivo TEXT,
                observaciones TEXT,
                usuario_creacion TEXT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario_actualizacion TEXT,
                fecha_actualizacion TEXT,
                usuario_anulacion TEXT,
                fecha_anulacion TEXT,
                motivo_anulacion TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS socios_cuentas_especificas_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                socio_id INTEGER NOT NULL,
                vinculo_id INTEGER,
                tipo_cuenta TEXT,
                evento TEXT NOT NULL,
                detalle TEXT,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                motivo TEXT,
                usuario TEXT,
                fecha_evento TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_socios_cuentas_especificas_socio
            ON socios_cuentas_especificas (empresa_id, socio_id, estado, tipo_cuenta)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_socios_cuentas_especificas_cuenta
            ON socios_cuentas_especificas (empresa_id, cuenta_empresa_id, estado)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_socios_cuentas_especificas_activa
            ON socios_cuentas_especificas (empresa_id, socio_id, tipo_cuenta)
            WHERE estado <> 'ANULADA'
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_socios_cuentas_especificas_eventos
            ON socios_cuentas_especificas_eventos (empresa_id, socio_id, fecha_evento)
            """
        )
        if propia:
            conn.commit()
    finally:
        if propia:
            conn.close()


def _registrar_evento(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    socio_id: int,
    vinculo_id: int | None,
    tipo_cuenta: str,
    evento: str,
    detalle: str,
    valor_anterior: Any = "",
    valor_nuevo: Any = "",
    motivo: str = "",
    usuario: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO socios_cuentas_especificas_eventos
        (empresa_id, socio_id, vinculo_id, tipo_cuenta, evento, detalle,
         valor_anterior, valor_nuevo, motivo, usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(empresa_id),
            int(socio_id),
            int(vinculo_id) if vinculo_id is not None else None,
            _normalizar_clave(tipo_cuenta),
            _normalizar_clave(evento),
            _texto(detalle),
            _json(valor_anterior) if not isinstance(valor_anterior, str) else valor_anterior,
            _json(valor_nuevo) if not isinstance(valor_nuevo, str) else valor_nuevo,
            _texto(motivo),
            _texto(usuario),
        ),
    )


def _obtener_socio_activo(conn: sqlite3.Connection, socio_id: int, empresa_id: int) -> dict[str, Any]:
    fila = conn.execute(
        """
        SELECT *
        FROM socios_empresa
        WHERE id = ?
          AND empresa_id = ?
        LIMIT 1
        """,
        (int(socio_id), int(empresa_id)),
    ).fetchone()
    if not fila:
        raise ValueError("No se encontró el socio indicado para la empresa activa.")
    socio = _row_to_dict(fila)
    if _texto(socio.get("estado")).upper() != "ACTIVO":
        raise ValueError("No se puede preparar una cuenta específica para un socio dado de baja.")
    return socio


def catalogo_tipos_cuentas_socios() -> pd.DataFrame:
    filas = []
    for tipo, datos in TIPOS_CUENTA_SOCIO.items():
        filas.append(
            {
                "tipo_cuenta": tipo,
                "nombre": datos["nombre"],
                "descripcion": datos["descripcion"],
                "tipo_vinculo": datos["tipo_vinculo"],
            }
        )
    return pd.DataFrame(filas)


def _tipo_por_modelo(modelo: dict[str, Any]) -> str | None:
    texto = _texto_busqueda(
        " ".join(
            [
                _texto(modelo.get("nombre")),
                _texto(modelo.get("uso_operativo_sistema")),
                _texto(modelo.get("rubro")),
                _texto(modelo.get("cuenta")),
                _texto(modelo.get("subcuenta")),
                _texto(modelo.get("observaciones")),
            ]
        )
    )
    for tipo, datos in TIPOS_CUENTA_SOCIO.items():
        for palabra in datos["palabras_clave"]:
            if _texto_busqueda(palabra) in texto:
                return tipo
    return None


def listar_modelos_socios(empresa_id: int = 1, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        if not _table_exists(conn, "plan_cuentas_maestro"):
            return pd.DataFrame()

        filas = conn.execute(
            """
            SELECT
                id,
                codigo,
                nombre,
                codigo_madre,
                nivel,
                imputable,
                es_cuenta_modelo,
                permite_copiar_modelo,
                uso_operativo_sistema,
                rubro,
                cuenta,
                subcuenta,
                observaciones,
                estado
            FROM plan_cuentas_maestro
            WHERE estado = 'ACTIVA'
              AND (
                lower(nombre) LIKE '%socio%'
                OR lower(nombre) LIKE '%accionista%'
                OR lower(nombre) LIKE '%integracion%'
                OR lower(nombre) LIKE '%integración%'
                OR lower(nombre) LIKE '%prestamo%'
                OR lower(nombre) LIKE '%préstamo%'
                OR lower(nombre) LIKE '%retiro%'
                OR lower(nombre) LIKE '%reintegro%'
                OR lower(COALESCE(uso_operativo_sistema, '')) LIKE '%socio%'
              )
            ORDER BY codigo
            """
        ).fetchall()
        registros = []
        for fila in filas:
            modelo = _row_to_dict(fila)
            tipo = _tipo_por_modelo(modelo)
            if not tipo:
                continue
            modelo["tipo_cuenta_sugerida"] = tipo
            modelo["estado_modelo"] = (
                "MODELO_COPIABLE"
                if int(modelo.get("es_cuenta_modelo") or 0) == 1
                and int(modelo.get("permite_copiar_modelo") or 0) == 1
                else "NO_HABILITADO_PARA_COPIA"
            )
            registros.append(modelo)
        return pd.DataFrame(registros)
    finally:
        if propia:
            conn.close()


def _modelos_por_tipo(conn: sqlite3.Connection, empresa_id: int) -> dict[str, list[dict[str, Any]]]:
    df = listar_modelos_socios(empresa_id=empresa_id, conn=conn)
    if df.empty:
        return {tipo: [] for tipo in TIPOS_CUENTA_SOCIO}
    resultado: dict[str, list[dict[str, Any]]] = {tipo: [] for tipo in TIPOS_CUENTA_SOCIO}
    for registro in df.to_dict("records"):
        tipo = _normalizar_clave(registro.get("tipo_cuenta_sugerida"))
        if tipo in resultado:
            resultado[tipo].append(registro)
    return resultado


def _seleccionar_modelo_para_tipo(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    tipo_cuenta: str,
    cuenta_modelo_id: int | None = None,
) -> dict[str, Any] | None:
    tipo = _normalizar_tipo_cuenta(tipo_cuenta)
    if cuenta_modelo_id is not None:
        fila = conn.execute(
            """
            SELECT *
            FROM plan_cuentas_maestro
            WHERE id = ?
              AND estado = 'ACTIVA'
            LIMIT 1
            """,
            (int(cuenta_modelo_id),),
        ).fetchone()
        if not fila:
            return None
        modelo = _row_to_dict(fila)
        modelo["tipo_cuenta_sugerida"] = _tipo_por_modelo(modelo) or tipo
        modelo["estado_modelo"] = (
            "MODELO_COPIABLE"
            if int(modelo.get("es_cuenta_modelo") or 0) == 1
            and int(modelo.get("permite_copiar_modelo") or 0) == 1
            else "NO_HABILITADO_PARA_COPIA"
        )
        return modelo

    modelos = _modelos_por_tipo(conn, empresa_id).get(tipo, [])
    copiables = [m for m in modelos if m.get("estado_modelo") == "MODELO_COPIABLE"]
    if copiables:
        return copiables[0]
    return modelos[0] if modelos else None


def _obtener_vinculo_activo(
    conn: sqlite3.Connection,
    *,
    empresa_id: int,
    socio_id: int,
    tipo_cuenta: str,
) -> dict[str, Any] | None:
    fila = conn.execute(
        """
        SELECT *
        FROM socios_cuentas_especificas
        WHERE empresa_id = ?
          AND socio_id = ?
          AND tipo_cuenta = ?
          AND estado <> 'ANULADA'
        LIMIT 1
        """,
        (int(empresa_id), int(socio_id), _normalizar_tipo_cuenta(tipo_cuenta)),
    ).fetchone()
    return _row_to_dict(fila) if fila else None


def listar_cuentas_especificas_socios(
    empresa_id: int = 1,
    socio_id: int | None = None,
    incluir_anuladas: bool = False,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_socios_cuentas_especificas(conn)
        condiciones = ["v.empresa_id = ?"]
        params: list[Any] = [int(empresa_id)]
        if socio_id is not None:
            condiciones.append("v.socio_id = ?")
            params.append(int(socio_id))
        if not incluir_anuladas:
            condiciones.append("v.estado <> 'ANULADA'")

        where = " AND ".join(condiciones)
        filas = conn.execute(
            f"""
            SELECT
                v.*,
                s.nombre AS socio_nombre,
                s.cuit AS socio_cuit,
                s.estado AS socio_estado
            FROM socios_cuentas_especificas v
            LEFT JOIN socios_empresa s
              ON s.id = v.socio_id
             AND s.empresa_id = v.empresa_id
            WHERE {where}
            ORDER BY s.nombre, v.tipo_cuenta, v.id
            """,
            params,
        ).fetchall()
        return pd.DataFrame([_row_to_dict(f) for f in filas])
    finally:
        if propia:
            conn.close()


def obtener_estado_preparacion_socios(
    empresa_id: int = 1,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_socios_cuentas_especificas(conn)
        socios = conn.execute(
            """
            SELECT id, nombre, cuit, tipo_socio, porcentaje_participacion, estado,
                   cuenta_particular_habilitada, cuenta_particular_codigo, cuenta_particular_nombre
            FROM socios_empresa
            WHERE empresa_id = ?
              AND estado = 'ACTIVO'
            ORDER BY nombre
            """,
            (int(empresa_id),),
        ).fetchall()
        modelos_por_tipo = _modelos_por_tipo(conn, int(empresa_id))
        registros: list[dict[str, Any]] = []
        for socio_row in socios:
            socio = _row_to_dict(socio_row)
            for tipo, config in TIPOS_CUENTA_SOCIO.items():
                vinculo = _obtener_vinculo_activo(
                    conn,
                    empresa_id=int(empresa_id),
                    socio_id=int(socio["id"]),
                    tipo_cuenta=tipo,
                )
                modelos = modelos_por_tipo.get(tipo, [])
                modelo_copiable = next((m for m in modelos if m.get("estado_modelo") == "MODELO_COPIABLE"), None)
                modelo_referencia = modelo_copiable or (modelos[0] if modelos else None)
                if vinculo:
                    estado = "CUENTA_VINCULADA"
                elif modelo_copiable:
                    estado = "LISTA_PARA_CREAR"
                elif modelo_referencia:
                    estado = "MODELO_NO_HABILITADO"
                else:
                    estado = "SIN_MODELO"
                registros.append(
                    {
                        "empresa_id": int(empresa_id),
                        "socio_id": int(socio["id"]),
                        "socio_nombre": socio.get("nombre"),
                        "socio_cuit": socio.get("cuit"),
                        "tipo_socio": socio.get("tipo_socio"),
                        "tipo_cuenta": tipo,
                        "cuenta_requerida": config["nombre"],
                        "estado_preparacion": estado,
                        "cuenta_empresa_id": vinculo.get("cuenta_empresa_id") if vinculo else None,
                        "cuenta_empresa_codigo": vinculo.get("cuenta_empresa_codigo") if vinculo else "",
                        "cuenta_empresa_nombre": vinculo.get("cuenta_empresa_nombre") if vinculo else "",
                        "cuenta_modelo_id": modelo_referencia.get("id") if modelo_referencia else None,
                        "cuenta_modelo_codigo": modelo_referencia.get("codigo") if modelo_referencia else "",
                        "cuenta_modelo_nombre": modelo_referencia.get("nombre") if modelo_referencia else "",
                        "modelo_permite_copia": int(modelo_referencia.get("permite_copiar_modelo") or 0) if modelo_referencia else 0,
                        "modelo_es_cuenta_modelo": int(modelo_referencia.get("es_cuenta_modelo") or 0) if modelo_referencia else 0,
                    }
                )
        return pd.DataFrame(registros)
    finally:
        if propia:
            conn.close()


def crear_cuenta_especifica_socio(
    *,
    socio_id: int,
    tipo_cuenta: str,
    empresa_id: int = 1,
    cuenta_modelo_id: int | None = None,
    codigo_nuevo: str = "",
    nombre_nuevo: str = "",
    motivo: str,
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not _texto(motivo):
        return {"ok": False, "errores": ["Debe indicar un motivo para crear o vincular la cuenta específica del socio."]}
    tipo = _normalizar_tipo_cuenta(tipo_cuenta)
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_socios_cuentas_especificas(conn)
        socio = _obtener_socio_activo(conn, int(socio_id), int(empresa_id))
        existente = _obtener_vinculo_activo(conn, empresa_id=int(empresa_id), socio_id=int(socio_id), tipo_cuenta=tipo)
        if existente:
            return {
                "ok": True,
                "ya_existia": True,
                "vinculo_id": existente.get("id"),
                "cuenta_empresa_id": existente.get("cuenta_empresa_id"),
                "codigo": existente.get("cuenta_empresa_codigo"),
                "nombre": existente.get("cuenta_empresa_nombre"),
                "mensaje": "El socio ya tiene una cuenta específica activa para este concepto.",
            }

        modelo = _seleccionar_modelo_para_tipo(
            conn,
            empresa_id=int(empresa_id),
            tipo_cuenta=tipo,
            cuenta_modelo_id=cuenta_modelo_id,
        )
        if not modelo:
            return {
                "ok": False,
                "errores": [
                    "No se encontró una cuenta modelo relacionada con este concepto en el Plan Maestro FF. "
                    "Primero debe marcarse una cuenta modelo copiable desde el mantenimiento del Plan Maestro."
                ],
            }
        if int(modelo.get("es_cuenta_modelo") or 0) != 1 or int(modelo.get("permite_copiar_modelo") or 0) != 1:
            return {
                "ok": False,
                "errores": [
                    "La cuenta encontrada en el Plan Maestro no está habilitada como modelo copiable. "
                    "No se crea una cuenta específica para evitar deformar el Plan Maestro."
                ],
                "cuenta_modelo_id": modelo.get("id"),
                "cuenta_modelo_codigo": modelo.get("codigo"),
                "cuenta_modelo_nombre": modelo.get("nombre"),
            }

        codigo_final = _texto(codigo_nuevo) or _codigo_candidato(_texto(modelo.get("codigo")), socio, conn, int(empresa_id))
        nombre_final = _texto(nombre_nuevo) or TIPOS_CUENTA_SOCIO[tipo]["nombre_cuenta"].format(
            socio=_nombre_socio_limpio(_texto(socio.get("nombre")))
        )

        resultado = crear_cuenta_empresa_desde_modelo(
            empresa_id=int(empresa_id),
            cuenta_maestro_id=int(modelo["id"]),
            codigo_nuevo=codigo_final,
            nombre_nuevo=nombre_final,
            motivo=motivo,
            usuario=usuario,
            conn=conn,
        )
        if not resultado.get("ok"):
            if propia:
                conn.rollback()
            return resultado

        cuenta_empresa_id = int(resultado["cuenta_empresa_id"])
        conn.execute(
            """
            INSERT INTO socios_cuentas_especificas
            (empresa_id, socio_id, tipo_cuenta, tipo_vinculo,
             cuenta_modelo_id, cuenta_modelo_codigo, cuenta_modelo_nombre,
             cuenta_empresa_id, cuenta_empresa_codigo, cuenta_empresa_nombre,
             estado, origen, motivo, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VINCULADA', 'CREADA_DESDE_MODELO', ?, ?)
            """,
            (
                int(empresa_id),
                int(socio_id),
                tipo,
                TIPOS_CUENTA_SOCIO[tipo]["tipo_vinculo"],
                int(modelo["id"]),
                _texto(modelo.get("codigo")),
                _texto(modelo.get("nombre")),
                cuenta_empresa_id,
                _texto(resultado.get("codigo") or codigo_final),
                _texto(resultado.get("nombre") or nombre_final),
                _texto(motivo),
                _texto(usuario),
            ),
        )
        vinculo_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        _registrar_evento(
            conn,
            empresa_id=int(empresa_id),
            socio_id=int(socio_id),
            vinculo_id=vinculo_id,
            tipo_cuenta=tipo,
            evento="CUENTA_SOCIO_CREADA_DESDE_MODELO",
            detalle="Se creó y vinculó una cuenta específica de empresa para el socio desde una cuenta modelo del Plan Maestro FF.",
            valor_nuevo={
                "cuenta_empresa_id": cuenta_empresa_id,
                "codigo": resultado.get("codigo") or codigo_final,
                "nombre": resultado.get("nombre") or nombre_final,
                "modelo": modelo.get("codigo"),
                "socio_id": int(socio_id),
            },
            motivo=motivo,
            usuario=usuario,
        )
        if propia:
            conn.commit()
        return {
            "ok": True,
            "vinculo_id": vinculo_id,
            "cuenta_empresa_id": cuenta_empresa_id,
            "codigo": resultado.get("codigo") or codigo_final,
            "nombre": resultado.get("nombre") or nombre_final,
            "mensaje": "Cuenta específica del socio creada y vinculada correctamente.",
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def vincular_cuenta_empresa_existente_socio(
    *,
    socio_id: int,
    tipo_cuenta: str,
    cuenta_empresa_id: int,
    empresa_id: int = 1,
    motivo: str,
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not _texto(motivo):
        return {"ok": False, "errores": ["Debe indicar un motivo para vincular la cuenta existente al socio."]}
    tipo = _normalizar_tipo_cuenta(tipo_cuenta)
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_socios_cuentas_especificas(conn)
        _obtener_socio_activo(conn, int(socio_id), int(empresa_id))
        existente = _obtener_vinculo_activo(conn, empresa_id=int(empresa_id), socio_id=int(socio_id), tipo_cuenta=tipo)
        if existente:
            return {
                "ok": True,
                "ya_existia": True,
                "vinculo_id": existente.get("id"),
                "cuenta_empresa_id": existente.get("cuenta_empresa_id"),
                "codigo": existente.get("cuenta_empresa_codigo"),
                "nombre": existente.get("cuenta_empresa_nombre"),
                "mensaje": "El socio ya tiene una cuenta específica activa para este concepto.",
            }

        cuenta = conn.execute(
            """
            SELECT id, cuenta_maestro_id, codigo, nombre, estado
            FROM plan_cuentas_empresa
            WHERE id = ?
              AND empresa_id = ?
            LIMIT 1
            """,
            (int(cuenta_empresa_id), int(empresa_id)),
        ).fetchone()
        if not cuenta:
            return {"ok": False, "errores": ["No se encontró la cuenta empresa indicada."]}
        cuenta_dict = _row_to_dict(cuenta)
        if _texto(cuenta_dict.get("estado")).upper() != "ACTIVA":
            return {"ok": False, "errores": ["La cuenta empresa indicada no está activa."]}

        conn.execute(
            """
            INSERT INTO socios_cuentas_especificas
            (empresa_id, socio_id, tipo_cuenta, tipo_vinculo,
             cuenta_modelo_id, cuenta_modelo_codigo, cuenta_modelo_nombre,
             cuenta_empresa_id, cuenta_empresa_codigo, cuenta_empresa_nombre,
             estado, origen, motivo, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, '', '', ?, ?, ?, 'VINCULADA', 'VINCULADA_EXISTENTE', ?, ?)
            """,
            (
                int(empresa_id),
                int(socio_id),
                tipo,
                TIPOS_CUENTA_SOCIO[tipo]["tipo_vinculo"],
                cuenta_dict.get("cuenta_maestro_id"),
                int(cuenta_dict["id"]),
                _texto(cuenta_dict.get("codigo")),
                _texto(cuenta_dict.get("nombre")),
                _texto(motivo),
                _texto(usuario),
            ),
        )
        vinculo_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        _registrar_evento(
            conn,
            empresa_id=int(empresa_id),
            socio_id=int(socio_id),
            vinculo_id=vinculo_id,
            tipo_cuenta=tipo,
            evento="CUENTA_SOCIO_VINCULADA_EXISTENTE",
            detalle="Se vinculó al socio una cuenta existente del Plan de Cuentas Empresa sin crear movimientos ni modificar el Plan Maestro.",
            valor_nuevo={
                "cuenta_empresa_id": cuenta_dict.get("id"),
                "codigo": cuenta_dict.get("codigo"),
                "nombre": cuenta_dict.get("nombre"),
            },
            motivo=motivo,
            usuario=usuario,
        )
        if propia:
            conn.commit()
        return {
            "ok": True,
            "vinculo_id": vinculo_id,
            "cuenta_empresa_id": int(cuenta_dict["id"]),
            "codigo": cuenta_dict.get("codigo"),
            "nombre": cuenta_dict.get("nombre"),
            "mensaje": "Cuenta existente vinculada correctamente al socio.",
        }
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def anular_vinculo_cuenta_socio(
    *,
    vinculo_id: int,
    empresa_id: int = 1,
    motivo: str,
    usuario: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if not _texto(motivo):
        return {"ok": False, "errores": ["Debe indicar un motivo para anular el vínculo de cuenta del socio."]}
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_socios_cuentas_especificas(conn)
        fila = conn.execute(
            """
            SELECT *
            FROM socios_cuentas_especificas
            WHERE id = ?
              AND empresa_id = ?
            LIMIT 1
            """,
            (int(vinculo_id), int(empresa_id)),
        ).fetchone()
        if not fila:
            return {"ok": False, "errores": ["No se encontró el vínculo de cuenta indicado."]}
        vinculo = _row_to_dict(fila)
        if _texto(vinculo.get("estado")).upper() == "ANULADA":
            return {"ok": True, "mensaje": "El vínculo ya estaba anulado.", "vinculo_id": int(vinculo_id)}

        conn.execute(
            """
            UPDATE socios_cuentas_especificas
               SET estado = 'ANULADA',
                   usuario_anulacion = ?,
                   fecha_anulacion = CURRENT_TIMESTAMP,
                   motivo_anulacion = ?,
                   usuario_actualizacion = ?,
                   fecha_actualizacion = CURRENT_TIMESTAMP
             WHERE id = ?
               AND empresa_id = ?
            """,
            (_texto(usuario), _texto(motivo), _texto(usuario), int(vinculo_id), int(empresa_id)),
        )
        _registrar_evento(
            conn,
            empresa_id=int(empresa_id),
            socio_id=int(vinculo.get("socio_id")),
            vinculo_id=int(vinculo_id),
            tipo_cuenta=_texto(vinculo.get("tipo_cuenta")),
            evento="CUENTA_SOCIO_VINCULO_ANULADO",
            detalle="Se anuló lógicamente el vínculo entre el socio y la cuenta específica. No se elimina la cuenta ni se modifican movimientos históricos.",
            valor_anterior=vinculo,
            valor_nuevo={"estado": "ANULADA"},
            motivo=motivo,
            usuario=usuario,
        )
        if propia:
            conn.commit()
        return {"ok": True, "mensaje": "Vínculo de cuenta del socio anulado correctamente.", "vinculo_id": int(vinculo_id)}
    except Exception as exc:
        if propia:
            conn.rollback()
        return {"ok": False, "errores": [str(exc)]}
    finally:
        if propia:
            conn.close()


def listar_eventos_cuentas_especificas_socios(
    empresa_id: int = 1,
    socio_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    propia = conn is None
    conn = conn or conectar()
    _asegurar_row_factory(conn)
    try:
        asegurar_estructura_socios_cuentas_especificas(conn)
        condiciones = ["empresa_id = ?"]
        params: list[Any] = [int(empresa_id)]
        if socio_id is not None:
            condiciones.append("socio_id = ?")
            params.append(int(socio_id))
        filas = conn.execute(
            f"""
            SELECT *
            FROM socios_cuentas_especificas_eventos
            WHERE {' AND '.join(condiciones)}
            ORDER BY fecha_evento DESC, id DESC
            LIMIT 300
            """,
            params,
        ).fetchall()
        return pd.DataFrame([_row_to_dict(f) for f in filas])
    finally:
        if propia:
            conn.close()