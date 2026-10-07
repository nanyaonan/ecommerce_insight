# ecommerce_insight：电商经营数据洞察 API

> 一个用 FastAPI 搭的后端服务项目，从建库、写接口到接大模型，五天做完。
> 主要目的是练手 + 作为一份能现场演示的材料，所以代码以「跑得通、讲得清」为目标，不是生产级工程。
> 下面是它实际长什么样、以及过程中踩过的坑。

---

## 一、它做了什么

提供一组围绕电商订单数据的 HTTP 接口：查品类、查大盘、查趋势、查排行、下单，另有两路接大模型的实验性功能。

| 层 | 内容 | 状态 |
|---|---|---|
| 数据查询 | 接口 ①②③④⑥，SQL 聚合 + 写库 | 稳定可用 |
| AI 解读 | 接口 ⑤，把数字交给大模型说成人话 | 可用，效果尚可 |
| AI 问答 | 接口 ⑦，基于周报库做问答 | 实验性质，效果一般（见第七节） |

---

## 二、技术栈

| 组件 | 版本 | 用途 |
|---|---|---|
| Python | 3.13 | 运行环境 |
| FastAPI | 0.142 | 接口框架 |
| SQLAlchemy | 2.1 | ORM |
| PostgreSQL | 16 | 数据存储 |
| httpx | 0.28 | 调大模型 API |
| python-dotenv | 1.2 | 加载 `.env` 配置 |
| DeepSeek API | deepseek-chat | AI 解读与问答（实验） |

---

## 三、数据与架构

```
PostgreSQL（唯一数据源）
  product_type  8 个品类
  orders        10000 条订单
  reports       57 篇周报
        │
        │  SQLAlchemy ORM
        ▼
  FastAPI 接口层 ──── 统计/写库（①②③④⑥）
        │
        └──── 模型解读（⑤⑦）────▶ DeepSeek API
                    ▲
                    │
              只把算好的数字传出去，模型不碰数据库
```

为什么不让模型碰数据库：模型只能看到拼好的数字和文本，看不到表结构。一是避免它自己编数，二是接口的数字永远对得上账。

---

## 四、FastAPI 应用要点（本项目的主体）

这一节是我在这个项目里主要练的东西。

### 4.1 路由与参数

```python
@app.get("/api/topn")
def get_top(start: str | None = None, end: str | None = None, n: int = 8):
```

- 装饰器 `@app.get("路径")` 把普通函数变成接口，**路径必须带前导斜杠**（写成 `"api/topn"` 是 404）。
- 查询参数直接写在函数签名里：带默认值 = 可选参数；不写默认值 = 必填（漏传会 422）。
- `start: str | None = None` 这种写法，FastAPI 会自动在 `/docs` 里标注为可选项。
- **装饰器必须紧贴函数定义**：`@app.get("...")` 和 `def` 之间隔了空行，装饰器就会叠到下一个函数头上——不报错，但路由悄悄挂错。本项目 `/api/overview` 曾因此挂到 `list_categories` 上，请求它返回的是品类列表。

### 4.2 请求体用 Pydantic 模型接

```python
from pydantic import BaseModel

class AskIn(BaseModel):
    question: str
    top_k: int = 3
```
pydantic 会帮助校验字段类型

函数签名里声明 `body: AskIn`，FastAPI 就做三件事：解析 JSON、按类型校验、在 `/docs` 生成示例请求体。**类型不对自动返回 422 并指出哪个字段错了**，不用手写 if。

这里有个和 ORM 容易混的点：Pydantic 字段用**类型标注（冒号）**，SQLAlchemy 字段用**赋值（等号）**，两套写法恰好相反。

### 4.3 数据库会话：一次请求一个 session

```python
@app.get("/api/gmv")
def sum_gmv(...):
    session = Session()
    try:
        ...
    finally:
        session.close()
```

`try/finally` 保证无论是否报错都关闭连接。**更地道的做法是用 FastAPI 的 `Depends` 做依赖注入**，目前还是手写的版本——这是下一步想改的地方。

