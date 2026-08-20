"""
core/ — 纯算法/通用工具层(models 之上, services 之下)。

本层禁止:
  - 导入 services 或 routers 模块
  - 依赖数据库 Session
  - 持有关联 HTTP 请求的副作用
"""