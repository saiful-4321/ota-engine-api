"""ICAO 9303 three-letter state codes → ISO 3166 alpha-2 (the OTA booking API uses alpha-2)."""

from typing import Optional

import pycountry

# ICAO codes that are not ISO alpha-3, or that need a specific mapping
_ICAO_SPECIAL = {
    "D": "DE",     # Germany
    "GBD": "GB", "GBN": "GB", "GBO": "GB", "GBP": "GB", "GBS": "GB",  # British nationality classes
    "RKS": "XK",   # Kosovo
    "EUE": None,   # European Union laissez-passer
    "UNO": None, "UNA": None, "UNK": None,  # United Nations
    "XXA": None, "XXB": None, "XXC": None, "XXX": None,  # stateless / refugee / unspecified
}


def icao_to_iso2(code: str) -> Optional[str]:
    code = (code or "").replace("<", "").upper()
    if not code:
        return None
    if code in _ICAO_SPECIAL:
        return _ICAO_SPECIAL[code]
    country = pycountry.countries.get(alpha_3=code)
    return country.alpha_2 if country else None


def country_name(code: str) -> Optional[str]:
    code = (code or "").replace("<", "").upper()
    if code == "D":
        code = "DEU"
    country = pycountry.countries.get(alpha_3=code)
    return country.name if country else None
