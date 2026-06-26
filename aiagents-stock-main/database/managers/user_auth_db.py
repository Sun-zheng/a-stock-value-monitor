import sqlite3
import json
from datetime import datetime
import os

class UserAuthDatabase:
    """用户认证数据库管理器"""
    
    def __init__(self, db_path="database/files/user_auth.db"):
        """初始化数据库连接"""
        self.db_path = db_path
        # 确保数据库所在目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT NULL,
                login_attempts INTEGER DEFAULT 0,
                locked_until TEXT NULL
            )
        ''')
        
        # 创建会话表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ip_address TEXT NULL,
                user_agent TEXT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # 创建验证码表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS verification_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def execute_transaction(self, query, params=()):
        """执行数据库事务"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid if cursor.lastrowid else True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_user_by_username(self, username):
        """根据用户名获取用户信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, password_hash, email, created_at, updated_at, last_login_at, login_attempts, locked_until
            FROM users
            WHERE username = ?
        ''', (username,))
        
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return None
        
        return {
            'id': user[0],
            'username': user[1],
            'password_hash': user[2],
            'email': user[3],
            'created_at': user[4],
            'updated_at': user[5],
            'last_login_at': user[6],
            'login_attempts': user[7],
            'locked_until': user[8]
        }
    
    def get_user_by_email(self, email):
        """根据邮箱获取用户信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, password_hash, email, created_at, updated_at, last_login_at, login_attempts, locked_until
            FROM users
            WHERE email = ?
        ''', (email,))
        
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return None
        
        return {
            'id': user[0],
            'username': user[1],
            'password_hash': user[2],
            'email': user[3],
            'created_at': user[4],
            'updated_at': user[5],
            'last_login_at': user[6],
            'login_attempts': user[7],
            'locked_until': user[8]
        }
    
    def create_user(self, username, password_hash, email):
        """创建新用户"""
        now = datetime.now().isoformat()
        
        try:
            user_id = self.execute_transaction('''
                INSERT INTO users (username, password_hash, email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (username, password_hash, email, now, now))
            return user_id
        except sqlite3.IntegrityError:
            # 用户名或邮箱已存在
            raise ValueError("用户名或邮箱已存在")
    
    def update_user_password(self, user_id, new_password_hash):
        """更新用户密码"""
        now = datetime.now().isoformat()
        
        try:
            result = self.execute_transaction('''
                UPDATE users
                SET password_hash = ?, updated_at = ?
                WHERE id = ?
            ''', (new_password_hash, now, user_id))
            return result
        except Exception as e:
            raise e
    
    def update_user_login_attempts(self, user_id, attempts, locked_until=None):
        """更新用户登录尝试次数"""
        now = datetime.now().isoformat()
        
        try:
            result = self.execute_transaction('''
                UPDATE users
                SET login_attempts = ?, locked_until = ?, updated_at = ?
                WHERE id = ?
            ''', (attempts, locked_until, now, user_id))
            return result
        except Exception as e:
            raise e
    
    def update_last_login(self, user_id):
        """更新用户最后登录时间"""
        now = datetime.now().isoformat()
        
        try:
            result = self.execute_transaction('''
                UPDATE users
                SET last_login_at = ?, updated_at = ?
                WHERE id = ?
            ''', (now, now, user_id))
            return result
        except Exception as e:
            raise e
    
    def create_session(self, session_id, user_id, expires_at, ip_address=None, user_agent=None):
        """创建用户会话"""
        now = datetime.now().isoformat()
        
        try:
            session_id = self.execute_transaction('''
                INSERT INTO sessions (session_id, user_id, created_at, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (session_id, user_id, now, expires_at, ip_address, user_agent))
            return session_id
        except Exception as e:
            raise e
    
    def get_session(self, session_id):
        """获取会话信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, session_id, user_id, created_at, expires_at, ip_address, user_agent
            FROM sessions
            WHERE session_id = ?
        ''', (session_id,))
        
        session = cursor.fetchone()
        conn.close()
        
        if not session:
            return None
        
        return {
            'id': session[0],
            'session_id': session[1],
            'user_id': session[2],
            'created_at': session[3],
            'expires_at': session[4],
            'ip_address': session[5],
            'user_agent': session[6]
        }
    
    def delete_session(self, session_id):
        """删除会话"""
        try:
            result = self.execute_transaction('''
                DELETE FROM sessions
                WHERE session_id = ?
            ''', (session_id,))
            return result
        except Exception as e:
            raise e
    
    def delete_expired_sessions(self):
        """删除过期会话"""
        now = datetime.now().isoformat()
        
        try:
            result = self.execute_transaction('''
                DELETE FROM sessions
                WHERE expires_at < ?
            ''', (now,))
            return result
        except Exception as e:
            raise e
    
    def create_verification_code(self, email, code, expires_at):
        """创建验证码"""
        now = datetime.now().isoformat()
        
        try:
            code_id = self.execute_transaction('''
                INSERT INTO verification_codes (email, code, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (email, code, now, expires_at))
            return code_id
        except Exception as e:
            raise e
    
    def get_verification_code(self, email, code):
        """获取验证码信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, email, code, created_at, expires_at, used
            FROM verification_codes
            WHERE email = ? AND code = ? AND used = 0
            ORDER BY created_at DESC
            LIMIT 1
        ''', (email, code))
        
        verification_code = cursor.fetchone()
        conn.close()
        
        if not verification_code:
            return None
        
        return {
            'id': verification_code[0],
            'email': verification_code[1],
            'code': verification_code[2],
            'created_at': verification_code[3],
            'expires_at': verification_code[4],
            'used': verification_code[5]
        }
    
    def mark_verification_code_used(self, code_id):
        """标记验证码为已使用"""
        try:
            result = self.execute_transaction('''
                UPDATE verification_codes
                SET used = 1
                WHERE id = ?
            ''', (code_id,))
            return result
        except Exception as e:
            raise e
    
    def delete_expired_verification_codes(self):
        """删除过期验证码"""
        now = datetime.now().isoformat()
        
        try:
            result = self.execute_transaction('''
                DELETE FROM verification_codes
                WHERE expires_at < ? OR used = 1
            ''', (now,))
            return result
        except Exception as e:
            raise e

# 全局数据库实例
user_auth_db = UserAuthDatabase()