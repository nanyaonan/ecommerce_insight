# app/main.py
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import create_engine, func, Integer, String, DateTime, DECIMAL
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from app.models import ProductType, Orders
import logging
logger = logging.getLogger("uvicorn")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://apple:apple@127.0.0.1:5432/ecommerce_insight")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

_session =Session()
id_to_name ={p.id:p.prd_name for p in _session.query(ProductType).all()}
_session.close()

app = FastAPI(title="电商经营数据洞察API")

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
        start=session.query(func.min(Orders.order_time)).scalar() if start is None else datetime.strptime(start, '%Y-%m-%d')
        end=session.query(func.max(Orders.order_time)).scalar() if end is None else datetime.strptime(end, '%Y-%m-%d')+timedelta(days=1,seconds=-1)

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
        start=session.query(func.min(Orders.order_time)).scalar() if start is None else datetime.strptime(start, '%Y-%m-%d')
        end=session.query(func.max(Orders.order_time)).scalar() if end is None else datetime.strptime(end, '%Y-%m-%d')+timedelta(days=1,seconds=-1)

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
        start=session.query(func.min(Orders.order_time)).scalar() if start is None else datetime.strptime(start, '%Y-%m-%d')
        end=session.query(func.max(Orders.order_time)).scalar() if end is None else datetime.strptime(end, '%Y-%m-%d')+timedelta(days=1,seconds=-1)

        sales=(session.query(Orders.prd_id,func.sum(Orders.amount),func.count(Orders.id)).filter(Orders.order_time>=start
                                                                  ,Orders.order_time<=end
                                                          ,Orders.status=='已完成').group_by(Orders.prd_id).order_by(func.sum(Orders.amount).desc(),func.count(Orders.id).desc())
               .limit(max(n,1)).all())
        result=[]
        for i,s in enumerate(sales,1):
            result.append({
                "rank":i,
                "name":id_to_name.get(s[0]),
                "gmv":float(s[1] or 0),
                "order_count":s[2],
                "avg_amount":round (float(s[1] or 0)/ s[2],2) if  s[2] else 0
            })

        # print (result)
        return result
    finally:
        session.close()