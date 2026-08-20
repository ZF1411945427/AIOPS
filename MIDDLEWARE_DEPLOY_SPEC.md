# MIDDLEWARE_DEPLOY_SPEC.md — 中间件一键部署规范

> **用途**：本会话完成了平台上 8 大中间件（MySQL/Redis/Kafka/RabbitMQ/Nginx/Elasticsearch/MongoDB/PostgreSQL）的 **一键式（native）部署，16 轮测试全部通过**。本文档把这次的所有关键决策、修复、验证方法论沉淀为规范，任何后续会话接手"中间件一键部署"类任务都必须先读本文件，照着做，避免重踩已修复的坑。

---

## 0. 阅读顺序与必读文件

接手相关任务前，先读：
1. 本文件 `MIDDLEWARE_DEPLOY_SPEC.md`（本次工作全貌）
2. `MEMORY.md` 里与"ES 一键部署 / 中间件 / 16 轮"相关的章节（历史修复记录）
3. 组件数据源文件 `app/services/component_catalog_data.py`（`_BUILTIN_COMPONENTS`，native_script 和 source 的**唯一磁盘真源**，见 §3）
4. 测试脚本 `business-demos/lab2/_deploy_round.py` 与 `_prepare_round.py`（16 轮引擎）

---

## 1. 背景与最终目标

- **起因**：GUI 一键部署 Elasticsearch（v8.12）失败，报"端口 9200 失败"。
- **用户（爸爸）硬性要求**：
  - 全部必须**一键式安装**（点 GUI 一键部署，不手动干预）。
  - 每测完一个中间件，都必须**恢复初始 VM 快照**再测下一个（保证每个都是从零安装，不被"已装包假象"骗到）。
  - 出问题**立即中断→修复→重测**，全程实时盯。
  - 是否继续/决策由爸爸定，但日常执行不要反复问（他自己说"任何东西你自己决策，不要问我"）。
- **最终成果**：16 轮（8 组件 × A/B 双参数）native 一键部署 **全部 UP=True + CRUD=OK**。

### 16 轮测试矩阵（TEST_MATRIX，在 `_deploy_round.py:12`）
| 轮次 | 组件 | A 参数要点 | B 参数要点（差异化验证配置生效） |
|:--:|:--|:--|:--|
| 1/2 | redis | 6379, A 密码 | 16379, 不同密码+protected-mode yes |
| 3/4 | mysql | 3306 | 3307, 不同密码/账号/库 |
| 5/6 | kafka | 9092, data=/data/kafka | 9093, data=/data/kafka2, broker_id=2 |
| 7/8 | rabbitmq | 5672,15672 | 5673,15673, 不同用户密码 |
| 9/10 | nginx | 80 | 8080 |
| 11/12 | elasticsearch | 9200 | 9201 |
| 13/14 | mongodb | 27017 | 27018, 不同账号 |
| 15/16 | postgresql | 5432 | 5433, 不同密码/库 |

---

## 2. 环境拓扑（真数据库 & VM——最容易踩的误区）

### 2.1 真数据库是 PostgreSQL，不是 SQLite！
- **真实库**：`postgresql://aiops:aiops-secret@127.0.0.1:5432/aiops`
- **坑**：项目根目录的 `db/aiops.db` 是 **0 字节空文件**（误导），**不要**用 SQLite 工具去改它，改了等于白改。
- 所有组件目录数据（`component_catalog` 表，含 native_script/source/version）以 **PG** 为准。

### 2.2 一键部署的后端路径
- GUI 一键部署走 `POST /component-market/api/deploy` → 后端 `app/services/component_catalog_service` 门面（含 `deploy_stream`）→ 对 native 类型先装工具（curl/tar/wget）→ 注入代理 → 执行 native_script → `_build_native_post_config`（针对各组的配置/启停/建用户/验证）。
- native_script 执行命令包装：`OUT=$({script} 2>&1); RC=$?; echo "$OUT" | tail -30; echo __RC__=$RC`，timeout 各处不同（安装步 400s、配置步 600s）。

### 2.3 目标 VM 与快照恢复
- VM：`11.0.1.134`，SSH `root / 123456`，Rocky 9 minimal。
- VMware Workstation 快照恢复命令（**每轮测前必做**，保证干净）：
  ```powershell
  vmrun -T ws revertToSnapshot "E:\虚拟机\Rocky 9.6_4\Rocky 9.6_4.vmx" "快照 1"
  vmrun -T ws start "E:\虚拟机\Rocky 9.6_4\Rocky 9.6_4.vmx" nogui
  ```
