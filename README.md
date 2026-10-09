# ecommerce_insight：电商经营数据洞察 API

> 一个基于 FastAPI + PostgreSQL 的电商数据后端，覆盖查询聚合、下单入库、AI 数据解读三类能力，共 9 个接口。
> 主要用来验证三件事：**FastAPI 依赖注入与异步模型**、**SQLAlchemy 工程实践**、**“数据在后端算好、模型只负责解读”的 AI 集成架构**。
> 项目附带完整测试（13 个用例全通过）、接口鉴权、以及一份同步/异步对照实验。

---

## 一、这个项目能证明什么

| 能力 | 证据 |
|---|---|
| FastAPI 工程能力 | 9 个接口、依赖注入、API Key 鉴权、Pydantic 校验、`/docs` 可交互 |
| 异步模型理解 | 同步/异步边界分析、`run_in_threadpool`、并行查询实测数据（见附录 A） |
| SQLAlchemy 实践 | 聚合查询、`.all()/.first()/.scalar()` 区分、日期边界处理、JSON 序列化 |
| 测试意识 | 13 个 pytest 用例，覆盖字段完整性、口径正确、鉴权 401/403、AI 失败降级、并行耗时 |
| 数据开发背景 | 6 年数仓经验，口径统一（GMV 只算“已完成”订单），造数贴近真实业务分布 |
| AI 集成判断 | 模型不碰数据库，只拿算好的数字；程度类问题走 SQL 精确排序，不交给模型猜 |


---

## 二、技术栈

| 组件 | 版本 | 用途 |
|---|---|---|
| Python | 3.13 | 运行环境 |
| FastAPI | 0.142 | 接口框架 |
| SQLAlchemy | 2.1 | ORM |
| PostgreSQL | 16 | 数据存储 |
| httpx | 0.28 | 调用大模型 API |
| python-dotenv | 1.2 | 加载 `.env` |
| DeepSeek API | deepseek-chat | AI 解读与问答 |
| pytest | — | 测试（13 用例） |

---

## 三、接口清单

| # | 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|---|
| ① | GET | `/api/categories` | 登录 | 全部品类及订单量 |
| ② | GET | `/api/gmv` | 登录 | 大盘 GMV、订单数、客单价 |
| ③ | GET | `/api/trend` | 登录 | 逐日 GMV 与订单趋势 |
| ④ | GET | `/api/category/topn` | 登录 | GMV TopN 品类排行 |
| ⑤ | GET | `/api/insight` | **管理员** | AI 经营解读（调用 DeepSeek） |
| ⑥ | POST | `/api/orders` | 登录 | 下单写库，返回订单 id |
| ⑦ | POST | `/api/rag/ask` | **管理员** | 周报问答（关键词检索 + LLM 生成） |
| ⑧ | GET | `/api/overview` | 登录 | 汇总＋趋势＋TopN 三查询并行 |
| ⑨ | GET | `/api/me/order` | 登录 | 查看当前用户订单 |

**GMV 口径统一**：只统计「已完成」订单，①②③④⑧ 五个接口的数字互相印证。

**鉴权分级**：普通用户（analyst）可查数据、下单、看自己订单；管理员（admin）额外可调 AI 接口（成本保护）。

---

## 四、架构

```
PostgreSQL（唯一数据源）
  product_type   8 个品类
  orders         10000 条订单
  reports        57 篇周报
  users          api_key + is_admin
        │
        │  SQLAlchemy ORM
        ▼
  FastAPI 接口层 ──── 查询/写库（①~④⑥⑧⑨）
        │
        └──── AI 解读/问答（⑤⑦）────▶ DeepSeek API
                    ▲
                    │
              只把算好的数字传出去，模型不碰数据库
```

**为什么不让模型碰数据库**：模型只看到拼好的数字和文本，看不到表结构。一是避免它编数，二是接口数字永远对得上账。

---

## 五、鉴权

- 使用 **API Key**，通过 `X-API-Key` 请求头传递
- 实现方式：FastAPI `APIKeyHeader` + 依赖注入 `get_current_user`
- 权限分级：`require_admin` 依赖，校验 `is_admin`，无权限返回 403
- `/docs` 右上角 Authorize 可直接填 key，一键测试所有接口

