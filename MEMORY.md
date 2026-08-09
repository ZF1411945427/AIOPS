# AIOps 项目记忆

> 每次会话开始时读取。按时间倒序,最新在最上面。完整历史见 git log。

### 2026-08-09: AI 运维沙盒(Sandbox)独立模块落地

- **目标**: 控制 AI Agent 下发到节点后的作用范围。独立菜单，暂不侵入 agent_service/remediation_service/edge_tunnel_service 现有执行链，测试闭环后再融入
- **新增表**: `sandbox_configs`(全局配置,单行) / `sandbox_policies`(细粒度策略) / `sandbox_execution_logs`(执行日志)
- **策略字段**: scope_type(global/role/user/session)、资产/工具/命令黑白名单、max_risk_level、每日配额、require_second_approval、执行窗口
- **决策顺序**: 黑名单→白名单→风险等级→执行窗口(高危写操作)
- **文件**:
  - `app/models.py` 末尾 3 个模型
  - `app/services/sandbox_service.py` 策略引擎(evaluate_request/log_execution)
  - `app/routers/sandbox.py` API(prefix=/sandbox): config/policies/evaluate/logs/risk-levels/scope-types
  - `frontend/src/views/SandboxView.vue` 4 个 Tab(全局配置/策略管理/决策测试/执行日志)
  - `menu_config.json` 新增 `sandbox` 分组 → `sandbox-management` → `sandbox-overview`(path=/sandbox, key 已授权 admin)
- **坑**: 新 API 必须加入 `main.py` PUBLIC_PATHS 的 `/sandbox`,否则 AuthMiddleware 未认证重定向到 /login 返回 SPA HTML 而非 JSON
- **已验证**: config/policies/evaluate/logs 全部正常;沙盒关闭时 evaluate 返回 allowed,开启 dry_run 后返回 dry_run
- **CONTRACT.md 第九章** 已记录字段契约

### 2026-08-09: 清理所有演示数据，准备接入靶场

- **动作**: 编写 `_clear_data.py` 清空 demo 和 real 两个库共 120 张表(PRAGMA foreign_keys=OFF 全表 DELETE FROM)
- **保留**: admin 用户 + 3 个预设角色 + 菜单权限 + 通知渠道 + seed marker(`seed_data_applied=v2`)
- **效果**: 重启后端后 seed 被跳过(日志无 seed 记录),`/assets/api/list` 返回 0 条;胚芽模板/AgentConfig/TagCategory 因独立于 marker 会在启动时重新播种(参考数据,非展示数据)
- **注意**: 清理脚本已删除,如需再次清理可重新生成;种子标记在 SystemConfig 表中,若删除 DB 文件需重新标记

### 2026-08-09: License 公钥不匹配修复 + gRPC opentelemetry 依赖补装

- **问题1**: gRPC OTLP TraceService 启动失败 `No module named 'opentelemetry'`。根因: `app/grpc_server.py` 模块顶层 import opentelemetry,main.py import grpc_server 时即失败。修复: 改为懒加载(import 移到函数内),并补装 `opentelemetry-proto`(注意!后端跑在 `C:\Users\zhuming\AppData\Local\hermes\hermes-agent\venv` 的 Python 3.11,不是系统 Python 3.13,必须用该 venv 的 python -m pip install)
- **问题2**: 全站 403 `授权签名验证失败`。根因: commit `988e252` 重导了 License 公钥(代码硬编码 + tools/public_key.pem),但本地 `tools/private_key.pem` 是旧私钥,与线上公钥不匹配 → 旧 license.lic 验不过。修复(经用户确认): 用本地私钥推导公钥,同步更新 `app/services/license_service.py` 的 PUBLIC_KEY_PEM 和 `tools/public_key.pem`,再用 `tools/generate_license.py` 重签 `license.lic`(客户"开发测试"、旗舰版、2099-12-31、指纹 329b1dfdc67bddc68de64d03a1581a44、max_nodes 9999)
- **已验证**: `/license/api/status` 返回 `{"status":"active","valid":true,"remaining_days":26807}`;gRPC TraceService listening on 0.0.0.0:4317
- **坑**: `tools/public_key.pem` 虽已在 .gitignore,但加入前已被 git 追踪,需 `git rm --cached tools/public_key.pem` 才生效
- **注意**: 现本地私钥即授权私钥,必须妥善保管(已 gitignore);公钥文件路径: `app/services/license_service.py:19`

### 2026-08-09: 日志搜索修复——level 排除法保留堆栈行

- **根因**: 正向 `level=~"(?i)^error$"` 标签过滤会排除无 level 标签的堆栈行,导致多行合并失效
- **修复**: 数据查询改用**排除法** `level!~"(?i)^(info|debug|warn|warning)$"`——排除 info/debug/warn 但保留 ERROR + 无 level 标签的堆栈行;计数查询仍用正向过滤保证 total 准确
- **效果**: `level=error` 过滤时完整堆栈(38行)合并成功,repeat=5, total=46;无 level 过滤时也正常
- 已构建前端

### 2026-08-09: 日志搜索修复——level 过滤回归标签方式

- **根因**: 数据查询去掉 level 标签过滤后,大量 DEBUG 日志挤占 limit 导致 error 日志搜不到(共 45 条但返回 0 条)
- **修复**: 数据查询恢复 level 标签过滤,保证搜索准确;多行合并只在**无 level 过滤**时生效(此时堆栈行不会被排除)
- **效果**: level=error 搜索正常(1 条 dedup 结果,repeat=10);无 level 过滤时多行合并正常工作
- 已构建前端,已验证: level=error含结果 / 无level含结果 / 24h范围正常

### 2026-08-09: 多行日志合并修复——level 过滤改为后端做

- **根因**: Loki 的 `level` 标签过滤会在查询阶段排除掉堆栈行(at okhttp3...等无 level 标签的行),导致多行合并失效
- **修复**:
  - `LokiAdapter.query`: 数据查询**移除 level 标签过滤**(改为 `count_expr_base` 单独带 level 过滤保证 total 准确),保留堆栈行 → 合并多行
  - `logs.py _query_loki`: 合并后对消息**前 150 字符**做 `\berror\b` 正则级别匹配(避免消息内容如 `error='null'` 误判)
- **效果**: 完整 Java 堆栈(38 行)合并成一条,展开可见全部;级别过滤准确
- **坑**: 80 字符太短(otel 格式 ERROR 在 ~83 字符处),需 150 字符

### 2026-08-09: 多行日志合并——Java 异常堆栈还原为一条完整记录

- **问题**: promtail 按行拆分日志,Java 多行堆栈(异常声明+`at `+`Caused by`)每行是独立 Loki 记录,页面只显示第一行
- **改动**: `LokiAdapter.query` 新增 `_merge_multiline()`——在返回前把相邻的堆栈续行合并回主日志:
  - 缩进行(`\tat ...`)→续行
  - `Caused by:`/`... N more`/`Suppressed:`→续行
  - 异常声明行(`java.net.ConnectException: message`)→续行(匹配 `[a-z]+.[a-zA-Z]` + `Exception|Error|Throwable`)
  - 合并后堆栈完整显示,点击展开可查看全部
- **效果**: 降噪也受益——合并后完整消息经归一化比较,相同异常可正确折叠

### 2026-08-09: 日志列表改为 Grafana 紧凑风格 + 时间范围格式修复

- **紧凑风格**: 日志条目从卡片式改为单行流式——奇偶行交替背景、无边框、无 padding、单行截断(message 用 text-overflow ellipsis);级别改为单字母缩写(E/I/W)
- **时间范围格式**: 降噪折叠后时间范围端显示 `~HH:MM:SS` 代替完整日期(`~19:39:00` 而非 `~2026-08-08 19:39:00`),避免同一天重复日期
- 已构建前端

### 2026-08-09: 日志降噪改进——时间范围显示 + 路由冲突修复

