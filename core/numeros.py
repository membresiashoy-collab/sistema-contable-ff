import pandas as pd


def limpiar_numero(v):
    """
    Convierte números argentinos del CSV a float.
    Soporta:
    - 103305,76
    - 103.305,76
    - 103305.76
    - $ 103.305,76
    """
    try:
        if pd.isna(v):
            return 0.0

        if isinstance(v, (int, float)):
            return float(v)

        valor = str(v).strip()

        if valor == "" or valor.lower() in ["nan", "none"]:
            return 0.0

        valor = valor.replace("$", "").replace(" ", "")

        if "," in valor:
            valor = valor.replace(".", "").replace(",", ".")
        else:
            if valor.count(".") > 1:
                valor = valor.replace(".", "")

        return float(valor)

    except Exception:
        return 0.0


def moneda(valor):
    try:
        return f"$ {float(valor):,.2f}"
    except Exception:
        return "$ 0.00"