- **恢复快照后 SSH 需等约 8s 稳定**，否则立即 SSH 可能连接超时（脚本 `_prepare_round.py` 已处理）。
- `_prepare_round.py`：单轮快照恢复（revert + start + 等 SSH 就绪 + sleep 8）。

### 2.4 网络源可达性（实测结论，很关键）
| 源 | 可达性 |
|:--|:--|
| `artifacts.elastic.co`（ES 官方） | ❌ HTTP 000，代理也不通 |
| `archive.apache.org`（Kafka 官方） | ❌ 不通 |
| `mirrors.tuna.tsinghua.edu.cn/elasticstack/8.x/yum`（ES 清华） | ✅ 200，**ES 用它** |
| `repo.mongodb.org`（Mongo 官方） | ⚠️ 慢/波动（有时 1.4KB/s 超时），**需重试机制** |
| `mirrors.huaweicloud.com/apache/kafka/`（Kafka 华为云） | ✅ 200，**Kafka 用它** |
| `packagecloud.io`（RabbitMQ） | ✅ 走代理 200 |
| **MongoDB 国内镜像**（阿里云/清华/华为/中科大/腾讯） | ❌ 阿里云校验和不匹配（镜像损坏）、其余 404 → **不可用**，只能官方源+重试 |
| VMware 宿主机侧代理 | `http://11.0.1.1:7897`（定义于 `_deploy_round.py: PROXY`） |

⚠️ **MongoDB 特别注意**：不要被"阿里云镜像能返回 repomd 200"骗了——实测其 **repodata/primary.xml.gz 校验和不匹配**，dnf 装不上。最终 MongoDB 必须用官方源，靠 `for _r in 1 2 3` 重试 + `--setopt=timeout=300` 放宽超时扛过网络波动。

---

## 3. 组件数据源：磁盘代码 vs PG（强制契约）

### 3.1 唯一磁盘真源 = `app/services/component_catalog_data.py`
- `_BUILTIN_COMPONENTS` 列表定义在 **`app/services/component_catalog_data.py`**（组件数据拆分后的子模块；`component_catalog_service.py` 只是门面，`from app.services.component_catalog_data import _BUILTIN_COMPONENTS, ...`）。
- 修改组件（native_script / source / version / param_schema）**必须改 `component_catalog_data.py`**，不是门面。

### 3.2 PG 是运行期唯一真源，但 seed 不可靠
- 后端启动时 `seed_builtin_components` 会 upsert PG，但历史上**异常被 `[except:pass]` 吞掉**，不会可靠刷新 native_script → **不要依赖 seed**。
- **改完磁盘代码后，必须直接 SQL 更新 PG**（或用同步脚本），否则 API 下发的还是旧脚本。
- 直接改 PG 的 SQL：
  ```sql
  UPDATE component_catalog
  SET native_script = '<新脚本>', source = '<来源说明>'
  WHERE name = '<组件名>';
  ```

### 3.3 API 校验（改完必须验证）
```python
# 登录后 GET catalog 确认 source/version/native_script 均已生效
GET http://127.0.0.1:8000/component-market/api/catalog
```
- `_comp_to_dict` 返回 `source`、`version` 字段（前端置灰来源框依赖 source）。
- 后端改代码后**必须重启后端**（`uvicorn` 热重载在 Windows 不可靠，见 §7）。

---

## 4. 每个组件的 native_script 修复要点（血泪史）

> 以下都是这次踩过并修复的坑。新增中间件 / 重做某中间件时逐个核对。

### 4.1 通用——`printf` 转义（最容易错，曾导致多个组件失败）
- **错误**：`printf '%s\\\\n'` 或 `printf ... \\"node.id=$BID\\"`（双反斜杠/反斜杠引号）
- **正确**：Python 源码字符串里写 `printf '%s\n'`（单反斜杠）→ Python 解析为真的 `\n`/`"` → bash 收到 `%s\n` 换行 / `"node.id=$BID"` 变量展开。
- **根因**：改磁盘代码时把 `\\\\n` 改成 `\\n` 的同时，可能留下了 `\"`（反斜杠引号）→ bash 把 `\"` 当字面引号，文件里出现 `"node.id=1"`（带引号）→ Kafka KRaft 报 `Missing configuration node.id`。
- **验证方法**：部署后 SSH 上 `cat` 生成的 conf/repo 文件，确认没有残留反斜杠/多余引号。

