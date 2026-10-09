
from sqlalchemy import Column, Integer, String, DateTime, func, DECIMAL, Boolean
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

class Users(Base):
    # """模拟用户表的一条记录。"""
    """周报表："""
    __tablename__ = "users"
    # 用户的唯一标识，必须为正整数。
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 登录用户名，长度限制为 3 到 30 个字符。
    username = Column(String(200))
    # 用户角色是否管理员。
    is_admin = Column(Boolean,default=False)
    # API_KEY
    api_key=Column(String(200),unique=True, index=True)
    api_key_prefix=Column(String(200),unique=True, index=True)
    api_key_hash=Column(String(200),unique=True, index=True)


from pydantic import BaseModel

class OrderIn(BaseModel):
    prd_id: int
    amount: float
    status: str='已完成'

class AskIn(BaseModel):
    question:str
    top_k:int