### 4.4 返回值要能进 JSON

数据库里取出来的东西不都能直接返回：

- `Decimal`（金额聚合结果）→ `float(x)`
- `date` 对象 → `strftime("%Y-%m-%d")`
- ORM 对象 → 自己拼成 dict

不转会 500，且报错信息很长。现在代码里凡是金额都带 `float(x or 0)`，`or 0` 是防 `None` 兜底。

### 4.5 其他细节

- 创建类接口用 `status_code=201`，比默认 200 更符合 HTTP 语义，201可以通过状态码单独统计创建量，以及增强可读性：一眼看出是创建新的。
- `/docs` 是自带的交互测试台，改完代码直接在页面上点，不用 curl http://127.0.0.1:8000/docs 。
- **同一个路由函数不要重名**——Python 后定义的会覆盖先定义的。

### 4.6 同步 def 与异步 async def：只在 I/O 等待处用异步

同一个路由函数，写成 `def` 还是 `async def`，调度方式完全不同：

- **`def`（同步）**：FastAPI 把它丢进**线程池**执行，不占事件循环，函数里阻塞也不影响其他请求。anyio 默认线程池 40 个令牌，并发 ≤40 时同步与异步耗时几乎没差别，要到更高并发才拉开差距。
- **`async def`（异步）**：跑在**事件循环**里，靠 `await` 让出控制权。所以异步函数里**不能留同步阻塞代码**（同步 SQLAlchemy 查询就是），否则整个事件循环被卡死，比同步写法还慢。
- 本项目用的是同步 SQLAlchemy，所以异步接口里的查询要显式丢回线程池：`await run_in_threadpool(查询函数)`。

`/api/overview` 就是这么做的——三个互不相干的查询并行跑：

```python
async def get_overview(start=None, end=None, n=5):
    summary, trend, topn = await asyncio.gather(
        run_in_threadpool(q_summary, start, end),
        run_in_threadpool(q_trend, start, end),
        run_in_threadpool(q_topn, start, end, n),
    )
    return {**summary, "trend": trend, "top_categories": topn}
```

实测：把三个查询各换成 `sleep(1)`，串行应为 3 秒，`gather` 并行实测 **1.00 秒**（`pytest -k 并发 --durations=1`）。

#### 但并发下是反的：这是延迟换吞吐，不是性能提升

起服务后用 60 并发压测 `/api/overview` 与同步的 `/api/gmv`：

| 并发 | `/api/gmv`（同步 `def`） | `/api/overview`（异步 + 线程池） |
|---|---|---|
| 10 | 0.63s | 2.24s |
| 30 | 0.72s | 3.36s |
| 60 | 0.59s | **4.98s** |

异步接口反而慢 3.5～8 倍。根因：同步请求一次占 **1 个**线程池令牌，overview 一次并发三个查询占 **3 个**，anyio 默认 40 个令牌——**约 14 个并发请求就把线程池抽干**，后面的全排队。

所以准确的说法是：**单请求延迟降 3 倍，多请求吞吐掉到约 1/8**。要真上量得换 asyncpg 走全链路 `await`，数据库连接不再占线程；短期只能调大 `anyio.to_thread.current_default_thread_limiter().total_tokens`，但那只是把瓶颈往后推。

#### 附：什么是"阻塞"（20 并发，每个任务 1 秒）

| 写法 | 总耗时 | 吞吐 |
|---|---|---|
| `async def` + `time.sleep(1)` | 20.11s | 1.0 req/s |
| `async def` + 同步 `httpx.get` 调外部 API | 20.44s | 1.0 req/s |
| `async def` + `await asyncio.sleep(1)` | 1.03s | 19.5 req/s |
| `async def` + `await run_in_threadpool(...)` | 1.06s | 18.9 req/s |
| `def`（FastAPI 自动丢线程池） | 1.04s | 19.3 req/s |