**为什么用 API Key 而不是 JWT**：本项目定位是内部数据服务，调用方是程序不是人，不需要无状态令牌和登录流程。要扩展成 JWT，只需替换 `get_current_user` 的实现。

---

## 六、测试

```bash
pytest test/ -v
# 13 passed
```

覆盖范围：

| 类别 | 用例 |
|---|---|
| 数据正确性 | 品类数量、订单总量、GMV 口径、趋势排序、TopN 排序 |
| 鉴权 | 普通用户访问 admin 接口 → 403；admin 访问 → 200 |
| AI 降级 | DeepSeek 返回 500 时接口仍返回 200 + 降级文案 |
| 并行 | 三个查询各 `sleep(1)`，总耗时 < 2s，证明 `asyncio.gather` 生效 |

---

## 七、启动

前置：本机已安装并启动 PostgreSQL 16。

```bash
# 1. 建库
createdb ecommerce_insight

# 2. 虚拟环境与依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置环境变量（.env.example 只有键名，不含真实密钥）
cp .env.example .env
#   编辑 .env：填入数据库串与 DeepSeek 密钥

# 4. 建表 + 造数（约几秒），终端会打印 admin/analyst 的 API Key
python scripts/gen_data.py

# 5. 启动
uvicorn app.main:app --reload

# 6. 打开交互文档
open http://127.0.0.1:8000/docs
```

---

## 八、已知局限（诚实说明）

| 项 | 现状 | 如果继续做 |
|---|---|---|
| RAG 检索 | 关键词 `LIKE` 匹配，57 篇周报全含 “GMV”，等于没检索 | 上向量检索（embedding + 向量库） |
| 意图路由 | 精确关键词匹配，不兼容拼写错误（"gvm" 漏接） | 用 LLM 做意图分类 |
| 鉴权 | API Key，无登录态 | 加 `password_hash` + JWT，替换 `get_current_user` |
| 项目结构 | 路由全在 `main.py` | 拆成 router + service 分层 |
| 配置读取 | `os.getenv` + dotenv | 换 pydantic-settings 统一管配置 |

**这些不是没做，是知道该怎么做但演示项目不需要。** 每条都能讲清楚“为什么现在不做、要做怎么做”。

---

## 附录 A：同步 def 与异步 async def 的边界

> 这一节是项目里最重要的技术判断，面试被问到的概率最高。

同一个路由函数，`def` 和 `async def` 调度方式完全不同：

- **`def`（同步）**：FastAPI 丢进线程池，不占事件循环。默认 40 个令牌，并发 ≤40 时同步与异步几乎没差别。
- **`async def`（异步）**：跑在事件循环里，靠 `await` 让出。**不能留同步阻塞代码**，否则整个事件循环被卡死。
- 本项目用同步 SQLAlchemy，所以异步接口里的查询要显式丢回线程池：`await run_in_threadpool(...)`。

`/api/overview` 就是这么做的：三个互不相干的查询并行跑。

```python
async def get_overview(start=None, end=None, n=5):
    summary, trend, topn = await asyncio.gather(
        run_in_threadpool(q_summary, start, end),
        run_in_threadpool(q_trend, start, end),
        run_in_threadpool(q_topn, start, end, n),
    )
    return {**summary, "trend": trend, "top_categories": topn}
```

**实测数据**（三个查询各换成 `sleep(1)`）：
- 串行应为 3 秒，`gather` 并行实测 **1.00 秒**

**但要知道并行不是免费的**：

| 并发 | `/api/gmv`（同步 def） | `/api/overview`（异步并行） | 慢多少 |
|---|---|---|---|
| 10 | 0.07s | 0.50s | 7.1x |
| 30 | 0.19s | 1.47s | 7.6x |
| 60 | 0.37s | 3.01s | 8.2x |

**结论一句话**：单请求延迟降了，代价是并发吞吐掉到同步接口的几分之一。
- 同步请求占 1 个线程池令牌，overview 占 3 个
- overview 一个请求干三份活，吞吐上限天生低

