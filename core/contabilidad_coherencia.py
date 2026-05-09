from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
import unicodedata
from typing import Any, Iterable

FORMATO_FECHA_ARGENTINA = "%d/%m/%Y"
FORMATO_FECHA_ISO = "%Y-%m-%d"

SEVERIDAD_OK = "OK"
SEVERIDAD_INFO = "INFO"
SEVERIDAD_ADVERTENCIA = "ADVERTENCIA"
SEVERIDAD_ERROR = "ERROR"

SEVERIDADES_VALIDAS = {
    SEVERIDAD_OK,
    SEVERIDAD_INFO,
    SEVERIDAD_ADVERTENCIA,
    SEVERIDAD_ERROR,
}

COMPORTAMIENTOS_CONTABLES: dict[str, dict[str, str]] = {
    "CAJA": {
        "nombre": "Caja",
        "naturaleza": "ACTIVO",
        "descripcion": "Cuenta que representa dinero físico disponible.",
    },
    "BANCO": {
        "nombre": "Banco",
        "naturaleza": "ACTIVO",
        "descripcion": "Cuenta bancaria operativa o cuenta corriente bancaria.",
    },
    "IVA_CREDITO": {
        "nombre": "IVA crédito fiscal",
        "naturaleza": "ACTIVO",
        "descripcion": "Crédito fiscal computable o saldo técnico a favor vinculado a IVA.",
    },
    "IVA_DEBITO": {
        "nombre": "IVA débito fiscal",
        "naturaleza": "PASIVO",
        "descripcion": "Débito fiscal generado por ventas o ajustes de IVA.",
    },
    "CAPITAL_SOCIAL": {
        "nombre": "Capital social",
        "naturaleza": "PATRIMONIO_NETO",
        "descripcion": "Capital suscripto de socios o accionistas.",
    },
    "SOCIOS_INTEGRACION": {
        "nombre": "Socios / accionistas por integración",
        "naturaleza": "ACTIVO",
        "descripcion": "Crédito contra socios por capital suscripto pendiente de integración.",
    },
    "APORTE_IRREVOCABLE": {
        "nombre": "Aportes irrevocables",
        "naturaleza": "PATRIMONIO_NETO",
        "descripcion": "Aportes recibidos con destino a futura capitalización u origen similar.",
    },
    "PRESTAMO_SOCIO": {
        "nombre": "Préstamos de socios",
        "naturaleza": "PASIVO",
        "descripcion": "Fondos recibidos de socios con obligación de devolución.",
    },
    "CUENTA_PARTICULAR_SOCIO": {
        "nombre": "Cuenta particular socios",
        "naturaleza": "ACTIVO_PASIVO",
        "descripcion": "Cuenta puente para movimientos particulares con socios.",
    },
    "SUELDOS_GASTO": {
        "nombre": "Sueldos y jornales",
        "naturaleza": "RESULTADO_NEGATIVO",
        "descripcion": "Gasto devengado por remuneraciones.",
    },
    "SUELDOS_A_PAGAR": {
        "nombre": "Sueldos a pagar",
        "naturaleza": "PASIVO",
        "descripcion": "Obligación pendiente de pago por remuneraciones liquidadas.",
    },
    "CARGAS_SOCIALES_GASTO": {
        "nombre": "Cargas sociales",
        "naturaleza": "RESULTADO_NEGATIVO",
        "descripcion": "Gasto patronal devengado por seguridad social.",
    },
    "CARGAS_SOCIALES_A_PAGAR": {
        "nombre": "Cargas sociales a pagar",
        "naturaleza": "PASIVO",
        "descripcion": "Obligación a pagar por contribuciones y conceptos sociales.",
    },
    "ART_A_PAGAR": {
        "nombre": "ART a pagar",
        "naturaleza": "PASIVO",
        "descripcion": "Obligación pendiente con aseguradora de riesgos del trabajo.",
    },
    "OBRA_SOCIAL_A_PAGAR": {
        "nombre": "Obra social a pagar",
        "naturaleza": "PASIVO",
        "descripcion": "Obligación pendiente por obra social.",
    },
    "SINDICATO_A_PAGAR": {
        "nombre": "Sindicato a pagar",
        "naturaleza": "PASIVO",
        "descripcion": "Obligación pendiente por aportes o contribuciones sindicales.",
    },
}

COMPORTAMIENTOS_CRITICOS = tuple(COMPORTAMIENTOS_CONTABLES.keys())

