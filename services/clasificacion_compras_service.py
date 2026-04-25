import re
import unicodedata

import pandas as pd

from database import ejecutar_query
from core.numeros import limpiar_numero


# ======================================================
# NORMALIZACIÓN
# ======================================================

def quitar_acentos(texto):
    texto = str(texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def normalizar_nombre_columna(nombre):
    nombre = quitar_acentos(nombre)
    nombre = nombre.lower().strip()
    nombre = nombre.replace(".", "")
    nombre = nombre.replace("-", "_")
    nombre = nombre.replace("/", "_")
    nombre = nombre.replace("%", "")
    nombre = nombre.replace(",", "")
    nombre = nombre.replace(" ", "_")

    while "__" in nombre:
        nombre = nombre.replace("__", "_")

    return nombre


def normalizar_df_columnas(df):
    df_normalizado = df.copy()
    df_normalizado.columns = [normalizar_nombre_columna(c) for c in df_normalizado.columns]
    return df_normalizado


def valor_fila(fila, columna, default=""):
    try:
        if columna in fila.index:
            valor = fila[columna]

            if pd.isna(valor):
                return default

            return valor

        return default
    except Exception:
        return default


def normalizar_entero_texto(valor_original):
    texto = str(valor_original).strip()

    if texto.lower() in ("nan", "none"):
        return ""

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = texto.replace(" ", "")
    texto = texto.replace(",", "")
    texto = texto.replace(".", "")
    texto = texto.replace("-", "")
    texto = texto.replace("/", "")

    return texto


def normalizar_codigo(valor_original):
    texto = normalizar_entero_texto(valor_original)
    texto = texto.lstrip("0")

    if texto == "":
        return ""

    return texto


def normalizar_punto_venta(valor_original):
    texto = normalizar_entero_texto(valor_original)

    if texto == "":
        return ""

    return texto.zfill(5)


def normalizar_numero_comprobante(valor_original):
    texto = normalizar_entero_texto(valor_original)

    if texto == "":
        return ""

    return texto.zfill(8)


def normalizar_cuit(valor_original):
    return normalizar_entero_texto(valor_original)


def clave_proveedor(cuit, proveedor):
    cuit = str(cuit).strip()
    proveedor = str(proveedor).strip().upper()

    if cuit:
        return cuit

    return proveedor


def key_segura(texto):
    texto = str(texto)
    texto = re.sub(r"[^A-Za-z0-9_]+", "_", texto)
    texto = texto.strip("_")

    if texto == "":
        texto = "SIN_KEY"

    return texto


def sanitizar_nombre_archivo(texto):
    texto = str(texto).strip().upper()
    texto = re.sub(r"[^A-Z0-9]+", "_", texto)
    texto = texto.strip("_")

    if texto == "":
        texto = "SIN_CATEGORIA"

    return texto


def nombre_archivo_interno(nombre_archivo, categoria):
    return f"{nombre_archivo}__{sanitizar_nombre_archivo(categoria)}"


# ======================================================
# HISTORIAL / APRENDIZAJE
# ======================================================

def obtener_proveedores_configurados():
    try:
        return ejecutar_query("""
            SELECT 
                cuit,
                proveedor,
                categoria_habitual,
                observacion
            FROM proveedores_configuracion
            WHERE activo = 1
        """, fetch=True)
    except Exception:
        return pd.DataFrame(columns=["cuit", "proveedor", "categoria_habitual", "observacion"])


def obtener_historial_categorias_compras():
    try:
        return ejecutar_query("""
            SELECT
                cuit,
                proveedor,
                categoria_compra,
                COUNT(*) AS veces_usada,
                MAX(fecha_carga) AS ultima_vez,
                SUM(ABS(total)) AS importe_total
            FROM compras_comprobantes
            WHERE COALESCE(cuit, '') <> ''
              AND COALESCE(categoria_compra, '') <> ''
            GROUP BY cuit, proveedor, categoria_compra
            ORDER BY cuit, veces_usada DESC
        """, fetch=True)
    except Exception:
        return pd.DataFrame(columns=[
            "cuit",
            "proveedor",
            "categoria_compra",
            "veces_usada",
            "ultima_vez",
            "importe_total"
        ])


def es_configuracion_automatica(observacion):
    texto = quitar_acentos(str(observacion or "")).upper()

    patrones_automaticos = [
        "CATEGORIA HABITUAL DETECTADA DESDE CARGA DE COMPRAS",
        "CATEGORIA DETECTADA DESDE CARGA DE COMPRAS",
        "DETECTADA DESDE CARGA DE COMPRAS"
    ]

    return any(p in texto for p in patrones_automaticos)


def construir_mapa_sugerencias(categorias_disponibles):
    """
    Orden de sugerencia:
    1) compras_comprobantes cargadas y vigentes.
       Esto es lo más seguro, porque si una carga se elimina, el historial se recalcula.
    2) proveedores_configuracion solo si parece configuración manual.
       Se ignoran configuraciones automáticas viejas para evitar arrastrar errores.
    3) categoría default.
    """

    historial = obtener_historial_categorias_compras()
    configurados = obtener_proveedores_configurados()

    mapa = {}

    if not historial.empty:
        for cuit, grupo in historial.groupby("cuit"):
            grupo = grupo.copy()
            grupo["veces_usada"] = pd.to_numeric(grupo["veces_usada"], errors="coerce").fillna(0)
            grupo = grupo.sort_values(by="veces_usada", ascending=False)

            total_usos = int(grupo["veces_usada"].sum())
            categoria_top = str(grupo.iloc[0]["categoria_compra"]).strip()
            veces_top = int(grupo.iloc[0]["veces_usada"])
            ultima_vez = str(grupo.iloc[0].get("ultima_vez", "") or "")

            categorias_distintas = grupo["categoria_compra"].dropna().astype(str).unique().tolist()
            categorias_historicas = ", ".join(categorias_distintas)

            if categoria_top not in categorias_disponibles:
                continue

            if len(categorias_distintas) == 1:
                confianza = "ALTA"
                origen = "HISTORIAL"
            elif veces_top / max(total_usos, 1) >= 0.70:
                confianza = "MEDIA"
                origen = "HISTORIAL MIXTO"
            else:
                confianza = "BAJA"
                origen = "HISTORIAL MIXTO"

            mapa[str(cuit)] = {
                "categoria": categoria_top,
                "origen": origen,
                "confianza": confianza,
                "veces_usada": veces_top,
                "ultima_vez": ultima_vez,
                "categorias_historicas": categorias_historicas
            }

    if not configurados.empty:
        for _, fila in configurados.iterrows():
            observacion = fila.get("observacion", "")

            if es_configuracion_automatica(observacion):
                continue

            cuit = normalizar_cuit(fila.get("cuit", ""))
            proveedor = str(fila.get("proveedor", "")).strip()
            categoria = str(fila.get("categoria_habitual", "")).strip()

            clave = clave_proveedor(cuit, proveedor)

            if clave and clave not in mapa and categoria in categorias_disponibles:
                mapa[clave] = {
                    "categoria": categoria,
                    "origen": "CONFIGURACION MANUAL",
                    "confianza": "MEDIA",
                    "veces_usada": 0,
                    "ultima_vez": "",
                    "categorias_historicas": categoria
                }

    return mapa


# ======================================================
# CLASIFICACIÓN
# ======================================================

def obtener_categoria_default(categorias_disponibles):
    prioridades = [
        "OTROS GASTOS A REVISAR",
        "SERVICIOS CONTRATADOS",
        "INSUMOS VARIOS",
        "SERVICIOS"
    ]

    for categoria in prioridades:
        if categoria in categorias_disponibles:
            return categoria

    if categorias_disponibles:
        return categorias_disponibles[0]

    return ""


def construir_detalle_preclasificacion(df_original, df_categorias):
    df_norm = normalizar_df_columnas(df_original)

    categorias_disponibles = df_categorias["categoria"].tolist()
    categoria_default = obtener_categoria_default(categorias_disponibles)
    mapa_sugerencias = construir_mapa_sugerencias(categorias_disponibles)

    filas = []

    for idx, fila in df_norm.iterrows():
        fecha = valor_fila(fila, "fecha_de_emision", "")
        codigo = normalizar_codigo(valor_fila(fila, "tipo_de_comprobante", ""))
        punto_venta = normalizar_punto_venta(valor_fila(fila, "punto_de_venta", ""))
        numero = normalizar_numero_comprobante(valor_fila(fila, "numero_de_comprobante", ""))
        numero_full = f"{punto_venta}-{numero}"

        cuit = normalizar_cuit(valor_fila(fila, "nro_doc_vendedor", ""))
        proveedor = str(valor_fila(fila, "denominacion_vendedor", "")).strip()

        if proveedor == "":
            proveedor = "PROVEEDOR SIN NOMBRE"

        total = limpiar_numero(valor_fila(fila, "importe_total", 0))

        clave = clave_proveedor(cuit, proveedor)
        sugerencia = mapa_sugerencias.get(clave)

        if sugerencia:
            categoria_sugerida = sugerencia["categoria"]
            origen = sugerencia["origen"]
            confianza = sugerencia["confianza"]
            veces_usada = sugerencia["veces_usada"]
            ultima_vez = sugerencia["ultima_vez"]
            categorias_historicas = sugerencia["categorias_historicas"]
        else:
            categoria_sugerida = categoria_default
            origen = "SIN HISTORIAL"
            confianza = "BAJA"
            veces_usada = 0
            ultima_vez = ""
            categorias_historicas = ""

        filas.append({
            "idx_original": idx,
            "clave_proveedor": clave,
            "fecha": fecha,
            "codigo": codigo,
            "numero": numero_full,
            "cuit": cuit,
            "proveedor": proveedor,
            "total": total,
            "categoria_compra": categoria_sugerida,
            "categoria_sugerida": categoria_sugerida,
            "origen_sugerencia": origen,
            "confianza_sugerencia": confianza,
            "veces_usada": veces_usada,
            "ultima_vez": ultima_vez,
            "categorias_historicas": categorias_historicas
        })

    return pd.DataFrame(filas)


def construir_resumen_por_proveedor(df_detalle):
    if df_detalle.empty:
        return pd.DataFrame(columns=[
            "clave_proveedor",
            "cuit",
            "proveedor",
            "comprobantes",
            "total",
            "categoria_compra",
            "categoria_sugerida",
            "origen_sugerencia",
            "confianza_sugerencia",
            "veces_usada",
            "ultima_vez",
            "categorias_historicas"
        ])

    resumen = df_detalle.groupby(
        ["clave_proveedor", "cuit", "proveedor"],
        as_index=False
    ).agg({
        "idx_original": "count",
        "total": "sum",
        "categoria_compra": "first",
        "categoria_sugerida": "first",
        "origen_sugerencia": "first",
        "confianza_sugerencia": "first",
        "veces_usada": "max",
        "ultima_vez": "first",
        "categorias_historicas": "first"
    })

    resumen = resumen.rename(columns={
        "idx_original": "comprobantes"
    })

    resumen = resumen.sort_values(by=["proveedor", "cuit"], ascending=True)

    return resumen


def aplicar_categorias_y_excepciones(
    df_detalle_base,
    categorias_por_proveedor,
    excepciones_por_indice
):
    df = df_detalle_base.copy()

    df["categoria_compra"] = (
        df["clave_proveedor"]
        .astype(str)
        .map(categorias_por_proveedor)
    )

    for idx, categoria in excepciones_por_indice.items():
        try:
            idx_original = int(idx)
            df.loc[df["idx_original"] == idx_original, "categoria_compra"] = categoria
        except Exception:
            pass

    return df


def resumen_final_por_categoria(df_final):
    if df_final.empty:
        return pd.DataFrame(columns=["categoria_compra", "comprobantes", "total"])

    resumen = df_final.groupby(
        ["categoria_compra"],
        as_index=False
    ).agg({
        "idx_original": "count",
        "total": "sum"
    })

    resumen = resumen.rename(columns={
        "idx_original": "comprobantes"
    })

    return resumen.sort_values(by="categoria_compra")


def guardar_categoria_habitual_proveedores(df_final, df_categorias):
    """
    Decisión de diseño:
    No se guarda aprendizaje automático en proveedores_configuracion.

    El aprendizaje se toma desde compras_comprobantes.
    Si una carga se elimina, sus comprobantes desaparecen y la sugerencia futura se recalcula.
    Así evitamos arrastrar una categoría mal asignada de un archivo eliminado.

    Más adelante podemos crear una pantalla específica para configurar manualmente
    proveedor -> categoría habitual.
    """

    return 0