- **降噪**: 后端 `_dedup_logs` 改为归一化比较(去掉消息首段 `[xxx]` 内嵌时间戳),折叠后记录 `time_start`(最新)~`time_end`(最旧),前端显示 `21:40:08 ~ 21:38:09` 时间范围
- **默认数据源 BUG**: `GET /api/log-default` 与 `GET /api/{source_id}` 路由冲突(路由定义顺序问题),`/api/log-default` 被 `{source_id}` 拦截返回 422。修复:将 log-default 路由定义移到 `{source_id}` 之前
- 前端 `DatasourcesView.vue`: `loadDefaultSource()` 加 `await` 避免加载时序问题
- 已构建前端

### 2026-08-09: 日志中心——点击展开完整日志 + 降噪/默认配置说明

- **需求**: ① 日志截断,多行内容只显示第一行;② 降噪默认没生效(实际是嵌入式时间戳导致消息不同)
- **改动**:
  - `LogsView.vue`: 日志条目点击展开/收起——默认折叠显示前 3 行(max-height 4.8em),hover 显示"展开"按钮,点击展开完整内容,再次点击收起;搜索时自动重置展开状态
  - 降噪确认: 默认开启(`dedup=1`),但含嵌入式时间戳的日志(如 Java 堆栈的首行)因消息不同不会折叠,如需更智能降噪可后续做正则归一化
- **已构建前端**

### 2026-08-09: 日志中心默认数据源配置 + 降噪状态提示

- **需求**: ①每次点日志中心页面没有默认数据源,手动选很麻烦 ②降噪时没有状态提示
- **实现**:
  - **后端** `datasources.py`: 新增 `GET /datasources/api/log-default` 和 `POST /datasources/api/log-default`——通过 `config_service` 存/取 `default_log_source_id` 配置
  - **前端** `DatasourcesView.vue`: 表格新增"日志默认"列,非默认数据源显示"设为默认"按钮,当前默认源显示紫色"默认"徽章
  - **前端** `LogsView.vue`: `onMounted` 时调 `loadDefaultSource()` 读取默认数据源,自动选中并触发搜索;复选框旁显示"降噪中"紫色徽章
- **已构建前端**

### 2026-08-09: 日志中心加"降噪"去重——折叠相邻相同日志

- **需求**: 日志中心默认折叠相邻相同日志(降噪),勾选"显示原日志"后展示原始日志
- **实现**:
  - 后端 `logs.py` `api_log_search`: 新增 `dedup: int = 1` 参数,默认降噪;新增 `_dedup_logs()` 函数——按 (service, message) 相邻相同则折叠,加 `repeat` 字段记录连续重复次数
  - 前端 `LogsView.vue`: 工具栏搜索按钮前加"显示原日志"复选框(`showOriginal`,默认false→dedup=1);日志条目显示 `×N` 重复徽章(紫色)
- **验证**: `_dedup_logs` 单元测试通过——相邻重复折叠为 `repeat=2`,被不同日志隔开的不折叠
- 已构建前端

### 2026-08-09: 指标监控改造——聚合修复 + Grafana 风格图表 + 自定义 PromQL 卡片

- **背景**: 用户反馈指标监控选"全部资产"时展示的不是平均值,而是最后一条随机资产的值;且折线图把多资产数据点混成一条乱线
- **改动**:
  - **后端** (`metric_v2_service.py`):
    - 新增 `query_latest_aggregated(aggregate)` — 用 `avg/sum/max/min by (__name__)` PromQL 计算跨资产聚合值 + 返回参与资产数 count
    - 新增 `query_range_aggregated(name, aggregate, hours)` — 返回 `{avg, series}` 两路:avg 为聚合折线(粗实线),series 为各资产明细(细线,透明度 0.35)
    - 新增 `query_custom_promql(promql, hours)` — 执行任意 PromQL range 查询,返回 `{series: [{name, labels, values}]}`
  - **后端** (`metrics.py`):
    - `GET /api/v2/latest` 增加 `aggregate` 参数(asset_id=0 时生效),传 `avg/sum/max/min` 走聚合查询
    - `GET /api/v2/range` 增加 `aggregate` 参数,传聚合值时返回 `{avg, series}` 结构
    - 新增 `POST /api/v2/custom-query` — 体接收 `{promql, hours}`,执行自定义 PromQL
  - **前端** (`MetricsView.vue` 完全重写):
    - 页头增加聚合方式下拉框(平均值/总和/最大值/最小值),选"全部资产"时自动聚合,卡片值显示 `[平均] 83.5% (10 台)`
    - 图表:聚合模式时渲染粗实线(avg) + 半透明细线(各资产)叠加,非聚合时保持原逻辑
    - 新增"自定义仪表盘"区域:4 列 CSS Grid 布局,支持 HTML5 拖拽排序 + 右下角缩放手柄
    - 新增卡片弹窗:输入标题 + PromQL + 时间范围 + 宽高,layout 存 localStorage(key=`metrics_custom_cards`)
    - 每 15 秒自动刷新系统指标 + 自定义卡片图表
- **效果**: 全部资产下显示真实平均值+资产数,图表一眼看清整体趋势+各资产波动;自定义卡片可拖拽排列/缩放大小,布局持久化
- **已构建前端**: `MetricsView-B2pkA380.js` + `MetricsView-DSO3KVak.css`

### 2026-08-08: HPA 推荐页——无 Metrics Server 时不再显示估算数据
- **背景**: 用户反馈调目标利用率"感觉没变化",根因是无 Metrics Server 时使用率是固定估算值(30%/40%),调目标利用率不改变推荐结果
- **改动**: 后端 `api_hpa_recommend` 检查所有 Deployment 的 `has_metrics`,若全为 false 则返回空列表 + warning"集群未安装 Metrics Server";前端 warning 替代估算数据表格
- **效果**: 没装 Metrics Server 的集群,页面直接显示提示,不再展示虚假估算数据,减少用户困惑

### 2026-08-08: HPA 配置推荐页全面优化(7 项设计缺陷修复)
- **背景**: 原页面仅 1 个输入框+1 个表格,「分析」和「刷新」按钮冗余,无集群选择器,无目标利用率可调,无 metrics server 缺失提示,无一键应用能力
- **后端改动**(`k8s_resources.py`):
  - `api_hpa_recommend` 增加 `target_cpu`/`target_mem`/`window` 参数,去掉硬编码 50/50,返回 `clusters` 列表供前端集群选择器
  - 新增 `POST /k8s/api/hpa/recommend/apply` 接口:生成 autoscaling/v2 HPA YAML(dry_run=true 预览/false 直接创建)
- **前端改动**(`K8sHpaRecommendView.vue` 完全重写):
  - 工具栏:集群下拉框 + 命名空间过滤 + CPU/内存目标利用率滑块(30-90%) + 时间窗口选择(实时/1h/6h/24h) + 单「分析」按钮(删除冗余刷新)
  - 表格新增 CPU 请求/mem 请求/操作列,操作列「应用」按钮弹出 YAML 预览弹窗,确认后直接创建 HPA
  - 无 metrics server 时显示红色警告横幅
- **验证**(6 轮测试全部通过):
  - 默认参数返回 17 items,集群信息正常
  - 自定义参数(namespace+target_cpu=70+target_mem=80+window=1h)正确传递
  - Apply dry_run=true 生成正确 autoscaling/v2 YAML(含 CPU+Memory 双指标)
  - 边界:空命名空间→0 items、不存在集群→友好提示+可用集群列表、缺少 name→错误提示
  - 前端构建产物含新 chunk(K8sHpaRecommendView-*.js)
- **注意**: 集群无 metrics server 时使用率均为估算值,建议安装后重新分析

### 2026-08-08: 日志中心/指标监控加业务域检索筛选 + K8s 微服务接入 gRPC OTLP
- **需求**: 日志中心(LogsView)和指标监控(MetricsView)加业务域筛选下拉,放在服务/资产筛选前面
- **后端**(`app/routers/traces_api.py`): 新增 `GET /api/traces/asset-domains` 返回资产id→域列表映射(供指标监控按域过滤资产)
- **前端 LogsView**: 高级过滤区首项加业务域下拉(选域后联动筛选服务列表)
- **前端 MetricsView**: 工具栏首项加业务域下拉(选域后联筛资产列表,通过 `assetDomains` 映射)
- 已构建前端;PUBLIC_PATHS 加 `/api/traces/asset-domains`
- **K8s 微服务接入**: 平台加 gRPC 端点(`app/grpc_server.py`, 监听 4317),微服务原生 OTel SDK 通过 `COLLECTOR_SERVICE_ADDR=11.0.1.1:4317` + `ENABLE_TRACING=1` 直连上报;7/12 个微服务成功接入(19277 spans/2916 traces)

