
import logging
import math
import os
import re
import time
import unicodedata
from collections import OrderedDict
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product"

HEADERS = {
    "User-Agent": os.environ.get(
        "OPEN_FOOD_FACTS_USER_AGENT",
        "Nutrivoq/1.0 (personal food tracking application)"
    ),
    "Accept": "application/json"
}

PAGE_SIZE = 20
SEARCH_LIMIT = 50
MAXIMUM_API_PAGES = 10

CACHE_DURATION = 3600
CACHE_LIMIT = 200

PRODUCT_FIELDS = (
    "code,product_name,product_name_en,brands,"
    "nutriments,image_front_small_url"
)

logger = logging.getLogger(__name__)

cache = OrderedDict()
cache_lock = Lock()

session = requests.Session()

retry_strategy = Retry(
    total=1,
    connect=1,
    read=0,
    status=1,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET"],
    respect_retry_after_header=True
)

adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)


def get_cached(key):
    with cache_lock:
        if key not in cache:
            return None

        timestamp, value = cache[key]

        if time.time() - timestamp > CACHE_DURATION:
            del cache[key]
            return None

        cache.move_to_end(key)

        return value


def save_cached(key, value):
    with cache_lock:
        cache[key] = (time.time(), value)
        cache.move_to_end(key)

        while len(cache) > CACHE_LIMIT:
            cache.popitem(last=False)


def normalize_text(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value or "").casefold()
    )

    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )

    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def format_product(product):
    if not isinstance(product, dict):
        return None

    nutrition = product.get("nutriments") or {}

    name = (
        product.get("product_name")
        or product.get("product_name_en")
        or ""
    )

    barcode = str(
        product.get("code") or product.get("_id") or ""
    )

    if not name.strip():
        return None

    if not barcode.isdigit():
        return None

    nutrient_names = (
        "energy-kcal_100g",
        "proteins_100g",
        "carbohydrates_100g",
        "fat_100g"
    )

    try:
        values = [
            float(nutrition[name])
            for name in nutrient_names
        ]

    except (KeyError, ValueError, TypeError):
        return None

    if not all(
        math.isfinite(value) and 0 <= value <= 100000
        for value in values
    ):
        return None

    return {
        "barcode": barcode,
        "name": name.strip(),
        "brand": product.get("brands") or "",
        "image": product.get("image_front_small_url") or "",
        "calories": round(values[0], 1),
        "protein": round(values[1], 1),
        "carbs": round(values[2], 1),
        "fat": round(values[3], 1)
    }


def calculate_relevance(product, search_query):
    name = normalize_text(product["name"])
    brand = normalize_text(product["brand"])
    query = normalize_text(search_query)

    if not query:
        return 0

    name_words = name.split()
    query_words = query.split()

    score = 0

    if name == query:
        score += 1000

    elif name.startswith(query + " "):
        score += 800

    elif name.endswith(" " + query):
        score += 700

    elif query in name_words:
        score += 600

    elif query in name:
        score += 300

    elif all(word in name_words for word in query_words):
        score += 250

    elif all(word in name for word in query_words):
        score += 100

    if query in brand:
        score += 20

    if product.get("image"):
        score += 5

    score -= min(len(name_words), 20) * 2

    milk_queries = {"melk", "milk"}

    milk_types = {
        "volle",
        "halfvolle",
        "magere",
        "houdbare",
        "verse",
        "whole",
        "semi skimmed",
        "skimmed",
        "fresh"
    }

    if query in milk_queries:
        if name == query:
            score += 500

        if any(
            name == f"{milk_type} {query}"
            or name.startswith(f"{milk_type} {query} ")
            for milk_type in milk_types
        ):
            score += 450

        if name.startswith(query + " "):
            score += 200

        unrelated_categories = {
            "chocolade",
            "chocolate",
            "reep",
            "bar",
            "koek",
            "cookie",
            "biscuit",
            "skyr",
            "yoghurt",
            "yogurt",
            "pudding",
            "ijs",
            "ice cream"
        }

        if any(
            category in name_words
            for category in unrelated_categories
        ):
            score -= 500

    return score


