"""
Double Order Checker for Femzai
Checks for orders with the same shipping name + address in the last 7 days.
Posts matches to Slack so the shipping team can combine them.
"""

import os
import sys
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

SHOPIFY_STORE = os.environ["SHOPIFY_STORE"]
SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]
CHECK_WINDOW_MINUTES = int(os.environ.get("CHECK_WINDOW_MINUTES", "65"))


def get_orders(created_after):
    orders = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/orders.json"
    params = {
        "created_at_min": created_after.isoformat(),
        "status": "open",
        "limit": 250,
        "fields": "id,name,created_at,shipping_address,total_price,line_items,order_number",
    }

    while url:
        resp = requests.get(
            url,
            headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN},
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        orders.extend(data.get("orders", []))

        link = resp.headers.get("Link", "")
        if 'rel="next"' in link:
            url = link.split("<")[1].split(">")[0]
            params = {}
        else:
            url = None

    return orders


def normalize(text):
    if not text:
        return ""
    return " ".join(text.lower().strip().split())


def get_address_key(order):
    addr = order.get("shipping_address") or {}
    name = normalize(addr.get("name", ""))
    line1 = normalize(addr.get("address1", ""))
    zip_code = normalize(addr.get("zip", ""))

    if not name or not line1:
        return None

    return f"{name}|{line1}|{zip_code}"


def post_to_slack(message):
    resp = requests.post(SLACK_WEBHOOK, json={"text": message})
    resp.raise_for_status()


def format_order_line(order):
    created = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00"))
    date_str = created.strftime("%b %d, %H:%M")
    items = len(order.get("line_items", []))
    return (
        f"  • #{order.get('order_number', order['name'])} "
        f"- ${order['total_price']} "
        f"- {items} item{'s' if items != 1 else ''} "
        f"- {date_str}"
    )


def main():
    now = datetime.now(timezone.utc)
    check_since = now - timedelta(minutes=CHECK_WINDOW_MINUTES)
    seven_days_ago = now - timedelta(days=7)

    # Pull all open orders from the last 7 days
    all_orders = get_orders(seven_days_ago)
    print(f"Found {len(all_orders)} open orders in the last 7 days.")

    # Identify which ones are new (within the check window)
    new_orders = [
        o
        for o in all_orders
        if datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")) >= check_since
    ]

    if not new_orders:
        print("No new orders in check window. Done.")
        return

    print(f"{len(new_orders)} new order(s) to check.")

    # Group every order by normalized name + address + zip
    groups = defaultdict(list)
    for order in all_orders:
        key = get_address_key(order)
        if key:
            groups[key].append(order)

    # Notify on groups that have 2+ orders AND at least one is new
    notified = 0
    for key, orders in groups.items():
        if len(orders) < 2:
            continue

        has_new = any(
            datetime.fromisoformat(o["created_at"].replace("Z", "+00:00")) >= check_since
            for o in orders
        )
        if not has_new:
            continue

        orders.sort(key=lambda o: o["created_at"])

        addr = orders[0].get("shipping_address", {})
        name = addr.get("name", "Unknown")
        address_line = (
            f"{addr.get('address1', '')}, "
            f"{addr.get('city', '')}, "
            f"{addr.get('province_code', '')} {addr.get('zip', '')}"
        )

        order_lines = "\n".join(format_order_line(o) for o in orders)

        store_name = SHOPIFY_STORE.replace(".myshopify.com", "")
        admin_base = f"https://admin.shopify.com/store/{store_name}/orders"

        order_links = "\n".join(
            f"  <{admin_base}/{o['id']}|View #{o.get('order_number', o['name'])}>"
            for o in orders
        )

        message = (
            f":rotating_light: *Duplicate Orders Detected*\n"
            f"*Customer:* {name}\n"
            f"*Address:* {address_line}\n\n"
            f"*Orders ({len(orders)}):*\n{order_lines}\n\n"
            f"*Links:*\n{order_links}\n\n"
            f"_Consider combining these for shipping_"
        )

        post_to_slack(message)
        notified += 1
        print(f"Notified: {name} ({len(orders)} orders)")

    print(f"Done. {len(new_orders)} new orders checked, {notified} duplicate group(s) found.")


if __name__ == "__main__":
    main()