### 2026-08-08: 链路追踪+架构巡检图加业务域筛选(业务域下拉为空的根因)
- **需求**: 链路追踪(TraceView)与架构巡检图(FireMapView 域详情页)加业务域筛选,放在服务筛选前面
- **后端**(`app/routers/traces_api.py`): 新增 `GET /api/traces/domains`(有链路数据的业务域)、`GET /api/traces/services?domain=`(按域过滤服务)、`GET /api/traces` 加 `domain` 参数(域→服务映射复用 `health_engine._match_asset_to_services` 模糊匹配)
- **前端**: TraceView.vue 筛选栏首项加业务域下拉(选域清空服务重载);FireMapView.vue 域详情页搜索栏首项加业务域下拉(可切换域)
- **⚠️ 大坑(业务域下拉为空)**: 用户反馈下拉空,**根因不是筛选代码,而是后端没启动**——`app/routers/k8s_resources.py:172` 缩进错误(SyntaxError)导致 `python run.py` 启动即崩 → 所有 API 连接拒绝 → domainList 拉不到数据。修复缩进重启后端后,下拉正常显示 2 域
- **教训**: 排查"某页某下拉/列表为空",先确认后端是否真在跑(curl 看响应),再怀疑前端;后端启动失败常见于语法错误,查启动日志
- 已构建前端;PUBLIC_PATHS 加 `/api/traces/domains`、`/api/traces/services`

### 2026-08-08: HPA 配置推荐页`'V1DeploymentList' object is not iterable` 修复
- **Bug**: `k8s_resources.py:1390` 中 `list_namespaced_deployment(namespace)` 返回 `V1DeploymentList` 对象,没加 `.items`,前端选命名空间过滤时 `for d in raw` 报错,显示 `'V1DeploymentList' object is not iterable`
- **修复**: 同一文件还有一处同样问题(172 行,`api_deployment_list` 函数),两处都加了 `.items` → `list_namespaced_deployment(namespace).items`
- **验证**: `GET /k8s/api/hpa/recommend?namespace=cert-manager` 返回 3 条数据(cert-manager/cert-manager-cainjector/cert-manager-webhook),warning 为空
- **注意**: 集群无 metrics server(`has_metrics: false`),使用率全为 0,推荐基于 `replicas<=1` 启发式规则

### 2026-08-08: 链路追踪接入完成——传统部署(裸机)+K8s 全靶场打通
- **背景**: 接续 Docker mall-swarm 接入完成,继续接入 132 裸机 mall(传统部署)+131 K8s microservices-demo
- **传统部署(132 裸机 mall)**: mall-bare-admin(8180)/mall-bare-portal(8185) 原无 OTel Agent → 重建容器挂 -javaagent + OTel 环境变量(与 Docker 配置一致),验证 spans 从 731→917(+186),services 新增 mall-bare-admin/mall-bare-portal
- **K8s(131 microservices-demo)**: OTel Operator v0.156.0 已安装,Instrumentation CR `aiops-tracing` 指向 `http://11.0.1.1:8000`,default ns 已打 `opentelemetry-injection=enabled` 标签
  - **Java 自动注入成功但 adservice 崩溃**: OTel Java Agent 2.30.0 加载成功但 gRPC liveness probe 冲突(probe timeout→容器被 kill→exit 143)
  - **修复**: pod template 加 `instrumentation.opentelemetry.io/inject-java=false` 注解 + 手动清理 Operator 已写入的 env/volume,adservice 恢复正常
  - **Node.js/Python 自动注入静默失败**: emailservice/recommendationservice 无 initContainers,Operator 语言检测未命中(Operator 镜像已缓存但 webhook 未触发注入)
  - **Go 注入不可用**: Operator 配置 `enable-go-auto-instrumentation=false`
  - **手动验证 OTLP 管道**: 创建 Python 测试 pod(python:3.12-slim + OTel SDK),手动创建 span 上报到平台 → `k8s-microservices-demo` 服务成功入库,15 条 trace,耗时 ~10ms,状态 OK
- **最终状态**: 9 个服务(3 Docker + 2 裸机 + 1 K8s 测例 + 3 测试服务),1189 spans/718 traces
- **文档更新**: `business-demos/链路追踪接入实战.md` 新增第四章(传统部署)、第五章(K8s 接入)、更新验证结果/踩坑记录(新增 4 条 K8s 相关坑)
- **关键踩坑**: ① adservice gRPC probe 被 Java Agent 干扰→需排除注解 ② K8s 内 pod 无外网→需 HTTP_PROXY ③ 手动 SDK 不设 Resource 则 service.name=unknown_service ④ Operator 对非 Java 镜像检测不命中

### 2026-08-08: 链路追踪真实靶场接入完成(132 Docker mall-swarm + 平台新增标准 OTLP 端点)
- **背景**: 按 `business-demos/部署文档.md`,依据接入指引页(TraceAgentGuide.vue)把真实业务链路接入平台,验证链路追踪接入。本机即 VMnet8 网关 11.0.1.1,后端 0.0.0.0:8000;132 虚机(无外网,走代理 11.0.1.1:7897)上 mall-swarm 应用为手动 `docker run`(非 compose,`--network host`,JAR bind mount)
- **关键坑①(协议)**: OTel Java Agent ≥2.x 已**移除 `http/json`** 协议,只支持 `http/protobuf`/`grpc`;旧接入指引的 `OTEL_EXPORTER_OTLP_PROTOCOL=http/json` 会启动失败。改为 signal 级配置: `OTEL_TRACES_EXPORTER=otlp`、`OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf`、`OTEL_METRICS_EXPORTER=none`、`OTEL_LOGS_EXPORTER=none`
- **关键坑②(endpoint 语义)**: OTel SDK exporter 请求 URL = `OTEL_EXPORTER_OTLP_ENDPOINT` + `/v1/traces`。所以 SDK/Agent 配 base 地址 `http://11.0.1.1:8000`(不带路径);手动 SDK(如 Python `OTLPSpanExporter(endpoint=...)`)需带完整 `/v1/traces`
- **关键坑③(平台只收 JSON)**: 原平台只有 `/api/v1/traces/otlp`(仅 OTLP JSON),现代 SDK 用 protobuf → 为平台新增标准端点 **`POST /v1/traces`**(按 Content-Type 分发:json→`ingest_otlp_json`,其它→新 `ingest_otlp_protobuf`;装 `opentelemetry-proto`)
- **代码改动**: `app/routers/trace_ingest.py`(新增 `standard_router`+`receive_otlp_standard`;`ingest-status` 返回 `otlp_endpoint="/v1/traces"`+`otlp_base`;`agent-guide` 的 java/python/go/nodejs/k8s/docker/traditional 七块全改为 http/protobuf + base endpoint + metrics/logs none,**0 处旧 http/json 残留**)、`app/services/trace_ingest_service.py`(`ingest_otlp_protobuf`+`_pb_value_to_str`/`_pb_attrs_to_dict`)、`app/main.py`(注册 standard_router+PUBLIC_PATHS 加 `/v1/traces`)、`app/services/license_service.py`(白名单 `_LICENSE_PUBLIC_PREFIXES` 加 `/v1/traces`,非 `/api/` 路径必须加否则被拦截)
- **132 接入**: 下载 OTel Java Agent 2.30.0 到 `/data/otel/opentelemetry-javaagent.jar`;重建 mall-portal/mall-gateway 容器(`/data/_rebuild_mall_otel.sh` 驻留 132),javaagent + `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://11.0.1.1:8000/v1/traces`;流量入口: `curl http://localhost:8201/mall-portal/home/content`、`/home/recommendProductList`、`/product/list?pageNum=1&pageSize=5`
- **验证结果**: 平台 ingest-status 141 spans/58 traces/services [mall-auth,mall-gateway,mall-portal](+测试服务);真实跨服务链路验证:① gateway→portal→**MySQL(mall.pms_product SELECT 子 Span)** ② gateway→auth→**Redis GET 子 Span**。登录后 `/api/traces` 列表/详情正常,拓扑 gateway→portal/auth 正确
- **前端无需改**: TraceAgentGuide.vue 直接消费 `res.otlp_endpoint`(`/v1/traces`),dev 构建产物直接生效
- **清理**: logs/ 下临时脚本全删(`_ssh.py/_deploy.py/_trace_otlp_test.py/_trace_pb_test.py/_rebuild_mall_otel.sh` 及 _*.log)
- **契约**: CONTRACT.md 的 `spans` 章节后新增「OTLP/HTTP 链路接入契约」(标准端点 /v1/traces、http/protobuf 禁用 json、Content-Type 分发、endpoint 语义、License 白名单)
- **遗留可选**: 131 K8s microservices-demo(12 服务)接入;spans 表含测试数据(std-ep-test/pb-gateway 2 条),可选择性清理

