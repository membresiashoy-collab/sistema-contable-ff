import pandas as pd


def formatear_fecha(fecha):
    """
    Devuelve fecha en formato día/mes/año.
    """
    try:
        f = pd.to_datetime(fecha, dayfirst=True, errors="coerce")

        if pd.isna(f):
            return str(fecha)

        return f.strftime("%d/%m/%Y")

    except Exception:
        return str(fecha)


def obtener_anio_mes(fecha):
    try:
        f = pd.to_datetime(fecha, dayfirst=True, errors="coerce")

        if pd.isna(f):
            return None, None

        return int(f.year), int(f.month)

    except Exception:
        return None, None


def fecha_para_ordenar(fecha):
    return pd.to_datetime(fecha, dayfirst=True, errors="coerce")


def ordenar_dataframe_por_fecha(df, columna_indice=0):
    df_ordenado = df.copy()
    df_ordenado["_fecha_orden"] = pd.to_datetime(
        df_ordenado.iloc[:, columna_indice],
        dayfirst=True,
        errors="coerce"
    )

    df_ordenado = df_ordenado.sort_values(by="_fecha_orden")
    df_ordenado = df_ordenado.drop(columns=["_fecha_orden"])

    return df_ordenado