**判据只有一条**：时间是不是花在等 I/O 上。纯 CPU 计算改成异步不会变快。

**安全边界**：本项目 8 个路由里只有 `/api/overview` 是 `async def`。谁把 `/api/insight`、`/api/rag/ask` 改成 `async def` 而不把 `httpx.post` 换成 `AsyncClient`，整站会立刻掉到 1 req/s。

---

## 附录 B：开发中踩过的坑

> 完整版见仓库 wiki 或 commit history。这里只保留能体现判断力的几条。

### B.1 日期与边界

| 现象 | 原因 | 解决 |
|---|---|---|
| 单日查询 500，`ZeroDivisionError` | `strptime("2026-08-18")` 解析成当天 00:00:00，`<=` 把整天排除，结果 0 条，除以 0 | `+ timedelta(days=1, seconds=-1)` 推到 23:59:59 |
| 除法在特定输入下崩 | 分母可能为 0 | `... if done_cnt else 0`，写除法先问分母会不会为零 |

### B.2 ORM 与查询

| 现象 | 原因 | 解决 |
|---|---|---|
| `list indices must be integers` | 查询结果是元组列表，却当字典用 `x[k]`；列表/字典变量混用 | 区分类型；字典查可能不存在的键一律 `.get(k, 0)` |
| 某天 GMV 取不到键 | 那天全是未完成订单，过滤后不出现在结果里 | `.get(k, 0)` 兜底 |
| 只要一条却拿到列表 | `.all()` 永远返回列表；`.first()` 给元组；`.scalar()` 给单值 | 多条 `.all()`、首条 `.first()`、单值 `.scalar()` |
| 手动循环数数截断 TopN | 用 `for` + 计数器模拟 LIMIT | 交给 SQL：`.limit(max(n, 1))` |

### B.3 工程与仓库卫生

| 现象 | 原因 | 解决 |
|---|---|---|
| 启动就炸 | 模块顶层开 session 且从不关闭 | 用完立刻 `close()`；静态映射表可启动时查一次，连接要关 |
| `git add .` 混入 8 个无关文件 | `__pycache__`、`.idea/`、`.DS_Store` | 补 `.gitignore`，`git rm -r --cached` 除名 |
| `session.add()` 后库里没数据 | 没 `commit` | `add` → `commit` → 需要主键时 `refresh` |
| `os.getenv` 读不到 key | `.env` 不会自动生效 | `python-dotenv`，且 `load_dotenv()` 必须排在第一次 `getenv` 之前 |

---

## 附录 C：数据设计

| 表 | 内容                                                     |
|---|----------------------------------------------------------|
| `product_type` | 8 个品类：女装、数码、美妆、食品、家居、运动、母婴、图书 |
| `orders` | 10000 条订单，覆盖约13个月                                |
| `reports` | 57 篇周报，按 ISO 周聚合生成                             |

造数刻意贴近真实业务：

- 品类分布走二八法则，权重 `[0.30, 0.20, 0.18, 0.10, 0.08, 0.06, 0.05, 0.03]`
- 金额服从对数正态分布（μ=4.2，σ=0.6），均值约 80 元，少量高价单拉出长尾
- 周末订单密度为工作日的 1.3 倍，造完 SQL 验证周末占比约 33.6%
- 订单状态：已完成 88% / 待发货 7% / 已取消 5%

---

## 附录 D：项目结构

```
ecommerce_insight/
├── app/
│   ├── main.py          # 全部路由 + 鉴权 + AI 调用
│   └── models.py        # ORM 模型 + Pydantic 请求体模型
├── scripts/
│   ├── gen_data.py      # 建表 + 造订单 + 生成周报 + 创建用户
│   └── block_demo.py    # 同步/异步阻塞对照实验
├── test/
│   ├── test_read.py     # 查询类接口 + insight + overview（含并发）
│   └── test_write.py    # 下单接口，带回滚清理
├── conftest.py          # pytest fixture：client + 鉴权 mock
├── requirements.txt
├── .env                 # 本地配置，不入库
└── .gitignore
```