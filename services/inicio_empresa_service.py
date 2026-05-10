from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from database import conectar, ejecutar_query


TIPO_SUJETO_NO_DEFINIDO = "NO_DEFINIDO"
TIPO_SUJETO_PERSONA_HUMANA = "PERSONA_HUMANA"
TIPO_SUJETO_PERSONA_JURIDICA = "PERSONA_JURIDICA_SOCIEDAD"
TIPO_SUJETO_OTRO_ENTE = "OTRO_ENTE"

ESTADO_ONBOARDING_PENDIENTE = "PENDIENTE"
ESTADO_ONBOARDING_INCOMPLETO = "INCOMPLETO"
ESTADO_ONBOARDING_OPERATIVA_BASE = "OPERATIVA_BASE"

TABLA_DOCUMENTACION = "empresa_documentacion_respaldo"
TABLA_EVENTOS = "empresa_inicio_eventos"

TOLERANCIA = 0.01


def _resultado(ok: bool, mensaje: str, **extras) -> Dict[str, Any]:
    data = {"ok": bool(ok), "mensaje": str(mensaje)}
    data.update(extras)
    return data


def _texto(valor: Any, default: str = "") -> str:
    if valor is None:
        return default
    try:
        if pd.isna(valor):
            return default
    except Exception:
        pass
    return str(valor).strip()


def _texto_upper(valor: Any) -> str:
    return _texto(valor).upper()


def _numero(valor: Any, default: float = 0.0) -> float:
    try:
        if valor is None:
            return default
        if isinstance(valor, str) and valor.strip() == "":
            return default
        if pd.isna(valor):
            return default
        return round(float(valor), 2)
    except Exception:
        return default


def _normalizar_cuit(valor: Any) -> str:
    return "".join(ch for ch in _texto(valor) if ch.isdigit())


def _normalizar_fecha_opcional(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()

    texto = _texto(valor)
    if not texto:
        return ""

    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except Exception:
        return texto


def _normalizar_token(valor: Any) -> str:
    texto = _texto(valor).upper()
    reemplazos = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ñ": "N",
        "-": " ",
        "_": " ",
        "/": " ",
        ".": " ",
    }
    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)
    return " ".join(texto.split())


def normalizar_tipo_sujeto(valor: Any) -> str:
    texto = _normalizar_token(valor)

    if not texto:
        return TIPO_SUJETO_NO_DEFINIDO

    persona_humana = {
        "PERSONA HUMANA",
        "HUMANA",
        "FISICA",
        "PERSONA FISICA",
        "PF",
        "PH",
        "MONOTRIBUTISTA",
        "RESPONSABLE INSCRIPTO PERSONA HUMANA",
    }
    if texto in persona_humana:
        return TIPO_SUJETO_PERSONA_HUMANA

    if texto in {"OTRO", "OTRO ENTE", "ENTE", "FIDEICOMISO", "CONSORCIO", "SUCESION INDIVISA"}:
        return TIPO_SUJETO_OTRO_ENTE

    palabras_sociedad = {
        "SOCIEDAD",
        "JURIDICA",
        "PERSONA JURIDICA",
        "SA",
        "S A",
        "SRL",
        "S R L",
        "SAS",
        "S A S",
        "SOCIEDAD ANONIMA",
        "SOCIEDAD DE RESPONSABILIDAD LIMITADA",
        "SOCIEDAD POR ACCIONES SIMPLIFICADA",
        "ASOCIACION",
        "FUNDACION",
        "COOPERATIVA",
    }
    if texto in palabras_sociedad:
        return TIPO_SUJETO_PERSONA_JURIDICA

    if "SOCIEDAD" in texto or "JURIDICA" in texto:
        return TIPO_SUJETO_PERSONA_JURIDICA

    return TIPO_SUJETO_NO_DEFINIDO