最直观的证据是**传染**：1 个慢请求 + 5 个 `/health`（纯 CPU，正常 0.01 秒）同时打，`async def` 里同步阻塞时 `/health` 被拖慢 **400 倍**；改成 `await` 或 `run_in_threadpool` 后只有 3～5 倍，属于噪声。绝对值取决于探针发出的时机，判定只看倍数（`python scripts/block_demo.py` 可复现）。一个毫不相干的接口被拖慢两个数量级——这就是事件循环被独占。

推论：本项目 8 个路由里只有 `/api/overview` 是 `async def`，其余全是 `def`，安全。**谁把 `/api/insight`、`/api/rag/ask` 改成 `async def` 而不把 `httpx.post` 换成 `AsyncClient`，整站会立刻掉到 1 req/s。**

值不值得上异步，判据只有一条：**时间是不是花在等 I/O 上**（等数据库、等外部 API、等文件读写）。纯 CPU 计算改成异步不会变快，因为 GIL 之下它根本没有"让出"的机会。

---

## 五、接口清单

| # | 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|---|
| ① | GET | `/api/categories` | — | 全部品类及各品类订单量 |
| ② | GET | `/api/gmv` | `start`、`end`（可选） | 大盘 GMV、订单数、客单价 |
| ③ | GET | `/api/trend` | `start`、`end`（可选） | 逐日 GMV 与订单趋势 |
| ④ | GET | `/api/category/topn` | `start`、`end`、`n`（默认 8） | GMV TopN 品类排行榜 |
| ⑤ | GET | `/api/insight` | `start`、`end`（可选） | AI 经营解读（实验） |
| ⑥ | POST | `/api/orders` | 请求体 `prd_id`、`amount`、`status` | 下单写库，返回新订单 id |
| ⑦ | POST | `/api/rag/ask` | 请求体 `question`、`top_k` | 周报问答（实验，效果一般） |
| ⑧ | GET | `/api/overview` | `start`、`end`、`n`（默认 5） | 汇总＋趋势＋TopN 三查询并行，异步接口 |

全项目 GMV 口径统一：**只统计「已完成」订单**，五个接口的数字互相印证。

---

## 六、数据设计

| 表 | 内容 |
|---|---|
| `product_type` | 8 个品类：女装、数码、美妆、食品、家居、运动、母婴、图书 |
| `orders` | 10000 条订单，覆盖约九个月 |
| `reports` | 57 篇周报，按 ISO 周聚合生成 |

造数时刻意贴近真实业务，避免「一均匀就假」：

- 品类分布走二八法则，权重 `[0.30, 0.20, 0.18, 0.10, 0.08, 0.06, 0.05, 0.03]`
- 金额服从对数正态分布（μ=4.2，σ=0.6），均值约 80 元，少量高价单拉出长尾
- 周末订单密度为工作日的 1.3 倍（拒绝采样），造完用 SQL 验证过周末占比约 33.6%
- 订单状态：已完成 88% / 待发货 7% / 已取消 5%

验证口径的 SQL：

```sql
SELECT count(*) FILTER (WHERE extract(dow FROM order_time) IN (0,6)) AS weekend_cnt,
       count(*) AS total_cnt
FROM orders;
```

---

## 七、开发中踩过的坑（按类别）

这部分是这个项目真正的收获，都是真跑真炸出来的。

### 7.1 日期与边界

| 现象 | 原因 | 解决 |
|---|---|---|
| 单日查询返回 500，`ZeroDivisionError` | `strptime("2026-08-18")` 解析成当天 **00:00:00**，`<=` 把这一整天全排除，结果为 0 条，除以 0 | `+ timedelta(days=1, seconds=-1)` 推到 23:59:59 |
| 除法在特定输入下崩 | 分母可能为 0 | `... if done_cnt else 0` 三元兜底，写除法先问一句分母会不会为零 |

### 7.2 ORM 与查询