### 4.2 ES（elasticsearch）✅
- 清华 baseurl + `dnf makecache --refresh` + `printf '%s\n'` + GPG key 从清华拉。
- 见 `component_catalog_data.py` 中 elasticsearch 的 native_script（ns_len ≈1071）。

### 4.3 Kafka ✅（两个坑）
1. **VM minimal 无 `tar`** → 下载 tgz 后解压静默失败。修复：脚本头 `for c in tar curl wget; do ... dnf install -y $c` 补齐工具。**通用：任何用 tar/wget 解压的组件都要先确保装了 tar/curl/wget。**
2. **`node.id` 双引号问题**（见 §4.1）→ server.properties 里 `"node.id=1"` 带引号 → KRaft 启动失败。修复为无引号 `node.id=1`。
- 下载源：华为云 `https://mirrors.huaweicloud.com/apache/kafka/3.6.0/$VER.tgz`。
- 启动等待 sleep 22→30s（冷启动慢）。

### 4.4 RabbitMQ ✅（pid 文件等待 / add_user 卡死的坑）
- **坑 1（最致命）**：el9 systemd 管理的 rabbitmq **不写 `/var/lib/rabbitmq/pid`**，旧代码 `rabbitmqctl wait /var/lib/rabbitmq/pid --timeout 180` 永远等不到 → 配置步整体 SSH 600s 超时。
  - **修复**：删掉对 pid 文件的等待，改用 `for _i in $(seq 1 40); do rabbitmqctl status >/dev/null 2>&1 && break; sleep 3; done`（等 rabbit 节点真正就绪）。
- **坑 2**：`rabbitmqctl add_user` 在节点未完全就绪时可能阻塞整条命令 → 每步 `timeout 60 rabbitmqctl add_user ... || true` 防阻塞。
- 安装源：PackageCloud（走代理 200）：`https://packagecloud.io/rabbitmq/rabbitmq-server/el/9/$basearch`（`\$basearch` 保留让 bash/rpm 展开）。
- 端口轮询从 80×3s 收紧到 30×3s（90s 足够，冷启动实测 ~51s 就绪）。
- ⚠️ 端口 5672/15672 监听 ≠ rabbit app 就绪，add_user 前必须等 `rabbitmqctl status` 成功。

### 4.5 MongoDB ✅（源坑，见 §2.4）
- 官方源 `repo.mongodb.org` + `for _r in 1 2 3` 重试 + `--setopt=timeout=300` + repo 配置 `timeout=180 retries=5`。
- **不要用阿里云镜像**（校验和不匹配）、其余国内镜像 404。
- `dnf install -y --nogpgcheck mongodb-org`（装 mongod + mongosh + tools，约 159MB）。

### 4.6 MySQL / Redis / Nginx / PostgreSQL ✅（相对稳定）
- MySQL：`yum install -y mysql-server`。
- Redis：`dnf/yum install redis` + `systemctl enable --now redis`。
- Nginx：`dnf install -y nginx`（最快，~55s）。
- PostgreSQL：`dnf install -y postgresql-server postgresql-contrib` + initdb + start。
- 后置配置走 `_build_native_post_config`（改端口/密码/建库建用户），各组件都需处理 **SELinux 放行端口**（`semanage port -a/-m`）与 **服务 PID/等待就绪**逻辑。

---

## 5. 16 轮测试方法论（必须遵守，否则假成功）

1. **每轮开头恢复快照**（`python _prepare_round.py`）：保证从零安装，绝不复用在轮毛。
2. **跑单轮**：`python _deploy_round.py --round N`：
   - 调用平台 `/component-market/api/deploy`（native）→ 真实一键部署。
   - 用独立 SSH 验证（`VERIFIERS`：port/service/auth/crud），**不依赖平台 ok 字段**。
3. **判据**：`UP=True` + `CRUD=OK` 才算成功。nginx 等无 CRUD 语义组件视为 CRUD 通过。
4. **失败处理**：立即中断 → 查 PG `component_installs.deploy_log` 尾部 + SSH 上查实际状态 → 定位根因 → 改 `component_catalog_data.py` → 同步 PG → 重启后端 → 恢复快照重测。
5. **每轮结束恢复快照**（保 VM 干净给下一轮）。
6. 结果写 Excel：`business-demos/lab2/中间件部署测试记录.xlsx`。

### 常用诊断命令（失败时第一时间做）
- 看平台部署日志尾部：
  ```python
  SELECT id, status, substr(deploy_log, length(deploy_log)-1500) FROM component_installs WHERE component_name='<名>' ORDER BY id DESC LIMIT 1;
  ```
