"""Canonical UK car make names."""

KNOWN_MAKES = [
    "Abarth", "Alfa Romeo", "Audi", "BMW", "BYD", "Citroen", "Cupra", "Dacia", "DS", "Fiat", "Ford",
    "Honda", "Hyundai", "Jaguar", "Jeep", "Kia", "Land Rover", "Lexus", "Mazda", "Mercedes-Benz", "MG",
    "Mini", "Mitsubishi", "Nissan", "Peugeot", "Polestar", "Porsche", "Renault", "Seat", "Skoda",
    "Smart", "Subaru", "Suzuki", "Tesla", "Toyota", "Vauxhall", "Volkswagen", "Volvo",
]
MAKE_ALIASES = {"vw": "Volkswagen", "merc": "Mercedes-Benz", "mercedes": "Mercedes-Benz", "range rover": "Land Rover", "citroën": "Citroen"}


def canonical_make(raw: str) -> str:
    v = raw.strip()
    low = v.lower()
    if low in MAKE_ALIASES:
        return MAKE_ALIASES[low]
    for make in KNOWN_MAKES:
        if make.lower() == low:
            return make
    return v if (v.isupper() and len(v) <= 3) else v.title()
