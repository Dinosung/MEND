def test_populate_by_field_name_and_alias():
    import target

    by_name = target.make_customer(42, "Ada")
    assert by_name.customer_id == 42
    assert by_name.display_name == "Ada"

    by_alias = target.Customer.model_validate({"customerId": 1, "displayName": "Bob"})
    assert by_alias.model_dump(by_alias=True) == {"customerId": 1, "displayName": "Bob"}
