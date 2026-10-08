# app/main.py
import asyncio
from collections import Counter
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.params import Depends
from sqlalchemy import create_engine, func, Integer, String, DateTime, DECIMAL
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from app.models import ProductType, Orders, OrderIn, AskIn, Reports
import logging
import httpx
logger = logging.getLogger("uvicorn")
from dotenv import load_dotenv
load_dotenv()

def q_summary(start,end):
    session = Session()
    try:
        start, end = resolve_range(session, start, end)

        gmv = session.query(func.sum(Orders.amount)).filter(Orders.order_time >= start
                                                            , Orders.order_time <= end
                                                            , Orders.status == '已完成').scalar()
        count = session.query(func.count(Orders.id)).filter(Orders.order_time >= start
                                                            , Orders.order_time <= end).scalar()
        done_cnt = session.query(func.count(Orders.id)).filter(
            Orders.order_time >= start, Orders.order_time <= end,
            Orders.status == '已完成').scalar()

        return {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "gmv": gmv or 0,
            "total_count": count,
            "avg_amount": round(float(gmv or 0) / done_cnt, 2) if done_cnt else 0,
            # Decimal 不能直接进 JSON，要 float() 转一道
        }
    finally:
        session.close()

def q_trend(start,end):
    session = Session()
    try:
        start, end = resolve_range(session, start, end)
        gmv = session.query(func.date(Orders.order_time), func.sum(Orders.amount)).filter(Orders.order_time >= start
                                                                                          , Orders.order_time <= end
                                                                                          ,
                                                                                          Orders.status == '已完成').group_by(
            func.date(Orders.order_time)).all()
        count = (session.query(func.date(Orders.order_time), func.count(Orders.id)).filter(Orders.order_time >= start
                                                                                           ,
                                                                                           Orders.order_time <= end).group_by(
            func.date(Orders.order_time)).order_by(func.date(Orders.order_time)).all())
        done_cnt = session.query(func.date(Orders.order_time), func.count(Orders.id)).filter(
            Orders.order_time >= start, Orders.order_time <= end,
            Orders.status == '已完成').group_by(func.date(Orders.order_time)).all()
        gmv_dict = {g[0]: g[1] for g in gmv}
        count_dict = {g[0]: g[1] for g in count}
        done_cnt_dict = {g[0]: g[1] for g in done_cnt}
        result = []
        for k, v in count_dict.items():
            result.append({
                "date": k.strftime("%Y-%m-%d"),
                "gmv": float(gmv_dict.get(k, 0)),
                "total_count": v,
                "order_count_done": done_cnt_dict.get(k, 0),
                "avg_amount": round(float(gmv_dict.get(k, 0)) / done_cnt_dict.get(k, 0), 2) if done_cnt_dict.get(k,0) else 0
            })
        # print (result)
        return result
    finally:
        session.close()



def q_topn(start,end,n):
    session=Session()
    try:
        start, end = resolve_range(session, start, end)
        sales = (session.query(Orders.prd_id, func.sum(Orders.amount), func.count(Orders.id)).filter(
            Orders.order_time >= start
            , Orders.order_time <= end
            , Orders.status == '已完成').group_by(Orders.prd_id).order_by(func.sum(Orders.amount).desc(),
                                                                          func.count(Orders.id).desc())
                 .limit(max(n, 1)).all())
        result = []
        for i, s in enumerate(sales, 1):
            result.append({
                "name": id_to_name.get(s[0]),
                "gmv": float(s[1] or 0),
                "rank": i,
                "order_count": s[2],
                "avg_amount": round(float(s[1] or 0) / s[2], 2) if s[2] else 0
            })

        # print (result)
        return result
    finally:
        session.close()



def resolve_range(session, start, end):
    """把可选的日期字符串解析成 (start, end)，没传就用数据的实际范围"""
    s = session.query(func.min(Orders.order_time)).scalar() if start is None else datetime.strptime(start, '%Y-%m-%d')
    e = session.query(func.max(Orders.order_time)).scalar() if end is None else datetime.strptime(end, '%Y-%m-%d') + timedelta(days=1, seconds=-1)
    return s, e

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://apple:apple@127.0.0.1:5432/ecommerce_insight")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

_session =Session()
id_to_name ={p.id:p.prd_name for p in _session.query(ProductType).all()}
_session.close()

def get_session():
    session = Session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

app = FastAPI(title="电商经营数据洞察API")
@app.get("/api/overview",name='经营总览：汇总＋趋势＋TopN三查询并行')
async def get_overview(start:str|None=None, end:str|None=None, n:int = 5):
    summary, trend, topn = await asyncio.gather(
        run_in_threadpool(q_summary, start, end),
        run_in_threadpool(q_trend, start, end),
        run_in_threadpool(q_topn, start, end, n)
    )
    return {**summary, "trend": trend, "top_categories": topn}


