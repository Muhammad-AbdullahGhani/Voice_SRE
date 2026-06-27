from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import uuid
import json
import asyncio
from langchain_core.messages import HumanMessage
from app.config import settings
from app.tools.kubernetes import get_pod_status, get_node_metrics, restart_pod, scale_deployment
from app.agents.supervisor import agent_graph

app = FastAPI(
    title=settings.APP_NAME,
    description="FastAPI Backend for Voice-Activated SRE Agent (Agentic Infrastructure Supervisor)",
    version="0.1.0"
)

class RestartPodRequest(BaseModel):
    name: str
    namespace: str = "production"

class ScaleDeploymentRequest(BaseModel):
    name: str
    replicas: int
    namespace: str = "production"

@app.get("/")
@app.get("/health")
def health_check():
    """
    Check the health of the FastAPI backend and connection status of dependencies.
    """
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "kubernetes": {
            "mode": "mock" if settings.KUBERNETES_USE_MOCK else "live"
        },
        "prometheus": {
            "url": settings.PROMETHEUS_URL
        }
    }

@app.get("/api/pods", response_model=List[Dict[str, Any]])
def read_pods(namespace: Optional[str] = Query(None, description="Filter pods by namespace")):
    """
    Retrieve the status and resource usage of pods.
    """
    try:
        pods = get_pod_status(namespace=namespace)
        return pods
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch pod status: {str(e)}")

@app.get("/api/nodes", response_model=List[Dict[str, Any]])
def read_nodes():
    """
    Retrieve the resource metrics and status of nodes.
    """
    try:
        nodes = get_node_metrics()
        return nodes
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch node metrics: {str(e)}")

@app.post("/api/pods/restart")
def api_restart_pod(req: RestartPodRequest):
    """
    Restart a specific pod.
    """
    res = restart_pod(name=req.name, namespace=req.namespace)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.post("/api/deployments/scale")
def api_scale_deployment(req: ScaleDeploymentRequest):
    """
    Scale a deployment to the specified replica count.
    """
    res = scale_deployment(name=req.name, replicas=req.replicas, namespace=req.namespace)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.get("/api/livekit/token")
def get_livekit_token(
    room: str = Query("sre-war-room", description="The room name to join"),
    identity: str = Query("sre-operator", description="Participant identity")
):
    """
    Generates a LiveKit JWT token for connecting to the real-time audio session.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        return {
            "token": "dummy-token-for-dev-use-only-no-keys-configured",
            "server_url": settings.LIVEKIT_API_URL or "ws://localhost:7880"
        }
        
    try:
        from livekit.api import AccessToken
        token = AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        token.add_grants(
            room_join=True,
            room=room,
            identity=identity,
            name=identity
        )
        return {
            "token": token.to_jwt(),
            "server_url": settings.LIVEKIT_API_URL or "ws://localhost:7880"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")

@app.websocket("/api/ws/agent")
async def websocket_agent_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time interaction. Streams LangGraph node transitions
    back to the client, providing the backend events needed for the 'War Room' visualization.
    """
    await websocket.accept()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                query_data = json.loads(data)
                user_query = query_data.get("query", "")
            except Exception:
                user_query = data
                
            if not user_query.strip():
                continue
                
            await websocket.send_json({"event": "listen", "content": user_query})
            
            initial_state = {"messages": [HumanMessage(content=user_query)]}
            
            # Execute agent_graph streaming node traversal asynchronously
            def run_stream():
                return list(agent_graph.stream(initial_state, config))
                
            events = await asyncio.to_thread(run_stream)
            
            for event in events:
                for node_name, node_output in event.items():
                    payload = {"event": "node_complete", "node": node_name}
                    
                    if node_name == "reason" and "messages" in node_output:
                        msg = node_output["messages"][0]
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            payload["detail"] = f"Executing tools: {[c['name'] for c in msg.tool_calls]}"
                        elif msg.content:
                            payload["detail"] = f"Reasoning finished: {msg.content}"
                    elif node_name == "tool_use" and "messages" in node_output:
                        payload["detail"] = "Tool execution completed."
                    elif node_name == "synthesize_response" and "voice_synthesis" in node_output:
                        payload["detail"] = "Voice synthesis prepared."
                        payload["result"] = node_output["voice_synthesis"]
                        
                    await websocket.send_json(payload)
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Avoid crashing the endpoint, just log or send error
        try:
            await websocket.send_json({"event": "error", "message": str(e)})
        except Exception:
            pass



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG
    )
