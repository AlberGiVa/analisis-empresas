"""Sector taxonomy and bond seniority, with their Spanish labels.

The taxonomy is the fund's own and deliberately small (GICS requires a licence). Real providers
will map their classifications (BICS, RBICS) onto it.
"""

from enum import StrEnum


class Sector(StrEnum):
    INDUSTRIALS = "industrials"
    CONSUMER = "consumer"
    TECHNOLOGY = "technology"
    UTILITIES = "utilities"
    FINANCIALS = "financials"
    HEALTH_CARE = "health_care"
    ENERGY = "energy"

    @property
    def label(self) -> str:
        return _SECTOR_LABELS[self]


class Industry(StrEnum):
    CAPITAL_GOODS = "capital_goods"
    TRANSPORTATION = "transportation"
    CONSTRUCTION = "construction"
    FOOD_BEVERAGE = "food_beverage"
    RETAIL = "retail"
    CONSUMER_PRODUCTS = "consumer_products"
    SOFTWARE = "software"
    SEMICONDUCTORS = "semiconductors"
    IT_SERVICES = "it_services"
    ELECTRIC_UTILITIES = "electric_utilities"
    BANKS = "banks"
    INSURANCE = "insurance"
    PHARMACEUTICALS = "pharmaceuticals"
    MEDICAL_DEVICES = "medical_devices"
    OIL_GAS = "oil_gas"

    @property
    def label(self) -> str:
        return _INDUSTRY_LABELS[self]

    @property
    def sector(self) -> Sector:
        return _INDUSTRY_SECTOR[self]


# Banks and insurers: metrics based on EBITDA, net debt or EV do not apply to them.
FINANCIAL_INSTITUTIONS = frozenset({Industry.BANKS, Industry.INSURANCE})


class Seniority(StrEnum):
    SENIOR_SECURED = "senior_secured"
    SENIOR_UNSECURED = "senior_unsecured"
    SENIOR_NON_PREFERRED = "senior_non_preferred"
    SUBORDINATED = "subordinated"
    JUNIOR_SUBORDINATED = "junior_subordinated"

    @property
    def label(self) -> str:
        return _SENIORITY_LABELS[self]


_SECTOR_LABELS = {
    Sector.INDUSTRIALS: "Industria",
    Sector.CONSUMER: "Consumo",
    Sector.TECHNOLOGY: "Tecnología",
    Sector.UTILITIES: "Utilities",
    Sector.FINANCIALS: "Financiero",
    Sector.HEALTH_CARE: "Salud",
    Sector.ENERGY: "Energía",
}

_INDUSTRY_LABELS = {
    Industry.CAPITAL_GOODS: "Bienes de equipo",
    Industry.TRANSPORTATION: "Transporte y logística",
    Industry.CONSTRUCTION: "Construcción e infraestructuras",
    Industry.FOOD_BEVERAGE: "Alimentación y bebidas",
    Industry.RETAIL: "Distribución minorista",
    Industry.CONSUMER_PRODUCTS: "Productos de consumo",
    Industry.SOFTWARE: "Software",
    Industry.SEMICONDUCTORS: "Semiconductores",
    Industry.IT_SERVICES: "Servicios tecnológicos",
    Industry.ELECTRIC_UTILITIES: "Eléctricas",
    Industry.BANKS: "Bancos",
    Industry.INSURANCE: "Seguros",
    Industry.PHARMACEUTICALS: "Farmacéuticas",
    Industry.MEDICAL_DEVICES: "Tecnología médica",
    Industry.OIL_GAS: "Petróleo y gas",
}

_INDUSTRY_SECTOR = {
    Industry.CAPITAL_GOODS: Sector.INDUSTRIALS,
    Industry.TRANSPORTATION: Sector.INDUSTRIALS,
    Industry.CONSTRUCTION: Sector.INDUSTRIALS,
    Industry.FOOD_BEVERAGE: Sector.CONSUMER,
    Industry.RETAIL: Sector.CONSUMER,
    Industry.CONSUMER_PRODUCTS: Sector.CONSUMER,
    Industry.SOFTWARE: Sector.TECHNOLOGY,
    Industry.SEMICONDUCTORS: Sector.TECHNOLOGY,
    Industry.IT_SERVICES: Sector.TECHNOLOGY,
    Industry.ELECTRIC_UTILITIES: Sector.UTILITIES,
    Industry.BANKS: Sector.FINANCIALS,
    Industry.INSURANCE: Sector.FINANCIALS,
    Industry.PHARMACEUTICALS: Sector.HEALTH_CARE,
    Industry.MEDICAL_DEVICES: Sector.HEALTH_CARE,
    Industry.OIL_GAS: Sector.ENERGY,
}

_SENIORITY_LABELS = {
    Seniority.SENIOR_SECURED: "Sénior garantizada",
    Seniority.SENIOR_UNSECURED: "Sénior no garantizada",
    Seniority.SENIOR_NON_PREFERRED: "Sénior no preferente",
    Seniority.SUBORDINATED: "Subordinada",
    Seniority.JUNIOR_SUBORDINATED: "Subordinada júnior (híbrida)",
}