@app.get("/api/categories",name ='返回全部品类及每个品类的订单量')
def list_categories(session=Depends(get_session)):
    """接口①：返回全部品类及每个品类的订单量"""
    rows = session.query(ProductType).all()
    sales = session.query(Orders.prd_id,func.count(Orders.id)).group_by(Orders.prd_id).all()
    sale_data={s[0]:s[1] for s in sales}
    logger.info([(s[0],s[1])for s in sales])
    return [{"id":p.id, "name": p.prd_name,"sales": sale_data.get(p.id)} for p in rows]




@app.get("/api/gmv", name='按日期汇总销售额')
def sum_gmv(start: str|None=None, end: str |None = None,session=Depends(get_session)):
    start, end = resolve_range(session, start, end)

    gmv = session.query(func.sum(Orders.amount)).filter(Orders.order_time >= start
                                                        , Orders.order_time <= end
                                                        , Orders.status == '已完成').scalar()
    count = session.query(func.count(Orders.id)).filter(Orders.order_time >= start
                                                        , Orders.order_time <= end).scalar()
    done_cnt = session.query(func.count(Orders.id)).filter(
        Orders.order_time >= start, Orders.order_time <= end,
        Orders.status == '已完成').scalar()

    return {
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "gmv": gmv or 0,
        "total_count": count,
        "avg_amount": round(float(gmv or 0) / done_cnt, 2) if done_cnt else 0,
        # Decimal 不能直接进 JSON，要 float() 转一道
    }


#趋势查询
@app.get("/api/trend",name='按天销售趋势查询')
def get_trend(start: str|None=None, end: str|None=None, session=Depends(get_session)):
    start, end = resolve_range(session, start, end)
    gmv = session.query(func.date(Orders.order_time), func.sum(Orders.amount)).filter(Orders.order_time >= start
                                                                                      , Orders.order_time <= end
                                                                                      ,
                                                                                      Orders.status == '已完成').group_by(
        func.date(Orders.order_time)).all()
    count = (session.query(func.date(Orders.order_time), func.count(Orders.id)).filter(Orders.order_time >= start
                                                                                       ,
                                                                                       Orders.order_time <= end).group_by(
        func.date(Orders.order_time)).order_by(func.date(Orders.order_time)).all())
    done_cnt = session.query(func.date(Orders.order_time), func.count(Orders.id)).filter(
        Orders.order_time >= start, Orders.order_time <= end,
        Orders.status == '已完成').group_by(func.date(Orders.order_time)).all()
    gmv_dict = {g[0]: g[1] for g in gmv}
    count_dict = {g[0]: g[1] for g in count}
    done_cnt_dict = {g[0]: g[1] for g in done_cnt}
    result = []
    for k, v in count_dict.items():
        result.append({
            "date": k.strftime("%Y-%m-%d"),
            "gmv": float(gmv_dict.get(k, 0)),
            "total_count": v,
            "order_count_done": done_cnt_dict.get(k, 0),
            "avg_amount": round(float(gmv_dict.get(k, 0)) / done_cnt_dict.get(k, 0), 2) if done_cnt_dict.get(k,
                                                                                                             0) else 0
        })
    # print (result)
    return result



#返回topN的品类销售额和销量
@app.get("/api/category/topn", name='按日期汇总返回topN的品类销售额和销量')
def get_top(start: str|None=None, end: str|None=None, n:int =8,session=Depends(get_session)):
    start, end = resolve_range(session, start, end)
    sales = (session.query(Orders.prd_id, func.sum(Orders.amount), func.count(Orders.id)).filter(
        Orders.order_time >= start
        , Orders.order_time <= end
        , Orders.status == '已完成').group_by(Orders.prd_id).order_by(func.sum(Orders.amount).desc(),
                                                                      func.count(Orders.id).desc())
             .limit(max(n, 1)).all())
    result = []
    for i, s in enumerate(sales, 1):
        result.append({
            "name": id_to_name.get(s[0]),
            "gmv": float(s[1] or 0),
            "rank": i,
            "order_count": s[2],
            "avg_amount": round(float(s[1] or 0) / s[2], 2) if s[2] else 0
        })

    # print (result)
    return result


#经营数据AI解读

