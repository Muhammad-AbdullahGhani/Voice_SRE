import sys
import os
import uuid
import logging
from langchain_core.messages import HumanMessage
from app.agents.supervisor import agent_graph

# Configure logging to show graph transitions nicely
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Suppress verbose standard logs from other libraries to keep CLI clean
logging.getLogger("httpx").setLevel(logging.WARNING)

def run_cli():
    print("=" * 60)
    print(" Voice SRE Supervisor Agent CLI (Phase 2 - LangGraph)")
    print("=" * 60)
    print("Type your command to the supervisor (e.g. 'check pods', 'restart payment-gateway-7f8c9b8d-def34', 'scale payment-gateway to 5').")
    print("Type 'exit' or 'quit' to end the session.\n")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            user_input = input("SRE User > ")
            if not user_input.strip():
                continue
            if user_input.strip().lower() in ["exit", "quit"]:
                print("Exiting SRE Supervisor. Goodbye!")
                break

            print("\n--- Agent Execution Start ---")
            
            # Prepare state dict
            initial_state = {
                "messages": [HumanMessage(content=user_input)]
            }

            # Run graph with streaming to print node transitions
            for event in agent_graph.stream(initial_state, config):
                # The event dict contains keys corresponding to the active nodes
                for node_name, node_output in event.items():
                    print(f"\n>>> [Completed Node: {node_name.upper()}]")
                    # If it's a reason node with tool calls, print them
                    if node_name == "reason" and "messages" in node_output:
                        msg = node_output["messages"][0]
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            print(f"    Action: Wants to call tools: {[c['name'] for c in msg.tool_calls]}")
                        elif msg.content:
                            print(f"    Response: {msg.content}")
                    elif node_name == "tool_use" and "messages" in node_output:
                        for tool_msg in node_output["messages"]:
                            print(f"    Tool Return ({tool_msg.name}): Output length is {len(tool_msg.content)} chars.")
                    elif node_name == "synthesize_response" and "voice_synthesis" in node_output:
                        print(f"    Final Voice Synthesis: {node_output['voice_synthesis']}")
                
            print("--- Agent Execution End ---\n")

        except KeyboardInterrupt:
            print("\nExiting SRE Supervisor. Goodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}\n")

if __name__ == "__main__":
    # Ensure current directory is in Python path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    run_cli()
