import pandas as pd


def limpiar_texto(v):
    try:
        if pd.isna(v):
            return ""

        texto = str(v).strip()

        if texto.lower() in ["nan", "none"]:
            return ""

        if texto.endswith(".0"):
            texto = texto[:-2]

        return texto

    except Exception:
        return ""


def normalizar_nombre(nombre, reemplazo="SIN NOMBRE"):
    texto = limpiar_texto(nombre)

    if texto == "":
        return reemplazo

    return texto.upper().strip()