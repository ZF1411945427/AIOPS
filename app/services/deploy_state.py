"""deploy_service 拆分后共享模块级状态(所有子模块 import 同一对象)。"""
from typing import Any, Dict

# 进程内执行互斥：同一计划同一时刻只允许一个执行流(HTTP 或 WS)。僵尸 running 状态可重跑。
_EXEC_LOCK: Dict[int, bool] = {}
# 活跃 SSH 客户端注册表（供停止接口关闭连接中断执行）
_RUNNING_CLIENTS: Dict[int, Any] = {}
# 停止请求标志：producer 检测到后立即终止且不覆盖状态
_STOPPED: Dict[int, bool] = {}
# 用户决策队列：plan_id -> queue.Queue（WS 路由转发用户"修复/重试/回滚/跳过"决策）
_DECISIONS: Dict[int, Any] = {}
# 单步骤 SSH 命令最大执行时长（docker build 等长任务，超时终止）
_STEP_TIMEOUT = 600
