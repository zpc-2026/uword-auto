"""外研U词后端（真实接口）封装。"""

from .auth import (TokenStore, current_token, login, login_with_sms, sms_captcha,
                   sms_send, sms_set_password, sso_login, sso_to_word)
from .client import ApiError, AuthExpired, Client
from .ops import learn, review, set_plan, status
from .solver import solve

__all__ = [
    "Client", "ApiError", "AuthExpired",
    "TokenStore", "current_token", "login", "login_with_sms", "sms_captcha",
    "sms_send", "sms_set_password", "sso_login", "sso_to_word",
    "status", "learn", "review", "set_plan", "solve",
]
