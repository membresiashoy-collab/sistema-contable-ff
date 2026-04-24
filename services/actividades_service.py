from io import BytesIO
import unicodedata

import pandas as pd

from database import ejecutar_query


# ======================================================
# TABLAS
# ======================================================

def asegurar_tablas_actividades():
    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS actividades_economicas (
            codigo TEXT PRIMARY KEY,
            descripcion TEXT,
            descripcion_larga TEXT,
            activo INTEGER DEFAULT 1,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    ejecutar_query("""
        CREATE TABLE IF NOT EXISTS empresa_actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            codigo_actividad TEXT NOT NULL,
            principal INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(empresa_id, codigo_actividad)
        )
    """)


# ======================================================
# UTILIDADES
# ======================================================

def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def normalizar_columna(nombre):
    nombre = quitar_acentos(nombre)
    nombre = nombre.upper().strip()
    nombre = nombre.replace(".", "")
    nombre = nombre.replace("-", "_")
    nombre = nombre.replace("/", "_")
    nombre = nombre.replace(" ", "_")

    while "__" in nombre:
        nombre = nombre.replace("__", "_")

    return nombre


def limpiar_texto(valor):
    try:
        if pd.isna(valor):
            return ""
        texto = str(valor).strip()
        texto = texto.replace("\t", " ")
        while "  " in texto:
            texto = texto.replace("  ", " ")
        return texto
    except Exception:
        return ""


def limpiar_codigo(valor):
    codigo = limpiar_texto(valor)

    if codigo.endswith(".0"):
        codigo = codigo[:-2]

    codigo = "".join([c for c in codigo if c.isdigit()])

    if codigo == "":
        return ""

    return codigo.zfill(6)


def contar_actividades():
    asegurar_tablas_actividades()

    df = ejecutar_query("""
        SELECT COUNT(*) AS cantidad
        FROM actividades_economicas
    """, fetch=True)

    if df.empty:
        return 0

    return int(df.iloc[0]["cantidad"])


# ======================================================
# LECTURA DEL TXT ARCA
# ======================================================

def leer_nomenclador_actividades(archivo):
    """
    Lee el TXT/CSV del nomenclador de actividades económicas ARCA F.883.

    Formato esperado:
    COD_ACTIVIDAD_F883;DESC_ACTIVIDAD_F883;DESCL_ACTIVIDA_F883;
    """

    if hasattr(archivo, "getvalue"):
        contenido = archivo.getvalue()
    elif hasattr(archivo, "read"):
        contenido = archivo.read()
    else:
        with open(archivo, "rb") as f:
            contenido = f.read()

    errores = []

    for encoding in ["utf-8-sig", "latin-1"]:
        try:
            df = pd.read_csv(
                BytesIO(contenido),
                sep=";",
                engine="python",
                encoding=encoding,
                dtype=str
            )
            break
        except Exception as e:
            errores.append(str(e))
            df = None

    if df is None:
        raise ValueError("No se pudo leer el archivo. Errores: " + " | ".join(errores))

    df = df.drop(columns=[c for c in df.columns if str(c).lower().startswith("unnamed")], errors="ignore")
    df.columns = [normalizar_columna(c) for c in df.columns]

    renombres = {}

    for col in df.columns:
        if col.startswith("COD_ACTIVIDAD"):
            renombres[col] = "codigo"

        elif col.startswith("DESC_ACTIVIDAD"):
            renombres[col] = "descripcion"

        elif col.startswith("DESCL_ACTIVIDA") or col.startswith("DESCRIPCION_LARGA"):
            renombres[col] = "descripcion_larga"

    df = df.rename(columns=renombres)

    if "codigo" not in df.columns:
        raise ValueError("El archivo no tiene columna de código de actividad.")

    if "descripcion" not in df.columns:
        df["descripcion"] = ""

    if "descripcion_larga" not in df.columns:
        df["descripcion_larga"] = df["descripcion"]

    df["codigo"] = df["codigo"].apply(limpiar_codigo)
    df["descripcion"] = df["descripcion"].apply(limpiar_texto)
    df["descripcion_larga"] = df["descripcion_larga"].apply(limpiar_texto)

    df = df[df["codigo"] != ""].copy()
    df = df.drop_duplicates(subset=["codigo"], keep="last")

    df = df[["codigo", "descripcion", "descripcion_larga"]]
    df = df.sort_values(by="codigo")

    return df


# ======================================================
# CARGA / CONSULTA
# ======================================================

def cargar_nomenclador_actividades(df, reemplazar=False):
    asegurar_tablas_actividades()

    if reemplazar:
        ejecutar_query("DELETE FROM empresa_actividades")
        ejecutar_query("DELETE FROM actividades_economicas")

    antes = contar_actividades()

    procesadas = 0

    for _, fila in df.iterrows():
        codigo = limpiar_codigo(fila.get("codigo", ""))
        descripcion = limpiar_texto(fila.get("descripcion", ""))
        descripcion_larga = limpiar_texto(fila.get("descripcion_larga", ""))

        if codigo == "":
            continue

        ejecutar_query("""
            INSERT OR REPLACE INTO actividades_economicas
            (codigo, descripcion, descripcion_larga, activo)
            VALUES (?, ?, ?, 1)
        """, (codigo, descripcion, descripcion_larga))

        procesadas += 1

    despues = contar_actividades()

    return {
        "procesadas": procesadas,
        "insertadas_o_actualizadas": procesadas,
        "total_antes": antes,
        "total_despues": despues
    }


def buscar_actividades(filtro="", limite=300):
    asegurar_tablas_actividades()

    filtro = limpiar_texto(filtro)

    if filtro == "":
        return ejecutar_query("""
            SELECT codigo, descripcion, descripcion_larga, activo
            FROM actividades_economicas
            WHERE activo = 1
            ORDER BY codigo
            LIMIT ?
        """, (int(limite),), fetch=True)

    patron = f"%{filtro.upper()}%"

    return ejecutar_query("""
        SELECT codigo, descripcion, descripcion_larga, activo
        FROM actividades_economicas
        WHERE activo = 1
          AND (
                UPPER(codigo) LIKE ?
             OR UPPER(descripcion) LIKE ?
             OR UPPER(descripcion_larga) LIKE ?
          )
        ORDER BY codigo
        LIMIT ?
    """, (patron, patron, patron, int(limite)), fetch=True)


def obtener_actividad(codigo):
    asegurar_tablas_actividades()

    codigo = limpiar_codigo(codigo)

    df = ejecutar_query("""
        SELECT codigo, descripcion, descripcion_larga, activo
        FROM actividades_economicas
        WHERE codigo = ?
    """, (codigo,), fetch=True)

    if df.empty:
        return None

    fila = df.iloc[0]

    return {
        "codigo": str(fila["codigo"]),
        "descripcion": str(fila["descripcion"]),
        "descripcion_larga": str(fila["descripcion_larga"]),
        "activo": int(fila["activo"])
    }


def obtener_empresas_para_actividades():
    asegurar_tablas_actividades()

    return ejecutar_query("""
        SELECT id, nombre, cuit, razon_social, actividad
        FROM empresas
        WHERE activo = 1
        ORDER BY nombre
    """, fetch=True)


def obtener_actividades_empresa(empresa_id):
    asegurar_tablas_actividades()

    return ejecutar_query("""
        SELECT 
            ea.id,
            ea.empresa_id,
            ea.codigo_actividad,
            ae.descripcion,
            ae.descripcion_larga,
            ea.principal,
            ea.activo
        FROM empresa_actividades ea
        INNER JOIN actividades_economicas ae 
                ON ae.codigo = ea.codigo_actividad
        WHERE ea.empresa_id = ?
          AND ea.activo = 1
        ORDER BY ea.principal DESC, ea.codigo_actividad
    """, (int(empresa_id),), fetch=True)


def asignar_actividad_empresa(empresa_id, codigo_actividad, principal=False):
    asegurar_tablas_actividades()

    empresa_id = int(empresa_id)
    codigo_actividad = limpiar_codigo(codigo_actividad)

    actividad = obtener_actividad(codigo_actividad)

    if actividad is None:
        return {
            "ok": False,
            "mensaje": "La actividad seleccionada no existe en el nomenclador."
        }

    if principal:
        ejecutar_query("""
            UPDATE empresa_actividades
            SET principal = 0
            WHERE empresa_id = ?
        """, (empresa_id,))

    ejecutar_query("""
        INSERT INTO empresa_actividades
        (empresa_id, codigo_actividad, principal, activo)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(empresa_id, codigo_actividad)
        DO UPDATE SET
            principal = excluded.principal,
            activo = 1
    """, (empresa_id, codigo_actividad, 1 if principal else 0))

    if principal:
        texto_actividad = f"{actividad['codigo']} - {actividad['descripcion']}"

        ejecutar_query("""
            UPDATE empresas
            SET actividad = ?
            WHERE id = ?
        """, (texto_actividad, empresa_id))

    return {
        "ok": True,
        "mensaje": "Actividad asignada correctamente."
    }


def marcar_actividad_principal(empresa_id, codigo_actividad):
    asegurar_tablas_actividades()

    empresa_id = int(empresa_id)
    codigo_actividad = limpiar_codigo(codigo_actividad)

    actividad = obtener_actividad(codigo_actividad)

    if actividad is None:
        return {
            "ok": False,
            "mensaje": "La actividad no existe."
        }

    ejecutar_query("""
        UPDATE empresa_actividades
        SET principal = 0
        WHERE empresa_id = ?
    """, (empresa_id,))

    ejecutar_query("""
        UPDATE empresa_actividades
        SET principal = 1
        WHERE empresa_id = ?
          AND codigo_actividad = ?
          AND activo = 1
    """, (empresa_id, codigo_actividad))

    texto_actividad = f"{actividad['codigo']} - {actividad['descripcion']}"

    ejecutar_query("""
        UPDATE empresas
        SET actividad = ?
        WHERE id = ?
    """, (texto_actividad, empresa_id))

    return {
        "ok": True,
        "mensaje": "Actividad principal actualizada."
    }


def quitar_actividad_empresa(empresa_id, codigo_actividad):
    asegurar_tablas_actividades()

    ejecutar_query("""
        UPDATE empresa_actividades
        SET activo = 0
        WHERE empresa_id = ?
          AND codigo_actividad = ?
    """, (int(empresa_id), limpiar_codigo(codigo_actividad)))

    return {
        "ok": True,
        "mensaje": "Actividad quitada de la empresa."
    }