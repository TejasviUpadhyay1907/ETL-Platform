"""
Development seed data generator.

Populates the database with realistic retail data for local development and
dashboard testing. Uses a fixed random seed for deterministic, repeatable
output — the same script always produces the same data.

Target volumes:
    100  Suppliers
    2000 Products
    5000 Customers
    3000 Inventory records
    50000 Orders  (with line items)
    20000 Payments
    Pipeline run history (50 runs)

Usage:
    python scripts/seed_data.py                  # full seed
    python scripts/seed_data.py --truncate       # clear tables first
    python scripts/seed_data.py --count small    # 10% volume (quick dev)
"""

import argparse
import random
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.core.config import get_config
from app.database.engine import get_session
from app.database.models.operational.customers import Customer
from app.database.models.operational.inventory import Inventory
from app.database.models.operational.orders import Order, OrderItem
from app.database.models.operational.payments import Payment
from app.database.models.operational.products import Product
from app.database.models.operational.suppliers import Supplier
from app.database.models.pipeline.pipeline_run import PipelineRun
from app.logging.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Deterministic seed — same output every run
# ─────────────────────────────────────────────────────────────────────────────
RANDOM_SEED = 42
rng = random.Random(RANDOM_SEED)

# ─────────────────────────────────────────────────────────────────────────────
# Reference data pools
# ─────────────────────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "James","Mary","John","Patricia","Robert","Jennifer","Michael","Linda",
    "William","Barbara","David","Elizabeth","Richard","Susan","Joseph","Jessica",
    "Thomas","Sarah","Charles","Karen","Emma","Liam","Olivia","Noah","Ava","Sophia",
    "Lucas","Mia","Mason","Isabella","Ethan","Charlotte","Logan","Amelia","Oliver",
    "Harper","Elijah","Evelyn","Aiden","Abigail","Daniel","Emily","Henry","Ella",
    "Alexander","Madison","Sebastian","Scarlett","Jackson","Victoria",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson",
    "Anderson","Taylor","Thomas","Hernandez","Moore","Martin","Jackson","Thompson",
    "White","Lopez","Lee","Harris","Clark","Lewis","Robinson","Walker","Hall","Young",
    "Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores","Green","Adams",
    "Nelson","Baker","Carter","Mitchell","Perez","Roberts","Turner","Phillips",
    "Campbell","Parker","Evans","Edwards","Collins",
]
CITIES_US = [
    ("New York","NY","US"),("Los Angeles","CA","US"),("Chicago","IL","US"),
    ("Houston","TX","US"),("Phoenix","AZ","US"),("Philadelphia","PA","US"),
    ("San Antonio","TX","US"),("San Diego","CA","US"),("Dallas","TX","US"),
    ("San Jose","CA","US"),("Austin","TX","US"),("Jacksonville","FL","US"),
    ("Fort Worth","TX","US"),("Columbus","OH","US"),("Charlotte","NC","US"),
    ("Indianapolis","IN","US"),("San Francisco","CA","US"),("Seattle","WA","US"),
    ("Denver","CO","US"),("Washington","DC","US"),("Boston","MA","US"),
    ("Nashville","TN","US"),("Las Vegas","NV","US"),("Portland","OR","US"),
    ("Memphis","TN","US"),("Louisville","KY","US"),("Atlanta","GA","US"),
    ("Miami","FL","US"),("Minneapolis","MN","US"),("Raleigh","NC","US"),
]
CITIES_INTL = [
    ("London","ENG","GB"),("Toronto","ON","CA"),("Sydney","NSW","AU"),
    ("Melbourne","VIC","AU"),("Vancouver","BC","CA"),("Auckland","AUK","NZ"),
    ("Dublin","L","IE"),("Edinburgh","SCO","GB"),("Manchester","ENG","GB"),
    ("Calgary","AB","CA"),
]
ALL_CITIES = CITIES_US * 8 + CITIES_INTL  # weight toward US

DOMAINS = ["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com",
           "protonmail.com","company.com","business.net","enterprise.org"]