ORIGENES_ECONOMICOS_OPERATIVOS: dict[str, dict[str, str]] = {
    "COBRANZA_CLIENTE": {
        "nombre": "Cobranza de cliente",
        "modulo": "Cobranzas/Banco/Caja",
        "descripcion": "Ingreso por cancelación total o parcial de deuda de cliente.",
    },
    "PAGO_PROVEEDOR": {
        "nombre": "Pago a proveedor",
        "modulo": "Pagos/Banco/Caja",
        "descripcion": "Egreso por cancelación total o parcial de deuda con proveedor.",
    },
    "APORTE_SOCIO": {
        "nombre": "Aporte de socio",
        "modulo": "Capital/Banco/Caja",
        "descripcion": "Ingreso patrimonial aportado por socio sin tratarlo como venta ni cobranza.",
    },
    "INTEGRACION_CAPITAL": {
        "nombre": "Integración de capital",
        "modulo": "Inicio contable/Capital/Banco/Caja",
        "descripcion": "Ingreso que cancela capital suscripto pendiente de integración.",
    },
    "PRESTAMO_SOCIO": {
        "nombre": "Préstamo de socio",
        "modulo": "Banco/Caja",
        "descripcion": "Ingreso de fondos de socio con naturaleza de pasivo.",
    },
    "RETIRO_SOCIO": {
        "nombre": "Retiro de socio",
        "modulo": "Banco/Caja",
        "descripcion": "Egreso hacia socio que debe clasificarse contablemente.",
    },
    "GASTO_MENOR": {
        "nombre": "Gasto menor",
        "modulo": "Caja",
        "descripcion": "Egreso operativo de caja pendiente de imputación contable específica.",
    },
    "TRANSFERENCIA_INTERNA": {
        "nombre": "Transferencia interna",
        "modulo": "Banco/Caja/Tesorería",
        "descripcion": "Movimiento entre cuentas propias sin generar ingreso ni gasto.",
    },
    "DEPOSITO_CAJA_A_BANCO": {
        "nombre": "Depósito de caja a banco",
        "modulo": "Caja/Banco",
        "descripcion": "Traslado de efectivo a una cuenta bancaria propia.",
    },
    "RETIRO_BANCO_A_CAJA": {
        "nombre": "Retiro desde banco a caja",
        "modulo": "Banco/Caja",
        "descripcion": "Extracción de fondos bancarios para disponibilidad en caja.",
    },
    "PAGO_FISCAL": {
        "nombre": "Pago fiscal",
        "modulo": "Banco/Caja/IVA",
        "descripcion": "Egreso aplicado a obligaciones impositivas.",
    },
    "PAGO_SUELDO": {
        "nombre": "Pago de sueldo",
        "modulo": "Sueldos/Banco/Caja",
        "descripcion": "Cancelación de remuneraciones liquidadas externamente.",
    },
    "PAGO_CARGAS_SOCIALES": {
        "nombre": "Pago de cargas sociales",
        "modulo": "Sueldos/Banco/Caja",
        "descripcion": "Cancelación de obligaciones laborales y de seguridad social.",
    },
    "AJUSTE_CAJA": {
        "nombre": "Ajuste de caja",
        "modulo": "Caja",
        "descripcion": "Diferencia de arqueo o ajuste operativo con trazabilidad.",
    },
}


@dataclass(frozen=True)
class DiagnosticoCoherencia:
    area: str
    severidad: str
    codigo: str
    titulo: str
    detalle: str
    referencia_tipo: str | None = None
    referencia_id: int | str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "severidad": self.severidad,
            "codigo": self.codigo,
            "titulo": self.titulo,
            "detalle": self.detalle,
            "referencia_tipo": self.referencia_tipo,
            "referencia_id": self.referencia_id,
        }


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = re.sub(r"\s+", " ", texto)
    return texto


def normalizar_codigo(valor: Any) -> str:
    texto = normalizar_texto(valor)
    texto = re.sub(r"[^A-Z0-9_]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto


def _parse_fecha_texto(texto: str) -> date:
    limpio = texto.strip()
    if not limpio:
        raise ValueError("La fecha está vacía.")

    formatos = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y%m%d",
    )
    for formato in formatos:
        try:
            return datetime.strptime(limpio, formato).date()
        except ValueError:
            continue

    raise ValueError(f"Formato de fecha no reconocido: {texto!r}.")


def convertir_a_fecha(valor: Any) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        return _parse_fecha_texto(valor)
    raise ValueError(f"Tipo de fecha no soportado: {type(valor).__name__}.")


