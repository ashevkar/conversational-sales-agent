"""Data-quality checks on the Olist tables. Run after load_data.py.

Findings feed the assumptions documented in DESIGN.md.
"""
import duckdb

CHECKS = [
    ("Order status counts",
     "SELECT order_status, COUNT(*) AS n FROM orders GROUP BY 1 ORDER BY n DESC"),

    ("Orders per year",
     """SELECT year(CAST(order_purchase_timestamp AS TIMESTAMP)) AS yr, COUNT(*) AS n
        FROM orders GROUP BY 1 ORDER BY 1"""),

    ("Orders per month in 2016 and late 2018 (sparse edges?)",
     """SELECT strftime(CAST(order_purchase_timestamp AS TIMESTAMP), '%Y-%m') AS month, COUNT(*) AS n
        FROM orders
        WHERE CAST(order_purchase_timestamp AS TIMESTAMP) < '2017-01-01'
           OR CAST(order_purchase_timestamp AS TIMESTAMP) >= '2018-08-01'
        GROUP BY 1 ORDER BY 1"""),

    ("Orders with no line items, by status",
     """SELECT o.order_status, COUNT(*) AS n
        FROM orders o LEFT JOIN order_items i ON o.order_id = i.order_id
        WHERE i.order_id IS NULL GROUP BY 1 ORDER BY n DESC"""),

    ("Orders with no payment row",
     """SELECT COUNT(*) AS n FROM orders o
        WHERE NOT EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.order_id)"""),

    ("Payment total vs items total (price + freight)",
     """WITH items AS (SELECT order_id, SUM(price + freight_value) AS items_total
                       FROM order_items GROUP BY 1),
             pay AS (SELECT order_id, SUM(payment_value) AS paid
                     FROM payments GROUP BY 1)
        SELECT COUNT(*) AS orders_compared,
               SUM(CASE WHEN ABS(items_total - paid) > 1 THEN 1 ELSE 0 END) AS differ_by_more_than_1
        FROM items JOIN pay ON items.order_id = pay.order_id"""),

    ("Payment types",
     "SELECT payment_type, COUNT(*) AS n FROM payments GROUP BY 1 ORDER BY n DESC"),

    ("Products with no category",
     "SELECT COUNT(*) AS n FROM products WHERE product_category_name IS NULL"),

    ("Categories with no English translation",
     """SELECT DISTINCT p.product_category_name
        FROM products p
        LEFT JOIN category_translation t ON p.product_category_name = t.product_category_name
        WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL"""),

    ("customer_id vs customer_unique_id",
     """SELECT COUNT(DISTINCT customer_id) AS customer_ids,
               COUNT(DISTINCT customer_unique_id) AS unique_people
        FROM customers"""),

    ("Orders with more than one review",
     "SELECT COUNT(*) AS n FROM (SELECT order_id FROM reviews GROUP BY 1 HAVING COUNT(*) > 1)"),

    ("Delivered orders missing a delivery date",
     """SELECT COUNT(*) AS n FROM orders
        WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL"""),
]


def main():
    con = duckdb.connect("data/olist.duckdb", read_only=True)
    for title, sql in CHECKS:
        print(f"\n=== {title} ===")
        con.sql(sql).show()
    con.close()


if __name__ == "__main__":
    main()
