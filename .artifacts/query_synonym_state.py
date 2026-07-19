import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

connection = sqlite3.connect("data/app.db")
connection.row_factory = sqlite3.Row

queries = {
    "versions": "SELECT id, file_id, version_no, description, created_time FROM taxonomy_version ORDER BY id",
    "nodes": """
        SELECT version_id, category_id, category_name, parent_id, path_names, syn_list
        FROM category_node
        WHERE category_name IN ('苹果手机', '华为手机', '小米手机', '电饭煲', '榨汁机', '苹果')
        ORDER BY version_id, category_id
    """,
    "issues": """
        SELECT id, version_id, issue_type, node_id, node_name, description,
               reason, evidence, source
        FROM diagnosis_issue
        WHERE node_name IN ('苹果手机', '华为手机', '小米手机', '电饭煲', '榨汁机', '苹果')
           OR description LIKE '%同义词%'
           OR evidence LIKE '%华为手机%'
        ORDER BY version_id, id
    """,
    "issue_counts": """
        SELECT version_id, issue_type, source, COUNT(*) AS count
        FROM diagnosis_issue
        GROUP BY version_id, issue_type, source
        ORDER BY version_id, issue_type, source
    """,
}

for label, query in queries.items():
    print(label)
    print(json.dumps([dict(row) for row in connection.execute(query)], ensure_ascii=False, indent=2))
