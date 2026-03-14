from __future__ import annotations

from fastapi.testclient import TestClient

# Realistic VTB statement text that the new block-based parser can handle
FAKE_STATEMENT_TEXT = """\
Номер карты 220024******1234
Период выписки 01.01.2026 - 31.01.2026
Кредитный лимит 500,000.00 RUB
Доступный остаток 100,000.00 RUB
Общая сумма задолженности* 400,000.00
Минимальный платеж 10,000.00 RUB
Статус беспроцентного периода Действует
Операции по карте
Проведена Обработана В валюте Поступление Расход Комиссия Задолженность Описание операции
15.01.2026
10:30:00
16.01.2026
14:00:00
-1,200.00 RUB 0 RUB 1,200.00 RUB 0.00 RUB 401,200.00 Оплата товаров и услуг. TEST MERCHANT
20.01.2026
08:00:00
21.01.2026
12:00:00
-500.00 RUB 0 RUB 500.00 RUB 0.00 RUB 401,700.00 Оплата товаров и услуг. METRO
25.01.2026
15:00:00
26.01.2026
10:00:00
3,000.00 RUB 3,000.00 RUB 0 RUB 0.00 RUB 398,700.00 OOO STIMUL
"""


def _upload_pdf(client: TestClient, name: str, content: bytes) -> dict:
    response = client.post(
        "/api/v1/statements/upload-pdf",
        files={"file": (name, content, "application/pdf")},
    )
    return {"status_code": response.status_code, "json": response.json()}


def test_upload_rejects_non_pdf_file(client: TestClient) -> None:
    result = _upload_pdf(client, "statement.txt", b"not-a-pdf")
    assert result["status_code"] == 400
    assert result["json"]["detail"] == "Only PDF files are supported"


def test_upload_rejects_empty_payload(client: TestClient) -> None:
    result = _upload_pdf(client, "statement.pdf", b"")
    assert result["status_code"] == 400
    assert result["json"]["detail"] == "Uploaded file is empty"


def test_pipeline_upload_parse_normalize_score_summary(client: TestClient) -> None:
    result = _upload_pdf(client, "statement.pdf", FAKE_STATEMENT_TEXT.encode("utf-8"))
    assert result["status_code"] == 200
    statement_id = result["json"]["statement"]["id"]

    parse_response = client.post(f"/api/v1/statements/{statement_id}/parse")
    assert parse_response.status_code == 200
    assert parse_response.json()["status"] == "parsed"
    assert parse_response.json()["details"]["rows"] >= 1

    normalize_response = client.post(f"/api/v1/statements/{statement_id}/normalize")
    assert normalize_response.status_code == 200
    assert normalize_response.json()["status"] == "normalized"

    score_response = client.post(f"/api/v1/statements/{statement_id}/score")
    assert score_response.status_code == 200
    assert score_response.json()["status"] == "scored"

    summary_response = client.get(f"/api/v1/statements/{statement_id}/summary")
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["statement_id"] == statement_id
    assert payload["total_operations"] >= 1
    assert "total_inflow" in payload
    assert "total_outflow" in payload
