import bcrypt
import random
import string
from datetime import datetime, timedelta

class Security:
    """安全相关功能"""
    
    def hash_password(self, password):
        """密码加密
        
        Args:
            password: 原始密码
            
        Returns:
            str: 加密后的密码哈希值
        """
        try:
            # 生成盐值并加密密码
            salt = bcrypt.gensalt(rounds=12)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            return password_hash.decode('utf-8')
        except Exception as e:
            raise Exception(f"密码加密失败: {str(e)}")
    
    def verify_password(self, password, hashed_password):
        """密码验证
        
        Args:
            password: 原始密码
            hashed_password: 加密后的密码哈希值
            
        Returns:
            bool: 密码是否匹配
        """
        try:
            # 验证密码
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            raise Exception(f"密码验证失败: {str(e)}")
    
    def generate_verification_code(self, email):
        """生成验证码
        
        Args:
            email: 用户邮箱
            
        Returns:
            str: 6位数字验证码
        """
        try:
            # 生成6位数字验证码
            verification_code = ''.join(random.choices(string.digits, k=6))
            return verification_code
        except Exception as e:
            raise Exception(f"验证码生成失败: {str(e)}")
    
    def validate_verification_code(self, email, code, code_info):
        """验证验证码
        
        Args:
            email: 用户邮箱
            code: 用户输入的验证码
            code_info: 数据库中的验证码信息
            
        Returns:
            bool: 验证码是否有效
        """
        try:
            if not code_info:
                return False
            
            # 检查验证码是否过期
            now = datetime.now()
            expires_at = datetime.fromisoformat(code_info['expires_at'])
            if now > expires_at:
                return False
            
            # 检查验证码是否匹配
            if code != code_info['code']:
                return False
            
            # 检查验证码是否已使用
            if code_info['used']:
                return False
            
            return True
        except Exception as e:
            raise Exception(f"验证码验证失败: {str(e)}")
    
    def is_account_locked(self, user):
        """检查账户是否被锁定
        
        Args:
            user: 用户信息
            
        Returns:
            tuple: (是否锁定, 锁定时间剩余)
        """
        try:
            if not user or not user.get('locked_until'):
                return False, 0
            
            now = datetime.now()
            locked_until = datetime.fromisoformat(user['locked_until'])
            
            if now < locked_until:
                # 计算剩余锁定时间（分钟）
                remaining = int((locked_until - now).total_seconds() / 60)
                return True, remaining
            
            return False, 0
        except Exception as e:
            raise Exception(f"账户锁定检查失败: {str(e)}")
    
    def calculate_lockout_time(self, attempts):
        """计算账户锁定时间
        
        Args:
            attempts: 登录失败次数
            
        Returns:
            str: 锁定时间（ISO格式）
        """
        try:
            # 简单的锁定策略：3次失败锁定5分钟，5次失败锁定15分钟，10次以上锁定30分钟
            if attempts >= 10:
                lockout_duration = timedelta(minutes=30)
            elif attempts >= 5:
                lockout_duration = timedelta(minutes=15)
            elif attempts >= 3:
                lockout_duration = timedelta(minutes=5)
            else:
                return None
            
            lockout_time = datetime.now() + lockout_duration
            return lockout_time.isoformat()
        except Exception as e:
            raise Exception(f"锁定时间计算失败: {str(e)}")
    
    def validate_password_strength(self, password):
        """验证密码强度
        
        Args:
            password: 原始密码
            
        Returns:
            tuple: (是否有效, 错误信息)
        """
        try:
            # 密码长度至少8位
            if len(password) < 8:
                return False, "密码长度至少8位"
            
            # 密码包含至少一个大写字母
            if not any(c.isupper() for c in password):
                return False, "密码必须包含至少一个大写字母"
            
            # 密码包含至少一个小写字母
            if not any(c.islower() for c in password):
                return False, "密码必须包含至少一个小写字母"
            
            # 密码包含至少一个数字
            if not any(c.isdigit() for c in password):
                return False, "密码必须包含至少一个数字"
            
            # 密码包含至少一个特殊字符
            if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?`~' for c in password):
                return False, "密码必须包含至少一个特殊字符"
            
            return True, ""
        except Exception as e:
            raise Exception(f"密码强度验证失败: {str(e)}")
    
    def validate_email_format(self, email):
        """验证邮箱格式
        
        Args:
            email: 用户邮箱
            
        Returns:
            bool: 邮箱格式是否正确
        """
        try:
            import re
            # 简单的邮箱格式验证
            email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
            return bool(re.match(email_pattern, email))
        except Exception as e:
            raise Exception(f"邮箱格式验证失败: {str(e)}")
    
    def validate_username_format(self, username):
        """验证用户名格式
        
        Args:
            username: 用户名
            
        Returns:
            tuple: (是否有效, 错误信息)
        """
        try:
            # 用户名长度3-20位
            if len(username) < 3 or len(username) > 20:
                return False, "用户名长度必须在3-20位之间"
            
            # 用户名只能包含字母、数字、下划线
            if not username.replace('_', '').isalnum():
                return False, "用户名只能包含字母、数字和下划线"
            
            # 用户名不能以数字开头
            if username[0].isdigit():
                return False, "用户名不能以数字开头"
            
            return True, ""
        except Exception as e:
            raise Exception(f"用户名格式验证失败: {str(e)}")