def sort_products(products, search_query):
    return sorted(
        products,
        key=lambda product: (
            -calculate_relevance(product, search_query),
            normalize_text(product["name"]),
            product["barcode"]
        )
    )


def fetch_json(url, parameters=None):
    response = session.get(
        url,
        params=parameters,
        headers=HEADERS,
        timeout=(5, 12)
    )

    response.raise_for_status()

    return response.json()


def fetch_search_page(query, page):
    parameters = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page": page,
        "page_size": SEARCH_LIMIT,
        "fields": PRODUCT_FIELDS
    }

    return fetch_json(
        SEARCH_URL,
        parameters
    )


def create_search_state():
    return {
        "products": [],
        "next_api_page": 1,
        "has_more": True,
        "failed": False
    }


def get_ranked_products(search_query, minimum_results=20):
    query = search_query.strip()
    cache_key = ("ranked_search", query.casefold())

    cached = get_cached(cache_key)

    if cached is not None:
        state = {
            "products": cached["products"].copy(),
            "next_api_page": cached["next_api_page"],
            "has_more": cached["has_more"],
            "failed": False
        }
    else:
        state = create_search_state()

    products = state["products"]

    seen_barcodes = {
        product["barcode"]
        for product in products
    }

    while (
        len(products) < minimum_results
        and state["has_more"]
        and state["next_api_page"] <= MAXIMUM_API_PAGES
    ):
        api_page = state["next_api_page"]

        try:
            data = fetch_search_page(query, api_page)

            raw_products = data.get("products")

            if not isinstance(raw_products, list):
                raise ValueError("Unexpected search response")

        except (requests.RequestException, ValueError) as error:
            logger.warning(
                "Open Food Facts search page %s failed: %s",
                api_page,
                error
            )

            state["failed"] = True

            if not products:
                raise

            break

        for raw_product in raw_products:
            product = format_product(raw_product)

            if product is None:
                continue

            if product["barcode"] in seen_barcodes:
                continue

            seen_barcodes.add(product["barcode"])
            products.append(product)

        state["has_more"] = len(raw_products) >= SEARCH_LIMIT
        state["next_api_page"] += 1

    if state["next_api_page"] > MAXIMUM_API_PAGES:
        state["has_more"] = False

    state["products"] = sort_products(products, query)

    if not state["failed"]:
        save_cached(cache_key, {
            "products": state["products"],
            "next_api_page": state["next_api_page"],
            "has_more": state["has_more"]
        })

    return state


def search_products(search_query, page=1):
    query = search_query.strip()
    page = max(1, int(page))

    if not query:
        return {
            "products": [],
            "page": 1,
            "total_pages": 0,
            "total_results": 0
        }

    minimum_results = page * PAGE_SIZE

    state = get_ranked_products(
        query,
        minimum_results
    )

    products = state["products"]

    start_index = (page - 1) * PAGE_SIZE
    end_index = start_index + PAGE_SIZE

    total_results = len(products)

    total_pages = math.ceil(
        total_results / PAGE_SIZE
    )

    if state["has_more"] and not state["failed"]:
        total_pages = max(
            total_pages,
            page + 1
        )

    return {
        "products": products[start_index:end_index],
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results
    }


def get_product(barcode):
    barcode = str(barcode).strip()

    if not barcode.isdigit() or len(barcode) > 14:
        return None

    cache_key = ("product", barcode)

    cached = get_cached(cache_key)

    if cached is not None:
        return cached

    data = fetch_json(
        f"{PRODUCT_URL}/{barcode}",
        {"fields": PRODUCT_FIELDS}
    )

    if data.get("status") != 1:
        return None

    product = format_product(
        data.get("product") or {}
    )

    if product is not None:
        save_cached(cache_key, product)

    return product
