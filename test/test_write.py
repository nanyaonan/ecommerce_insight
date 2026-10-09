import pytest
from sqlalchemy import func
from app.main import Session, Orders
from conftest import as_admin,as_normal


class FakeResp:
    def __init__(self,status_code, body=None, text=""):
        self.status_code=status_code
        self._body=body
        self.text=text
    def json(self):
        return self._body

@pytest.fixture
def rollback_orders():
    """下单用例专用：跑完删掉新增行，保证 orders 恒为 10000"""
    s = Session()
    max_id = s.query(func.max(Orders.id)).scalar()
    yield
    s.query(Orders).filter(Orders.id > max_id).delete(synchronize_session=False)
    s.commit()
    assert s.query(func.count(Orders.id)).scalar() == 10000   # 自检
    s.close()


def test_orders_创建成功返回201与自增id(client, rollback_orders,as_normal):
    r = client.post("/api/orders", json={"prd_id": 27, "amount": 99.9})  # 品类 id 实测是 27-34
    assert r.status_code == 201
    assert r.json()["message"] == "已完成"
    assert isinstance(r.json()["id"], int)

def test_orders_无token返回401(client):
    r = client.post("/api/orders", json={"prd_id": 27, "amount": 99.9})  # 品类 id 实测是 27-34
    assert r.status_code == 401


def test_orders_缺字段被Pydantic拦成422(client, rollback_orders,as_normal):
    assert client.post("/api/orders", json={"prd_id": 27}).status_code == 422




#
# def test_rag_程度类走SQL不打LLM(client, monkeypatch):
#     monkeypatch.setattr("app.main.httpx.post", lambda *a, **k: pytest.fail("程度类不该调 LLM"))
#     d = client.post("/api/rag/ask", json={"question": "哪一周GMV最高？", "top_k": 3}).json()
#     assert d["mode"] == "sql-order" and d["sources"]
#
#
# def test_rag_关键词提取失败降级(client, monkeypatch):
#     monkeypatch.setattr("app.main.httpx.post", lambda *a, **k: FakeResp(500, text="boom"))
#     d = client.post("/api/rag/ask", json={"question": "退货政策是什么", "top_k": 3}).json()
#     assert d["answer"] == "关键词提取服务不可用" and d["sources"] == []
#
#
# def test_rag_成功路径两次LLM按system分派(client, monkeypatch):
#     calls = []
#     def fake_post(url, **kwargs):
#         system = kwargs["json"]["messages"][0]["content"]
#         calls.append(system)
#         if "提取2-3个" in system:
#             return FakeResp(200, {"choices": [{"message": {"content": "GMV, 趋势"}}]})
#         if "你只能依据下面提供的材料" in system:
#             return FakeResp(200, {"choices": [{"message": {"content": "据第40周材料"}}]})
#         raise AssertionError(f"未预期的 LLM 调用: {system[:40]}")
#     monkeypatch.setattr("app.main.httpx.post", fake_post)
#     d = client.post("/api/rag/ask", json={"question": "退货政策是什么", "top_k": 3}).json()
#     assert len(calls) == 2 and d["answer"] == "据第40周材料" and d["mode"] == "rag"
