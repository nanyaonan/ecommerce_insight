import random
from datetime import datetime, timedelta
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.models import ProductType, Orders,Reports,Users
from dotenv import load_dotenv
load_dotenv()

# DEFAULT_DATABASE_URL = "postgresql://apple:apple@127.0.0.1:5432/ecommerce_insight"


DATABASE_URL = os.getenv("DATABASE_URL")

Base = declarative_base()

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

Base.metadata.create_all(engine)

session.query(Orders).delete()
session.query(Reports).delete()
session.query(ProductType).delete()
session.commit()
products =[
    ProductType(prd_name='女装'),
    ProductType(prd_name='数码'),
    ProductType(prd_name='美妆'),
    ProductType(prd_name='食品'),
    ProductType(prd_name='家居'),
    ProductType(prd_name='运动'),
    ProductType(prd_name='母婴'),
    ProductType(prd_name='图书')
]

session.add_all(products)
session.commit()

name_to_id ={p.prd_name:p.id for p in session.query(ProductType).all()}
id_to_name = {v: k for k, v in name_to_id.items()}

print(name_to_id)
products_list=['女装','数码','美妆','食品','家居','运动','母婴','图书']
products_weights = [0.30, 0.20, 0.18, 0.10, 0.08, 0.06, 0.05, 0.03]  # 8个品类，权重和=1
product_type_list = random.choices(products_list,products_weights,k=10000)
status=['已完成','已取消','退款']
status_weights=[0.88,0.07,0.05]
status_list = random.choices(status,status_weights,k=10000)
amount_random = [random.lognormvariate(mu=4.2, sigma=0.6) for _ in range(10000)]
# print (amount_random)


start = datetime(2025, 9, 1)
days = 395  # 13个月
def random_order_time():
    while True:
        d=start+timedelta(days=random.randint(0,days-1)
                          ,hours=random.randint(0,23))
        accept =1 if d.weekday()>=5 else 0.77
        if random.random() < accept:
            return d

data = []
for i in range(10000):
    data.append(Orders(order_id=i, user_id=random.randint(1,2000), prd_id=name_to_id[product_type_list[i]], amount=round(amount_random[i],2)
                       ,order_time=random_order_time(), status=status_list[i]))

session.add_all(data)
session.commit()


from collections import defaultdict
# 生成周报
weekly = defaultdict(list)
orders=session.query(Orders).all()
for order in orders:
    iso = order.order_time.isocalendar()
    weekly[iso[0], iso[1]].append(order)

repos=[]
for key, value in sorted(weekly.items()):
    print (key )
    gmv=round(sum(o.amount for o in value if o.status=='已完成'),2)
    print(len(value))
    product_count=defaultdict(int)
    for v in value:
        product_count[v.prd_id]+=1

    top3=sorted(product_count.items(),key=lambda x:x[1], reverse=True)[:3]
    top_product=[(id_to_name[i[0]],i[1]) for i in top3]
    print(top_product)

    top_str= "、".join((f"{t[0]}{t[1]}单"for t in top_product))
    text=f"{key[0]}年第{key[1]}周的周报如下:汇总GMV:{gmv:.2f};单量{len(value)};Top品类及销量:{top_str};"
    print(text)
    repos.append(Reports(iso_year=key[0],iso_week=key[1],gmv=gmv,order_cnt=len(value),top_products=top_str
                         ,report_text=text))

session.add_all(repos)
session.commit()