| 现象 | 原因                                                                                                                             | 解决 |
|---|----------------------------------------------------------------------------------------------------------------------------------|---|
| `TypeError: list indices must be integers, not datetime.date` | 查询结果是**元组列表**，却当字典用 `x[k]` 索引；且有两个长得像的变量（`done_cnt` 列表 / `done_dict` 字典）混用                   | 区分「列表」和「字典」；字典查可能不存在的键一律用 `.get(k, 0)` |
| 某天 GMV 取不到键 | 那天全是未完成订单，按状态过滤后该日不出现在结果里                                                                               | `.get(k, 0)` 兜底 |
| 只要一条却拿到列表 | `.all()` 永远返回列表（一条也是长度 1）；`.first()` 给元组；`.scalar()` 给单值（第一行第一列）；`.one()`用于校验是否恰好返回一条 | 多条用 `.all()`、首条用 `.first()`、单值用 `.scalar()` |
| 手动循环数数截断 TopN | 用 `for` + 计数器模拟 LIMIT                                                                                                      | 交给 SQL：`.limit(max(n, 1))`，数据在库里截好再取出来 |
| 求和多写了 `group_by` | 按天分组的写法串台                                                                                                               | 要总和就纯聚合，要分组才 `group_by` |

### 7.3 Python 语法

| 现象 | 原因                                                                                        | 解决 |
|---|---------------------------------------------------------------------------------------------|---|
| IDE 报 `Generator has no attribute items` | `({k: v} for x in ...)` for在花括号外  = 生成器；`{k: v for x in ...}` 才是字典推导式       | 括号位置决定类型，容器括号要包住整个表达式 |
| 硬编码列表变成嵌套列表 | `keywords = [...split(',')]` 多套一层方括号，元素成了 list                                  | 直接 `= ...split(',')` |
| 关键词永远检索不到 | 模型返回 `"GMV, 最高"`，`split(',')` 切出 `" 最高"` 带前导空格                              | `.strip()`，字符串里的空格是隐形杀手 |
| 请求体字段报错 | DeepSeek 的字段名是 `messages`（复数），写成 `message` 返回 400，再取 `choices` 就 KeyError | 对字段名保持警惕，先看原始响应再猜 |

### 7.4 工程与仓库卫生

| 现象 | 原因 | 解决 |
|---|---|---|
| 启动就炸，整个应用起不来 | 模块顶层开了个 session 且从不关闭，数据库没起时 import 阶段就失败 | 用完立刻 `close()`；静态映射表可以启动时查一次常驻内存，但连接要关 |
| `git add .` 之后 commit 里有 8 个文件 | 把 `__pycache__`、`.idea/`、`.DS_Store` 也扫进去了 | 补全 `.gitignore`，再用 `git rm -r --cached` 除名（**不加 `--cached` 会真删文件**） |
| 有 import 从没用过 | IDE 自动补全热心加的 | 悬停看灰色提示，孤儿 import 立即删 |
| 函数里有一行 `if i > n: return` 永远不触发 | SQL 已经 `limit` 截断了，Python 层再截一次是死代码 | 同一件事只做一次 |
| `session.add()` 之后库里没数据 | 没 `commit`，只在内存排队 | `add` → `commit` → 需要主键时再 `refresh(obj)` |

### 7.5 环境与配置

| 现象 | 原因 | 解决 |
|---|---|---|
| `os.getenv` 读不到 key | **`.env` 只是文本文件，不会自动生效** | 用 `python-dotenv`，且 `load_dotenv()` 必须排在第一次 `getenv` 之前 |
| 终端 export 了还是读不到 | 在 zsh 里又敲了 `bash`，套了一层 shell，变量没传到；且 `--reload` 只重载代码不重读环境变量 | 退出嵌套 shell，重启 uvicorn；根本解法还是 dotenv |
| 启动报 500，看不出所以然 | IDE 误 import 了未安装的包（opentelemetry） | 看 traceback 最后一行定位；没写过的 import 先怀疑 IDE |

---

## 八、关于 AI 的两路功能（实验性质，不作为重点）

