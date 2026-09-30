"""
Pydantic models for the Home Finder & Optimizer.
Defines the core data schema for properties, search specs, and valuation results.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class PropertyType(str, Enum):
    SINGLE_FAMILY = "single_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    MULTI_FAMILY = "multi_family"
    LAND = "land"
    OTHER = "other"


class PropertyCondition(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class Property(BaseModel):
    """Core property record."""
    id: str
    address: str
    city: str
    state: str
    zip_code: str
    county: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Listing details
    list_price: float
    property_type: PropertyType = PropertyType.SINGLE_FAMILY
    bedrooms: int = 0
    bathrooms: float = 0.0
    sqft: int = 0
    lot_sqft: Optional[int] = None
    year_built: Optional[int] = None
    stories: Optional[int] = None
    garage_spaces: Optional[int] = None
    condition: PropertyCondition = PropertyCondition.UNKNOWN

    # Features
    has_pool: bool = False
    has_basement: bool = False
    has_fireplace: bool = False
    has_central_air: bool = False
    has_garage: bool = False
    hoa_fee: Optional[float] = None

    # Listing metadata
    days_on_market: Optional[int] = None
    listing_date: Optional[datetime] = None
    source: str = "unknown"
    url: Optional[str] = None
    image_url: Optional[str] = None

    # Tax / financial
    annual_tax: Optional[float] = None
    tax_assessed_value: Optional[float] = None


class SearchSpecs(BaseModel):
    """User search criteria."""
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    min_bathrooms: Optional[float] = None
    max_bathrooms: Optional[float] = None
    min_sqft: Optional[int] = None
    max_sqft: Optional[int] = None
    property_types: Optional[List[PropertyType]] = None
    max_year_built: Optional[int] = None
    min_year_built: Optional[int] = None
    max_hoa: Optional[float] = None
    must_have_pool: bool = False
    must_have_basement: bool = False
    must_have_garage: bool = False
    max_days_on_market: Optional[int] = None
    sort_by: str = "deal_score"  # deal_score, price_asc, price_desc, newest


class PriceVariable(BaseModel):
    """A single variable contributing to the estimated value."""
    name: str
    category: str  # location, physical, features, market
    raw_impact: float  # dollar amount impact on price
    percentage_impact: float  # percentage impact
    description: str
    comparable_avg: Optional[float] = None  # average value in comparable properties


class ValuationResult(BaseModel):
    """Full valuation of a single property."""
    property_id: str
    estimated_value: float
    confidence_score: float = Field(ge=0.0, le=1.0)  # 0-1
    price_per_sqft: float
    market_price_per_sqft: float  # area average

    # Price breakdown
    base_land_value: float
    structure_value: float
    feature_adjustments: float
    location_premium: float
    market_adjustment: float

    # Variable-by-variable breakdown
    variables: List[PriceVariable]

    # Comparison
    list_price: float
    price_difference: float  # estimated - list (positive = underpriced)
    price_difference_pct: float


class DealScore(BaseModel):
    """Optimizer output for a property."""
    property: Property
    valuation: ValuationResult
    deal_score: float = Field(ge=0.0, le=100.0)
    deal_grade: str  # A+, A, B+, B, C+, C, D, F
    reasons: List[str]
    risk_factors: List[str]
    monthly_payment_estimate: Optional[float] = None
    estimated_roi_5yr: Optional[float] = None


class MarketStats(BaseModel):
    """Market-level statistics for an area."""
    area_name: str
    median_price: float
    avg_price_per_sqft: float
    median_days_on_market: int
    total_listings: int
    avg_year_built: int


class SearchResponse(BaseModel):
    """Full search response."""
    deals: List[DealScore]
    market_stats: MarketStats
    total_results: int
    search_specs: SearchSpecs


class LoanQuoteRequest(BaseModel):
    """Borrower + property inputs for a mortgage quote."""
    home_price: float = Field(gt=0)
    down_payment: float = Field(ge=0)
    annual_income: float = Field(ge=0)
    monthly_debts: float = Field(ge=0, default=0)
    credit_score: int = Field(ge=300, le=850)
    property_type: str = "primary"          # primary | second_home | investment
    loan_term: int = 30                     # 30 | 20 | 15 | 10
    loan_type: str = "conventional"         # conventional | fha | va | usda
    annual_property_tax: float = Field(ge=0, default=0)
    annual_home_insurance: float = Field(ge=0, default=0)
    monthly_hoa: float = Field(ge=0, default=0)
    base_rate_override: Optional[float] = None


class LenderQuote(BaseModel):
    name: str
    rate: float
    monthly_payment: float


class LoanQuoteResponse(BaseModel):
    """Full prorated mortgage quote."""
    eligible: bool
    base_rate: float
    base_rate_source: str                   # fred | cache | fallback | override
    interest_rate: Optional[float] = None
    apr: Optional[float] = None
    loan_amount: float
    down_payment: float
    down_payment_percent: float
    monthly_pi: float
    monthly_tax: float
    monthly_insurance: float
    monthly_hoa: float
    total_monthly: float
    dti: float
    max_affordable_home: float
    lender_quotes: List[LenderQuote]
    ineligible_reason: Optional[str] = None
