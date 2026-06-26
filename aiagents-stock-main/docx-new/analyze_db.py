import sqlite3
import json

# 连接数据库
conn = sqlite3.connect('database/files/stock_analysis.db')
cursor = conn.cursor()

# 获取所有表名
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("=== 数据库表结构分析 ===")
print("\n1. 所有表名:")
for table in tables:
    print(f"   - {table[0]}")

# 分析每个表的结构
table_structures = {}
print("\n2. 表结构详情:")
for table_name in [t[0] for t in tables]:
    print(f"\n   表: {table_name}")
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    table_structures[table_name] = []
    for col in columns:
        col_info = {
            "id": col[0],
            "name": col[1],
            "type": col[2],
            "notnull": col[3],
            "default": col[4],
            "pk": col[5]
        }
        table_structures[table_name].append(col_info)
        print(f"     - {col[1]} ({col[2]}) {'[PK]' if col[5] else ''}")

# 查找外键关系
print("\n3. 外键关系:")
has_foreign_keys = False
for table_name in [t[0] for t in tables]:
    cursor.execute(f"PRAGMA foreign_key_list({table_name});")
    foreign_keys = cursor.fetchall()
    if foreign_keys:
        has_foreign_keys = True
        print(f"\n   表: {table_name}")
        for fk in foreign_keys:
            print(f"     - 从 {fk[3]} 引用 {fk[2]}.{fk[4]}")

if not has_foreign_keys:
    print("   未发现外键关系")

# 查找索引
print("\n4. 索引信息:")
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index';")
indexes = cursor.fetchall()
if indexes:
    for idx in indexes:
        print(f"   - {idx[0]}: {idx[1]}")
else:
    print("   未发现索引")

# 保存结构到文件
with open('db_structure.json', 'w', encoding='utf-8') as f:
    json.dump(table_structures, f, ensure_ascii=False, indent=2)

print("\n5. 结构已保存到 db_structure.json 文件")

# 关闭连接
conn.close()
print("\n分析完成!")