def etiqueta_tipo_sujeto(tipo_sujeto: Any) -> str:
    tipo = normalizar_tipo_sujeto(tipo_sujeto)
    if tipo == TIPO_SUJETO_PERSONA_HUMANA:
        return "Persona humana"
    if tipo == TIPO_SUJETO_PERSONA_JURIDICA:
        return "Persona jurídica / sociedad"
    if tipo == TIPO_SUJETO_OTRO_ENTE:
        return "Otro ente"
    return "No definido"


def opciones_tipo_sujeto() -> List[Dict[str, str]]:
    return [
        {"codigo": TIPO_SUJETO_PERSONA_HUMANA, "nombre": "Persona humana"},
        {"codigo": TIPO_SUJETO_PERSONA_JURIDICA, "nombre": "Persona jurídica / sociedad"},
        {"codigo": TIPO_SUJETO_OTRO_ENTE, "nombre": "Otro ente"},
    ]


def _sql_migracion_inicio_empresa() -> str:
    ruta = Path(__file__).resolve().parents[1] / "migrations" / "023_inicio_empresa_tipo_sujeto.sql"
    if ruta.exists():
        return ruta.read_text(encoding="utf-8")
    return f"""
    CREATE TABLE IF NOT EXISTS {TABLA_DOCUMENTACION} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL,
        tipo_documento TEXT NOT NULL,
        referencia TEXT,
        descripcion TEXT,
        archivo_nombre TEXT,
        archivo_ruta TEXT,
        obligatorio INTEGER NOT NULL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'ACTIVO',
        usuario_creacion TEXT,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        usuario_anulacion TEXT,
        fecha_anulacion TIMESTAMP,
        motivo_anulacion TEXT
    );

    CREATE TABLE IF NOT EXISTS {TABLA_EVENTOS} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL,
        evento TEXT NOT NULL,
        detalle TEXT,
        usuario TEXT,
        fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """


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