@app.get("/api/insight", name="按日期汇总解读经营数据")
def get_insight(start: str|None=None, end: str|None=None,session=Depends(get_session)):

    start, end = resolve_range(session, start, end)
    gmv = (session.query( func.sum(Orders.amount))
           .filter(Orders.order_time >= start, Orders.order_time <= end,Orders.status == '已完成').scalar())
    sales=(session.query(Orders.prd_id,func.sum(Orders.amount))
           .filter(Orders.order_time>=start,Orders.order_time<=end,Orders.status=='已完成')
           .group_by(Orders.prd_id).order_by(func.sum(Orders.amount).desc(),func.count(Orders.id).desc())
           .limit(1).first())
    count=(session.query(func.count(Orders.id))
           .filter(Orders.order_time >= start,Orders.order_time <= end,Orders.status=='已完成')
           .scalar())
    total_count = (session.query(func.count(Orders.id))
             .filter(Orders.order_time >= start, Orders.order_time <= end)
             .scalar())
    r={
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "gmv":float(gmv or 0),
        "order_count_done":count,
        "total_count":total_count,
        "top_category":id_to_name.get(sales[0]),
    }
    ratio=round((float(sales[1] or 0)/r.get('gmv') if r.get('gmv') !=0 else 0)*100,2)
    logger.info (r)
    content=(f"时间范围{r.get('start_date')}至{r.get('end_date')}：GMV共{r.get('gmv')}元，订单{r.get('total_count')}单，其中已完成{r.get('order_count_done')}单"
             f"，销售额第一名是{r.get('top_category')}（占比{ratio}%）")
    logger.info( content)
    resp = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization":f"Bearer {os.getenv('DEEPSEEK_API_KEY')}"},
        json={
            "model":"deepseek-chat",
            "messages":[
                {"role":"system","content":"你是一个电商数据分析师,请用3句话给店铺老板做经营解读：一句话讲大盘，一句话讲结构性亮点，一句话给建议。不要使用markdown格式"},
                {"role":"user","content":content}
            ],
        },
        timeout=60,
    )

    if resp.status_code == 200:
        r["insight"]=resp.json()["choices"][0]["message"]["content"]
    else:
        r["insight"]="模型服务暂停不可用请稍后再试"
        logger.info(f"DeepSeek返回: status={resp.status_code}, body={resp.text[:500]}")

    return r


@app.post("/api/orders", status_code=201, name ='增加订单')
def post_order(order:OrderIn,session = Depends(get_session)):
    user_id=1 #先写死
    o = Orders(order_time=datetime.now(), prd_id=order.prd_id, amount=order.amount, user_id=user_id,status=order.status)
    session.add(o)
    session.commit()
    session.refresh(o)
    return {"id":o.id,"message":"已完成"}


@app.post("/api/rag/ask")
def post_rag(q: AskIn,session=Depends(get_session)):

    question = q.question

    # ===== ① 程度类：交给 SQL 排序，答案精确且自带出处 =====
    if "GMV" in question.upper() or "销售额" in question:
        metric, name, unit = Reports.gmv, "GMV", "元"
    elif "订单" in question or "单量" in question or "销量" in question or "销售量" in question or "订单量" in question:
        metric, name, unit = Reports.order_cnt, "订单量", "单"
    else:
        metric, name, unit = None, "", ""

    logger.info(metric)
    if metric is not None:
        if any(w in question for w in ("最高", "最多", "最大", "最好")):
            row, deg = session.query(Reports).order_by(metric.desc()).first(), "最高"
        elif any(w in question for w in ("最低", "最少", "最小", "最差")):
            row, deg = session.query(Reports).order_by(metric.asc()).first(), "最低"
        else:
            row, deg = None, ""
        if row is not None:
            value = round(float(row.gmv), 2) if name == "GMV" else row.order_cnt
            return {
                "question": question,
                "answer": f"{name}{deg}的是{row.iso_year}年第{row.iso_week}周，为{value}{unit}（结论由数据库排序直接得出）",
                "sources": [{"week": f"{row.iso_year}-W{row.iso_week:02d}", "content": row.report_text}],
                "mode": "sql-order",
            }

    # ===== ② 检索：LLM 抽关键词 + LIKE 多词命中 =====
    resp = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}"},
        json={"model": "deepseek-chat", "messages": [
            {"role": "system", "content": "从用户问题中提取2-3个用于检索数据库的关键词，只输出关键词，用逗号分隔。"},
            {"role": "user", "content": question}]},
        timeout=60,
    )
    if resp.status_code != 200:
        return {"question": question, "answer": "关键词提取服务不可用", "sources": [], "mode": "rag"}
    keywords = [k.strip() for k in resp.json()["choices"][0]["message"]["content"].split(",") if k.strip()]
    matched, score = {}, Counter()
    for kw in keywords:
        for t in session.query(Reports).filter(Reports.report_text.like(f"%{kw}%")).all():
            matched[t.id] = t
            score[t.id] += 1
    hits = [matched[i] for i, _ in score.most_common(q.top_k)]
    if not hits:
        hits = session.query(Reports).order_by(Reports.iso_year.desc(), Reports.iso_week.desc()).limit(3).all()

    # ===== ③ 生成：只基于给定材料回答，不许编造 =====
    materials = "\n\n".join([f"【{t.iso_year}年第{t.iso_week}周】{t.report_text}" for t in hits])
    resp2 = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}"},
        json={"model": "deepseek-chat", "messages": [
            {"role": "system", "content": "你只能依据下面提供的材料回答。材料中没有的信息，直接回答'材料中没有相关信息'，不得编造或推测。回答末尾注明依据的是哪一周的材料。"},
            {"role": "user", "content": f"材料：\n{materials}\n\n问题：{question}"}]},
        timeout=60,
    )
    answer = resp2.json()["choices"][0]["message"]["content"] if resp2.status_code == 200 else "模型服务暂不可用"
    return {
        "question": question,
        "answer": answer,
        "sources": [{"week": f"{t.iso_year}-W{t.iso_week:02d}", "content": t.report_text} for t in hits],
        "mode": "rag",
    }
