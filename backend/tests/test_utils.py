"""Tests de las utilidades de ingesta. Casos fijados por el prompt."""
import pytest

from ingestion.utils import limpiar_concepto, normalizar_nif, parse_es_number


class TestParseEsNumber:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("4.500.000,00-", -4500000.0),   # signo contable final
            ("1.234.567,89 ", 1234567.89),   # formato español con espacio
            ("0,00", 0.0),
            ("881768964.31", 881768964.31),  # nativo anglosajón
            (4500000, 4500000.0),            # int nativo
            (881768964.31, 881768964.31),    # float nativo
            (None, 0.0),
            ("", 0.0),
            ("  ", 0.0),
            ("3.000.000,00", 3000000.0),
            ("-1.500,50", -1500.50),         # signo al inicio
        ],
    )
    def test_parse(self, entrada, esperado):
        assert parse_es_number(entrada) == pytest.approx(esperado)

    def test_bool_no_es_numero(self):
        assert parse_es_number(True) == 0.0


class TestNormalizarNif:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("901128135-5", "901128135"),
            ("901207879S", "901207879"),
            ("1.035.864.525-0", "1035864525"),
            ("70901974-N", "70901974"),
            ("B12550877", "B12550877"),   # NIF empresa español: se conserva
            ("901331202-1", "901331202"),
            ("  900529233-6 ", "900529233"),
            (None, ""),
        ],
    )
    def test_normaliza(self, entrada, esperado):
        assert normalizar_nif(entrada) == esperado


class TestLimpiarConcepto:
    def test_quita_prefijo_fecha(self):
        assert limpiar_concepto("01/2026 PAGO PROVEEDOR") == "PAGO PROVEEDOR"

    def test_quita_sufijo_factura(self):
        assert limpiar_concepto("DIGITAL CENTER S. FRA: 12345") == "DIGITAL CENTER"

    def test_quita_acentos_y_signos(self):
        assert limpiar_concepto("Pérez & Cardona, S.A.") == "PEREZ CARDONA S A"

    def test_vacio(self):
        assert limpiar_concepto(None) == ""
