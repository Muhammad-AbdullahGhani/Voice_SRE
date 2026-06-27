import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Kubernetes API clients if not running in mock mode
_core_api = None
_custom_api = None
_apps_api = None
_initialized = False

def _init_k8s_clients():
    global _core_api, _custom_api, _apps_api, _initialized
    if _initialized:
        return
    
    if settings.KUBERNETES_USE_MOCK:
        logger.info("Kubernetes tool initialized in MOCK mode.")
        _initialized = True
        return

    try:
        from kubernetes import client, config
        try:
            config.load_kube_config()
            logger.info("Loaded kube-config successfully.")
        except Exception as e_kube:
            logger.warning(f"Failed to load local kubeconfig: {e_kube}. Trying in-cluster config...")
            try:
                config.load_incluster_config()
                logger.info("Loaded in-cluster config successfully.")
            except Exception as e_in:
                logger.error(f"Failed to load in-cluster config: {e_in}. Falling back to MOCK mode.")
                settings.KUBERNETES_USE_MOCK = True
                _initialized = True
                return
                
        _core_api = client.CoreV1Api()
        _custom_api = client.CustomObjectsApi()
        _apps_api = client.AppsV1Api()
        _initialized = True
    except Exception as e:
        logger.error(f"Error importing or initializing kubernetes client: {e}. Falling back to MOCK mode.")
        settings.KUBERNETES_USE_MOCK = True
        _initialized = True

# --- MOCK DATA ---
MOCK_PODS = [
    {
        "name": "payment-gateway-7f8c9b8d-abc12",
        "namespace": "production",
        "status": "Running",
        "ready": "1/1",
        "restarts": 0,
        "ip": "10.244.1.15",
        "cpu_usage": "340m",
        "memory_usage": "256Mi",
        "creation_timestamp": "2026-06-25T10:00:00Z"
    },
    {
        "name": "payment-gateway-7f8c9b8d-def34",
        "namespace": "production",
        "status": "Running",
        "ready": "1/1",
        "restarts": 0,
        "ip": "10.244.2.20",
        "cpu_usage": "850m",  # High CPU! Fits the scenario in the blueprint
        "memory_usage": "512Mi",
        "creation_timestamp": "2026-06-25T10:05:00Z"
    },
    {
        "name": "payment-gateway-7f8c9b8d-ghi56",
        "namespace": "production",
        "status": "Running",
        "ready": "1/1",
        "restarts": 2,
        "ip": "10.244.3.5",
        "cpu_usage": "120m",
        "memory_usage": "210Mi",
        "creation_timestamp": "2026-06-25T10:10:00Z"
    },
    {
        "name": "recommendation-service-5c6d7e8f-xyz98",
        "namespace": "production",
        "status": "Running",
        "ready": "1/1",
        "restarts": 0,
        "ip": "10.244.1.16",
        "cpu_usage": "45m",
        "memory_usage": "180Mi",
        "creation_timestamp": "2026-06-25T11:20:00Z"
    },
    {
        "name": "db-postgres-0",
        "namespace": "production",
        "status": "Running",
        "ready": "1/1",
        "restarts": 0,
        "ip": "10.244.2.4",
        "cpu_usage": "150m",
        "memory_usage": "1024Mi",
        "creation_timestamp": "2026-06-24T08:00:00Z"
    },
    {
        "name": "auth-service-9d8e7f6c-12345",
        "namespace": "production",
        "status": "CrashLoopBackOff",
        "ready": "0/1",
        "restarts": 14,
        "ip": "10.244.3.12",
        "cpu_usage": "0m",
        "memory_usage": "0Mi",
        "creation_timestamp": "2026-06-26T22:15:00Z"
    },
    {
        "name": "coredns-55cb58b774-abcde",
        "namespace": "kube-system",
        "status": "Running",
        "ready": "1/1",
        "restarts": 1,
        "ip": "10.244.0.2",
        "cpu_usage": "12m",
        "memory_usage": "32Mi",
        "creation_timestamp": "2026-06-23T00:01:00Z"
    }
]

MOCK_NODES = [
    {
        "name": "minikube",
        "status": "Ready",
        "cpu_usage": "1.52 Cores (38%)",
        "memory_usage": "4.2 GiB (52.5%)",
        "cpu_capacity": "4",
        "memory_capacity": "8Gi",
        "cpu_allocatable": "4",
        "memory_allocatable": "7.8Gi"
    }
]


