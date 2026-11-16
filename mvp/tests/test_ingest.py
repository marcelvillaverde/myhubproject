from hubcarros.ingest import parse_csv


def test_aliases_and_normalisation():
    csv = (
        "Registration,Make,Model,Year,Price,Mileage,Fuel Type,Transmission,Body Type\n"
        'ab12 cde,VW,Golf,2018,"£9,995",45k,Unleaded,DSG,Hatch\n'
    )
    r = parse_csv(csv, "d1")
    assert r.errors == []
    v = r.vehicles[0]
    assert (v.reg, v.make, v.price_gbp, v.mileage) == ("AB12CDE", "Volkswagen", 9995, 45000)
    assert (v.fuel, v.transmission, v.body) == ("petrol", "automatic", "hatchback")


def test_missing_required_column_reports_and_returns_nothing():
    r = parse_csv("reg,make,model,year\nAB12CDE,Ford,Fiesta,2018\n", "d1")
    assert r.vehicles == []
    assert "mileage" in r.errors[0].reason


def test_bad_rows_are_reported_not_dropped_silently():
    csv = (
        "reg,make,model,year,mileage\n"
        "AB12CDE,Ford,Fiesta,2018,30000\n"
        "AB12CDE,Ford,Fiesta,2018,30000\n"
        ",Ford,Ka,2015,1000\n"
        "XY13ZZZ,Ford,Ka,abc,1000\n"
    )
    r = parse_csv(csv, "d1")
    assert len(r.vehicles) == 1
    assert [e.line for e in r.errors] == [3, 4, 5]


def test_features_split():
    r = parse_csv("reg,make,model,year,mileage,features\nA1,Kia,Ceed,2020,1,Sat nav; DAB|Heated seats\n", "d")
    assert r.vehicles[0].features == ["Sat nav", "DAB", "Heated seats"]


def test_make_canonicalisation():
    r = parse_csv("reg,make,model,year,mileage\nA1,FORD,Focus,2019,1\nA2,bmw,320d,2020,1\nA3,mercedes,C200,2020,1\n", "d")
    assert [v.make for v in r.vehicles] == ["Ford", "BMW", "Mercedes-Benz"]