CATEGORIES = {
    "Electronics":    ["Smartphones","Laptops","Tablets","Accessories","Audio","Cameras"],
    "Apparel":        ["Men's Clothing","Women's Clothing","Footwear","Bags","Jewelry"],
    "Home & Garden":  ["Furniture","Bedding","Kitchen","Garden","Decor","Lighting"],
    "Sports":         ["Fitness","Outdoor","Team Sports","Water Sports","Cycling"],
    "Health":         ["Vitamins","Personal Care","Medical Devices","Wellness"],
    "Food & Grocery": ["Beverages","Snacks","Dairy","Produce","Canned Goods"],
    "Automotive":     ["Parts","Accessories","Tools","Care Products"],
    "Office":         ["Supplies","Furniture","Technology","Paper Products"],
}

BRANDS = [
    "TechCore","UrbanWear","HomePro","SportMax","HealthPlus","FreshFarm",
    "AutoParts Co","OfficeSmart","EliteGear","PrimeCraft","NextGen","ValueBrand",
    "ProSeries","BasicLine","LuxuryPick","EcoChoice","FastShip","BudgetBest",
]

PAYMENT_METHODS = [
    "credit_card","credit_card","credit_card",  # weighted highest
    "debit_card","debit_card",
    "paypal","stripe",
    "bank_transfer","store_credit","apple_pay",
]

ORDER_STATUSES = [
    "delivered","delivered","delivered","delivered",  # most are delivered
    "shipped","processing","pending","cancelled","refunded","on_hold",
]

SUPPLIER_NAMES = [
    "Global Trade Partners","Pacific Rim Imports","Atlantic Supply Co",
    "Midwest Distribution Hub","Southern Logistics Group","Northeast Vendors Inc",
    "Western Supply Chain","Central Procurement LLC","Premier Wholesale Group",
    "National Distribution Corp","Allied Products Inc","United Merchandise Co",
    "Continental Goods Ltd","Transatlantic Trading Co","Horizon Supply Group",
    "Summit Wholesale Partners","Valley Distribution Inc","Coastal Logistics Co",
    "Mountain Supply Group","Desert Trade Partners","Forest Products Inc",
    "Plains Distribution LLC","Harbor Trading Co","River Supply Corp",
    "Lake Merchandise Group",
]

WAREHOUSES = ["WH-EAST-01","WH-WEST-01","WH-CENTRAL-01","WH-SOUTH-01","WH-NORTH-01"]


# ─────────────────────────────────────────────────────────────────────────────
# Generator helpers
# ─────────────────────────────────────────────────────────────────────────────

def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))


def random_email(first: str, last: str) -> str:
    domain = rng.choice(DOMAINS)
    sep = rng.choice([".", "_", ""])
    suffix = rng.randint(1, 999) if rng.random() < 0.4 else ""
    return f"{first.lower()}{sep}{last.lower()}{suffix}@{domain}"


def random_phone() -> str:
    return f"+1{rng.randint(200,999)}{rng.randint(200,999)}{rng.randint(1000,9999)}"


def random_postal() -> str:
    return f"{rng.randint(10000,99999)}"


def supplier_code(n: int) -> str:
    return f"SUP-{n:05d}"


def product_sku(category: str, n: int) -> str:
    prefix = category[:3].upper()
    return f"{prefix}-{n:06d}"


def order_number(n: int) -> str:
    return f"ORD-2025-{n:06d}"


# ─────────────────────────────────────────────────────────────────────────────
# Seeder functions
# ─────────────────────────────────────────────────────────────────────────────