### 2026-08-08: 智能推荐「基线检查」0 项修复——根因是 `security_baseline_templates` 表为空 + seed 缺失
- **根因**: 基线模板表 `security_baseline_templates` 全表 0 行;`seed_data.py` 从未播种该表。后端逻辑本身是通的(`baseline_service.get_baseline_templates` 按 `ci_type` 经 `_CI_ALIASES` 归一化 virtual_machine→server 匹配 `ci_type IN ([归一化值, "all"])` + enabled),空表导致前端「基线检查项 · 0 项 / 该资产暂无基线模板」
- **修复**(`app/seed_data.py`,纯数据播种,后端无需重启):
  - import 补 `SecurityBaselineTemplate`
  - 新增 `seed_baseline_templates(db)`(幂等,按 ci_type+check_key 查重),**20 条模板**: `all`5(空密码用户/shadow 权限/docker 存活/高危端口/补丁人工复核)、`server`4(SSH 禁密码/禁 root/磁盘<80%/防火墙)、`database`4(MySQL 空密码/匿名/root 远程/密码强度)、`middleware`3(Redis requirepass/RabbitMQ guest/版本复核)、`kubernetes_cluster`4(APIServer readyz/匿名绑定/异常 Pod/节点 Ready)
  - `seed_all()` 内 **marker v2 检查之前**调用 `seed_baseline_templates(db)`(同 AgentConfig 播种策略,否则 marker 早退不生效)
  - 执行:`python -c "from app.seed_data import seed_all; seed_all()"` → 20 条落库(all5/server4/database4/middleware3/k8s4)
- **验证**: `GET /baseline/checks/{id}` 现返回:asset1/2(vm→server)=9 项、asset3(k8s_cluster)=9 项、pod 资产=5 项(all 兜底);`POST /baseline/check-all/1` 真实 SSH 连 11.0.1.131 出结果:pass 2(docker_alive/disk_usage_ok 39%)、fail 4(no_blank_passwd/shadow_permission/ssh_no_password_auth/ssh_no_root_login)、na 3(manual 1 + 执行失败 2)
- **已知小缺陷(非本次 bug,后续可优化)**: ① SSH 检查 `actual_value` 有时只回 `exit_code=0` 而非命令 stdout(expect 正则对不上 → 误判 fail) ② `grep -c` 计数为 0 时退出码 1 被当成「执行失败」na(danger_ports_closed 应 pass) ③ Windows 控制台打印中文需 `sys.stdout.reconfigure(encoding='utf-8')` 否则 mojibake(DB/API 数据本身是正常 UTF-8)
- **测试脚本**: `business-demos/_rb_scenario_test.py`(Runbook)在侧;基线播种验证用内联 python 脚本即可

### 2026-08-08: Agent 评测三页合并为一页「Agent 评测中心」(Agent 评估 + GroundTruth + A/B 测试)
- **背景**: Agent 管理分组下 8 个菜单过密;Agent 评估(线上质量看板)/GroundTruth(离线基准测试集)/A/B 测试(模型对比实验)同属"Agent 质量评估",拆分是功能碎片化
- **合并**: `AgentEvalView.vue` 改造为三 Tab 容器(质量看板/基准测试集/模型对比),后两 Tab 直接 import 原 `AgentGroundTruthView.vue`、`ABTestView.vue` 作为子组件
- **删除**: ① menu_config.json 删除 `ab-test`、`agent-ground-truth` 两个菜单项,`agent-eval` 改名为「Agent 评测中心」② AppLayout.vue 删除 ABTestView/AgentGroundTruthView 组件注册 + VUE_PAGES 中两 key
- **保留**: `AgentGroundTruthView.vue` / `ABTestView.vue` 文件本身(作为 AgentEvalView 的 Tab 子组件被 import,非死代码)
- **后端不动**: `/agent/api/ground-truth/*`、`/agent/api/ab-test/*` 路由仍由 Tab 页消费
- **验证**: 前端 build 通过(37s);menu JSON 合法;后端重启后 `/api/menu` 无 ab-test/agent-ground-truth(0),「Agent 评测中心」存在;HTTP 303 正常

### 2026-08-08: 删除「运维知识图谱」独立页面(kb-graph 与架构巡检图功能重叠)
- **背景**: 知识管理分组下 8 个入口过密;「运维知识图谱」(ECharts 力导向图)仅展示 `asset_relations` 依赖,与架构巡检图(FireMapView,分层模型/故障高亮/49 条连线)功能重叠,无下游依赖、非功能入口
- **保留**: 「知识图谱推理」页(graph-inference,故障传播/根因定位)及其后端 `/knowledge/graph/api/*` 路由(`GraphInferenceView.vue` 依赖,不可删);`knowledge_graph_service` 被 alert_service/incidents 引用,保留
- **删除**: ① menu_config.json 移除 kb-graph 菜单项(JSON 已校验) ② AppLayout.vue 移除组件注册+defineAsyncComponent+VUE_PAGES 中 'kb-graph' ③ 删除 `frontend/src/views/KnowledgeGraphView.vue`
- **验证**: 前端 build 通过(42s);后端重启后 `/api/menu` 返回中无 kb-graph(0);HTTP 303(未登录重定向,正常)
- 后端路由 `app/routers/knowledge_graph.py` 未删(被推理页消费)