def get_pod_status(namespace: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the status of pods in a specified namespace, or all namespaces if None is provided.
    Includes pod name, namespace, status, ready state, restart count, IP, resource usage, and creation time.

    Args:
        namespace (str, optional): The namespace to query. Defaults to None (all namespaces).

    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing pod status details.
    """
    _init_k8s_clients()

    if settings.KUBERNETES_USE_MOCK:
        logger.debug(f"Fetching mock pod status for namespace: {namespace}")
        if namespace:
            return [p for p in MOCK_PODS if p["namespace"] == namespace]
        return MOCK_PODS

    try:
        # Fetch live data using kubernetes client
        # CoreV1Api: list_pod_for_all_namespaces or list_namespaced_pod
        if namespace:
            pod_list = _core_api.list_namespaced_pod(namespace=namespace)
        else:
            pod_list = _core_api.list_pod_for_all_namespaces()

        # Try to fetch metrics if metrics server is available
        pod_metrics_dict = {}
        try:
            # Custom API query to metrics.k8s.io
            metrics_list = _custom_api.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="pods"
            )
            for item in metrics_list.get("items", []):
                p_name = item["metadata"]["name"]
                p_ns = item["metadata"]["namespace"]
                
                # Sum CPU and Memory of containers inside the pod
                total_cpu_nano = 0
                total_mem_ki = 0
                for container in item.get("containers", []):
                    cpu_str = container.get("usage", {}).get("cpu", "0")
                    mem_str = container.get("usage", {}).get("memory", "0")
                    
                    # Parse CPU (e.g. 100n, 250u, 10m, 1)
                    if cpu_str.endswith("n"):
                        total_cpu_nano += int(cpu_str[:-1])
                    elif cpu_str.endswith("u"):
                        total_cpu_nano += int(cpu_str[:-1]) * 1000
                    elif cpu_str.endswith("m"):
                        total_cpu_nano += int(cpu_str[:-1]) * 1000000
                    elif cpu_str.isdigit():
                        total_cpu_nano += int(cpu_str) * 1000000000
                        
                    # Parse Memory (e.g. 256Ki, 512Mi, 1Gi)
                    if mem_str.endswith("Ki"):
                        total_mem_ki += int(mem_str[:-2])
                    elif mem_str.endswith("Mi"):
                        total_mem_ki += int(mem_str[:-2]) * 1024
                    elif mem_str.endswith("Gi"):
                        total_mem_ki += int(mem_str[:-2]) * 1024 * 1024
                    elif mem_str.isdigit():
                        total_mem_ki += int(mem_str) // 1024
                        
                cpu_usage_m = f"{int(total_cpu_nano / 1000000)}m"
                mem_usage_mi = f"{int(total_mem_ki / 1024)}Mi"
                pod_metrics_dict[(p_ns, p_name)] = {
                    "cpu_usage": cpu_usage_m,
                    "memory_usage": mem_usage_mi
                }
        except Exception as e_metrics:
            logger.debug(f"Metrics server not accessible or returned error: {e_metrics}")

        results = []
        for pod in pod_list.items:
            p_name = pod.metadata.name
            p_ns = pod.metadata.namespace
            
            # Calculate container readiness
            container_statuses = pod.status.container_statuses or []
            total_containers = len(container_statuses)
            ready_containers = sum(1 for c in container_statuses if c.ready)
            ready_str = f"{ready_containers}/{total_containers}"
            
            # Restart count
            restarts = sum(c.restart_count for c in container_statuses)
            
            # CPU/Memory Metrics
            metrics = pod_metrics_dict.get((p_ns, p_name), {"cpu_usage": "N/A", "memory_usage": "N/A"})
            
            results.append({
                "name": p_name,
                "namespace": p_ns,
                "status": pod.status.phase,
                "ready": ready_str,
                "restarts": restarts,
                "ip": pod.status.pod_ip or "N/A",
                "cpu_usage": metrics["cpu_usage"],
                "memory_usage": metrics["memory_usage"],
                "creation_timestamp": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else "N/A"
            })
        return results

    except Exception as e:
        logger.error(f"Error fetching pod status: {e}. Returning mock fallback data.")
        # Fallback to mock data on errors
        if namespace:
            return [p for p in MOCK_PODS if p["namespace"] == namespace]
        return MOCK_PODS


def get_node_metrics() -> List[Dict[str, Any]]:
    """
    Retrieves the status, capacity, and resource metrics of the nodes in the cluster.
    Includes node name, ready status, CPU/Memory usage, capacity, and allocatable resources.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing node metrics and status.
    """
    _init_k8s_clients()

    if settings.KUBERNETES_USE_MOCK:
        logger.debug("Fetching mock node metrics")
        return MOCK_NODES

    try:
        # Fetch nodes
        nodes = _core_api.list_node()
        
        # Try to fetch metrics
        node_metrics_dict = {}
        try:
            metrics_list = _custom_api.list_cluster_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes"
            )
            for item in metrics_list.get("items", []):
                n_name = item["metadata"]["name"]
                cpu_str = item.get("usage", {}).get("cpu", "0")
                mem_str = item.get("usage", {}).get("memory", "0")
                
                # Parse CPU
                cpu_cores = 0.0
                if cpu_str.endswith("n"):
                    cpu_cores = int(cpu_str[:-1]) / 1000000000.0
                elif cpu_str.endswith("u"):
                    cpu_cores = int(cpu_str[:-1]) / 1000000.0
                elif cpu_str.endswith("m"):
                    cpu_cores = int(cpu_str[:-1]) / 1000.0
                elif cpu_str.isdigit():
                    cpu_cores = float(cpu_str)
                
                # Parse Memory
                mem_gib = 0.0
                if mem_str.endswith("Ki"):
                    mem_gib = int(mem_str[:-2]) / (1024.0 * 1024.0)
                elif mem_str.endswith("Mi"):
                    mem_gib = int(mem_str[:-2]) / 1024.0
                elif mem_str.endswith("Gi"):
                    mem_gib = float(mem_str[:-2])
                elif mem_str.isdigit():
                    mem_gib = float(mem_str) / (1024.0 * 1024.0 * 1024.0)

                node_metrics_dict[n_name] = {
                    "cpu_cores": cpu_cores,
                    "mem_gib": mem_gib
                }
        except Exception as e_metrics:
            logger.debug(f"Metrics server not accessible for nodes: {e_metrics}")

        results = []
        for node in nodes.items:
            n_name = node.metadata.name
            
            # Find status (Ready/NotReady)
            status = "Unknown"
            for condition in node.status.conditions:
                if condition.type == "Ready":
                    status = "Ready" if condition.status == "True" else "NotReady"
                    break
            
            # Capacity and Allocatable
            cpu_cap = node.status.capacity.get("cpu", "N/A")
            mem_cap = node.status.capacity.get("memory", "N/A")
            cpu_alloc = node.status.allocatable.get("cpu", "N/A")
            mem_alloc = node.status.allocatable.get("memory", "N/A")
            
            # Construct human readable usage percentages if metrics are available
            cpu_usage_str = "N/A"
            mem_usage_str = "N/A"
            if n_name in node_metrics_dict:
                metrics = node_metrics_dict[n_name]
                try:
                    # Clean up CPU capacity to int for calculation
                    cap_cpu_cores = int(cpu_cap) if cpu_cap.isdigit() else 1.0
                    cpu_pct = (metrics["cpu_cores"] / cap_cpu_cores) * 100
                    cpu_usage_str = f"{metrics['cpu_cores']:.2f} Cores ({cpu_pct:.1f}%)"
                except Exception:
                    cpu_usage_str = f"{metrics['cpu_cores']:.2f} Cores"
                
                try:
                    # Parse capacity memory to bytes/GiB
                    cap_mem_bytes = 0
                    if mem_cap.endswith("Ki"):
                        cap_mem_bytes = int(mem_cap[:-2]) * 1024
                    elif mem_cap.endswith("Mi"):
                        cap_mem_bytes = int(mem_cap[:-2]) * 1024 * 1024
                    elif mem_cap.endswith("Gi"):
                        cap_mem_bytes = int(mem_cap[:-2]) * 1024 * 1024 * 1024
                    elif mem_cap.endswith("Ki"):
                        cap_mem_bytes = int(mem_cap[:-2]) * 1024
                    else:
                        cap_mem_bytes = int(mem_cap)
                    
                    cap_mem_gib = cap_mem_bytes / (1024 * 1024 * 1024)
                    mem_pct = (metrics["mem_gib"] / cap_mem_gib) * 100
                    mem_usage_str = f"{metrics['mem_gib']:.2f} GiB ({mem_pct:.1f}%)"
                except Exception:
                    mem_usage_str = f"{metrics['mem_gib']:.2f} GiB"

            results.append({
                "name": n_name,
                "status": status,
                "cpu_usage": cpu_usage_str,
                "memory_usage": mem_usage_str,
                "cpu_capacity": cpu_cap,
                "memory_capacity": mem_cap,
                "cpu_allocatable": cpu_alloc,
                "memory_allocatable": mem_alloc
            })
        return results

    except Exception as e:
        logger.error(f"Error fetching node metrics: {e}. Returning mock fallback data.")
        return MOCK_NODES


def restart_pod(name: str, namespace: str = "production") -> Dict[str, Any]:
    """
    Restarts a pod by deleting it. The Kubernetes controller manager will recreate the replica.
    For mock environments, it simulates a restart by incrementing the restart count and resetting status.
    """
    _init_k8s_clients()

    if settings.KUBERNETES_USE_MOCK:
        logger.info(f"Mock restarting pod: {name} in namespace {namespace}")
        for pod in MOCK_PODS:
            if pod["name"] == name and pod["namespace"] == namespace:
                pod["restarts"] += 1
                pod["status"] = "Running"
                pod["ready"] = "1/1"
                pod["creation_timestamp"] = datetime.now(timezone.utc).isoformat() + "Z"
                return {
                    "success": True,
                    "message": f"Pod {name} restarted successfully (mocked). Restart count is now {pod['restarts']}.",
                    "pod": pod
                }
        return {
            "success": False,
            "message": f"Pod {name} not found in namespace {namespace} (mocked)."
        }

    try:
        _core_api.delete_namespaced_pod(name=name, namespace=namespace)
        return {
            "success": True,
            "message": f"Pod {name} in namespace {namespace} has been deleted and should restart shortly."
        }
    except Exception as e:
        logger.error(f"Error restarting pod {name}: {e}")
        return {
            "success": False,
            "message": f"Failed to restart pod {name}: {str(e)}"
        }


def scale_deployment(name: str, replicas: int, namespace: str = "production") -> Dict[str, Any]:
    """
    Scales a deployment to a new number of replicas.
    For mock environments, it adds or removes matching pods dynamically in our mock list.
    """
    _init_k8s_clients()

    if settings.KUBERNETES_USE_MOCK:
        logger.info(f"Mock scaling deployment {name} to {replicas} replicas in namespace {namespace}")
        existing_pods = [p for p in MOCK_PODS if p["name"].startswith(name) and p["namespace"] == namespace]
        current_count = len(existing_pods)

        if current_count == replicas:
            return {
                "success": True,
                "message": f"Deployment {name} is already at {replicas} replicas (mocked).",
                "replicas": replicas
            }
        
        if current_count < replicas:
            import random
            import string
            num_to_add = replicas - current_count
            for _ in range(num_to_add):
                suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
                new_pod = {
                    "name": f"{name}-7f8c9b8d-{suffix}",
                    "namespace": namespace,
                    "status": "Running",
                    "ready": "1/1",
                    "restarts": 0,
                    "ip": f"10.244.1.{100 + len(MOCK_PODS)}",
                    "cpu_usage": "150m",
                    "memory_usage": "256Mi",
                    "creation_timestamp": datetime.now(timezone.utc).isoformat() + "Z"
                }
                MOCK_PODS.append(new_pod)
        else:
            num_to_remove = current_count - replicas
            removed_count = 0
            for pod in list(reversed(MOCK_PODS)):
                if pod["name"].startswith(name) and pod["namespace"] == namespace:
                    MOCK_PODS.remove(pod)
                    removed_count += 1
                    if removed_count == num_to_remove:
                        break
        
        return {
            "success": True,
            "message": f"Scaled deployment {name} to {replicas} replicas successfully (mocked).",
            "replicas": replicas
        }

    try:
        body = {"spec": {"replicas": replicas}}
        _apps_api.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
        return {
            "success": True,
            "message": f"Scaled deployment {name} to {replicas} replicas successfully."
        }
    except Exception as e:
        logger.error(f"Error scaling deployment {name}: {e}")
        return {
            "success": False,
            "message": f"Failed to scale deployment {name}: {str(e)}"
        }

