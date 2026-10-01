
from sqlalchemy import  Column, Integer, String, DateTime, func, DECIMAL
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class ProductType (Base):
    """users 表的 ORM 映射，字段会保存到 SQLite 数据库。"""

    __tablename__ = "product_type"
    id =Column(Integer, primary_key=True,autoincrement=True)
    prd_name =Column(String(50), nullable=False,unique=True)
    create_time =Column(DateTime)
    update_time =Column(DateTime)

class Orders(Base):
    """users 表的 ORM 映射，字段会保存到 PostgreSQL 数据库。"""

    __tablename__ = "orders"
    id =Column(Integer, primary_key=True,autoincrement=True)
    order_id =Column(Integer)
    user_id =Column(Integer)
    prd_id =Column(Integer)
    amount =Column(DECIMAL)
    order_time =Column(DateTime)
    status = Column(String(10))

class Reports(Base):
    """周报表："""
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    iso_year = Column(Integer, nullable=False)
    iso_week = Column(Integer, nullable=False)
    gmv = Column(DECIMAL)
    order_cnt = Column(Integer)
    top_products = Column(String(200))
    report_text = Column(String(1000))