### 2026-08-08: Runbook 实际使用场景测试(16/16 通过) + 修复 2 个字段契约缺陷
- **文档**: `business-demos/Runbook场景测试.md` + 可复跑脚本 `business-demos/_rb_scenario_test.py`(幂等)
- **场景**(对齐 `business-demos/部署文档.md` 三靶场): ① 建 6 条靶场 Runbook(K8s Pod 删除/mall-swarm 中间件宕机/OOM/裸机进程崩溃/磁盘满/Web 重启) ② CRUD ③ MCP `query_runbook` 检索(关键词/分类/资产类型/limit/负例) ④ 告警→Runbook 智能推荐(alert#3 K8s pod→命中、#1 disk→磁盘手册、#2 memory→负例) ⑤ AI 对话触发 query_runbook(实测调用 3 次)
- **发现并修复 2 个缺陷**(`app/routers/runbooks.py`,纯后端,前端无需重建):
  - ① `tags` 传数组直接 500:`sqlite3 ProgrammingError: type 'list' not supported` → 新增 `_norm_tags()`(list→json.dumps 字符串),create/update 统一归一化
  - ② 前端「内容」字段(`content`)被静默丢弃:模型只有 symptom/diagnosis 无 content → 做 `content ↔ symptom` 别名互通(create/update 收 content 写 symptom,`_rb_to_dict` 返回 content),前端保存/回显恢复
- **契约**: CONTRACT.md 第七章后新增 `runbooks` API 契约小节(content 别名/tags 归一化/query_runbook 检索/告警联动评分)
- **数据**: aiops.db runbooks 表落 6 条演示数据;后端已重启(pid 已更新,HTTP 200)
- **踩坑**: ① PowerShell 命令里 `$` 变量被 bash 吞 → 报 ParserError,拆分命令避免 `$` ② `call_mcp_tool` 返回 `{status, result}`,结果在 `result.count` 不在外层 ③ smart-recommend 路由是 `/api/recommend` 不是 `/runbook-recommend` ④ Runbook 列表按 updated_at 倒序,测试不能假设 items[0]

### 2026-08-08: 资产"部署报告"按钮无反应——真正根因是模板 div 嵌套错位(修正此前 v-if 修复结论)
- **真相**: 前一条"v-if 依赖对象 ref 不触发重渲染"的结论是**错的**。用嵌套配对脚本(`<div` 开/闭栈追踪)证明:`AssetsView.vue` 编辑表单弹窗 `showForm`(85 行 `<div v-if="showForm" class="modal-overlay">`)缺少 1 个 `</div>`,一直开到最后(367 行)才闭合 → **WebSSH 弹窗(327 行)和部署报告弹窗(339 行)被错误嵌套进 showForm 内部**。点部署报告设 `deployDocVisible=true` 但父级 `showForm=false` → 整棵子树不渲染 → 弹窗不出现;点编辑 `showForm=true` → 嵌套的部署弹窗跟着渲染 → 用户看到部署报告弹窗
- **修复**: ① 在 showForm 的 modal-box 闭合处(原 324 行后)补 1 个 `</div>` 关闭 modal-overlay ② 末尾删 1 个多余的 `</div>`(原 368-369 行)。三个弹窗恢复为平级兄弟节点
- **验证**: 嵌套配对脚本 showForm@325 关闭、webssh@337、deploy@367,剩余未关闭 0;新 chunk hash 变为 `AssetsView-CZMnTz2M.js`(旧 `DXKcsxOu`),编译产物中三个弹窗分支 key:1/2/3 平级;8000 端口已吐新 chunk
- **教训**: 排查弹窗不显示,先验证**模板嵌套层级**再怀疑响应式;编译产物变量名被压缩,`grep` 源码变量名查 dist 会误判
- 改动: `frontend/src/views/AssetsView.vue`,已构建

### 2026-08-08: 移动端 401 误报"无法连接服务器"修复(统一请求层)
- **根因**: 移动端未登录时,`getDashboard()` 请求 `/mobile/dashboard`(`require_user`)返回 **401**。但 `dashboard.js` 等各 api 文件**自封装的 request 未处理 401**(仅 `request.js` 处理了),把 401 当普通失败 reject → `index.vue` `loadData` catch 弹"无法连接服务器"——实为**未登录**误报
- **修复**: ① `request.js` 的 401 分支增加清理残留登录态(`auth_token`/`user_info`/`biometric_token`/`session_cookie`)再 `reLaunch` 登录页;`request` 增加 `timeout` 参数支持 ② `dashboard/alert/incident/oncall/mobile/metrics/workflow/asset/agent` 九个 api 文件全部改为 `import { request } from './request.js'` 统一复用(`agent.js` 的 sendMessage 保留 120s 超时)③ `log.js` 因含 cancelKey 逻辑保留自有 request,单独补 401 处理 ④ `index.vue` `loadData` catch 内先 `userStore.loadFromStorage()` 再判断 token,避免 401 清存储后仍弹窗
- **验证**: `npm run build:h5 --prefix mobile` 构建通过;dev server 编译无错
- 纯前端改动,无后端改动

### 2026-08-08: 新增对外销售《功能清单与卖点手册》
- **文档**: `docs/对外销售功能清单与卖点手册.md`——面向客户/渠道伙伴的销售材料（原在 business-demos/，后移入 docs/）
- **内容**: ①一句话定位+电梯话术 ②客户痛点→本系统解法表(5条开场必讲) ③9大模块功能清单(可观测/告警/根因/AI助手/自动化/SRE/资产K8s/移动端/安全)每条配卖点话术 ④7条核心卖点(强调"AI真干活非演示壳""知识越用越聪明""6种根因算法+AI双保险""告警降噪90%""真环境演示") ⑤4档报价方案(源码打包1.5~5万/私有化交付10~20万/定制20~50万+/年维护15~20%) ⑥4种典型异议话术(对标Zabbix/质疑AI/嫌规模小/怕部署难) ⑦现场演示成交7步
- **口径依据**: 系统真实功能(经 routers/services/views 盘点),无虚标;demo 环境用 131 K8s 微服务 / 132 mall-swarm
- 纯文档,无代码改动

### 2026-08-08: 修复资产列表"部署报告"按钮无反应 bug
- **根因**: 部署弹窗 `v-if="deployDocAsset"` 依赖对象 ref，模板尾部 2 个多余 `</div>` 闭合标签(367-368 行)影响 Vue patch 机制，该 ref 变化时未触发重渲染；点击"编辑"触发 `showForm` 的更大范围重渲染才顺带带出部署弹窗
- **修复**: 新增 `deployDocVisible` boolean ref 独立控制显隐，`v-if="deployDocVisible"`，`deployDocAsset` 仅用于数据传递，关闭时同时重置两个 ref
- **改动**: `frontend/src/views/AssetsView.vue`(模板 + script)
- 已 `npm run build --prefix frontend` 构建通过

### 2026-08-08: 新增小白版《AI 处理问题逻辑顺序》指南文档
- **文档**: `docs/AI处理问题逻辑顺序小白指南.md`——专给非技术人员看，重点讲"顺序"（原在 business-demos/，后移入 docs/）
- **核心 5 步顺序**: ①先认人(`query_assets` 查设备档案) → ②翻病历(`query_alerts` 告警 + `query_change_records` 变更) → ③按需翻书(`query_runbook` 作业手册 / `query_knowledge_rag` 历史案例库/部署文档) → ④综合分析 → ⑤确认后动手(`propose_action`)
- **重要澄清(写入文档)**: `query_change_records` 只记**平台自身看到的资产变化**(前端改资产属性 `asset_service.py:69` + 健康扫描 `asset_change_service.py:36`)，**不感知 SSH 手动改 nginx.conf 等文件级改动**——属"平台元数据变更审计"非"配置审计"
- **部署文档两种用法(写入文档)**: 普通 AI 对话=第③步按需翻(`query_knowledge_rag(query, asset_id)`);系统自愈=`remediation_service.py:1558` 开场硬塞注入
- **两条完整路线示例**: A 主动提问 vs B 系统自愈，顺序差异(部署文档在第③步 vs 开场)
- 纯文档，无代码改动

### 2026-08-08: RAG 检索支持 asset_id 过滤——普通 AI 对话可稳定检索资产部署文档
- **背景**: 资产列表可上传部署文档（`knowledge_documents.py` 写 `asset_id`+`source_type="upload"`），但 `query_assets` 不返回文档内容；此前只有自愈/建议场景（`remediation_service.py:1558`）按 asset_id 注入部署文档，普通 AI 对话只能靠 `query_knowledge_rag` 内容相似度"撞"，不保证命中
- **补强**: ① `rag_service.vector_search` 新增 `asset_id` 参数，经 `kb_chunks.document_id JOIN kb_documents.id` 过滤 `kb_documents.asset_id`（`kb_chunks` 表**不加列**）② `mcp_tools.py` `query_knowledge_rag` schema + 实现透传 `asset_id` ③ `agent_service.py` system prompt 引导：用户提到具体资产/主机/服务时主动 `query_knowledge_rag(query=..., asset_id=资产ID)` 检索该资产部署文档/运维知识
- **契约**: CONTRACT.md RAG 检索链路约定追加 asset_id 过滤说明
- **验证三层通过**: ① 联调 `vector_search(asset_id=2)` 命中 doc1（部署文档，35 切片）；`asset_id=1` 隔离为空 ② `get_mcp_manifest()` schema 含 asset_id ③ 真实调用 `query_knowledge_rag(query="部署 安装 方式", asset_id=2)` → 命中 doc1 ×3（sim 最高 0.42）
- 后端已重启（HTTP 200）；无前端改动

### 2026-08-08: RAG 知识沉淀双写修复——多场景验证(6 场景全过)
- **新文档**: `business-demos/RAG知识沉淀双写验证.md`(缺陷背景 + 6 场景设计与实测结果)
- **场景覆盖**: ①告警源闭环(alert#127→kb3→doc5) ②故障单源(incident#1→kb5→doc6) ③SOP源(incident#25→kb6→doc7, linked_alerts=[36]) ④检索质量/过滤边界(asset_type/severity 过滤正确) ⑤幂等性(重复审批被拒) ⑥数据完整性(auto 文档=切片=6, 1:1)
- **发现(已知局限,非本次引入)**: v1 TF-IDF 中文按**单字**分词,`内存相关` 之类查询会匹配含"内/存"字文档产生低分噪音(sim<0.2);可用过滤条件降噪,升级 v2(BGE-M3+Milvus)自然消除
- 库中现有 6 条 auto 知识(草稿1/3/5/6/7/8 approved → kb1~6),全部已双写索引
- 临时脚本已删除

### 2026-08-08: 告警中心与故障单操作统一（简化+同步）
- **背景**: 告警中心要"确认→解决"两步，故障单直接"解决"一步，操作流程不一致
- **方案**: ① 告警中心去掉"确认"步骤，直接"解决"（与故障单一致）；② 告警解决后自动同步关联故障单（若关联故障单的所有告警都已解决，则自动解决该故障单）
- **改动**: `frontend/src/views/AlertsView.vue`(模板中告警操作按钮从"确认/解决"改为直接"解决"、移除"批量确认"/"全部确认"按钮、移除 script 中 `batchAckSelected`/`batchAck`/`ackAlert` 三个函数);`app/services/alert_service.py`(新增 `_auto_resolve_incident_for_alert` 函数——告警解决时查关联故障单，若全部告警已解决则自动关单；`resolve_alert` 和 `batch_resolve` 中均调用该函数)
- 已 `npm run build --prefix frontend` 构建通过

### 2026-08-08: 修复 RAG 同步缺口——approve_draft 审批通过后同步索引到 AI 助手可检索
- **修复**（`app/services/knowledge_autogen_service.py:167` `approve_draft`）：写入 `knowledge_base` + `alert_kb_links` 后，**新增创建 `kb_documents`（source_type=auto，kb_id 关联本知识，content=标题+症状+根因+解决方案+标签拼接）并调用 `rag_service.index_document` 索引**；索引失败则整体回滚审批。需 `from app.models import KbDocument`
- **同步契约**（CONTRACT.md）：knowledge_drafts API 约定补充"审批通过后同步 RAG"；新增 `kb_documents`/`kb_chunks` 表完整字段定义 + RAG 检索链路约定（query_knowledge_rag 只查 kb_chunks，故所有需被 RAG 检索的知识必须同步建 kb_documents 并 index）
- **数据回填**：本次演练遗留的 kb_id=1/2/3（此前只入 knowledge_base 无 RAG 文档）已补建 doc_id=3/4/5 并索引；草稿 #5（SOP）审批验证后生成 kb_id=4 + doc_id=2
- **验证通过（三层）**：① 审批后 kb_documents 自动出现 status=indexed ② `rag_service.vector_search` 三个查询全部命中新知识 ③ AI 助手真实路径 `call_mcp_tool('query_knowledge_rag')` 命中全部 4 条 auto 知识（chunk 36-39，sim 0.27~0.53）
- **⚠️ 踩坑**：`call_mcp_tool` 报 "Tool not found" 是因为装饰器注册在 `import app.services.mcp_tools` 时触发，脚本需先导入该模块再调用
- 临时验证脚本已全部删除；后端已重启（pid 39812, HTTP 200）

### 2026-08-08: 知识草稿审批功能全流程模拟通过(API 走通)
- **前提**: 库中草稿=0、resolved 告警=0,但有 38 个故障单/126 条告警 → 用故障单生成草稿
- **踩坑1**: 后端进程跑旧代码 → 所有 API 返回 SPA HTML(实为 303→/login),非路由丢失。杀进程重启后正常
- **踩坑2**: 后端鉴权是 **session cookie**(非 JWT),需先表单 POST `/login`(admin/admin123)拿 cookie,再用 opener 携带访问 `/knowledge/api/auto-gen/*`
- **流程验证**: 登录 → stats=全0 → 从故障单#38 生成知识草稿(draft_id=1「vm-131-master1 CPU使用率过高（81.4%）」) + SOP 草稿(draft_id=2) → 通过#1(返回 kb_id=1 + linked_alerts=[126]) → 拒绝#2(带 reason) → 列表/统计正确(pending=0/approved=1/rejected=1)
- **入库验证**: knowledge_base 新增 2 条(source_type=auto),alert_kb_links 建 2 条关联(alert 126 → kb 1/2)
- 临时脚本 `logs/_sim_draft.py` 已用完即删

### 2026-08-08: 故障单管理移除审批流程（简化操作）
- **背景**: 故障单列表同时有"解决"和"提交审批"两个按钮，审批流程增加操作复杂度，对运维场景效率优先
- **方案**: 隐藏所有审批相关 UI（提交审批/审批通过/驳回/审批设置），仅保留"解决"按钮直接关单
- **改动**: `frontend/src/views/IncidentsView.vue`(移除模板中审批按钮+弹窗+审批设置对话框、移除 script 中所有审批函数/状态/CSS);`frontend/src/views/UserGuideView.vue`(移除链路11审批流、更新链路1/9引用)
- **后端不变**: 审批相关 API 仍保留在 `app/routers/incidents.py` 和 `app/services/incident_service.py` 中，但不影响前端使用
- 已 `npm run build --prefix frontend` 构建通过

### 2026-08-08: 日志中心服务下拉改为真实服务名(修复只显示 k8s/docker 采集任务)
- **背景**: 服务下拉原读 Loki `label/job/values`,只返回采集任务名 `kubernetes-pods/docker-containers/mall-bare`,用户看不到具体服务
- **方案**: 服务名从 **filename 标签**解析:① k8s 路径 `/var/log/pods/<ns>_<pod>_<uid>/<c>/<n>.log` → 去 rs/pod hash 后缀得 deployment 名(如 `adservice-845cd8755b-rrfr4`→`adservice`);② docker 路径只有容器 hash → 后端 SSH 132 `docker ps` 建 id→name 映射(缓存 5 分钟)得 `mall-search` 等;③ 裸机 `/data/mall/logs/x.log` → 文件名
- **改动**: `app/services/log_query_service.py`(新增 `parse_loki_service_name`/`_load_docker_container_map`/`_service_selector`,adapter 的 service 从 `job=` 改 `filename=~` 匹配,返回 service 字段用真实名);`app/routers/logs.py`(新增 `GET /logs/api/services`);`frontend/src/views/LogsView.vue`(服务下拉改读 services 接口)
- **⚠️ 踩坑1**: Loki `=~` 是**全字符串匹配**(非部分匹配),正则必须以 `.*` 开头覆盖完整 filename(如 docker `/var/lib/docker/containers/...` 必须 `.*/containers/<id>.*`)
- **⚠️ 踩坑2**: Loki RE2 不支持 Python `re.escape` 产出的 `\-` 转义(`redis-cart`→`redis\-cart` 报 `invalid char escape`),需自定义 `_re2_escape` 只转义 `[\\\.\+\*\?\(\)\|\[\]\{\}\^\$]`
- **⚠️ 踩坑3**: docker 容器 hash 是 64 位全量,映射表只存 12 位短 id → 匹配正则用 `<id>[a-f0-9]*`
- **验证通过**: adservice 22067、mall-search 241324、mall-gateway 20247、redis-cart 365、kube-apiserver-master1 178、etcd-master1 271,全部命中且只返回对应服务
- **前端 Playwright 验证**: 服务下拉实际显示 28 个真实服务名(截图 logs_check.png),选中 mall-search 正常
- 需重启后端 + 重建前端;服务列表 28 项(k8s 微服务 + docker 容器 + 系统组件)
- 详见 `business-demos/Loki部署实战.md` 第九、十章(索引下拉 + 服务发现,踩坑 15~18)

### 2026-08-08: 解决误报根因——停用自适应检测，改用固定阈值
- **根因**: 3σ 和 EWMA 都犯同一个错——用极小 std_res 归一化，微小波动被放大成高 z 分位
- **操作**: 停掉 cpu_usage/memory_usage/disk_usage 的异常检测配置，改为固定阈值告警规则（CPU>90%、内存>85%、磁盘>90% → critical）
- **卡片说明**: 异常检测页顶部加引导 banner，明确区分"有危险线→去告警规则" vs "不知道正常值→用本页"
- **改动**: `frontend/src/views/AnomalyView.vue`(卡片说明)、`app/routers/reports.py`(修复 report.data→report.report_data)

### 2026-08-08: 日志中心索引过滤文本框改为自动加载下拉
- **背景**: 索引过滤原本是手动文本框,用户不知道 ES 索引名(如 `aiops-logs-2026.08.08`)无法填
- **改动**: `frontend/src/views/LogsView.vue` 索引输入框 → `<select>` 下拉,选中 ES 数据源后自动调 `/logs/api/indices` 拉取索引列表(`name (docs 条)` 显示);Loki 数据源隐藏索引过滤(Loki 无索引概念,用服务/job 下拉代替)
- 后端 `/logs/api/indices`(logs.py)为既有接口,无需改动;已 `npm run build --prefix frontend`
- ⚠️ 当前库里只有 Loki 数据源(id=2),无 ES 数据源 → 索引下拉不显示属正常

### 2026-08-08: 日志中心翻页修复(后端 total 恒为 1)
- **根因**: ① `LokiAdapter.query()` 用 `len(logs)` 当 total,但 Loki `query_range` 的 `limit` 是"每 stream 条数"、stream 间不排序,取回条数≠总数、无法按位置切片;② `_query_loki` 忽略 adapter 返回的 total 又用 `len(raw_logs)` 覆盖 → total 恒为单页条数 → 翻页按钮隐藏
- **修复**: ① 取日志前用 `count_over_time(expr[窗口])` 聚合真实总数(`app/services/log_query_service.py`);② 日志全局按 `timestamp` 倒序排序保证分页切片准确;③ `_query_loki` 透传 total,`limit = min(max(page*size, 200), 500)`(`app/routers/logs.py`)
- **⚠️ 踩坑**: Loki instant query 返回结构是 `{"value": [ts, count]}` 而非 range 的 `{"values": [...]}`,按 `values` 解析报 `float[1]` 错被 except 吞掉 → total=0;修复 `vals = s.get("values") or [s.get("value")]`
- **验证通过**: 1h 无过滤 217,549/4,351 页;service=kubernetes-pods 83,972;level=error 575/12 页;24h 508,175/10,164 页;page 间时间倒序正确
- 纯后端改动,前端已有分页 UI 无需改、无需重建前端
- 详见 `business-demos/Loki部署实战.md` 第八章

### 2026-08-08: 日志中心过滤修复(host/level/service 三维度全链路打通)
- **根因**: Loki 原本只有 `filename/job/stream` 标签,无 `host/level`;且 `_query_loki` 没把 `service` 传给 LokiAdapter → 三个过滤项全筛不出数据
- **promtail 采集端加标签**(131 `/data/promtail-k8s.yaml` + 132 `/data/promtail132.yaml`):
  - k8s job: `regex` 从 CRI JSON 提取 `severity/level` 为 `level` 标签 + `host: "11.0.1.131"`
  - docker-containers job: `regex ' (?P<level>[A-Z]+) '` 提取 level + `host: "11.0.1.132"`
  - mall-bare job: 已有 regex 提取 level,补 `labels: level` + `host: "11.0.1.132"`
  - 已应用: `kubectl apply + rollout restart daemonset promtail`(2 节点成功);`docker restart promtail132`
  - 验证: `label/host/values → ["11.0.1.131","11.0.1.132"]`;`label/level/values → ["DEBUG","ERROR","INFO","WARN","debug","info"]`
- **⚠️ 踩坑: promtail `template` stage 在 source 缺失时整行丢弃** → **不用 template 归一化大小写**,改后端 `(?i)` 正则匹配
- **后端**: `log_query_service.py` LokiAdapter `service→job=` 标签过滤 + `level=~"(?i)^x$"` 大小写不敏感;`routers/logs.py` `_query_loki` 透传 service + 新增 `GET /logs/api/jobs`(查 Loki `label/job/values`);`mcp_tools.py` query_logs 加 service 参数
- **前端**: `LogsView.vue` 服务过滤文本框→下拉(jobs 接口),Loki 显示下拉、ES 保持文本框;已 `npm run build`
- **API 验证通过**: `service=kubernetes-pods`→仅 131;`service=docker-containers`→仅 132;`level=error`→仅 ERROR;`host=11.0.1.132`→仅 132;`host=131+level=info` 组合正常
- ⚠️ 新标签只对新写入日志生效(positions 记偏移,不重读历史),host/level 过滤查不到修复前数据
- 详见 `business-demos/Loki部署实战.md` 第七章

### 2026-08-08: 事件统计 + 告警收敛闭环合并为一个页面
- 将「告警收敛闭环」功能并入「事件统计」页面，用顶部 Tab 切换（事件统计 / 告警收敛闭环）
- 移除独立菜单项 `alert-correlation`，菜单改名为「事件统计与收敛」
- **改动**: `frontend/src/views/EventStatsView.vue`(合并)、`app/routers/menu_config.json`、`frontend/src/layout/AppLayout.vue`(移除 AlertCorrelationView 注册)

### 2026-08-08: 3σ 异常检测误报修复 + 编辑功能支持
- **根因**: 3σ 不适合 disk_usage/memory_usage 等窄范围/趋势型指标，σ 极小导致微小波动放大为高 z 分位
- **修复**: disk_usage 和 memory_usage 改为 EWMA 算法（自适应基线漂移），CPU 保持 3σ 不变
- **新增**: 异常检测配置页增加「编辑」按钮 + 后端 `POST /api/configs/{id}/update` 端点
- **改动**: `app/routers/anomaly.py`、`frontend/src/views/AnomalyView.vue`、`MEMORY.md`

### 2026-08-08: Loki 实战部署完成(全链路验证通过)
- 131 Loki 2.9.2 + promtail DaemonSet;132 promtail Docker 容器 + 裸机 `/data/mall/logs`;135 实战文档 `business-demos/Loki部署实战.md`(一~六章全部填充)
- **AIOps 平台数据源 id=2 `Grafana Loki(131)` 创建并测试通过**(`Loki ok, labels=3`)
- **修复 LokiAdapter 空选择器 Bug**: 无过滤条件时生成 `{}` → Loki 400 `queries require at least one regexp...` → 兜底 `{job=~".+"}`(改动 `app/services/log_query_service.py:214`,改后需重启后端)
- **✅ 虚机时间已同步到本机**: 131/132 均 `date -u -s` 到本机 UTC 时间并重启 loki / promtail DaemonSet / promtail132。**时间差问题已消除**,平台默认 `1h` 窗口即可查到实时数据(131 K8s + 132 Docker 同屏),不再需要 `24h` 兜底
- ⚠️ 若虚机重启后时间回退漂移,需重新同步(`date -u -s "<本机UTC>"` + 重启 loki/promtail)
- **日志中心下拉框只有 1 个数据源是正常架构**: 132 日志由 promtail 远程推入 131 的 Loki,一个数据源即含 131 K8s + 132 Docker + 132 裸机三类日志
- 24h 行数(同步前): kubernetes-pods **230,027 行/27 流**、docker-containers **57,503 行/7 流**、mall-bare **2 行/2 流**(稀疏但实时)
- 平台 API 验证: `/logs/api/sources` 正常;`/logs/api/search?source_id=2&query=*&time_range=24h` 同时返回 kubernetes-pods + docker-containers;`query=ERROR` 命中 mall-search;分页正常

### 2026-08-08: 通知发送记录前端全部显示"失败"修复
- **根因**: `NotificationsView.vue:56` 用 `l.success` 引用后端 `is_success` 字段,字段名不匹配 → 永远 `undefined` → 全显"失败"
- **修复**: `l.success` → `l.is_success`
- **改动**: `frontend/src/views/NotificationsView.vue`

### 2026-08-08: 数据源接入 Grafana Loki(日志中心+MCP)
- 新增 `LokiAdapter`(LogQL),DS_TYPES 加 loki,`_test_loki` 测试连接,`_query_loki` 搜索
- 改动: `log_query_service.py`、`datasource_service.py`、`routers/logs.py`、`mcp_tools.py`、`CONTRACT.md`

### 2026-08-08: 指标监控资产下拉只显示"全部资产"修复
- **根因**: `MetricsView.vue` loadAssets 用 `Array.isArray(data)` 判断,但接口返回 `{items,total}` 对象 → 被判非数组
- **修复**: 改为 `data?.items || []`
- 架构巡检图分层模型盘点+智能分析室筛选能力盘点
- **改动**: `frontend/src/views/MetricsView.vue`

### 2026-08-08: K8s 资产误置灰修复(132 资产真实离线)
- **根因**: `_scrape_kubernetes` 未写 `status` 字段 → `asset_status=None` → 不更新 → 保留历史 offline
- **修复**: 各资源 attrs 补 status(cluster/namespace/ deployment/pod/service)
- 132 节点 16 资产真实离线(全端口 Timeout)
- **改动**: `app/services/datasource_service.py`

### 2026-08-08: 智能体测试绕熔断器 + 3σ 抑制机器启动误报
- `test_provider` 开头 `breaker.reset()` 绕过熔断器
- 3σ 检测新增 `_has_recent_gap()`(>180s 数据缺口跳过判定,避免关机后启动误报)
- **改动**: `ai_providers.py`、`anomaly_service.py`

### 2026-07-30: 新增「暗色玻璃」全局主题
- `html[data-theme="dark-glass"]`:纯黑背景+玻璃卡片+青绿强调色
- AgentChatView 全组件适配
- **改动**: `AppLayout.vue`、`main.css`

### 2026-07-30: 自愈工作流大修(3致命硬伤+编辑+模拟+日志FK)
- healthcheck 动作不存在、规则触发不走工作流、手动触发不按 rule_id 匹配 三项修复
- 新增编辑/模拟(dry-run)/步骤参数预览
- RemediationLog FK 修复(改为无 FK 列+remediation_type)
- **改动**: `remediation_service.py`、`remediation_workflow.py`、`alerts.py`、`models.py`、`main.py`、`RemediationWorkflowView.vue`

### 2026-07-30: 自愈 6 大功能(转交智能助手/知识沉淀/风险分类器/CI通道/关联分析/诊断包)
- 转交通道 `POST /agent/transfer-from-remediation`、执行成功自动生成知识草稿
- 风险分类器复用(critical:4 修复)、CI-Type-Aware 执行通道(K8s/Docker 放行只读命令)
- 关联分析注入(60s 缓存)、预置诊断命令包 MCP 工具
- 二次修复: _RISK_MAP 缺 critical、K8s/Docker run_command 限制、无 alert_id 诊断
- **改动**: `mcp_tools.py`、`remediation_service.py`、`RemediationView.vue` 等

### 2026-07-29: 规则自愈 AI 前端超时修复(axios 30s→130s)
- **根因**: `RemediationView.vue` 4 处 AI/诊断请求未传 timeout,axios 默认 30s 掐断 LLM 请求(后端 120s)
- 对比其他页面均正确传 130s,仅 RemediationView 漏传
- **改动**: `RemediationView.vue`

### 2026-07-29: 自愈迭代诊断循环(Agentic Diagnostic Loop)
- 最多 5 轮迭代,每轮 AI 判断 `diagnosis_sufficient`,不足则推荐工具自动补诊
- `DiagnosisReport` 加 `round_num` 字段,前端按轮次分组展示
- 菜单改名"灭火图"→"架构巡检图"
- **改动**: `models.py`、`main.py`、`remediation_service.py`、`RemediationView.vue`

### 2026-07-28: SVG拓扑连线+资产依赖49条+分层模型
- SVG 贝塞尔曲线连线故障实体红线,`drawRelations()` 通过 `data-eid` 定位
- 49 条资产关系写入 `asset_relations`
- 4 层分层模型:接口→应用→数据(DB+MQ并排)→基础设施
- **改动**: `FireMapView.vue`、`health_engine.py`

### 2026-07-27: 灭火图3域多域交叉+资产编辑加业务域+aiops.db修复
- 69 资产分 3 域,共享中间件多域交叉
- 资产编辑页加业务域字段(逗号分隔)
- aiops.db 严重损坏修复(`_fix_db.py` 逐表导出→重建→导入)
- 告警全清、License 公钥重导、K8s 关机仍 online 修复、离线告警抑制
- AI 自愈 JSON 解析容错(`_parse_lenient_ai_json`)、LLM 超时 30→90s
- **改动**: `health_engine.py`、`AssetsView.vue`、`alert_service.py`、`datasource_service.py` 等

### 2026-07-27: 诊断折叠面板 Bug 不存在(验证后确认)
### 2026-07-26: 诊断先行+三架构靶场+告警规则页
### 2026-07-25: 自愈资产感知+拓扑Tab化+多功能补齐
### 2026-07-24: AI 自愈 6 轮 70 用例通过
### 2026-07-21: 拓扑树默认展开+GuideDrawer 覆盖
### 2026-07-20: 安全加固+ES 超时+日志字段重命名
### 2026-07-19: 安全自查+移动端+全项目 fail-soft
### 2026-07-17~18: AI 助手 32 场景+产品介绍页 v2
### 2026-07-16: SSE 实时推送+ECharts 泳道图+多租户+RBAC
### 2026-07-15: 全库字段规范化+仪表盘+诊断工具+智能巡检
### 2026-07-14: 灭火图+路径清理+蓝绿发布+部署
### 2026-07-13: 异步安装+AI 工具+ Docker 化+K8s 终端
### 2026-07-10~12: Reranker+RAG V2+预测引擎+异常检测 7 算法

---

## 关键信息

| 项 | 值 |
|----|----|
| 项目路径 | `E:\AIOPS\project05` |
| Python venv | 上级目录 `.venv\Scripts\python.exe` |
| 启动后端 | `Start-Process python.exe -ArgumentList 'run.py' -WorkingDirectory '<项目>'`(端口 8000) |
| 启动前端 | `npm run dev --prefix frontend`(端口 3000→8000) |
| 构建前端 | `npm run build --prefix frontend` |
| 登录密码 | admin / **admin123** |
| 数据库 | SQLite(`db/aiops.db`+`db/aiops_real.db`) |
| 部署服务器 | 39.96.51.45(`/data/AIOPS`) |
| 一键重启 | `python tools/restart.py restart` |

**Windows 热重载**:`uvicorn --reload` 旧子进程不退出→端口被占。杀 Python 进程→确认端口释放→重新 `python run.py`。

**License**:`LicenseMiddleware` 拦截非白名单路径,换机器需 `tools/generate_license.py` + `private_key.pem` 重新签发。

---

## 重要架构决策

### AI 自愈+工作流协同(分级自愈)
- 已知→Playbook,未知→AI 单步;`ai_self_heal_analyze` 注入启用的工作流列表
- 自愈引擎成熟度:确定性风险分类器→CI-Type-Aware 分派→诊断先行→失败闭环→部署知识赋能

### fail-safe 审批闸门+双路径并行
- `check_and_remediate` 生成 `PendingAction(source=rule)`,末尾 `auto_ai_analyze_alerts` 生成 `PendingAction(source=ai)`
- 规则蓝/AI 紫并排,人工择优

### 关键原则
- 审批展示层与执行层参数补全逻辑必须一致;缺参数宁可拒绝执行也不能用资产名/IP 兜底
- LLM 调用前端 axios 必须显式传 `timeout≥130000`(后端 120s 留余量)
- 新增 Vue 页面需改 AppLayout+menu_config+role_menus 三处;catch-all 路由必须在 include_router 之后
- 字段名全项目统一:时间 `_at` / 布尔 `is_`/`has_` / JSON 加业务前缀 / FK 统一 `user_id`
- 文件路径禁止硬编码,用 `__file__`/`%~dp0` 动态计算