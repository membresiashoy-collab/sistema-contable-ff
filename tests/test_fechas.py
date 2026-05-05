from datetime import date, datetime

import pandas as pd

from core.fechas import (
    formatear_fecha,
    obtener_anio_mes,
    fecha_para_ordenar,
    normalizar_fecha_iso,
)


def test_fecha_arca_dd_mm_yyyy_no_invierte_dia_mes():
    valor = "03/12/2025"

    assert formatear_fecha(valor) == "03/12/2025"
    assert obtener_anio_mes(valor) == (2025, 12)
    assert normalizar_fecha_iso(valor) == "2025-12-03"
    assert fecha_para_ordenar(valor).date().isoformat() == "2025-12-03"


def test_fecha_iso_yyyy_mm_dd_no_se_interpreta_como_dayfirst():
    valor = "2025-12-03"

    assert formatear_fecha(valor) == "03/12/2025"
    assert obtener_anio_mes(valor) == (2025, 12)
    assert normalizar_fecha_iso(valor) == "2025-12-03"
    assert fecha_para_ordenar(valor).date().isoformat() == "2025-12-03"


def test_fecha_iso_marzo_no_se_transforma_en_diciembre():
    valor = "2025-03-12"

    assert formatear_fecha(valor) == "12/03/2025"
    assert obtener_anio_mes(valor) == (2025, 3)
    assert normalizar_fecha_iso(valor) == "2025-03-12"
    assert fecha_para_ordenar(valor).date().isoformat() == "2025-03-12"


def test_fecha_datetime_date_y_timestamp():
    assert formatear_fecha(date(2025, 12, 3)) == "03/12/2025"
    assert obtener_anio_mes(date(2025, 12, 3)) == (2025, 12)

    assert formatear_fecha(datetime(2025, 12, 3, 10, 30)) == "03/12/2025"
    assert obtener_anio_mes(datetime(2025, 12, 3, 10, 30)) == (2025, 12)

    assert formatear_fecha(pd.Timestamp("2025-12-03")) == "03/12/2025"
    assert obtener_anio_mes(pd.Timestamp("2025-12-03")) == (2025, 12)


def test_fechas_compactas():
    assert formatear_fecha("20251203") == "03/12/2025"
    assert obtener_anio_mes("20251203") == (2025, 12)

    assert formatear_fecha("03122025") == "03/12/2025"
    assert obtener_anio_mes("03122025") == (2025, 12)