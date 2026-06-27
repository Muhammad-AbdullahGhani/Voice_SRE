import logging
import json
import re
from typing import TypedDict, List, Dict, Any, Union, Literal
from datetime import datetime, timezone

from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.tools.kubernetes import get_pod_status, get_node_metrics, restart_pod, scale_deployment

logger = logging.getLogger(__name__)

# --- LANGCHAIN TOOLS ---
@tool
def get_pods(namespace: str = None) -> str:
    """
    Retrieves the status of pods in the cluster. You can optionally filter by namespace (e.g., 'production').
    """
    pods = get_pod_status(namespace=namespace)
    return json.dumps(pods, indent=2)

@tool
def get_nodes() -> str:
    """
    Retrieves cluster node metrics, including status, capacity, allocatable resources, and usage.
    """
    nodes = get_node_metrics()
    return json.dumps(nodes, indent=2)

@tool
def restart_a_pod(name: str, namespace: str = "production") -> str:
    """
    Restarts a specific Kubernetes pod by deleting it. Returns success status.
    """
    result = restart_pod(name=name, namespace=namespace)
    return json.dumps(result, indent=2)

@tool
def scale_a_deployment(name: str, replicas: int, namespace: str = "production") -> str:
    """
    Scales a Kubernetes deployment to the specified number of replicas. Returns success status.
    """
    result = scale_deployment(name=name, replicas=replicas, namespace=namespace)
    return json.dumps(result, indent=2)

# Tool mapping list for mock reasoning & tool execution
TOOLS = {
    "get_pods": get_pods,
    "get_nodes": get_nodes,
    "restart_a_pod": restart_a_pod,
    "scale_a_deployment": scale_a_deployment
}

# --- STATE DEFINITION ---
class AgentState(TypedDict):
    messages: List[BaseMessage]
    voice_synthesis: str  # Prepares output text for TTS engine in future phases


# --- NODE FUNCTIONS ---

def listen_node(state: AgentState) -> Dict[str, Any]:
    """
    [Listen Node] Represents the front-end speech capture (STT).
    In this text-based phase, it logs that it received user input.
    """
    last_msg = state["messages"][-1] if state["messages"] else "No input"
    logger.info(f"[Node: Listen] Audio transport transcript received: '{last_msg.content if hasattr(last_msg, 'content') else last_msg}'")
    return {}


def reason_node(state: AgentState) -> Dict[str, Any]:
    """
    [Reason Node] LLM determines next action: execute tools or synthesize response.
    Supports both ChatOpenAI (if key is set) and a smart Mock LLM fallback.
    """
    logger.info("[Node: Reason] SRE Supervisor evaluating cluster context...")
    
    # If API key is set, use OpenAI LLM
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.strip() != "":
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            llm_with_tools = llm.bind_tools(list(TOOLS.values()))
            response = llm_with_tools.invoke(state["messages"])
            return {"messages": [response]}
        except Exception as e:
            logger.error(f"Error invoking ChatOpenAI: {e}. Falling back to Mock LLM reasoning.")
            
    # Mock LLM Fallback (Regular Expressions & Rules)
    messages = state["messages"]
    
    # Get the latest human message
    user_query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
            
    # If the last message was a ToolMessage, we can formulate our final synthesized response
    if messages and isinstance(messages[-1], ToolMessage):
        # We need to answer the user query based on tool output
        tool_msg = messages[-1]
        try:
            tool_data = json.loads(tool_msg.content)
        except Exception:
            tool_data = tool_msg.content
            
        ai_response_content = ""
        if tool_msg.name == "get_pods":
            running_pods = sum(1 for p in tool_data if p["status"] == "Running")
            crashing_pods = [p for p in tool_data if p["status"] == "CrashLoopBackOff"]
            ai_response_content = f"The cluster has {len(tool_data)} pods in total. {running_pods} are currently Running."
            if crashing_pods:
                c_pod = crashing_pods[0]
                ai_response_content += f" Warning: the pod '{c_pod['name']}' in namespace '{c_pod['namespace']}' is in CrashLoopBackOff with {c_pod['restarts']} restarts."
        elif tool_msg.name == "get_nodes":
            node_name = tool_data[0]["name"] if tool_data else "unknown"
            node_cpu = tool_data[0]["cpu_usage"] if tool_data else "N/A"
            node_mem = tool_data[0]["memory_usage"] if tool_data else "N/A"
            ai_response_content = f"Cluster node '{node_name}' is Ready. Current resource usage: CPU is at {node_cpu} and Memory is at {node_mem}."
        elif tool_msg.name == "restart_a_pod":
            if isinstance(tool_data, dict) and tool_data.get("success"):
                ai_response_content = f"Done. I have successfully triggered a restart for that pod. It should be spin up shortly."
            else:
                ai_response_content = f"Error: I could not restart the pod. {tool_data.get('message', '') if isinstance(tool_data, dict) else tool_data}"
        elif tool_msg.name == "scale_a_deployment":
            if isinstance(tool_data, dict) and tool_data.get("success"):
                ai_response_content = f"Done. The deployment scale operation has completed successfully. New target replica count is {tool_data.get('replicas')}."
            else:
                ai_response_content = f"Error: Scaling operation failed. {tool_data.get('message', '') if isinstance(tool_data, dict) else tool_data}"
        else:
            ai_response_content = f"I processed the tool output: {tool_data}"
            
        return {"messages": [AIMessage(content=ai_response_content)]}
    
    # Process user query and issue tool calls
    user_query_lower = user_query.lower()
    
    # 1. Scaling Deployment
    scale_match = re.search(r"scale\s+([a-zA-Z0-9\-_]+)\s+(?:deployment\s+)?to\s+(\d+)", user_query_lower)
    if not scale_match:
        scale_match = re.search(r"set\s+replicas\s+(?:of\s+)?([a-zA-Z0-9\-_]+)\s+to\s+(\d+)", user_query_lower)
        
    if scale_match:
        dep_name = scale_match.group(1)
        replicas = int(scale_match.group(2))
        tool_call = {
            "name": "scale_a_deployment",
            "args": {"name": dep_name, "replicas": replicas, "namespace": "production"},
            "id": "call_scale_" + datetime.now(timezone.utc).strftime("%f")
        }
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        return {"messages": [ai_msg]}

    # 2. Restarting Pod
    restart_match = re.search(r"restart\s+(?:pod\s+)?([a-zA-Z0-9\-_]+)", user_query_lower)
    if restart_match:
        pod_name = restart_match.group(1)
        # Find if it exists in mock pods or just use production
        namespace = "production"
        if "kube-system" in user_query_lower or "dns" in pod_name:
            namespace = "kube-system"
        tool_call = {
            "name": "restart_a_pod",
            "args": {"name": pod_name, "namespace": namespace},
            "id": "call_restart_" + datetime.now(timezone.utc).strftime("%f")
        }
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        return {"messages": [ai_msg]}

    # 3. Pod Status Query
    if any(keyword in user_query_lower for keyword in ["pod", "pods", "status", "payment", "auth"]):
        ns = "production"
        if "all namespace" in user_query_lower or "every namespace" in user_query_lower:
            ns = None
        elif "kube-system" in user_query_lower:
            ns = "kube-system"
            
        tool_call = {
            "name": "get_pods",
            "args": {"namespace": ns},
            "id": "call_pods_" + datetime.now(timezone.utc).strftime("%f")
        }
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        return {"messages": [ai_msg]}

    # 4. Node Status/Metrics Query
    if any(keyword in user_query_lower for keyword in ["node", "nodes", "metrics", "cluster health", "cpu usage", "memory usage"]):
        tool_call = {
            "name": "get_nodes",
            "args": {},
            "id": "call_nodes_" + datetime.now(timezone.utc).strftime("%f")
        }
        ai_msg = AIMessage(content="", tool_calls=[tool_call])
        return {"messages": [ai_msg]}

    # Default direct response
    direct_reply = "Hello! I am your Voice SRE Supervisor. I can help you monitor and troubleshoot Kubernetes cluster issues. You can ask me to list pods, show node metrics, restart a crashing pod, or scale a deployment."
    return {"messages": [AIMessage(content=direct_reply)]}


