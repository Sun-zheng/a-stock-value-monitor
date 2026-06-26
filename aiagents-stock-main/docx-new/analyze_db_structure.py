import sqlite3
import os

def analyze_database(db_path):
    """
    分析SQLite数据库结构
    
    Args:
        db_path: 数据库文件路径
        
    Returns:
        dict: 包含数据库表结构的字典
    """
    if not os.path.exists(db_path):
        return {"error": f"数据库文件不存在: {db_path}"}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        result = {
            "database": os.path.basename(db_path),
            "tables": []
        }
        
        for table in tables:
            table_name = table[0]
            
            # 获取表结构
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            table_info = {
                "name": table_name,
                "columns": []
            }
            
            for column in columns:
                col_info = {
                    "id": column[0],
                    "name": column[1],
                    "type": column[2],
                    "notnull": column[3],
                    "dflt_value": column[4],
                    "pk": column[5]
                }
                table_info["columns"].append(col_info)
            
            # 获取索引信息
            cursor.execute(f"PRAGMA index_list({table_name});")
            indexes = cursor.fetchall()
            
            if indexes:
                table_info["indexes"] = []
                for idx in indexes:
                    idx_info = {
                        "id": idx[0],
                        "name": idx[1],
                        "unique": idx[2],
                        "origin": idx[3],
                        "partial": idx[4]
                    }
                    table_info["indexes"].append(idx_info)
            
            result["tables"].append(table_info)
        
        conn.close()
        return result
        
    except Exception as e:
        return {"error": f"分析数据库时出错: {str(e)}"}

def main():
    """
    主函数，分析所有数据库文件
    """
    db_files = [
        "main_force_batch.db",
        "low_price_bull_monitor.db",
        "profit_growth_monitor.db",
        "database/files/stock_analysis.db",
        "database/files/longhubang.db",
        "database/files/sector_strategy.db",
        "database/files/smart_monitor.db",
        "database/files/stock_monitor.db",
        "database/files/portfolio_stocks.db"
    ]
    
    for db_file in db_files:
        print(f"\n=== 分析数据库: {db_file} ===")
        result = analyze_database(db_file)
        
        if "error" in result:
            print(f"错误: {result['error']}")
        else:
            print(f"数据库: {result['database']}")
            print(f"表数量: {len(result['tables'])}")
            
            for table in result['tables']:
                print(f"\n表: {table['name']}")
                print("字段:")
                for col in table['columns']:
                    pk_mark = " (PK)" if col['pk'] else ""
                    notnull_mark = " NOT NULL" if col['notnull'] else ""
                    default = f" DEFAULT {col['dflt_value']}" if col['dflt_value'] else ""
                    print(f"  {col['name']} {col['type']}{notnull_mark}{default}{pk_mark}")
                
                if "indexes" in table:
                    print("索引:")
                    for idx in table['indexes']:
                        unique_mark = " (唯一)" if idx['unique'] else ""
                        print(f"  {idx['name']}{unique_mark}")

if __name__ == "__main__":
    main()
