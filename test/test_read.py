import re
TOTAL_ORDERS=10000
def test_categories_返回8个品类切订单量对的上总单量(client):
    r=client.get("/api/categories")
    assert r.status_code == 200
    data=r.json()
    assert len(data)==8
    for item in data:
        assert {'id','name','sales'}<=item.keys()

    assert sum(d['sales'] for d in data) == TOTAL_ORDERS


def test_gmv_字段齐全且口径符合状态已完成优先(client):
    r=client.get("/api/gmv")
    assert r.status_code==200
    d=r.json()
    assert {'start_date', 'end_date', 'gmv', 'total_count','avg_amount'} <= d.keys()
    assert d['gmv']>0
    assert d['total_count']==TOTAL_ORDERS
    assert d['avg_amount']>d['gmv']/d.pop('total_count')

def test_trend_按日期升序且已完成不超过总单量(client):
    r=client.get("/api/trend")
    assert r.status_code==200
    d=r.json()
    assert sum( i['total_count'] for i in d) <= TOTAL_ORDERS
    assert sum( i['order_count_done'] for i in d) < sum( i['total_count'] for i in d)
    dates= [date['date'] for date in d]
    assert dates == sorted(dates)
    for date in dates:
        assert re.match(r"^\d{4}-\d{2}-\d{2}$",date)

def test_topn_品类排序正确(client):
    r=client.get("/api/category/topn",params={'n':5})
    assert r.status_code==200
    d=r.json()
    ranks=[i['rank'] for i in d]
    assert ranks == sorted(ranks)
    assert len(ranks)==5
    assert ranks[0]==1
    gmv =[i['gmv'] for i in d]
    assert gmv == sorted(gmv,reverse=True)

def test_insight_mock失败路径返回值(client):
    r = client.get("/api/insight")

    assert r.status_code == 200
    d = r.json()
    assert {'start_date', 'end_date', 'gmv', 'order_count_done', 'total_count','top_category','insight'} <= d.keys()
    assert d['insight'] is not None