def tool_use_node(state: AgentState) -> Dict[str, Any]:
    """
    [Tool Use Node] Invokes the tool requested by the reason node and appends the result to message history.
    """
    last_msg = state["messages"][-1]
    tool_calls = last_msg.tool_calls if hasattr(last_msg, "tool_calls") else []
    
    results = []
    for call in tool_calls:
        tool_name = call["name"]
        tool_args = call["args"]
        call_id = call["id"]
        
        logger.info(f"[Node: Tool Use] Executing tool '{tool_name}' with args {tool_args}")
        
        if tool_name in TOOLS:
            try:
                # Call tool function directly
                output = TOOLS[tool_name].invoke(tool_args)
            except Exception as e:
                output = json.dumps({"success": False, "message": str(e)})
        else:
            output = f"Error: Tool '{tool_name}' not found."
            
        results.append(ToolMessage(content=output, name=tool_name, tool_call_id=call_id))
        
    return {"messages": results}


def synthesize_response_node(state: AgentState) -> Dict[str, Any]:
    """
    [Synthesize Response Node] Converts the final textual agent answer into the synthesized output field.
    In real-time audio phase, this triggers the TTS output generator.
    """
    last_msg = state["messages"][-1]
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    logger.info(f"[Node: Synthesize] Output text prepared for TTS: '{content}'")
    return {"voice_synthesis": content}


# --- CONDITIONAL ROUTING EDGE ---

def should_continue(state: AgentState) -> Literal["continue", "end"]:
    """
    Evaluates the last message to decide if we need tool execution or final synthesis.
    """
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "continue"
    return "end"


# --- WORKFLOW COMPILATION ---

def build_agent_graph() -> StateGraph:
    """
    Builds and compiles the SRE LangGraph supervisor agent with built-in memory state checks.
    """
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("listen", listen_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("tool_use", tool_use_node)
    workflow.add_node("synthesize_response", synthesize_response_node)

    # Set entrypoint
    workflow.set_entry_point("listen")

    # Add edges
    workflow.add_conditional_edges(
        "reason",
        should_continue,
        {
            "continue": "tool_use",
            "end": "synthesize_response"
        }
    )
    workflow.add_edge("listen", "reason")
    workflow.add_edge("tool_use", "reason")
    workflow.add_edge("synthesize_response", END)

    # Add checkpointer memory
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)

# Shared graph instance
agent_graph = build_agent_graph()