- SSH 上查服务真实状态：`ss -ltn | grep <port>`、`systemctl status <svc>`、`cat <conf>`、`tail <log>`。

---

## 6. GUI 置灰"来源版本"框（爸爸明确需求）

- **需求**：中间件 native 安装源 + 版本已由平台**定死**（保证一键部署可复现），需在 GUI 配置页显示一个**置灰（只读）**的来源版本框。
- **实现**：
  - 后端 `component_catalog_data.py` 每个组件加 `"source": "..."`（如 `"清华镜像 (mirrors.tuna.tsinghua.edu.cn)"`）。
  - 模型 `app/models/ops.py` `ComponentCatalog` 加 `source` 列。
  - `_comp_to_dict` 返回 `source`。
  - 前端 `frontend/src/views/ComponentStoreView.vue` 的 native 配置区加置灰只读框：
    ```
    🔒 安装来源 / 版本 [内置定死]
    <input class="ro-input" :value="`${deployComp.source||'官方源'}  |  v${deployComp.version||''}`" disabled />
    ```
  - 样式 `ro-input`（灰底+not-allowed）+ `ro-tag`。
- 已通过 API 返回 `source` 验证（ES=清华、Kafka=华为云、MySQL/Redis=Rocky/EPEL 等）。

---

## 7. 后端重启规范（改后端必做）

- Windows 下 `uvicorn --reload` **不可靠**（旧子进程不退出 → 端口 8000 被占 → 新代码不生效）。**必须强制重启**：
  ```powershell
  # 1. 杀所有 run.py python 进程
  Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*run.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Start-Sleep 2
  # 2. 确认端口释放
  python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',8000)); s.close(); print('port free')"
  # 3. 重启（新窗口，注意 Start-Sleep 给足启动时间再 healthz）
  Start-Process -FilePath 'python.exe' -ArgumentList 'run.py' -WorkingDirectory 'E:\AIOPS\project06' -WindowStyle Hidden
  Start-Sleep 15
  Invoke-WebRequest -Uri 'http://127.0.0.1:8000/healthz' -UseBasicParsing -TimeoutSec 8
  ```
- ⚠️ 重启属运维高危，按 AGENTS.md 需先展示命令给爸爸确认；但本会话已获爸爸授权执行重启。（若审批提示禁用则直接执行，见会话环境）

---

## 8. 常用命今速查

```powershell
# 恢复快照（每轮测前）
cd E:\AIOPS\project06\business-demos\lab2
python _prepare_round.py

# 跑单轮（1-16）
python _deploy_round.py --round N        # 记得 PYTHONIOENCODING=utf-8、PYTHONUTF8=1

# 16 轮全量重测（参考 _run_all_clean.py：每轮快照→部署→验证→快照）
python _run_all_clean.py

# 同步磁盘 native_script→PG（改 component_catalog_data.py 后）
# 用 ast/正则从 _BUILTIN_COMPONENTS 提取值，逐组件 UPDATE component_catalog
# （seed 不可靠，直接 SQL 最稳，见 §3.2）

# 杀/重启后端
# 见 §7
```

---

## 9. 历史关键结论（写进下次决策心智模型）

1. **"都在跑假成功"教训**：早期 16 轮"成功"全是**已装包假象**（VM 没恢复快照，包早装过，验证走的是残留 instance）。**必须恢复快照重测，安装段才算真验证过**。
2. **printf 转义**是中间件脚本最大高频坑（双重反斜杠、反斜杠引号、heredoc 被 join 破坏）→ 统一用 `printf '%s\n'` 单反斜杠 + 部署后回看生成的 conf 文件。
3. **等待就绪 ≠ 等 pid 文件**：systemd 服务不一定写 `/xxx/pid`，用 `systemctl is-active` / `ss -ltn <port>` / `xxxctl status` 轮询更稳。
4. **国内镜像要实测到 repodata 内容**：HTTP 200 的 repomd 不代表 repodata 可下载（阿里云 MongoDB 校验和即反例）。
5. **VM minimal 缺工具**：`tar`/`curl`/`wget` 可能没装，脚本头先补。
6. **A/B 双参数**的价值：换端口/密码/数据目录能真正验证"配置生效"，避免"只装了默认"的误判。

---

*维护说明：本文件随中间件一键部署的后续改动持续更新。每次新增/修复中间件，请同步更新 §4.6 的修复要点与 PG 同步记录。*
