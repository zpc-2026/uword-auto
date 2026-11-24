"""外研U词 全自动学习/检验/复习 工具包（纯标准库实现）。"""

__version__ = "1.0.0"

from .config import Config  # noqa: F401
from .engine import Engine  # noqa: F401
from .net import ApiError, AuthExpired, HttpClient  # noqa: F401
from .solver import Solver  # noqa: F401
from .store import Store  # noqa: F401
