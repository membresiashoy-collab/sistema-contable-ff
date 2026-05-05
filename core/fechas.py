import re
from datetime import date, datetime

import pandas as pd


# ======================================================
# FECHAS DEL SISTEMA
# ======================================================
#
# Regla general:
# - ARCA / AFIP suele venir como DD/MM/YYYY.
# - Streamlit / Python / SQLite pueden traer YYYY-MM-DD.
# - El sistema debe interpretar ambos formatos correctamente.
#
# Ejemplos correctos:
#   "03/12/2025" -> 03/12/2025 -> año 2025, mes 12
#   "2025-12-03" -> 03/12/2025 -> año 2025, mes 12
#
# No usar pd.to_datetime(..., dayfirst=True) de forma directa sobre todo,
# porque Pandas puede interpretar mal fechas ISO YYYY-MM-DD.
# ======================================================


VALORES_VACIOS = {"", "nan", "nat", "none", "null", "NaN", "NaT", "None", "NULL"}


def _es_vacio(valor):
    try:
        if valor is None:
            return True

        if pd.isna(valor):
            return True

    except Exception:
        pass

    texto = str(valor).strip()

    return texto in VALORES_VACIOS or texto.lower() in VALORES_VACIOS


def _anio_dos_digitos_a_cuatro(anio):
    anio = int(anio)

    if anio < 100:
        if anio <= 49:
            return 2000 + anio
        return 1900 + anio

    return anio


def _timestamp_seguro(anio, mes, dia):
    try:
        return pd.Timestamp(year=int(anio), month=int(mes), day=int(dia))
    except Exception:
        return pd.NaT


def parsear_fecha(valor):
    """
    Convierte un valor de fecha a pandas.Timestamp de forma segura.

    Soporta:
    - datetime/date/Timestamp ya nativos.
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY.
    - YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD.
    - YYYYMMDD.
    - DDMMYYYY.
    - Números seriales de Excel en rango razonable.

    Devuelve:
    - pandas.Timestamp si la fecha es interpretable.
    - pandas.NaT si no se puede interpretar.
    """

    if _es_vacio(valor):
        return pd.NaT

    if isinstance(valor, pd.Timestamp):
        if pd.isna(valor):
            return pd.NaT

        return pd.Timestamp(valor.date())

    if isinstance(valor, datetime):
        return pd.Timestamp(valor.date())

    if isinstance(valor, date):
        return pd.Timestamp(valor)

    texto = str(valor).strip()

    if texto in VALORES_VACIOS or texto.lower() in VALORES_VACIOS:
        return pd.NaT

    # Limpiar comillas comunes de CSV.
    texto = texto.strip('"').strip("'").strip()

    # Algunos valores pueden venir con hora: "2025-12-03 00:00:00"
    # o "03/12/2025 00:00:00". Los patrones aceptan el resto como opcional.

    # Formato ISO / técnico: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    match_iso = re.match(
        r"^\s*(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})(?:\s+.*)?\s*$",
        texto
    )

    if match_iso:
        anio, mes, dia = match_iso.groups()
        return _timestamp_seguro(anio, mes, dia)

    # Formato argentino / ARCA: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    match_arg = re.match(
        r"^\s*(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2,4})(?:\s+.*)?\s*$",
        texto
    )

    if match_arg:
        dia, mes, anio = match_arg.groups()
        anio = _anio_dos_digitos_a_cuatro(anio)
        return _timestamp_seguro(anio, mes, dia)

    # Formatos compactos: YYYYMMDD o DDMMYYYY
    if re.match(r"^\d{8}$", texto):
        primeros_4 = int(texto[:4])

        if 1900 <= primeros_4 <= 2100:
            anio = texto[:4]
            mes = texto[4:6]
            dia = texto[6:8]
            return _timestamp_seguro(anio, mes, dia)

        dia = texto[:2]
        mes = texto[2:4]
        anio = texto[4:8]
        return _timestamp_seguro(anio, mes, dia)

    # Serial Excel en rango razonable.
    # Ejemplo: 45994 puede representar una fecha.
    try:
        numero = float(texto.replace(",", "."))

        if numero.is_integer() and 20000 <= numero <= 60000:
            fecha_excel = pd.to_datetime(
                int(numero),
                unit="D",
                origin="1899-12-30",
                errors="coerce"
            )

            if not pd.isna(fecha_excel):
                return pd.Timestamp(fecha_excel.date())

    except Exception:
        pass

    # Último intento conservador para formatos raros.
    # Primero día/mes, porque el sistema opera con formato argentino.
    fecha = pd.to_datetime(texto, dayfirst=True, errors="coerce")

    if not pd.isna(fecha):
        return pd.Timestamp(fecha.date())

    return pd.NaT


def formatear_fecha(fecha):
    """
    Devuelve la fecha en formato argentino DD/MM/YYYY.
    Si no se puede interpretar, devuelve el valor original como texto.
    """

    try:
        f = parsear_fecha(fecha)

        if pd.isna(f):
            return str(fecha)

        return f.strftime("%d/%m/%Y")

    except Exception:
        return str(fecha)


def normalizar_fecha_iso(fecha):
    """
    Devuelve la fecha en formato ISO YYYY-MM-DD.
    Útil para guardar internamente, ordenar o comparar.
    Si no se puede interpretar, devuelve string vacío.
    """

    try:
        f = parsear_fecha(fecha)

        if pd.isna(f):
            return ""

        return f.date().isoformat()

    except Exception:
        return ""


def obtener_anio_mes(fecha):
    """
    Devuelve (año, mes) de una fecha interpretable.
    Si no se puede interpretar, devuelve ("", "").
    """

    try:
        f = parsear_fecha(fecha)

        if pd.isna(f):
            return "", ""

        return int(f.year), int(f.month)

    except Exception:
        return "", ""


def fecha_para_ordenar(fecha):
    """
    Devuelve pandas.Timestamp para ordenar DataFrames.
    Si no se puede interpretar, devuelve pandas.NaT.
    """

    try:
        return parsear_fecha(fecha)
    except Exception:
        return pd.NaT


def ordenar_dataframe_por_fecha(df, columna_indice=0):
    """
    Ordena un DataFrame por una columna de fecha usando parseo seguro.

    columna_indice:
    - Por defecto 0, porque los CSV ARCA suelen traer la fecha en la primera columna.
    """

    if df is None or df.empty:
        return df

    df_ordenado = df.copy()

    try:
        columna = df_ordenado.columns[columna_indice]
    except Exception:
        return df_ordenado

    df_ordenado["_fecha_orden"] = df_ordenado[columna].apply(fecha_para_ordenar)
    df_ordenado = df_ordenado.sort_values(by="_fecha_orden", na_position="last")
    df_ordenado = df_ordenado.drop(columns=["_fecha_orden"])

    return df_ordenado