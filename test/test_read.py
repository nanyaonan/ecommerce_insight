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
    r = client.get("/api/gmv" ,params={'start':'2025-12-31'})
    assert r.status_code == 200
    d = r.json()
    assert d['start_date']=='2025-12-31'

    r=client.get("/api/gmv")
    assert r.status_code==200
    d=r.json()
    assert {'start_date', 'end_date', 'gmv', 'total_count','avg_amount'} <= d.keys()
    assert d['gmv']>0
    assert d['total_count']==TOTAL_ORDERS
    assert d['avg_amount']>=d['gmv']/d['total_count']

def test_trend_按日期升序且已完成不超过总单量(client):
    r=client.get("/api/trend")
    assert r.status_code==200
    d=r.json()
    assert sum( i['total_count'] for i in d) <= TOTAL_ORDERS
    assert sum( i['order_count_done'] for i in d) <= sum( i['total_count'] for i in d)
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


class FakeResp:
    def __init__(self,status_code, body=None, text=""):
        self.status_code=status_code
        self._body=body
        self.text=text
    def json(self):
        return self._body

def test_insight_mock失败路径返回值(client, monkeypatch):
    monkeypatch.setattr('app.main.httpx.post', lambda *a, **k: FakeResp(500,text='{"error":"insufficient balance"}'))
    r = client.get("/api/insight")
    assert r.status_code == 200
    d = r.json()
    assert {'start_date', 'end_date', 'gmv', 'order_count_done', 'total_count','top_category','insight'} <= d.keys()
    assert d['insight'] is not None
    assert d['insight'] =="模型服务暂停不可用请稍后再试"

def test_insight_成功路径返回模型文案(client, monkeypatch):
    monkeypatch.setattr("app.main.httpx.post",
        lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": "本周GMV环比上升"}}]}))
    assert client.get("/api/insight").json()["insight"] == "本周GMV环比上升"


def test_overview(client):
    r=client.get("/api/overview",params={'start':'2025-12-31','end':'2026-03-31','n':5})
    assert r.status_code == 200
    r2=client.get("/api/gmv" ,params={'start':'2025-12-31','end':'2026-03-31'})
    r3=client.get("/api/trend" ,params={'start':'2025-12-31','end':'2026-03-31'})

    d=r.json()
    d2=r2.json()
    d3=r3.json()
    assert {'start_date','end_date','gmv','total_count','trend','top_categories'} <= d.keys()
    assert d['gmv']==d2['gmv']
    assert d['trend']==d3
    assert [i['rank'] for i in d['top_categories']] == [1,2,3,4,5]

import time
def test_overview_并发(client, monkeypatch):
    def slow(*a, **k):
        time.sleep(1)
        return {}
    monkeypatch.setattr("app.main.q_summary",slow)
    monkeypatch.setattr("app.main.q_trend",slow)
    monkeypatch.setattr("app.main.q_topn",slow)

    t0=time.time()
    r=client.get("/api/overview")
    dt=time.time()-t0

    assert r.status_code == 200
    assert dt<2
