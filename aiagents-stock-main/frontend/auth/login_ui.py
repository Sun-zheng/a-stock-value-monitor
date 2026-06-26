import streamlit as st
from backend.auth.authentication import Authentication

class LoginUI:
    """登录页面UI组件"""
    
    def __init__(self):
        """初始化登录UI"""
        self.auth = Authentication()
    
    def display_login_page(self):
        """显示登录页面"""
        # 清除所有会话状态
        self._clear_session_state()
        
        # 页面标题
        st.markdown("""
        <div class="top-nav">
            <h1 class="nav-title">📈 股票智能分析系统</h1>
            <p class="nav-subtitle">请登录以访问系统</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 登录卡片
        with st.container():
            # 选项卡：登录、注册、忘记密码
            tab1, tab2, tab3 = st.tabs(["登录", "注册", "忘记密码"])
            
            with tab1:
                self._display_login_form()
            
            with tab2:
                self._display_register_form()
            
            with tab3:
                self._display_reset_password_form()
    
    def _display_login_form(self):
        """显示登录表单"""
        st.subheader("用户登录")
        
        # 表单
        username = st.text_input("用户名", placeholder="请输入用户名", key="login_username")
        password = st.text_input("密码", placeholder="请输入密码", type="password", key="login_password")
        remember_me = st.checkbox("记住我", key="login_remember_me")
        
        # 登录按钮
        if st.button("登录", type="primary", use_container_width=True, key="login_button"):
            if not username or not password:
                st.error("请输入用户名和密码")
                return
            
            # 调用登录接口
            result = self.auth.login(username, password)
            
            if result["success"]:
                # 保存登录状态
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = result["user_id"]
                st.session_state["session_id"] = result["session_id"]
                st.session_state["username"] = username
                
                st.success("登录成功，正在跳转到系统主页...")
                # 重定向到系统主页
                st.rerun()
            else:
                st.error(result["message"])
    
    def _display_register_form(self):
        """显示注册表单"""
        st.subheader("用户注册")
        
        # 表单
        username = st.text_input("用户名", placeholder="请输入用户名", key="register_username")
        password = st.text_input("密码", placeholder="请输入密码", type="password", key="register_password")
        confirm_password = st.text_input("确认密码", placeholder="请再次输入密码", type="password", key="register_confirm_password")
        email = st.text_input("邮箱", placeholder="请输入邮箱", key="register_email")
        
        # 注册按钮
        if st.button("注册", type="primary", use_container_width=True, key="register_button"):
            # 验证输入
            if not username or not password or not confirm_password or not email:
                st.error("请填写所有必填字段")
                return
            
            if password != confirm_password:
                st.error("两次输入的密码不一致")
                return
            
            # 调用注册接口
            result = self.auth.register(username, password, email)
            
            if result["success"]:
                # 保存登录状态
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = result["user_id"]
                st.session_state["session_id"] = result["session_id"]
                st.session_state["username"] = username
                
                st.success("注册成功，正在跳转到系统主页...")
                # 重定向到系统主页
                st.rerun()
            else:
                st.error(result["message"])
    
    def _display_reset_password_form(self):
        """显示密码重置表单"""
        st.subheader("密码重置")
        
        # 表单
        email = st.text_input("邮箱", placeholder="请输入注册邮箱", key="reset_email")
        
        # 发送验证码按钮
        if st.button("发送验证码", use_container_width=True, key="reset_send_code"):
            if not email:
                st.error("请输入邮箱")
                return
            
            # 调用发送验证码接口
            result = self.auth.send_verification_code(email)
            
            if result["success"]:
                # 保存验证码（仅用于测试）
                if "verification_code" in result:
                    st.info(f"验证码: {result['verification_code']}（仅用于测试）")
                st.success("验证码已发送，请查收邮箱")
            else:
                st.error(result["message"])
        
        # 验证码和新密码
        verification_code = st.text_input("验证码", placeholder="请输入收到的验证码", key="reset_verification_code")
        new_password = st.text_input("新密码", placeholder="请输入新密码", type="password", key="reset_new_password")
        confirm_new_password = st.text_input("确认新密码", placeholder="请再次输入新密码", type="password", key="reset_confirm_new_password")
        
        # 重置密码按钮
        if st.button("重置密码", type="primary", use_container_width=True, key="reset_button"):
            # 验证输入
            if not email or not verification_code or not new_password or not confirm_new_password:
                st.error("请填写所有必填字段")
                return
            
            if new_password != confirm_new_password:
                st.error("两次输入的密码不一致")
                return
            
            # 调用密码重置接口
            result = self.auth.reset_password(email, verification_code, new_password)
            
            if result["success"]:
                st.success("密码重置成功，请使用新密码登录")
                # 切换到登录选项卡
                st.session_state["active_tab"] = "登录"
            else:
                st.error(result["message"])
    
    def _clear_session_state(self):
        """清除会话状态"""
        # 保留必要的会话状态
        if "logged_in" in st.session_state:
            del st.session_state["logged_in"]
        if "user_id" in st.session_state:
            del st.session_state["user_id"]
        if "session_id" in st.session_state:
            del st.session_state["session_id"]
        if "username" in st.session_state:
            del st.session_state["username"]
        
        # 清除功能页面标志
        for key in ['show_history', 'show_monitor', 'show_config', 'show_main_force',
                   'show_sector_strategy', 'show_longhubang', 'show_portfolio', 'show_low_price_bull',
                   'show_small_cap', 'show_profit_growth', 'show_smart_monitor']:
            if key in st.session_state:
                del st.session_state[key]
    
    def check_login_status(self):
        """检查登录状态
        
        Returns:
            bool: 是否已登录
        """
        return st.session_state.get("logged_in", False)
    
    def logout(self):
        """用户登出"""
        if "session_id" in st.session_state:
            # 调用登出接口
            self.auth.logout(st.session_state["session_id"])
        
        # 清除登录状态
        self._clear_session_state()
        
        st.success("已成功登出")
        st.rerun()