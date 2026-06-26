import os
import sqlite3

# 搜索所有.db文件
def find_db_files():
    db_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.db'):
                db_path = os.path.join(root, file).replace('\\', '/')
                db_files.append(db_path)
    return db_files

# 分析单个数据库
def analyze_db(db_path):
    result = {
        'path': db_path,
        'tables': [],
        'error': None
    }
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table_name in [t[0] for t in tables]:
            if table_name == 'sqlite_sequence':
                continue  # 跳过系统表
            
            # 获取表结构
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            
            table_info = {
                'name': table_name,
                'columns': []
            }
            
            for col in columns:
                col_info = {
                    'name': col[1],
                    'type': col[2],
                    'pk': col[5]
                }
                table_info['columns'].append(col_info)
            
            result['tables'].append(table_info)
        
        conn.close()
    except Exception as e:
        result['error'] = str(e)
    
    return result

# 主函数
def main():
    print("=== 股票智能分析系统数据库分析 ===")
    print("\n1. 查找所有数据库文件...")
    
    db_files = find_db_files()
    print(f"\n发现 {len(db_files)} 个数据库文件:")
    for db in db_files:
        print(f"   - {db}")
    
    print("\n2. 分析每个数据库的结构...")
    
    analysis_results = []
    for db_path in db_files:
        print(f"\n   分析: {db_path}")
        result = analyze_db(db_path)
        analysis_results.append(result)
        
        if result['error']:
            print(f"     错误: {result['error']}")
        else:
            print(f"     表数量: {len(result['tables'])}")
            for table in result['tables']:
                print(f"       - {table['name']} ({len(table['columns'])} 字段)")
    
    # 汇总分析
    print("\n3. 数据库功能分类分析:")
    print("\n   股票分析相关数据库:")
    analysis_dbs = []
    monitor_dbs = []
    strategy_dbs = []
    other_dbs = []
    
    for result in analysis_results:
        if not result['tables']:
            continue
        
        db_path = result['path']
        table_names = [t['name'] for t in result['tables']]
        
        # 分类判断
        if 'analysis' in db_path.lower() or any('analysis' in t.lower() for t in table_names):
            analysis_dbs.append((db_path, table_names))
        elif 'monitor' in db_path.lower() or any('monitor' in t.lower() for t in table_names):
            monitor_dbs.append((db_path, table_names))
        elif 'strategy' in db_path.lower() or 'main_force' in db_path.lower() or 'longhubang' in db_path.lower():
            strategy_dbs.append((db_path, table_names))
        else:
            other_dbs.append((db_path, table_names))
    
    if analysis_dbs:
        print("\n   分析类数据库:")
        for db_path, tables in analysis_dbs:
            print(f"     - {db_path}")
            for table in tables:
                print(f"       * {table}")
    
    if monitor_dbs:
        print("\n   监控类数据库:")
        for db_path, tables in monitor_dbs:
            print(f"     - {db_path}")
            for table in tables:
                print(f"       * {table}")
    
    if strategy_dbs:
        print("\n   策略类数据库:")
        for db_path, tables in strategy_dbs:
            print(f"     - {db_path}")
            for table in tables:
                print(f"       * {table}")
    
    if other_dbs:
        print("\n   其他数据库:")
        for db_path, tables in other_dbs:
            print(f"     - {db_path}")
            for table in tables:
                print(f"       * {table}")
    
    # 总结
    print("\n4. 总结:")
    print(f"   - 总数据库文件数: {len(db_files)}")
    print(f"   - 分析类数据库: {len(analysis_dbs)}")
    print(f"   - 监控类数据库: {len(monitor_dbs)}")
    print(f"   - 策略类数据库: {len(strategy_dbs)}")
    print(f"   - 其他数据库: {len(other_dbs)}")
    
    print("\n5. 数据存储架构特点:")
    print("   - 采用多数据库分离存储设计")
    print("   - 按功能模块划分数据库")
    print("   - 每个模块有独立的数据库文件")

if __name__ == "__main__":
    main()
