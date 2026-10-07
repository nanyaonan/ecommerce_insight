"""并发压测：/api/overview（异步）对比 /api/gmv（同步）

配套 README 4.6 节。看的是**吞吐**，不是单请求延迟：
单请求 overview 是快的（三个查询并行），但并发一上来就比同步接口慢一个量级。

用法（在项目根目录跑，需要数据库可用）：
    python scripts/bench.py
    # 自动起服务 → 先跑一轮冷启动 → 预热 → 三档压测 → 关服务，约 40 秒

脚本特意先跑一轮**不预热**的，再跑预热后的，两组摆在一起——
预热和不预热能差 4 倍，这个坑踩过一次就忘不掉。
"""

import os
import statistics
import sys
import threading
import time

# 从 scripts/ 里直接跑时，sys.path[0] 是 scripts/，看不到项目根的 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import concurrent.futures as cf

    import httpx
    import uvicorn

    from app.main import app

    PORT = 8123
    BASE = f"http://127.0.0.1:{PORT}"
    PATHS = ("/api/gmv", "/api/overview")   # 同步 def / 异步 async def
    LEVELS = (10, 30, 60)                   # 并发档位
    ROUNDS = 3                              # 每档跑几轮取中位数

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    for _ in range(50):
        try:
            httpx.get(f"{BASE}/api/gmv", timeout=1, trust_env=False)
            break
        except Exception:
            time.sleep(0.1)
    else:
        print("服务没起来：检查端口是否被占用，以及数据库是否可用")
        print("（app.main 在 import 时就会建 session 查一次品类表，库不通则起不来）")
        return

    def bench(path, n):
        """打 n 个并发请求，返回全部打完的总墙钟时间"""
        t0 = time.time()
        with httpx.Client(trust_env=False, timeout=120) as c:
            with cf.ThreadPoolExecutor(n) as ex:
                codes = list(ex.map(lambda _: c.get(BASE + path).status_code, range(n)))
        dt = time.time() - t0
        # 服务端扛不住会开始报错，而失败的请求返回得特别快，
        # 那样 dt 会变小数、吞吐虚高——看着很快其实是全崩了。必须拦住。
        assert codes.count(200) == n, f"有请求失败，结果不可信：{codes.count(200)}/{n}"
        return dt

    try:
        print("\n=== 第一轮：不预热（冷启动）===")
        print("连接池、线程、Postgres 执行计划全是冷的\n")
        print(f"{'并发':>6}{'/api/gmv':>14}{'/api/overview':>18}")
        print("-" * 40)
        cold = {}
        for n in LEVELS:
            g = bench("/api/gmv", n)
            o = bench("/api/overview", n)
            cold[n] = (g, o)
            print(f"{n:>6}{g:>12.2f}s{o:>16.2f}s")

        print("\n=== 预热（空跑，不计时）===")
        for path in PATHS:
            for _ in range(3):
                bench(path, 20)
        print("连接池、线程、执行计划已热\n")

        print("=== 第二轮：预热后，每档跑 %d 次取中位数 ===" % ROUNDS)
        print(f"{'并发':>6}{'/api/gmv':>14}{'/api/overview':>18}{'慢多少':>10}")
        print("-" * 48)
        for n in LEVELS:
            g = statistics.median([bench("/api/gmv", n) for _ in range(ROUNDS)])
            o = statistics.median([bench("/api/overview", n) for _ in range(ROUNDS)])
            cg, co = cold[n]
            print(f"{n:>6}{g:>12.2f}s{o:>16.2f}s{o / g:>9.1f}x")
            print(f"{'（冷启动同一档：':>6}{cg:>10.2f}s{co:>14.2f}s{'）':>10}")

        print("\n怎么看：")
        print("1. 冷启动那一轮通常偏大（连接池、线程、Postgres 执行计划都是冷的），")
        print("   但偏多少不保证——实测过差 4 倍，也实测过几乎没差，取决于机器当时的状态。")
        print("   结论只能是『必须预热』，不能是『一定差多少倍』。")
        print("   原理不变：不预热就等于把启动成本算进了性能里，那不是稳态性能。")
        print("2. 预热后 overview 稳定比 gmv 慢一个量级：单请求它更快（三个查询并行），")
        print("   但一个请求要占 3 个线程池令牌、干 3 倍聚合，人一多就从别人手里抢资源。")
        print("   所以这是『牺牲吞吐换延迟』，不是性能提升。")
        print("3. 绝对值随机器和数据量变化，别背；记『慢 5~10 倍』这个量级就够。\n")
    finally:
        server.should_exit = True
        t.join(timeout=5)


if __name__ == "__main__":
    main()
