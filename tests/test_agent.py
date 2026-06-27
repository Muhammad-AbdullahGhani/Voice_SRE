import pytest
import uuid
from langchain_core.messages import HumanMessage
from app.agents.supervisor import agent_graph

def test_agent_graph_compilation():
    """Verify that the supervisor graph compiles successfully and contains the correct nodes."""
    assert agent_graph is not None
    # Check if the expected nodes are present in the graph structure
    node_names = list(agent_graph.nodes.keys())
    assert "listen" in node_names
    assert "reason" in node_names
    assert "tool_use" in node_names
    assert "synthesize_response" in node_names

def test_agent_pod_query():
    """Verify that querying the agent about pods triggers get_pods and returns mock pod details."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Run the graph
    inputs = {"messages": [HumanMessage(content="Check the status of the pods in the cluster")]}
    output = agent_graph.invoke(inputs, config)
    
    # Verify traversal ended in voice synthesis
    assert "voice_synthesis" in output
    voice_resp = output["voice_synthesis"]
    assert "pods" in voice_resp.lower()
    # Check that it identifies the crashing auth-service
    assert "auth-service" in voice_resp.lower() or "production" in voice_resp.lower()

def test_agent_node_query():
    """Verify that querying the agent about node metrics triggers get_nodes and returns status."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    inputs = {"messages": [HumanMessage(content="What are the node metrics looking like?")]}
    output = agent_graph.invoke(inputs, config)
    
    assert "voice_synthesis" in output
    voice_resp = output["voice_synthesis"]
    # Check if the node name or metrics are mentioned
    assert "minikube" in voice_resp.lower() or "ready" in voice_resp.lower()

def test_agent_multi_turn_scale_memory():
    """Test memory and multi-turn scaling capabilities of the agent."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Step 1: Query the pods in production
    inputs1 = {"messages": [HumanMessage(content="List the pods in production namespace")]}
    output1 = agent_graph.invoke(inputs1, config)
    
    # Count how many payment-gateway pods exist originally (should be 3 in MOCK_PODS)
    resp1 = output1["voice_synthesis"].lower()
    assert "production" in resp1 or "pods" in resp1

    # Step 2: Scale the deployment payment-gateway to 5
    inputs2 = {"messages": [HumanMessage(content="Scale payment-gateway to 5")]}
    output2 = agent_graph.invoke(inputs2, config)
    assert "completed successfully" in output2["voice_synthesis"].lower() or "5" in output2["voice_synthesis"]

    # Step 3: Query pods again, verifying the count increased to 5 payment-gateway pods
    inputs3 = {"messages": [HumanMessage(content="Show me all production pods again")]}
    output3 = agent_graph.invoke(inputs3, config)
    resp3 = output3["voice_synthesis"]
    # Verify that the memory and execution has updated the in-memory mock pods state
    from app.tools.kubernetes import get_pod_status
    current_pods = get_pod_status(namespace="production")
    pg_pods = [p for p in current_pods if p["name"].startswith("payment-gateway")]
    assert len(pg_pods) == 5

def test_agent_restart_pod():
    """Verify that asking the agent to restart a pod executes the restart tool."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Check initial restarts of auth-service
    from app.tools.kubernetes import get_pod_status
    initial_pods = get_pod_status(namespace="production")
    auth_pod = next(p for p in initial_pods if p["name"].startswith("auth-service"))
    initial_restarts = auth_pod["restarts"]
    
    # Ask the agent to restart it
    inputs = {"messages": [HumanMessage(content=f"Please restart pod {auth_pod['name']}")]}
    output = agent_graph.invoke(inputs, config)
    
    assert "restarted successfully" in output["voice_synthesis"].lower() or "triggered" in output["voice_synthesis"].lower()
    
    # Verify restart count incremented in tools state
    updated_pods = get_pod_status(namespace="production")
    auth_pod_updated = next(p for p in updated_pods if p["name"] == auth_pod["name"])
    assert auth_pod_updated["restarts"] == initial_restarts + 1


def test_livekit_token_endpoint():
    """Verify the LiveKit token API route returns the dummy/real token payload."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    response = client.get("/api/livekit/token?room=test-room&identity=test-user")
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "server_url" in data


def test_websocket_agent_streaming():
    """Test the WebSocket endpoint's capability to traverse and stream LangGraph nodes."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    
    with client.websocket_connect("/api/ws/agent") as websocket:
        websocket.send_text("List pods in production")
        
        events_received = []
        try:
            # We read events until we get the synthesize_response node completion
            for _ in range(10):
                resp = websocket.receive_json()
                events_received.append(resp)
                if resp.get("event") == "node_complete" and resp.get("node") == "synthesize_response":
                    break
        except Exception as e:
            pytest.fail(f"WebSocket connection failed or timed out: {e}")
            
        assert len(events_received) > 0
        listen_events = [e for e in events_received if e.get("event") == "listen"]
        assert len(listen_events) == 1
        assert listen_events[0]["content"] == "List pods in production"
        
        nodes_completed = [e.get("node") for e in events_received if e.get("event") == "node_complete"]
        assert "listen" in nodes_completed
        assert "reason" in nodes_completed
        assert "synthesize_response" in nodes_completed

