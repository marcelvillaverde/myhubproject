from hubcarros.search import SearchFilters, parse_query


def test_parse_price_mileage_and_type():
    f = parse_query("automatic family SUV under £15k with under 50k miles")
    assert f.max_price == 15000 and f.max_mileage == 50000
    assert f.transmission == "automatic" and f.body == "suv"


def test_parse_mileage_not_confused_with_price():
    f = parse_query("less than 60,000 miles")
    assert f.max_mileage == 60000 and f.max_price is None


def test_parse_make_alias_fuel_seats_year():
    f = parse_query("vw diesel estate 7 seater 2018 or newer")
    assert (f.make, f.fuel, f.body, f.min_seats, f.min_year) == ("Volkswagen", "diesel", "estate", 7, 2018)


def test_parse_price_range():
    f = parse_query("hybrid between £10,000 to £14,000")
    assert (f.min_price, f.max_price, f.fuel) == (10000, 14000, "hybrid")


def test_plug_in_hybrid_wins_over_hybrid():
    assert parse_query("plug-in hybrid").fuel == "plug-in hybrid"


def test_explicit_filters_override_parsed():
    merged = parse_query("under £10k").merged_with(SearchFilters(max_price=12000))
    assert merged.max_price == 12000
