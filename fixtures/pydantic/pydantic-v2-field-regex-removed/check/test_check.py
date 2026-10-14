import pydantic


def test_sku_pattern_enforced():
    import target

    assert target.parse_product({"sku": "ABC-1234", "name": "Widget"}).sku == "ABC-1234"
    try:
        target.parse_product({"sku": "abc-12", "name": "Widget"})
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError("invalid SKU was accepted")
