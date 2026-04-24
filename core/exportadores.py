from io import BytesIO
import pandas as pd


def exportar_excel(diccionario_df):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for nombre_hoja, df in diccionario_df.items():
            df.to_excel(writer, index=False, sheet_name=nombre_hoja[:31])

    output.seek(0)
    return output