"""阻塞对照演示：async def 里留同步阻塞，会发生什么

配套 README 4.6 节与「异步问答口径」。三种写法放在同一个 app 里，
20 并发压一遍就能看出差别——慢的那个不是慢一点，是慢 20 倍。

用法一（自测，推荐）：
    python scripts/block_demo.py
    # 自动起服务 → 压测 → 打印结果 → 关服务，约 10 秒

用法二（手动起服务，方便现场点）：
    uvicorn scripts.block_demo:app --port 8124
"""

import asyncio
import time

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

app = FastAPI(title="阻塞对照演示")


@app.get("/health")
async def health():
    """纯 CPU，没有任何 I/O。正常情况 0.01 秒返回，用来观察是否被别的请求拖住"""
    return {"ok": True}


@app.get("/A_block")
async def a_block():
    """错误写法：async def 里同步阻塞，独占整个事件循环"""
    time.sleep(1)
    return {"way": "async def + time.sleep"}


@app.get("/B_async")
async def b_async():
    """正确写法一：真异步等待，await 时主动让出"""
    await asyncio.sleep(1)
    return {"way": "async def + await asyncio.sleep"}


@app.get("/C_thread")
async def c_thread():
    """正确写法二：同步代码丢线程池（本项目 /api/overview 用的就是这个）"""
    await run_in_threadpool(time.sleep, 1)
    return {"way": "async def + run_in_threadpool"}


@app.get("/D_syncdef")
def d_syncdef():
    """写成 def，FastAPI 自动丢线程池，永远不占事件循环"""
    time.sleep(1)
    return {"way": "sync def + time.sleep"}


def main():
    import threading

    import concurrent.futures as cf
    import httpx
    import uvicorn

    PORT = 8124
    BASE = f"http://127.0.0.1:{PORT}"
    CONCURRENCY = 20

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    for _ in range(50):
        try:
            httpx.get(f"{BASE}/health", timeout=1, trust_env=False)
            break
        except Exception:
            time.sleep(0.1)
    else:
        print("服务没起来，检查端口是否被占用")
        return

    try:
        print(f"\n=== {CONCURRENCY} 并发打同一个端点（每个任务耗时 1 秒）===\n")
        print(f"{'端点':<24}{'总耗时':>10}{'吞吐':>14}")
        print("-" * 48)
        for path in ("/A_block", "/B_async", "/C_thread", "/D_syncdef"):
            t0 = time.time()
            with httpx.Client(trust_env=False, timeout=60) as c:
                with cf.ThreadPoolExecutor(CONCURRENCY) as ex:
                    codes = list(ex.map(lambda _: c.get(BASE + path).status_code, range(CONCURRENCY)))
            dt = time.time() - t0
            print(f"{path:<24}{dt:>9.2f}s{CONCURRENCY / dt:>11.1f} req/s")
            assert codes.count(200) == CONCURRENCY, "有请求失败，结果不可信"

        print("\n=== 传染测试：1 个慢请求 + 5 个 /health 同时打 ===\n")
        print(f"{'慢请求':<22}{'/health 最慢一次':>16}{'对比基线':>12}")
        print("-" * 50)
        # 先测一个"没有慢请求时 /health 要多久"的基线，通常在 0.01s 上下
        with httpx.Client(trust_env=False, timeout=60) as c:
            t0 = time.time()
            c.get(BASE + "/health")
            baseline = max(time.time() - t0, 0.001)

        for path in ("/A_block", "/B_async", "/C_thread"):
            health_cost = []

            def hit_health():
                with httpx.Client(trust_env=False, timeout=60) as c:
                    s = time.time()
                    c.get(BASE + "/health")
                    health_cost.append(time.time() - s)

            def hit_slow():
                with httpx.Client(trust_env=False, timeout=60) as c:
                    c.get(BASE + path)

            slow_th = threading.Thread(target=hit_slow)
            slow_th.start()
            # 关键：等慢请求真的进入 sleep、占住循环之后再发探针。
            # 不等这一下的话，5 个 /health 会抢在它前面跑完，测出来全是 0.01s，
            # 看起来像"没有传染"——假阴性比测不出来更糟。
            time.sleep(0.3)

            threads = [threading.Thread(target=hit_health) for _ in range(5)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            slow_th.join()
            slow = max(health_cost)
            print(f"{path:<22}{slow:>14.2f}s{slow / baseline:>10.0f}x")

        print("\n怎么看：A 的总耗时是 B/C/D 的 20 倍，而且把毫不相干的 /health")
        print("拖慢几十倍——探针发出得越早，被拖的时间越长。事件循环是一根绳上的，")
        print("谁卡住全体排队。判定看倍数，不要看绝对值（绝对值取决于探针时机）。\n")
    finally:
        server.should_exit = True
        t.join(timeout=5)


if __name__ == "__main__":
    main()
