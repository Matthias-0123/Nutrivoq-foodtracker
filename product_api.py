
import requests

API_URL = "https://world.openfoodfacts.org/cgi/search.pl"

HEADERS = {
    "User-Agent": "JumboFoodTracker/0.1 (contact: shawkimatthias@gmail.com)"
}


def search_products(search_query):
    if not search_query.strip():
        return []

    parameters = {
        "search_terms": search_query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 100,
        "tagtype_0": "brands",
        "tag_contains_0": "contains",
        "tag_0": "jumbo",
        "fields": "code,product_name,brands,nutriments"
    }

    response = requests.get(
        API_URL,
        params=parameters,
        headers=HEADERS,
        timeout=10
    )
    response.raise_for_status()

    products = []

    for product in response.json().get("products", []):
        brand = product.get("brands", "")
        name = product.get("product_name", "")
        nutrition = product.get("nutriments", {})

        if "jumbo" not in brand.lower():
            continue

        required_fields = (
            "energy-kcal_100g",
            "proteins_100g",
            "carbohydrates_100g",
            "fat_100g"
        )

        if not name or not all(field in nutrition for field in required_fields):
            continue

        products.append({
            "barcode": product.get("code", ""),
            "name": name,
            "brand": brand,
            "calories": nutrition["energy-kcal_100g"],
            "protein": nutrition["proteins_100g"],
            "carbs": nutrition["carbohydrates_100g"],
            "fat": nutrition["fat_100g"]
        })



    return products

def get_product(barcode):
    if not barcode.isdigit() or len(barcode) > 14:
        return None

    response = requests.get(
        f"https://world.openfoodfacts.org/api/v2/product/{barcode}",
        params={
            "fields": "code,product_name,brands,nutriments"
        },
        headers=HEADERS,
        timeout=10
    )
    response.raise_for_status()

    data = response.json()

    if data.get("status") != 1:
        return None

    product = data["product"]
    nutrition = product.get("nutriments", {})

    if "jumbo" not in product.get("brands", "").lower():
        return None

    fields = (
        "energy-kcal_100g",
        "proteins_100g",
        "carbohydrates_100g",
        "fat_100g"
    )

    if not all(field in nutrition for field in fields):
        return None

    return {
        "name": product.get("product_name", "Unknown Product"),
        "calories": float(nutrition["energy-kcal_100g"]),
        "protein": float(nutrition["proteins_100g"]),
        "carbs": float(nutrition["carbohydrates_100g"]),
        "fat": float(nutrition["fat_100g"])
    }

