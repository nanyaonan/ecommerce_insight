# app/main.py

from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import create_engine, func, Integer, String, DateTime, DECIMAL
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from app.models import ProductType, Orders
import logging
import httpx
logger = logging.getLogger("uvicorn")
from dotenv import load_dotenv
load_dotenv()

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

app = FastAPI(title="电商经营数据洞察API")


# 放在 main.py 顶部，模型加载之后



@app.get("/api/categories")
def list_categories():
    """接口①：返回全部品类及每个品类的订单量"""
    session = Session()
    try:
        rows = session.query(ProductType).all()
        sales = session.query(Orders.prd_id,func.count(Orders.id)).group_by(Orders.prd_id).all()
        sale_data={s[0]:s[1] for s in sales}
        logger.info([(s[0],s[1])for s in sales])
        return [{"id":p.id, "name": p.prd_name,"sales": sale_data.get(p.id)} for p in rows]

    finally:
        session.close()


@app.get("/api/gmv")
def sum_gmv(start: str|None=None, end: str |None = None):
    session = Session()
    try:
        start,end=resolve_range(session, start, end)

        gmv=session.query(func.sum(Orders.amount)).filter(Orders.order_time>=start
                                                                  ,Orders.order_time<=end
                                                          ,Orders.status=='已完成').scalar()
        count = session.query(func.count(Orders.id)).filter(Orders.order_time >= start
                                                            , Orders.order_time <= end).scalar()
        done_cnt = session.query(func.count(Orders.id)).filter(
            Orders.order_time >= start, Orders.order_time <= end,
            Orders.status == '已完成').scalar()

        return {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "gmv": gmv or 0,
            "order_cnt": count,
            "avg_amount": round(float(gmv or 0) / done_cnt, 2) if done_cnt else 0,
            # Decimal 不能直接进 JSON，要 float() 转一道
        }

    finally:
        session.close()


#趋势查询
@app.get("/api/trend")
def get_trend(start: str|None=None, end: str|None=None):
    session = Session()
    try:
        start, end = resolve_range(session, start, end)
        gmv=session.query(func.date(Orders.order_time),func.sum(Orders.amount)).filter(Orders.order_time>=start
                                                                  ,Orders.order_time<=end
                                                          ,Orders.status=='已完成').group_by(func.date(Orders.order_time)).all()
        count = (session.query(func.date(Orders.order_time),func.count(Orders.id)).filter(Orders.order_time >= start
                                                            , Orders.order_time <= end).group_by(func.date(Orders.order_time)).order_by(func.date(Orders.order_time)).all())
        done_cnt = session.query(func.date(Orders.order_time),func.count(Orders.id)).filter(
            Orders.order_time >= start, Orders.order_time <= end,
            Orders.status == '已完成').group_by(func.date(Orders.order_time)).all()
        gmv_dict={g[0]:g[1] for g in gmv}
        count_dict={g[0]:g[1] for g in count}
        done_cnt_dict={g[0]:g[1] for g in done_cnt}
        result=[]
        for k,v in count_dict.items():
            result.append({
                "date":k.strftime("%Y-%m-%d"),
                "gmv":float(gmv_dict.get(k,0)),
                "order_count":v,
                "order_count_done":done_cnt_dict.get(k,0),
                "avg_amount":round(float(gmv_dict.get(k,0))/ done_cnt_dict.get(k,0),2) if done_cnt_dict.get(k,0) else 0
            })

        # print (result)
        return result
    finally:
        session.close()



#返回topN的品类销售额和销量
@app.get("/api/topn")
def get_top(start: str|None=None, end: str|None=None, n:int =8):
    session = Session()
    try:
        start, end = resolve_range(session, start, end)
        sales=(session.query(Orders.prd_id,func.sum(Orders.amount),func.count(Orders.id)).filter(Orders.order_time>=start
                                                                  ,Orders.order_time<=end
                                                          ,Orders.status=='已完成').group_by(Orders.prd_id).order_by(func.sum(Orders.amount).desc(),func.count(Orders.id).desc())
               .limit(max(n,1)).all())
        result=[]
        for i,s in enumerate(sales,1):
            result.append({
                "name":id_to_name.get(s[0]),
                "gmv":float(s[1] or 0),
                "rank":i,
                "order_count":s[2],
                "avg_amount":round (float(s[1] or 0)/ s[2],2) if  s[2] else 0
            })

        # print (result)
        return result
    finally:
        session.close()


#经营数据AI解读

@app.get("/api/insight")
def get_insight(start: str|None=None, end: str|None=None):
    session = Session()
    try:
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
            "order_count":count,
            "total_count":total_count,
            "top_category":id_to_name.get(sales[0]),
        }
        ratio=round((float(sales[1] or 0)/r.get('gmv') if r.get('gmv') !=0 else 0)*100,2)
        logger.info (r)
        content=(f"时间范围{r.get('start_date')}至{r.get('end_date')}：GMV共{r.get('gmv')}元，订单{r.get('total_count')}单，其中已完成{r.get('order_count')}单"
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
    finally:
        session.close()