顺带做的两个接口，验证「应用层查数 + 模型解读」这条架构能跑通：

- **接口⑤ `/api/insight`**：把算好的数字拼进提示词，让模型用三句话讲大盘、亮点、建议。数字引用准确，实用。
- **接口⑦ `/api/rag/ask`**：周报问答。检索用关键词 `LIKE` 匹配（不是向量检索），加上「只依据材料回答、不得编造」的约束。

**目前它俩的局限，直说**：

1. 检索环节是关键词匹配，57 篇周报正文全都包含「GMV」字样，命中数与内容相关度无关，**等于没检索**。所以「最高/最低」这类问题我改成直接走 SQL 排序——数据库算的必然对，让模型在可能不含正确答案的候选集里猜是错的。
2. 知识库只有 57 篇约 3.5KB，规模太小，检索这一步的价值体现不出来；真要到百万级内容，必须上向量检索（embedding）。
3. 关键词路由是精确匹配，不兼容拼写错误（输入 "gvm" 会漏接），生产环境应该用 LLM 做意图分类。

所以这部分**只是架构验证，不是这个项目的主要价值**——主要价值在第四节那套 FastAPI 接口和第七节那些坑。

---

## 九、启动步骤

**前置**：本机已安装并启动 PostgreSQL 16。

```bash
# 1. 建库（只需一次）
createdb ecommerce_insight

# 2. 虚拟环境与依赖
/Users/apple/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置环境变量（.env.example 只有键名和占位值，不含真实密钥）
cp .env.example .env
#   编辑 .env：填入本机的数据库串与 DeepSeek 密钥

# 4. 建表 + 造数（约几秒）
python scripts/gen_data.py

# 5. 启动服务
uvicorn app.main:app --reload

# 6. 打开交互文档
open http://127.0.0.1:8000/docs
```

> 键名以 `.env.example` 为唯一来源。`.env` 已在 `.gitignore` 中，真实密钥不进版本库；`load_dotenv()` 默认只加载 `.env`。

---

## 十、已知边界与后续

| 项 | 现状 | 之后想做的 |
|---|---|---|
| 鉴权 | 未做，仅本机访问 | 引入登录态，user_id 从 token 解析 |
| `user_id` | 下单接口暂写死为 1 | 同上 |
| session 管理 | 手写 `try/finally` | 改用 FastAPI `Depends` 依赖注入 |
| 配置读取 | `os.getenv` + dotenv | 可换 pydantic-settings 统一管配置 |
| 检索方式 | 关键词 `LIKE` | 规模上去后换向量检索 |
| 测试 | 10 条 pytest 用例覆盖 6 个接口；`/api/rag/ask` 未覆盖——单次请求内两次 LLM 调用且 URL 相同，mock 得按 system 提示词分派，耦合文案 | 把 LLM 调用抽成单一出口 `call_deepseek()`，只对出口做 mock，成本立刻降下来 |
| 异步范围 | 仅 `/api/overview` 走异步，其余接口同步跑线程池 | 数据库换 async driver 后再全量异步化 |
| 异步吞吐 | 单请求延迟降 3 倍（3s→1s），但 60 并发下吞吐只有同步接口的约 1/8（线程池 40 令牌被 3 倍消耗） | 换 asyncpg 走全链路 `await`，连接不再占线程；见 4.6 实测数据 |
| 项目结构 | 路由全在 `main.py` | 拆成 router + service 分层 |

---

## 附：项目结构

```
ecommerce_insight/
├── app/
│   ├── main.py          # 全部路由
│   └── models.py        # ORM 模型 + Pydantic 请求体模型
├── scripts/
│   └── gen_data.py      # 建表 + 造订单 + 生成周报
├── test/
│   ├── test_read.py     # 查询类接口 + insight + overview（含并发用例）
│   └── test_write.py    # 下单接口，带回滚清理
├── conftest.py          # pytest 的 client fixture，放项目根
├── requirements.txt
├── .env                 # 本地配置，不入库
└── .gitignore
```