def _asegurar_tabla_empresas_minima(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cuit TEXT,
            razon_social TEXT,
            domicilio TEXT,
            actividad TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def asegurar_estructura_inicio_empresa() -> None:
    conn = conectar()
    try:
        _asegurar_tabla_empresas_minima(conn)
        conn.executescript(_sql_migracion_inicio_empresa())

        _agregar_columna_si_no_existe(conn, "empresas", "tipo_sujeto", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "tipo_societario", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "fecha_inicio_actividades", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "fecha_inicio_contable", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "condicion_iva", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "condicion_ganancias", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "condicion_iibb", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "jurisdiccion_sede", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "marco_contable", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "estado_onboarding", "TEXT")
        _agregar_columna_si_no_existe(conn, "empresas", "fecha_actualizacion", "TIMESTAMP")

        conn.execute(
            """
            UPDATE empresas
            SET tipo_sujeto = ?
            WHERE COALESCE(TRIM(tipo_sujeto), '') = ''
            """,
            (TIPO_SUJETO_NO_DEFINIDO,),
        )
        conn.execute(
            """
            UPDATE empresas
            SET estado_onboarding = ?
            WHERE COALESCE(TRIM(estado_onboarding), '') = ''
            """,
            (ESTADO_ONBOARDING_PENDIENTE,),
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLA_DOCUMENTACION}_empresa_estado
            ON {TABLA_DOCUMENTACION} (empresa_id, estado)
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLA_EVENTOS}_empresa_fecha
            ON {TABLA_EVENTOS} (empresa_id, fecha_evento)
            """
        )

        conn.commit()
    finally:
        conn.close()


def _fila_a_dict(cursor, fila) -> Optional[Dict[str, Any]]:
    if not fila:
        return None
    columnas = [col[0] for col in cursor.description]
    return dict(zip(columnas, fila))


def _obtener_empresa_conn(conn, empresa_id: int) -> Optional[Dict[str, Any]]:
    if not _tabla_existe(conn, "empresas"):
        return None
    cur = conn.execute("SELECT * FROM empresas WHERE id = ? LIMIT 1", (int(empresa_id),))
    return _fila_a_dict(cur, cur.fetchone())


def obtener_empresa_inicio(empresa_id: int) -> Optional[Dict[str, Any]]:
    asegurar_estructura_inicio_empresa()
    conn = conectar()
    try:
        return _obtener_empresa_conn(conn, int(empresa_id))
    finally:
        conn.close()


def _registrar_evento_conn(conn, empresa_id: int, evento: str, detalle: str = "", usuario: Optional[str] = None) -> None:
    conn.execute(
        f"""
        INSERT INTO {TABLA_EVENTOS}
        (empresa_id, evento, detalle, usuario)
        VALUES (?, ?, ?, ?)
        """,
        (int(empresa_id), _texto(evento), _texto(detalle), usuario),
    )


def _datos_basicos_faltantes(empresa: Dict[str, Any]) -> List[str]:
    faltantes = []
    if not _texto(empresa.get("nombre")):
        faltantes.append("nombre interno")

    cuit = _normalizar_cuit(empresa.get("cuit"))
    if not cuit:
        faltantes.append("CUIT")
    elif len(cuit) != 11:
        faltantes.append("CUIT válido de 11 dígitos")

    if not _texto(empresa.get("razon_social")):
        faltantes.append("razón social")
    if not _texto(empresa.get("domicilio")):
        faltantes.append("domicilio")
    if not _texto(empresa.get("actividad")):
        faltantes.append("actividad")
    return faltantes


def _capital_societario_estado(empresa_id: int) -> Dict[str, Any]:
    conn = conectar()
    try:
        tiene_capital = False
        cantidad_capitales = 0
        cantidad_socios = 0
        total_pendiente = 0.0

        if _tabla_existe(conn, "capital_social_empresa"):
            fila = conn.execute(
                """
                SELECT COUNT(*) AS cantidad,
                       ROUND(COALESCE(SUM(total_pendiente_integracion), 0), 2) AS pendiente
                FROM capital_social_empresa
                WHERE empresa_id = ?
                  AND estado <> 'ANULADO'
                """,
                (int(empresa_id),),
            ).fetchone()
            cantidad_capitales = int((fila[0] if fila else 0) or 0)
            total_pendiente = _numero(fila[1] if fila else 0)
            tiene_capital = cantidad_capitales > 0

        if _tabla_existe(conn, "socios_empresa"):
            fila = conn.execute(
                """
                SELECT COUNT(*) AS cantidad
                FROM socios_empresa
                WHERE empresa_id = ?
                  AND estado = 'ACTIVO'
                """,
                (int(empresa_id),),
            ).fetchone()
            cantidad_socios = int((fila[0] if fila else 0) or 0)

        return {
            "tiene_capital_social": tiene_capital,
            "cantidad_capitales": cantidad_capitales,
            "tiene_socios": cantidad_socios > 0,
            "cantidad_socios": cantidad_socios,
            "total_pendiente_integracion": total_pendiente,
        }
    finally:
        conn.close()


def obtener_perfil_inicio_empresa(empresa_id: int) -> Dict[str, Any]:
    asegurar_estructura_inicio_empresa()
    empresa = obtener_empresa_inicio(int(empresa_id))
    if not empresa:
        return _resultado(False, "La empresa no existe.")

    tipo_sujeto = normalizar_tipo_sujeto(empresa.get("tipo_sujeto"))
    es_persona_humana = tipo_sujeto == TIPO_SUJETO_PERSONA_HUMANA
    es_sociedad = tipo_sujeto == TIPO_SUJETO_PERSONA_JURIDICA
    es_otro_ente = tipo_sujeto == TIPO_SUJETO_OTRO_ENTE

    campos_no_aplican = []
    if es_persona_humana:
        campos_no_aplican = [
            "socios",
            "porcentajes societarios",
            "capital social",
            "capital suscripto",
            "integración de capital",
            "cuenta particular de socios",
        ]

    return _resultado(
        True,
        "Perfil de inicio obtenido.",
        empresa_id=int(empresa_id),
        empresa=empresa,
        tipo_sujeto=tipo_sujeto,
        tipo_sujeto_etiqueta=etiqueta_tipo_sujeto(tipo_sujeto),
        es_persona_humana=es_persona_humana,
        es_sociedad=es_sociedad,
        es_otro_ente=es_otro_ente,
        requiere_inicio_societario=es_sociedad,
        requiere_socios=es_sociedad,
        requiere_capital_social=es_sociedad,
        usa_titular=es_persona_humana,
        documentacion_obligatoria=False,
        documentacion_opcional=True,
        campos_no_aplican=campos_no_aplican,
    )


def _requisito(codigo: str, nombre: str, ok: bool, detalle: str = "", bloqueante: bool = True, recomendado: bool = False) -> Dict[str, Any]:
    return {
        "codigo": codigo,
        "nombre": nombre,
        "ok": bool(ok),
        "estado": "OK" if ok else ("PENDIENTE_RECOMENDADO" if recomendado else "FALTA"),
        "detalle": detalle,
        "bloqueante": bool(bloqueante),
        "recomendado": bool(recomendado),
    }


def obtener_requisitos_inicio_empresa(empresa_id: int) -> List[Dict[str, Any]]:
    perfil = obtener_perfil_inicio_empresa(int(empresa_id))
    if not perfil.get("ok"):
        return [
            _requisito(
                "EMPRESA_EXISTE",
                "Empresa existente",
                False,
                perfil.get("mensaje", "La empresa no existe."),
                bloqueante=True,
            )
        ]

    empresa = perfil["empresa"]
    tipo_sujeto = perfil["tipo_sujeto"]
    requisitos: List[Dict[str, Any]] = []

    faltantes_basicos = _datos_basicos_faltantes(empresa)
    requisitos.append(
        _requisito(
            "DATOS_BASICOS",
            "Datos mínimos de empresa",
            not faltantes_basicos,
            "Completo." if not faltantes_basicos else "Faltan: " + ", ".join(faltantes_basicos) + ".",
            bloqueante=True,
        )
    )

    requisitos.append(
        _requisito(
            "TIPO_SUJETO",
            "Tipo de sujeto",
            tipo_sujeto != TIPO_SUJETO_NO_DEFINIDO,
            "Definido como " + etiqueta_tipo_sujeto(tipo_sujeto) + "."
            if tipo_sujeto != TIPO_SUJETO_NO_DEFINIDO
            else "Debe indicar si es Persona humana, Sociedad/persona jurídica u Otro ente.",
            bloqueante=True,
        )
    )

    if tipo_sujeto == TIPO_SUJETO_PERSONA_HUMANA:
        requisitos.append(
            _requisito(
                "INICIO_PERSONA_HUMANA",
                "Inicio simplificado de persona humana",
                True,
                "No corresponde exigir socios, capital social, suscripción ni integración.",
                bloqueante=True,
            )
        )

    if tipo_sujeto == TIPO_SUJETO_PERSONA_JURIDICA:
        tipo_societario = _texto(empresa.get("tipo_societario"))
        requisitos.append(
            _requisito(
                "TIPO_SOCIETARIO",
                "Tipo societario",
                bool(tipo_societario),
                "Tipo societario informado."
                if tipo_societario
                else "Debe informar tipo societario o forma jurídica.",
                bloqueante=True,
            )
        )

        capital = _capital_societario_estado(int(empresa_id))
        requisitos.append(
            _requisito(
                "SOCIOS",
                "Socios / accionistas",
                bool(capital.get("tiene_socios")),
                f"Socios activos: {capital.get('cantidad_socios', 0)}."
                if capital.get("tiene_socios")
                else "Debe cargar socios/accionistas para el inicio societario.",
                bloqueante=True,
            )
        )
        requisitos.append(
            _requisito(
                "CAPITAL_SOCIAL",
                "Capital social",
                bool(capital.get("tiene_capital_social")),
                "Capital social cargado."
                if capital.get("tiene_capital_social")
                else "Debe cargar capital suscripto para el inicio societario.",
                bloqueante=True,
            )
        )

        if capital.get("tiene_capital_social") and _numero(capital.get("total_pendiente_integracion")) > TOLERANCIA:
            requisitos.append(
                _requisito(
                    "INTEGRACION_PENDIENTE",
                    "Integración pendiente",
                    True,
                    f"Hay integración pendiente por {capital.get('total_pendiente_integracion'):.2f}. No bloquea: debe controlarse por socio y movimiento real.",
                    bloqueante=False,
                    recomendado=True,
                )
            )

    docs = documentacion_respaldo_listar(int(empresa_id))
    requisitos.append(
        _requisito(
            "DOCUMENTACION_RESPALDO",
            "Documentación respaldatoria",
            True,
            "Documentación cargada."
            if not docs.empty
            else "Opcional/recomendada. No bloquea el alta ni el inicio operativo básico.",
            bloqueante=False,
            recomendado=True,
        )
    )

    return requisitos


def obtener_estado_onboarding_empresa(empresa_id: int) -> Dict[str, Any]:
    asegurar_estructura_inicio_empresa()
    empresa = obtener_empresa_inicio(int(empresa_id))
    if not empresa:
        return _resultado(False, "La empresa no existe.", estado=ESTADO_ONBOARDING_PENDIENTE, faltantes=[])

    requisitos = obtener_requisitos_inicio_empresa(int(empresa_id))
    faltantes_bloqueantes = [
        req for req in requisitos
        if req.get("bloqueante") and not req.get("ok")
    ]
    recomendaciones = [
        req for req in requisitos
        if req.get("recomendado") and not req.get("ok")
    ]

    tipo_sujeto = normalizar_tipo_sujeto(empresa.get("tipo_sujeto"))
    if tipo_sujeto == TIPO_SUJETO_NO_DEFINIDO:
        estado = ESTADO_ONBOARDING_PENDIENTE
    elif faltantes_bloqueantes:
        estado = ESTADO_ONBOARDING_INCOMPLETO
    else:
        estado = ESTADO_ONBOARDING_OPERATIVA_BASE

    return _resultado(
        len(faltantes_bloqueantes) == 0,
        "Inicio de empresa completo para operación base."
        if len(faltantes_bloqueantes) == 0
        else "El inicio de empresa tiene faltantes bloqueantes.",
        empresa_id=int(empresa_id),
        estado=estado,
        tipo_sujeto=tipo_sujeto,
        tipo_sujeto_etiqueta=etiqueta_tipo_sujeto(tipo_sujeto),
        requisitos=requisitos,
        faltantes=[req["codigo"] for req in faltantes_bloqueantes],
        faltantes_detalle=faltantes_bloqueantes,
        recomendaciones=recomendaciones,
        documentacion_obligatoria=False,
    )


def _actualizar_estado_onboarding_persistido(empresa_id: int, estado: str) -> None:
    conn = conectar()
    try:
        if _tabla_existe(conn, "empresas") and "estado_onboarding" in _columnas_tabla(conn, "empresas"):
            conn.execute(
                """
                UPDATE empresas
                SET estado_onboarding = ?,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (_texto(estado) or ESTADO_ONBOARDING_PENDIENTE, int(empresa_id)),
            )
            conn.commit()
    finally:
        conn.close()