def seed_suppliers(session: Session, count: int) -> list[Supplier]:
    logger.info(f"Seeding {count} suppliers...")
    suppliers = []
    pool = SUPPLIER_NAMES * (count // len(SUPPLIER_NAMES) + 1)
    for i in range(1, count + 1):
        city_info = rng.choice(ALL_CITIES)
        sup = Supplier(
            supplier_code=supplier_code(i),
            company_name=f"{pool[i-1]} {rng.randint(1,99)}",
            contact_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            contact_email=f"procurement{i}@{rng.choice(DOMAINS)}",
            contact_phone=random_phone(),
            address_line1=f"{rng.randint(1,9999)} {rng.choice(LAST_NAMES)} St",
            city=city_info[0],
            state=city_info[1],
            country=city_info[2],
            postal_code=random_postal(),
            payment_terms=rng.choice(["net_30","net_30","net_60","net_90","prepaid"]),
            currency="USD",
            rating=Decimal(str(round(rng.uniform(2.5, 5.0), 2))),
            status=rng.choice(["active","active","active","active","inactive","on_hold"]),
            created_by="seed_script",
        )
        session.add(sup)
        suppliers.append(sup)
    session.flush()
    logger.info(f"  {count} suppliers created")
    return suppliers


def seed_products(session: Session, count: int, suppliers: list[Supplier]) -> list[Product]:
    logger.info(f"Seeding {count} products...")
    products = []
    cat_names = list(CATEGORIES.keys())
    n = 0
    for cat in cat_names:
        per_cat = count // len(cat_names)
        subcats = CATEGORIES[cat]
        for _ in range(per_cat):
            n += 1
            price = Decimal(str(round(rng.uniform(4.99, 999.99), 2)))
            cost = Decimal(str(round(float(price) * rng.uniform(0.3, 0.65), 2)))
            prod = Product(
                sku=product_sku(cat, n),
                product_name=f"{rng.choice(BRANDS)} {rng.choice(subcats)} {rng.randint(100,999)}",
                short_name=f"{rng.choice(subcats)} {rng.randint(10,99)}",
                brand=rng.choice(BRANDS),
                category=cat,
                subcategory=rng.choice(subcats),
                unit_price=price,
                unit_cost=cost,
                currency="USD",
                weight_grams=rng.randint(50, 5000),
                unit_of_measure="each",
                status=rng.choice(["active","active","active","active","inactive","discontinued"]),
                is_taxable=rng.random() > 0.1,
                tax_rate=Decimal("0.0825"),
                supplier_id=rng.choice(suppliers).id,
                created_by="seed_script",
            )
            session.add(prod)
            products.append(prod)
    session.flush()
    logger.info(f"  {n} products created")
    return products


def seed_inventory(session: Session, count: int, products: list[Product]) -> None:
    logger.info(f"Seeding {count} inventory records...")
    sampled = rng.sample(products, min(count, len(products)))
    for prod in sampled:
        wh = rng.choice(WAREHOUSES)
        qty = rng.randint(0, 500)
        inv = Inventory(
            product_id=prod.id,
            warehouse_id=wh,
            quantity_on_hand=qty,
            reserved_quantity=rng.randint(0, min(qty, 50)),
            reorder_point=rng.randint(5, 50),
            reorder_quantity=rng.randint(20, 200),
            unit_cost=prod.unit_cost,
            currency="USD",
            created_by="seed_script",
        )
        session.add(inv)
    session.flush()
    logger.info(f"  {len(sampled)} inventory records created")


def seed_customers(session: Session, count: int) -> list[Customer]:
    logger.info(f"Seeding {count} customers...")
    customers = []
    emails_used: set[str] = set()
    dob_start = date(1950, 1, 1)
    dob_end = date(2005, 12, 31)
    for _ in range(count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        # Ensure unique email
        for _ in range(5):
            email = random_email(first, last)
            if email not in emails_used:
                emails_used.add(email)
                break
        else:
            email = f"user{len(emails_used)+1}@example.com"
            emails_used.add(email)

        city_info = rng.choice(ALL_CITIES)
        cust = Customer(
            first_name=first,
            last_name=last,
            email=email,
            phone=random_phone() if rng.random() > 0.2 else None,
            gender=rng.choice(["male","female","non_binary","prefer_not_to_say",None]),
            date_of_birth=random_date(dob_start, dob_end) if rng.random() > 0.3 else None,
            address_line1=f"{rng.randint(1,9999)} {rng.choice(LAST_NAMES)} Ave",
            city=city_info[0],
            state=city_info[1],
            country=city_info[2],
            postal_code=random_postal(),
            customer_segment=rng.choice(["standard","standard","standard","silver","gold","platinum","vip"]),
            status=rng.choice(["active","active","active","active","inactive","suspended"]),
            source_system=rng.choice(["web_store","mobile_app","crm_import","pos"]),
            created_by="seed_script",
        )
        session.add(cust)
        customers.append(cust)
    session.flush()
    logger.info(f"  {count} customers created")
    return customers


def seed_orders(
    session: Session,
    count: int,
    customers: list[Customer],
    products: list[Product],
) -> list[Order]:
    logger.info(f"Seeding {count} orders with line items...")
    orders = []
    order_start = date(2023, 1, 1)
    order_end = date(2025, 6, 30)

    for i in range(1, count + 1):
        customer = rng.choice(customers)
        order_date = random_date(order_start, order_end)
        status = rng.choice(ORDER_STATUSES)
        n_items = rng.randint(1, 6)
        selected_products = rng.sample(products, min(n_items, len(products)))

        subtotal = Decimal("0")
        items: list[OrderItem] = []
        for prod in selected_products:
            qty = rng.randint(1, 10)
            price = prod.unit_price
            discount = Decimal("0")
            if rng.random() < 0.15:  # 15% of lines get a discount
                discount = (price * Decimal(str(round(rng.uniform(0.05, 0.25), 2)))).quantize(Decimal("0.01"))
            line_total = (price * qty) - discount
            subtotal += line_total
            items.append(OrderItem(
                product_id=prod.id,
                quantity=qty,
                unit_price_at_sale=price,
                discount_amount=discount,
                line_total=line_total,
            ))

        discount_order = Decimal("0")
        if rng.random() < 0.1:
            discount_order = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
        tax = ((subtotal - discount_order) * Decimal("0.0825")).quantize(Decimal("0.01"))
        shipping = Decimal(str(round(rng.uniform(0, 19.99), 2))) if rng.random() > 0.3 else Decimal("0")
        total = subtotal - discount_order + tax + shipping

        city_info = rng.choice(ALL_CITIES)
        shipped_date = (order_date + timedelta(days=rng.randint(1, 5))) if status in ("shipped","delivered") else None
        delivered_date = (shipped_date + timedelta(days=rng.randint(1, 7))) if status == "delivered" and shipped_date else None

        order = Order(
            order_number=order_number(i),
            customer_id=customer.id,
            order_date=order_date,
            shipped_date=shipped_date,
            delivered_date=delivered_date,
            subtotal=subtotal.quantize(Decimal("0.0001")),
            discount_amount=discount_order.quantize(Decimal("0.0001")),
            tax_amount=tax.quantize(Decimal("0.0001")),
            shipping_amount=shipping.quantize(Decimal("0.0001")),
            order_total=total.quantize(Decimal("0.0001")),
            currency="USD",
            status=status,
            payment_status="paid" if status in ("delivered","shipped") else "unpaid",
            fulfillment_channel=rng.choice(["standard","express","click_and_collect"]),
            shipping_address_line1=f"{rng.randint(1,9999)} {rng.choice(LAST_NAMES)} Blvd",
            shipping_city=city_info[0],
            shipping_state=city_info[1],
            shipping_country=city_info[2],
            shipping_postal_code=random_postal(),
            source_system=rng.choice(["web_store","mobile_app","pos","api"]),
            created_by="seed_script",
        )
        for item in items:
            order.items.append(item)
        session.add(order)
        orders.append(order)

        # Flush every 2000 records to avoid huge memory accumulation
        if i % 2000 == 0:
            session.flush()
            logger.info(f"  ... {i}/{count} orders flushed")

    session.flush()
    logger.info(f"  {count} orders created")
    return orders


def seed_payments(session: Session, count: int, orders: list[Order]) -> None:
    logger.info(f"Seeding {count} payments...")
    # Only create payments for orders that have been paid
    paid_orders = [o for o in orders if o.payment_status == "paid"]
    if not paid_orders:
        paid_orders = orders[:count]

    # Pick orders to attach payments to (some orders get multiple payments)
    target_orders = rng.choices(paid_orders, k=min(count, len(paid_orders) * 2))[:count]

    for i, order in enumerate(target_orders):
        method = rng.choice(PAYMENT_METHODS)
        pay_date = order.order_date + timedelta(days=rng.randint(0, 3))
        amount = order.order_total if rng.random() > 0.05 else order.order_total / 2

        payment = Payment(
            order_id=order.id,
            transaction_type="payment",
            transaction_status=rng.choice(["settled","settled","settled","captured","failed"]),
            payment_method=method,
            payment_date=pay_date,
            amount=amount.quantize(Decimal("0.0001")),
            currency="USD",
            payment_gateway=rng.choice(["stripe","paypal","adyen","square",None]),
            gateway_reference=str(uuid.uuid4()) if rng.random() > 0.05 else None,
            card_last_four=f"{rng.randint(1000,9999)}" if method in ("credit_card","debit_card") else None,
            card_brand=rng.choice(["visa","mastercard","amex","discover"]) if method in ("credit_card","debit_card") else None,
            created_by="seed_script",
        )
        session.add(payment)

        if i % 2000 == 0 and i > 0:
            session.flush()
            logger.info(f"  ... {i}/{count} payments flushed")

    session.flush()
    logger.info(f"  {count} payments created")


def seed_pipeline_runs(session: Session, count: int = 50) -> None:
    logger.info(f"Seeding {count} pipeline run records...")
    dataset_types = ["orders","customers","products","inventory","suppliers","payments"]
    statuses = ["completed","completed","completed","completed","failed","partial"]
    start_dt = datetime(2025, 1, 1, 8, 0, 0)

    for i in range(1, count + 1):
        ds = rng.choice(dataset_types)
        status = rng.choice(statuses)
        total = rng.randint(1000, 50000)
        valid = int(total * rng.uniform(0.85, 0.99))
        invalid = total - valid
        loaded = int(valid * rng.uniform(0.96, 1.0))
        duration = round(rng.uniform(15.0, 300.0), 3)
        quality = round((valid / total) * 100, 2)
        started = start_dt + timedelta(days=i, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))

        run = PipelineRun(
            run_number=f"{started.strftime('%Y%m%d')}-{i:04d}",
            pipeline_name=f"{ds}_pipeline",
            dataset_type=ds,
            started_at=started,
            completed_at=started + timedelta(seconds=duration),
            duration_seconds=Decimal(str(duration)),
            status=status,
            total_records=total,
            valid_records=valid,
            invalid_records=invalid,
            cleaned_records=valid,
            loaded_records=loaded,
            failed_records=total - loaded,
            warning_count=rng.randint(0, 50),
            quality_score=Decimal(str(quality)),
            triggered_by=rng.choice(["scheduler","api_key","manual"]),
            trigger_type=rng.choice(["scheduled","manual","api"]),
            execution_host="etl-worker-01",
        )
        session.add(run)

    session.flush()
    logger.info(f"  {count} pipeline runs created")


# ─────────────────────────────────────────────────────────────────────────────
# Truncation helper
# ─────────────────────────────────────────────────────────────────────────────

def truncate_tables(session: Session) -> None:
    """Truncate all operational and pipeline tables (CASCADE)."""
    logger.warning("Truncating all seed tables...")
    from sqlalchemy import text
    tables = [
        "data_quality_scores","cleaning_logs","validation_failures","audit_logs",
        "stage_results","ingestion_events","pipeline_runs",
        "payments","order_items","orders","inventory","products","customers","suppliers",
    ]
    for table in tables:
        session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
    session.commit()
    logger.info("All tables truncated")


# ─────────────────────────────────────────────────────────────────────────────
# Volume presets
# ─────────────────────────────────────────────────────────────────────────────

VOLUMES = {
    "full":  {"suppliers":100,"products":2000,"customers":5000,"inventory":3000,"orders":50000,"payments":20000},
    "small": {"suppliers":10, "products":200, "customers":500, "inventory":300, "orders":5000, "payments":2000},
    "tiny":  {"suppliers":5,  "products":50,  "customers":100, "inventory":80,  "orders":500,  "payments":200},
}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed development database")
    parser.add_argument("--truncate", action="store_true", help="Truncate all tables before seeding")
    parser.add_argument("--count", choices=["full","small","tiny"], default="small",
                        help="Data volume preset (default: small)")
    args = parser.parse_args()

    vol = VOLUMES[args.count]
    logger.info(f"Starting seed with volume={args.count!r}: {vol}")

    with get_session() as session:
        if args.truncate:
            truncate_tables(session)

        suppliers = seed_suppliers(session, vol["suppliers"])
        products = seed_products(session, vol["products"], suppliers)
        seed_inventory(session, vol["inventory"], products)
        customers = seed_customers(session, vol["customers"])
        orders = seed_orders(session, vol["orders"], customers, products)
        seed_payments(session, vol["payments"], orders)
        seed_pipeline_runs(session, count=50)

        session.commit()

    logger.info("Seed complete.")
    print(f"\nSeed summary ({args.count}):")
    for k, v in vol.items():
        print(f"  {k:12s}: {v:,}")


if __name__ == "__main__":
    main()
