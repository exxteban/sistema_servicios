from decimal import Decimal

from importar_productos_excel import normalizar_header, parse_decimal, parse_int, resolve_excel_file, row_to_payload


def test_normalizar_header_unifica_acentos_espacios_y_typos():
    assert normalizar_header("Código") == "codigo"
    assert normalizar_header("IVA ") == "porcentaje_iva"
    assert normalizar_header("STOK MINIO") == "stock_minimo"


def test_parse_decimal_acepta_numeros_con_separadores_locales():
    assert parse_decimal("1.234,50") == Decimal("1234.50")
    assert parse_decimal(1600.0) == Decimal("1600.00")
    assert parse_decimal(None) == Decimal("0.00")


def test_parse_int_acepta_decimal_y_default():
    assert parse_int("500.0", default=5) == 500
    assert parse_int(None, default=5) == 5


def test_row_to_payload_mapea_columnas_del_excel():
    row = {
        "Código": "60REFAMA",
        "CATEGORIA": "BOLSA DE BASURA REFORZADA",
        "NOMBRE DEL PRODUCTO": "60 LITROS REFORZADO AMARILLO",
        "DESCRIPCION": "48X60X23",
        "MARCA": 0,
        "MODELO": 0,
        "COLOR": "AMARILLO",
        "CAPACIDAD": "60 L",
        "PRECIO DE COMPRA": 1319,
        "PRECIO DE VENTA": 1600,
        "PRECIO MAYORISTA": 1400,
        "IVA ": 10,
        "STOK": None,
        "STOK MINIO": 500,
    }

    payload = row_to_payload(row)

    assert payload["codigo"] == "60REFAMA"
    assert payload["categoria_nombre"] == "BOLSA DE BASURA REFORZADA"
    assert payload["nombre"] == "60 LITROS REFORZADO AMARILLO"
    assert payload["descripcion"] == "48X60X23"
    assert payload["marca"] is None
    assert payload["modelo"] is None
    assert payload["color"] == "AMARILLO"
    assert payload["capacidad"] == "60 L"
    assert payload["precio_compra"] == Decimal("1319.00")
    assert payload["precio_venta"] == Decimal("1600.00")
    assert payload["precio_mayorista"] == Decimal("1400.00")
    assert payload["porcentaje_iva"] == 10
    assert payload["stock_actual"] == 0
    assert payload["stock_minimo"] == 500


def test_resolve_excel_file_usa_carpeta_del_script_sin_fallback_a_padre(tmp_path):
    script_dir = tmp_path / "repo"
    script_dir.mkdir()
    parent_file = tmp_path / "PRECIO_SISTEMA_NUEVO.xlsx"
    parent_file.write_text("placeholder")

    assert resolve_excel_file(None, base_dir=str(script_dir)) == str(script_dir / "PRECIO_SISTEMA_NUEVO.xlsx")
