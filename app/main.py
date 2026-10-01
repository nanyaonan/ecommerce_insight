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

# 三个模型照搬gen_data.py里的定义（ProductType/Orders/Reports）
# ...

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
        end=session.query(func.max(Orders.order_time)).scalar() if end is None else datetime.strptime(end, '%Y-%m-%d')

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
        }

    finally:
        session.close()