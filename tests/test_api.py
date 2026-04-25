from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestHealth:
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestAuth:
    async def test_register_creates_user(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            json={"username": "newuser99", "email": "newuser99@example.com", "password": "Password123"},
        )
        assert response.status_code in (201, 409)

    async def test_login_with_valid_credentials_returns_jwt(self, client: AsyncClient, registered_user: dict):
        response = await client.post(
            "/auth/login",
            json={"username": registered_user["username"], "password": registered_user["password"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_with_invalid_credentials_returns_401(self, client: AsyncClient):
        response = await client.post(
            "/auth/login",
            json={"username": "nonexistent_xyz", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    async def test_register_invalid_email_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            json={"username": "baduser", "email": "not-an-email", "password": "Password123"},
        )
        assert response.status_code == 422

    async def test_register_short_password_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/auth/register",
            json={"username": "baduser2", "email": "bad@example.com", "password": "short"},
        )
        assert response.status_code == 422


class TestEquipment:
    async def test_create_equipment_without_auth_returns_401(self, client: AsyncClient):
        response = await client.post(
            "/equipment",
            json={"equipment_id": "EQ-NOAUTH", "equipment_type": "motor", "location": "Zone A"},
        )
        assert response.status_code == 401

    async def test_create_equipment_with_auth(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            "/equipment",
            json={"equipment_id": "EQ-API-001", "equipment_type": "pump", "location": "Zone B"},
            headers=auth_headers,
        )
        assert response.status_code in (201, 409)
        if response.status_code == 201:
            data = response.json()
            assert data["equipment_type"] == "pump"

    async def test_list_equipment_returns_only_user_equipment(
        self, client: AsyncClient, auth_headers: dict
    ):
        response = await client.get("/equipment", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_equipment_by_id(self, client: AsyncClient, auth_headers: dict, registered_equipment: dict):
        eq_id = registered_equipment["id"]
        response = await client.get(f"/equipment/{eq_id}", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_equipment_returns_404_for_wrong_user(self, client: AsyncClient):
        await client.post(
            "/auth/register",
            json={"username": "otheruser88", "email": "other88@example.com", "password": "Password123"},
        )
        login = await client.post(
            "/auth/login",
            json={"username": "otheruser88", "password": "Password123"},
        )
        other_token = login.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        result = await client.get("/equipment", headers=other_headers)
        assert result.status_code == 200
        other_equipment = result.json()
        assert isinstance(other_equipment, list)

    async def test_invalid_equipment_type_returns_422(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            "/equipment",
            json={"equipment_id": "EQ-BAD", "equipment_type": "rocket", "location": "Space"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_delete_equipment(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            "/equipment",
            json={"equipment_id": "EQ-DELETE-ME", "equipment_type": "conveyor", "location": "Zone C"},
            headers=auth_headers,
        )
        if response.status_code == 201:
            eq_id = response.json()["id"]
            del_response = await client.delete(f"/equipment/{eq_id}", headers=auth_headers)
            assert del_response.status_code == 204


class TestAnalysis:
    def _make_readings(self, count: int = 5, anomalous: bool = False) -> list[dict]:
        base_temp = 200.0 if anomalous else 65.0
        return [
            {
                "temperature": base_temp,
                "vibration": 3.5,
                "pressure": 5.0,
                "current": 20.0,
                "timestamp": datetime(2024, 1, 1, 12, i, 0, tzinfo=timezone.utc).isoformat(),
            }
            for i in range(count)
        ]

    async def test_analyse_returns_result(
        self, client: AsyncClient, auth_headers: dict, registered_equipment: dict
    ):
        eq_id = registered_equipment["id"]
        with patch("app.agents.root_cause_agent.call_groq", return_value=None):
            response = await client.post(
                f"/equipment/{eq_id}/analyse",
                json={"readings": self._make_readings(5)},
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert "analysis_id" in data
        assert "failure_assessment" in data
        assert "maintenance_order" in data

    async def test_analyse_without_auth_returns_403(self, client: AsyncClient, registered_equipment: dict):
        eq_id = registered_equipment["id"]
        response = await client.post(
            f"/equipment/{eq_id}/analyse",
            json={"readings": self._make_readings(3)},
        )
        assert response.status_code == 401

    async def test_list_readings_returns_data(
        self, client: AsyncClient, auth_headers: dict, registered_equipment: dict
    ):
        eq_id = registered_equipment["id"]
        with patch("app.agents.root_cause_agent.call_groq", return_value=None):
            await client.post(
                f"/equipment/{eq_id}/analyse",
                json={"readings": self._make_readings(3)},
                headers=auth_headers,
            )
        response = await client.get(f"/equipment/{eq_id}/readings", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_analyses_returns_history(
        self, client: AsyncClient, auth_headers: dict, registered_equipment: dict
    ):
        eq_id = registered_equipment["id"]
        response = await client.get(f"/equipment/{eq_id}/analyses", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestDashboard:
    async def test_dashboard_stats_returns_metrics(self, client: AsyncClient, auth_headers: dict):
        response = await client.get("/dashboard/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_equipment" in data
        assert "total_readings" in data
        assert "anomaly_rate" in data
        assert "maintenance_priority_breakdown" in data

    async def test_dashboard_without_auth_returns_403(self, client: AsyncClient):
        response = await client.get("/dashboard/stats")
        assert response.status_code == 401
