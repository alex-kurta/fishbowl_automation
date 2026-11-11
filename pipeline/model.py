from dataclasses import dataclass, field


@dataclass
class Address:
    name: str = ""
    company: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = "United States"
    residential: bool = False


@dataclass
class OrderLine:
    sku: str = ""
    description: str = ""
    quantity: int = 0
    unit_price: float = 0.0
    product_id: str = ""
    selected_option: str = ""
    note: str = ""
    alert: str = ""


@dataclass
class Order:
    order_number: str = ""
    date: str = ""
    customer_name: str = ""
    customer_contact: str = ""
    billing: Address = field(default_factory=Address)
    shipping: Address = field(default_factory=Address)
    carrier: str = ""
    carrier_service: str = ""
    shipping_terms: str = ""
    payment_terms: str = ""
    payment_method: str = ""
    po_number: str = ""
    lines: list[OrderLine] = field(default_factory=list)
    subtotal: float = 0.0
    shipping_cost: float = 0.0
    total: float = 0.0
    note: str = ""
    email: str = ""
    phone: str = ""