def normalizar_fecha_iso(valor: Any) -> str | None:
    fecha = convertir_a_fecha(valor)
    if fecha is None:
        return None
    return fecha.strftime(FORMATO_FECHA_ISO)


def formatear_fecha_argentina(valor: Any, vacio: str = "") -> str:
    fecha = convertir_a_fecha(valor)
    if fecha is None:
        return vacio
    return fecha.strftime(FORMATO_FECHA_ARGENTINA)


def fecha_en_rango(fecha: Any, desde: Any, hasta: Any) -> bool:
    fecha_normalizada = convertir_a_fecha(fecha)
    desde_normalizada = convertir_a_fecha(desde)
    hasta_normalizada = convertir_a_fecha(hasta)
    if fecha_normalizada is None or desde_normalizada is None or hasta_normalizada is None:
        return False
    return desde_normalizada <= fecha_normalizada <= hasta_normalizada


def rangos_superpuestos(desde_a: Any, hasta_a: Any, desde_b: Any, hasta_b: Any) -> bool:
    inicio_a = convertir_a_fecha(desde_a)
    fin_a = convertir_a_fecha(hasta_a)
    inicio_b = convertir_a_fecha(desde_b)
    fin_b = convertir_a_fecha(hasta_b)
    if None in (inicio_a, fin_a, inicio_b, fin_b):
        return False
    return inicio_a <= fin_b and inicio_b <= fin_a


def periodo_yyyymm(valor: Any) -> str | None:
    fecha = convertir_a_fecha(valor)
    if fecha is None:
        return None
    return f"{fecha.year:04d}-{fecha.month:02d}"


def validar_rango_ejercicio(fecha_inicio: Any, fecha_fin: Any) -> list[DiagnosticoCoherencia]:
    diagnosticos: list[DiagnosticoCoherencia] = []
    try:
        inicio = convertir_a_fecha(fecha_inicio)
        fin = convertir_a_fecha(fecha_fin)
    except ValueError as exc:
        return [
            DiagnosticoCoherencia(
                area="Ejercicios",
                severidad=SEVERIDAD_ERROR,
                codigo="EJERCICIO_FECHA_INVALIDA",
                titulo="El ejercicio tiene fechas inválidas",
                detalle=str(exc),
            )
        ]

    if inicio is None or fin is None:
        diagnosticos.append(
            DiagnosticoCoherencia(
                area="Ejercicios",
                severidad=SEVERIDAD_ERROR,
                codigo="EJERCICIO_FECHA_FALTANTE",
                titulo="El ejercicio no tiene rango completo",
                detalle="Todo ejercicio contable debe tener fecha de inicio y fecha de cierre.",
            )
        )
        return diagnosticos

    if inicio > fin:
        diagnosticos.append(
            DiagnosticoCoherencia(
                area="Ejercicios",
                severidad=SEVERIDAD_ERROR,
                codigo="EJERCICIO_RANGO_INVERTIDO",
                titulo="El ejercicio tiene fecha de inicio posterior al cierre",
                detalle=f"Inicio {formatear_fecha_argentina(inicio)} y cierre {formatear_fecha_argentina(fin)}.",
            )
        )

    return diagnosticos


def validar_comportamiento_contable(comportamiento: Any) -> bool:
    return normalizar_codigo(comportamiento) in COMPORTAMIENTOS_CONTABLES


def describir_comportamiento(comportamiento: Any) -> dict[str, str] | None:
    return COMPORTAMIENTOS_CONTABLES.get(normalizar_codigo(comportamiento))


def comportamientos_para_selector() -> list[dict[str, str]]:
    filas = []
    for codigo, datos in COMPORTAMIENTOS_CONTABLES.items():
        filas.append(
            {
                "codigo": codigo,
                "nombre": datos["nombre"],
                "naturaleza": datos["naturaleza"],
                "descripcion": datos["descripcion"],
            }
        )
    return filas


def origenes_economicos_para_selector() -> list[dict[str, str]]:
    filas = []
    for codigo, datos in ORIGENES_ECONOMICOS_OPERATIVOS.items():
        filas.append(
            {
                "codigo": codigo,
                "nombre": datos["nombre"],
                "modulo": datos["modulo"],
                "descripcion": datos["descripcion"],
            }
        )
    return filas


def severidad_orden(severidad: str) -> int:
    orden = {
        SEVERIDAD_ERROR: 0,
        SEVERIDAD_ADVERTENCIA: 1,
        SEVERIDAD_INFO: 2,
        SEVERIDAD_OK: 3,
    }
    return orden.get(severidad, 9)