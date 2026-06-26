from database.managers.user_auth_db import user_auth_db

class UserManager:
    """用户管理类"""
    
    def __init__(self):
        """初始化用户管理"""
        self.db = user_auth_db
    
    def get_user_by_username(self, username):
        """根据用户名获取用户信息
        
        Args:
            username: 用户名
            
        Returns:
            dict: 用户信息
        """
        try:
            user = self.db.get_user_by_username(username)
            return user
        except Exception as e:
            raise Exception(f"获取用户失败: {str(e)}")
    
    def get_user_by_email(self, email):
        """根据邮箱获取用户信息
        
        Args:
            email: 用户邮箱
            
        Returns:
            dict: 用户信息
        """
        try:
            user = self.db.get_user_by_email(email)
            return user
        except Exception as e:
            raise Exception(f"获取用户失败: {str(e)}")
    
    def create_user(self, username, password_hash, email):
        """创建新用户
        
        Args:
            username: 用户名
            password_hash: 加密后的密码
            email: 用户邮箱
            
        Returns:
            int: 用户ID
        """
        try:
            user_id = self.db.create_user(username, password_hash, email)
            return user_id
        except ValueError as e:
            raise e
        except Exception as e:
            raise Exception(f"创建用户失败: {str(e)}")
    
    def update_user_password(self, user_id, new_password_hash):
        """更新用户密码
        
        Args:
            user_id: 用户ID
            new_password_hash: 新的加密密码
            
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.update_user_password(user_id, new_password_hash)
            return result
        except Exception as e:
            raise Exception(f"更新密码失败: {str(e)}")
    
    def update_user_login_attempts(self, user_id, attempts, locked_until=None):
        """更新用户登录尝试次数
        
        Args:
            user_id: 用户ID
            attempts: 登录尝试次数
            locked_until: 账户锁定时间
            
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.update_user_login_attempts(user_id, attempts, locked_until)
            return result
        except Exception as e:
            raise Exception(f"更新登录尝试次数失败: {str(e)}")
    
    def update_last_login(self, user_id):
        """更新用户最后登录时间
        
        Args:
            user_id: 用户ID
            
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.update_last_login(user_id)
            return result
        except Exception as e:
            raise Exception(f"更新登录时间失败: {str(e)}")
    
    def create_session(self, session_id, user_id, expires_at, ip_address=None, user_agent=None):
        """创建用户会话
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            expires_at: 会话过期时间
            ip_address: 用户IP地址
            user_agent: 用户代理
            
        Returns:
            int: 会话ID
        """
        try:
            session_id = self.db.create_session(session_id, user_id, expires_at, ip_address, user_agent)
            return session_id
        except Exception as e:
            raise Exception(f"创建会话失败: {str(e)}")
    
    def get_session(self, session_id):
        """获取会话信息
        
        Args:
            session_id: 会话ID
            
        Returns:
            dict: 会话信息
        """
        try:
            session = self.db.get_session(session_id)
            return session
        except Exception as e:
            raise Exception(f"获取会话失败: {str(e)}")
    
    def delete_session(self, session_id):
        """删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.delete_session(session_id)
            return result
        except Exception as e:
            raise Exception(f"删除会话失败: {str(e)}")
    
    def delete_expired_sessions(self):
        """删除过期会话
        
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.delete_expired_sessions()
            return result
        except Exception as e:
            raise Exception(f"删除过期会话失败: {str(e)}")
    
    def create_verification_code(self, email, code, expires_at):
        """创建验证码
        
        Args:
            email: 用户邮箱
            code: 验证码
            expires_at: 验证码过期时间
            
        Returns:
            int: 验证码ID
        """
        try:
            code_id = self.db.create_verification_code(email, code, expires_at)
            return code_id
        except Exception as e:
            raise Exception(f"创建验证码失败: {str(e)}")
    
    def get_verification_code(self, email, code):
        """获取验证码信息
        
        Args:
            email: 用户邮箱
            code: 验证码
            
        Returns:
            dict: 验证码信息
        """
        try:
            verification_code = self.db.get_verification_code(email, code)
            return verification_code
        except Exception as e:
            raise Exception(f"获取验证码失败: {str(e)}")
    
    def mark_verification_code_used(self, code_id):
        """标记验证码为已使用
        
        Args:
            code_id: 验证码ID
            
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.mark_verification_code_used(code_id)
            return result
        except Exception as e:
            raise Exception(f"标记验证码失败: {str(e)}")
    
    def delete_expired_verification_codes(self):
        """删除过期验证码
        
        Returns:
            bool: 是否成功
        """
        try:
            result = self.db.delete_expired_verification_codes()
            return result
        except Exception as e:
            raise Exception(f"删除过期验证码失败: {str(e)}")