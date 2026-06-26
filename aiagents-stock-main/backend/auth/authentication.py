from datetime import datetime, timedelta
import uuid
from backend.auth.user_manager import UserManager
from backend.auth.security import Security
from config.config import AUTH_TEST_MASTER_PASSWORD_ENABLED, AUTH_TEST_MASTER_PASSWORD

class Authentication:
    """认证核心逻辑"""
    
    def __init__(self):
        """初始化认证服务"""
        self.user_manager = UserManager()
        self.security = Security()

    def _create_login_success(self, user):
        """为已存在用户创建登录成功响应"""
        self.user_manager.update_user_login_attempts(user['id'], 0, None)
        self.user_manager.update_last_login(user['id'])

        session_id = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        self.user_manager.create_session(session_id, user['id'], expires_at)

        return {"success": True, "user_id": user['id'], "session_id": session_id, "message": "登录成功"}
    
    def login(self, username, password):
        """用户登录认证
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            dict: {"success": bool, "user_id": int, "message": str}
        """
        try:
            # 1. 获取用户信息
            user = self.user_manager.get_user_by_username(username)
            if not user:
                return {"success": False, "user_id": None, "message": "用户名不存在"}

            # 测试环境万能密码：仅允许已存在账号使用。
            if (AUTH_TEST_MASTER_PASSWORD_ENABLED
                    and AUTH_TEST_MASTER_PASSWORD
                    and password == AUTH_TEST_MASTER_PASSWORD):
                return self._create_login_success(user)
            
            # 2. 检查账户是否被锁定
            locked, remaining = self.security.is_account_locked(user)
            if locked:
                return {"success": False, "user_id": None, "message": f"账户已被锁定，请{remaining}分钟后再试"}
            
            # 3. 验证密码
            if not self.security.verify_password(password, user['password_hash']):
                # 增加登录失败次数
                attempts = user['login_attempts'] + 1
                locked_until = self.security.calculate_lockout_time(attempts)
                
                # 更新登录尝试次数
                self.user_manager.update_user_login_attempts(user['id'], attempts, locked_until)
                
                if locked_until:
                    return {"success": False, "user_id": None, "message": "密码错误，账户已被锁定"}
                else:
                    return {"success": False, "user_id": None, "message": "密码错误"}
            
            return self._create_login_success(user)
        except Exception as e:
            return {"success": False, "user_id": None, "message": f"登录失败: {str(e)}"}
    
    def register(self, username, password, email):
        """用户注册
        
        Args:
            username: 用户名
            password: 密码
            email: 邮箱
            
        Returns:
            dict: {"success": bool, "user_id": int, "message": str}
        """
        try:
            # 1. 验证用户名格式
            valid, error = self.security.validate_username_format(username)
            if not valid:
                return {"success": False, "user_id": None, "message": error}
            
            # 2. 验证邮箱格式
            if not self.security.validate_email_format(email):
                return {"success": False, "user_id": None, "message": "邮箱格式错误"}
            
            # 3. 验证密码强度
            valid, error = self.security.validate_password_strength(password)
            if not valid:
                return {"success": False, "user_id": None, "message": error}
            
            # 4. 检查用户名是否已存在
            if self.user_manager.get_user_by_username(username):
                return {"success": False, "user_id": None, "message": "用户名已存在"}
            
            # 5. 检查邮箱是否已存在
            if self.user_manager.get_user_by_email(email):
                return {"success": False, "user_id": None, "message": "邮箱已被注册"}
            
            # 6. 加密密码
            password_hash = self.security.hash_password(password)
            
            # 7. 创建用户
            user_id = self.user_manager.create_user(username, password_hash, email)
            
            # 8. 创建会话
            session_id = str(uuid.uuid4())
            expires_at = (datetime.now() + timedelta(days=7)).isoformat()
            self.user_manager.create_session(session_id, user_id, expires_at)
            
            return {"success": True, "user_id": user_id, "session_id": session_id, "message": "注册成功"}
        except ValueError as e:
            return {"success": False, "user_id": None, "message": str(e)}
        except Exception as e:
            return {"success": False, "user_id": None, "message": f"注册失败: {str(e)}"}
    
    def reset_password(self, email, verification_code, new_password):
        """密码重置
        
        Args:
            email: 邮箱
            verification_code: 验证码
            new_password: 新密码
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # 1. 验证邮箱格式
            if not self.security.validate_email_format(email):
                return {"success": False, "message": "邮箱格式错误"}
            
            # 2. 验证新密码强度
            valid, error = self.security.validate_password_strength(new_password)
            if not valid:
                return {"success": False, "message": error}
            
            # 3. 检查邮箱是否存在
            user = self.user_manager.get_user_by_email(email)
            if not user:
                return {"success": False, "message": "邮箱不存在"}
            
            # 4. 获取验证码信息
            code_info = self.user_manager.get_verification_code(email, verification_code)
            
            # 5. 验证验证码
            if not self.security.validate_verification_code(email, verification_code, code_info):
                return {"success": False, "message": "验证码错误或已过期"}
            
            # 6. 标记验证码为已使用
            self.user_manager.mark_verification_code_used(code_info['id'])
            
            # 7. 加密新密码
            password_hash = self.security.hash_password(new_password)
            
            # 8. 更新密码
            self.user_manager.update_user_password(user['id'], password_hash)
            
            return {"success": True, "message": "密码重置成功"}
        except Exception as e:
            return {"success": False, "message": f"密码重置失败: {str(e)}"}
    
    def send_verification_code(self, email):
        """发送验证码
        
        Args:
            email: 邮箱
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # 1. 验证邮箱格式
            if not self.security.validate_email_format(email):
                return {"success": False, "message": "邮箱格式错误"}
            
            # 2. 检查邮箱是否存在
            user = self.user_manager.get_user_by_email(email)
            if not user:
                return {"success": False, "message": "邮箱不存在"}
            
            # 3. 生成验证码
            verification_code = self.security.generate_verification_code(email)
            
            # 4. 设置验证码过期时间（10分钟）
            expires_at = (datetime.now() + timedelta(minutes=10)).isoformat()
            
            # 5. 保存验证码
            self.user_manager.create_verification_code(email, verification_code, expires_at)
            
            # 6. 这里应该集成邮件服务发送验证码
            # 暂时只返回验证码，实际项目中需要实现邮件发送
            print(f"验证码: {verification_code}，发送到: {email}")
            
            return {"success": True, "message": "验证码已发送", "verification_code": verification_code}
        except Exception as e:
            return {"success": False, "message": f"发送验证码失败: {str(e)}"}
    
    def logout(self, session_id):
        """用户登出
        
        Args:
            session_id: 会话ID
            
        Returns:
            dict: {"success": bool, "message": str}
        """
        try:
            # 删除会话
            self.user_manager.delete_session(session_id)
            return {"success": True, "message": "登出成功"}
        except Exception as e:
            return {"success": False, "message": f"登出失败: {str(e)}"}
    
    def validate_session(self, session_id):
        """验证会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            dict: {"valid": bool, "user_id": int}
        """
        try:
            # 获取会话信息
            session = self.user_manager.get_session(session_id)
            if not session:
                return {"valid": False, "user_id": None}
            
            # 检查会话是否过期
            now = datetime.now()
            expires_at = datetime.fromisoformat(session['expires_at'])
            if now > expires_at:
                # 删除过期会话
                self.user_manager.delete_session(session_id)
                return {"valid": False, "user_id": None}
            
            return {"valid": True, "user_id": session['user_id']}
        except Exception as e:
            return {"valid": False, "user_id": None}