def actualizar_inicio_empresa(
    empresa_id: int,
    tipo_sujeto: Optional[str] = None,
    tipo_societario: Optional[str] = None,
    fecha_inicio_actividades: Optional[Any] = None,
    fecha_inicio_contable: Optional[Any] = None,
    condicion_iva: Optional[str] = None,
    condicion_ganancias: Optional[str] = None,
    condicion_iibb: Optional[str] = None,
    jurisdiccion_sede: Optional[str] = None,
    marco_contable: Optional[str] = None,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    asegurar_estructura_inicio_empresa()

    conn = conectar()
    try:
        empresa = _obtener_empresa_conn(conn, int(empresa_id))
        if not empresa:
            return _resultado(False, "La empresa no existe.")

        campos = {}

        if tipo_sujeto is not None:
            campos["tipo_sujeto"] = normalizar_tipo_sujeto(tipo_sujeto)
        if tipo_societario is not None:
            campos["tipo_societario"] = _texto(tipo_societario)
        if fecha_inicio_actividades is not None:
            campos["fecha_inicio_actividades"] = _normalizar_fecha_opcional(fecha_inicio_actividades)
        if fecha_inicio_contable is not None:
            campos["fecha_inicio_contable"] = _normalizar_fecha_opcional(fecha_inicio_contable)
        if condicion_iva is not None:
            campos["condicion_iva"] = _texto(condicion_iva)
        if condicion_ganancias is not None:
            campos["condicion_ganancias"] = _texto(condicion_ganancias)
        if condicion_iibb is not None:
            campos["condicion_iibb"] = _texto(condicion_iibb)
        if jurisdiccion_sede is not None:
            campos["jurisdiccion_sede"] = _texto(jurisdiccion_sede)
        if marco_contable is not None:
            campos["marco_contable"] = _texto(marco_contable)

        if campos:
            campos["fecha_actualizacion"] = "CURRENT_TIMESTAMP"
            set_partes = []
            valores: List[Any] = []
            for campo, valor in campos.items():
                if campo == "fecha_actualizacion":
                    set_partes.append("fecha_actualizacion = CURRENT_TIMESTAMP")
                else:
                    set_partes.append(f"{campo} = ?")
                    valores.append(valor)
            valores.append(int(empresa_id))
            conn.execute(
                f"""
                UPDATE empresas
                SET {', '.join(set_partes)}
                WHERE id = ?
                """,
                tuple(valores),
            )
            _registrar_evento_conn(
                conn,
                int(empresa_id),
                "ACTUALIZACION_INICIO_EMPRESA",
                "Actualización de datos de inicio de empresa.",
                usuario,
            )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo actualizar el inicio de empresa: {exc}")
    finally:
        conn.close()

    estado = obtener_estado_onboarding_empresa(int(empresa_id))
    _actualizar_estado_onboarding_persistido(int(empresa_id), estado.get("estado", ESTADO_ONBOARDING_PENDIENTE))

    return _resultado(
        True,
        "Inicio de empresa actualizado correctamente.",
        empresa_id=int(empresa_id),
        estado_onboarding=estado.get("estado"),
        perfil=obtener_perfil_inicio_empresa(int(empresa_id)),
        estado=estado,
    )


def documentacion_respaldo_listar(empresa_id: int, incluir_anulada: bool = False) -> pd.DataFrame:
    asegurar_estructura_inicio_empresa()
    where_estado = "" if incluir_anulada else "AND estado = 'ACTIVO'"
    return ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_DOCUMENTACION}
        WHERE empresa_id = ?
        {where_estado}
        ORDER BY fecha_creacion DESC, id DESC
        """,
        (int(empresa_id),),
        fetch=True,
    )


def documentacion_respaldo_registrar(
    empresa_id: int,
    tipo_documento: str,
    referencia: Optional[str] = None,
    descripcion: Optional[str] = None,
    archivo_nombre: Optional[str] = None,
    archivo_ruta: Optional[str] = None,
    obligatorio: bool = False,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    asegurar_estructura_inicio_empresa()

    tipo_limpio = _texto(tipo_documento)
    if not tipo_limpio:
        return _resultado(False, "Debe indicar el tipo de documentación o respaldo.")

    conn = conectar()
    try:
        empresa = _obtener_empresa_conn(conn, int(empresa_id))
        if not empresa:
            return _resultado(False, "La empresa no existe.")

        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO {TABLA_DOCUMENTACION}
            (empresa_id, tipo_documento, referencia, descripcion, archivo_nombre, archivo_ruta,
             obligatorio, estado, usuario_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVO', ?)
            """,
            (
                int(empresa_id),
                tipo_limpio,
                _texto(referencia),
                _texto(descripcion),
                _texto(archivo_nombre),
                _texto(archivo_ruta),
                1 if obligatorio else 0,
                usuario,
            ),
        )
        doc_id = int(cur.lastrowid)
        _registrar_evento_conn(
            conn,
            int(empresa_id),
            "DOCUMENTACION_RESPALDO_REGISTRADA",
            f"Documentación opcional registrada: {tipo_limpio}.",
            usuario,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo registrar la documentación respaldatoria: {exc}")
    finally:
        conn.close()

    estado = obtener_estado_onboarding_empresa(int(empresa_id))
    _actualizar_estado_onboarding_persistido(int(empresa_id), estado.get("estado", ESTADO_ONBOARDING_PENDIENTE))

    return _resultado(
        True,
        "Documentación respaldatoria registrada correctamente. Es opcional y no bloquea el inicio operativo básico.",
        documentacion_id=doc_id,
        estado=estado,
    )


def documentacion_respaldo_anular(
    documentacion_id: int,
    motivo: str,
    usuario: Optional[str] = None,
) -> Dict[str, Any]:
    asegurar_estructura_inicio_empresa()
    motivo_limpio = _texto(motivo)
    if not motivo_limpio:
        return _resultado(False, "Para anular documentación se requiere motivo.")

    conn = conectar()
    try:
        cur = conn.execute(
            f"SELECT * FROM {TABLA_DOCUMENTACION} WHERE id = ? LIMIT 1",
            (int(documentacion_id),),
        )
        doc = _fila_a_dict(cur, cur.fetchone())
        if not doc:
            return _resultado(False, "No se encontró la documentación.")
        if _texto_upper(doc.get("estado")) == "ANULADO":
            return _resultado(False, "La documentación ya está anulada.")

        conn.execute(
            f"""
            UPDATE {TABLA_DOCUMENTACION}
            SET estado = 'ANULADO',
                usuario_anulacion = ?,
                fecha_anulacion = CURRENT_TIMESTAMP,
                motivo_anulacion = ?
            WHERE id = ?
            """,
            (usuario, motivo_limpio, int(documentacion_id)),
        )
        _registrar_evento_conn(
            conn,
            int(doc.get("empresa_id")),
            "DOCUMENTACION_RESPALDO_ANULADA",
            f"Documentación {documentacion_id} anulada. Motivo: {motivo_limpio}",
            usuario,
        )
        conn.commit()
        return _resultado(True, "Documentación anulada correctamente.", empresa_id=int(doc.get("empresa_id")))
    except Exception as exc:
        conn.rollback()
        return _resultado(False, f"No se pudo anular la documentación: {exc}")
    finally:
        conn.close()


def listar_eventos_inicio_empresa(empresa_id: int, limite: int = 100) -> pd.DataFrame:
    asegurar_estructura_inicio_empresa()
    return ejecutar_query(
        f"""
        SELECT *
        FROM {TABLA_EVENTOS}
        WHERE empresa_id = ?
        ORDER BY fecha_evento DESC, id DESC
        LIMIT ?
        """,
        (int(empresa_id), max(1, int(limite or 100))),
        fetch=True,
    )


__all__ = [
    "TIPO_SUJETO_NO_DEFINIDO",
    "TIPO_SUJETO_PERSONA_HUMANA",
    "TIPO_SUJETO_PERSONA_JURIDICA",
    "TIPO_SUJETO_OTRO_ENTE",
    "ESTADO_ONBOARDING_PENDIENTE",
    "ESTADO_ONBOARDING_INCOMPLETO",
    "ESTADO_ONBOARDING_OPERATIVA_BASE",
    "asegurar_estructura_inicio_empresa",
    "normalizar_tipo_sujeto",
    "etiqueta_tipo_sujeto",
    "opciones_tipo_sujeto",
    "obtener_empresa_inicio",
    "obtener_perfil_inicio_empresa",
    "actualizar_inicio_empresa",
    "obtener_requisitos_inicio_empresa",
    "obtener_estado_onboarding_empresa",
    "documentacion_respaldo_listar",
    "documentacion_respaldo_registrar",
    "documentacion_respaldo_anular",
    "listar_eventos_inicio_empresa",
]