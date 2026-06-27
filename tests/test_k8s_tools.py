import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.tools.kubernetes import get_pod_status, get_node_metrics

client = TestClient(app)

def test_config_defaults():
    """Test that config defaults are loaded properly."""
    assert settings.APP_NAME == "Voice SRE Agentic Supervisor"
    assert settings.KUBERNETES_USE_MOCK is True  # Should default to True in this dev environment

def test_get_pod_status_mock():
    """Test get_pod_status returns data matching the mock format."""
    pods = get_pod_status()
    assert isinstance(pods, list)
    assert len(pods) > 0
    
    # Verify structure of pod details
    first_pod = pods[0]
    required_keys = {"name", "namespace", "status", "ready", "restarts", "ip", "cpu_usage", "memory_usage", "creation_timestamp"}
    assert required_keys.issubset(first_pod.keys())
    
    # Test filtering by namespace
    production_pods = get_pod_status(namespace="production")
    assert all(p["namespace"] == "production" for p in production_pods)

def test_get_node_metrics_mock():
    """Test get_node_metrics returns data matching the mock format."""
    nodes = get_node_metrics()
    assert isinstance(nodes, list)
    assert len(nodes) > 0
    
    # Verify structure of node metrics
    first_node = nodes[0]
    required_keys = {"name", "status", "cpu_usage", "memory_usage", "cpu_capacity", "memory_capacity", "cpu_allocatable", "memory_allocatable"}
    assert required_keys.issubset(first_node.keys())

def test_api_health():
    """Test the FastAPI health-check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["kubernetes"]["mode"] == "mock"

def test_api_get_pods():
    """Test API endpoint /api/pods."""
    response = client.get("/api/pods")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Test query param filtering
    response_filtered = client.get("/api/pods?namespace=production")
    assert response_filtered.status_code == 200
    data_filtered = response_filtered.json()
    assert all(p["namespace"] == "production" for p in data_filtered)

def test_api_get_nodes():
    """Test API endpoint /api/nodes."""
    response = client.get("/api/nodes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["name"] == "minikube"
