"use client";

import { useState, useEffect, useRef } from "react";

interface Pod {
  name: string;
  namespace: string;
  status: string;
  ready: string;
  restarts: number;
  ip: string;
  cpu_usage: string;
  memory_usage: string;
  creation_timestamp: string;
}

interface NodeMetrics {
  name: string;
  status: string;
  cpu_usage: string;
  memory_usage: string;
  cpu_capacity: string;
  memory_capacity: string;
  cpu_allocatable: string;
  memory_allocatable: string;
}

interface TerminalLog {
  timestamp: string;
  node: string;
  message: string;
  type: "info" | "success" | "warning" | "error" | "action";
}

export default function Home() {
  const [pods, setPods] = useState<Pod[]>([]);
  const [nodes, setNodes] = useState<NodeMetrics[]>([]);
  const [terminalLogs, setTerminalLogs] = useState<TerminalLog[]>([]);
  const [inputText, setInputText] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [currentStep, setCurrentStep] = useState<"idle" | "listening" | "reasoning" | "executing" | "synthesizing">("idle");
  const [voiceSynthesisText, setVoiceSynthesisText] = useState("");
  
  // Dialog state for scaling
  const [scalingPod, setScalingPod] = useState<Pod | null>(null);
  const [targetReplicas, setTargetReplicas] = useState(3);
  
  // WebSocket reference
  const socketRef = useRef<WebSocket | null>(null);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);

  // Poll backend telemetry every 3 seconds
  useEffect(() => {
    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 3000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll terminal logs to bottom
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [terminalLogs]);

  // Connect to WebSocket on load
  useEffect(() => {
    connectWebSocket();
    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, []);

  const fetchTelemetry = async () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      
      const podsRes = await fetch(`${backendUrl}/api/pods`);
      if (podsRes.ok) {
        const podsData = await podsRes.json();
        setPods(podsData);
      }

      const nodesRes = await fetch(`${backendUrl}/api/nodes`);
      if (nodesRes.ok) {
        const nodesData = await nodesRes.json();
        setNodes(nodesData);
      }
      setIsConnected(true);
    } catch (err) {
      console.error("Failed to fetch telemetry:", err);
      setIsConnected(false);
    }
  };

  const connectWebSocket = () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      // Convert http/https to ws/wss
      const wsUrl = backendUrl.replace(/^http/, "ws") + "/api/ws/agent";
      
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        addLog("SYSTEM", "Connected to SRE Agent real-time visualizer WebSocket.", "success");
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleAgentEvent(data);
      };

      ws.onclose = () => {
        addLog("SYSTEM", "WebSocket disconnected. Reconnecting in 5s...", "warning");
        setTimeout(connectWebSocket, 5000);
      };
    } catch (err) {
      console.error("WebSocket connection error:", err);
    }
  };

  const handleAgentEvent = (data: any) => {
    const timeStr = new Date().toLocaleTimeString();
    
    if (data.event === "listen") {
      setCurrentStep("listening");
      addLog("LISTEN", `Listening: "${data.content}"`, "info");
    } else if (data.event === "node_complete") {
      const node = data.node;
      const detail = data.detail || "";
      
      if (node === "listen") {
        setCurrentStep("reasoning");
      } else if (node === "reason") {
        if (detail.includes("Executing tools")) {
          setCurrentStep("executing");
          addLog("REASON", detail, "action");
        } else {
          setCurrentStep("synthesizing");
          addLog("REASON", detail, "info");
        }
      } else if (node === "tool_use") {
        setCurrentStep("reasoning");
        addLog("TOOL_USE", detail, "success");
        // Trigger immediate fetch to show updated mock state
        fetchTelemetry();
      } else if (node === "synthesize_response") {
        setCurrentStep("idle");
        addLog("SYNTHESIZE", `Preparing TTS: "${data.result}"`, "success");
        setVoiceSynthesisText(data.result);
        speakText(data.result);
      }
    } else if (data.event === "error") {
      setCurrentStep("idle");
      addLog("ERROR", data.message, "error");
    }
  };

  const addLog = (node: string, message: string, type: TerminalLog["type"]) => {
    const timeStr = new Date().toLocaleTimeString();
    setTerminalLogs((prev) => [
      ...prev,
      { timestamp: timeStr, node, message, type },
    ]);
  };

  // Browser TTS fallback to read out the voice response for the recruiter!
  const speakText = (text: string) => {
    if (typeof window !== "undefined" && window.speechSynthesis) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      window.speechSynthesis.speak(utterance);
    }
  };

  const submitQuery = () => {
    if (!inputText.trim()) return;
    
    // Clear old voice synthesis
    setVoiceSynthesisText("");
    
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ query: inputText }));
      setInputText("");
    } else {
      addLog("SYSTEM", "Failed to send command. WebSocket is not open.", "error");
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      submitQuery();
    }
  };

  const triggerRestart = async (podName: string, namespace: string) => {
    addLog("ACTION", `User triggered restart for pod ${podName}...`, "action");
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/pods/restart`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: podName, namespace }),
      });
      if (res.ok) {
        addLog("SYSTEM", `Pod ${podName} restarted successfully.`, "success");
        fetchTelemetry();
      } else {
        const errData = await res.json();
        addLog("SYSTEM", `Failed to restart pod: ${errData.detail}`, "error");
      }
    } catch (err) {
      addLog("SYSTEM", "Failed to contact backend API.", "error");
    }
  };

  const triggerScale = async () => {
    if (!scalingPod) return;
    const depName = scalingPod.name.split("-")[0]; // Extract base name (e.g. payment-gateway)
    addLog("ACTION", `User scaling deployment ${depName} to ${targetReplicas} replicas...`, "action");
    try {
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${backendUrl}/api/deployments/scale`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: depName, replicas: targetReplicas, namespace: scalingPod.namespace }),
      });
      if (res.ok) {
        addLog("SYSTEM", `Deployment ${depName} scaled successfully to ${targetReplicas} replicas.`, "success");
        setScalingPod(null);
        fetchTelemetry();
      } else {
        const errData = await res.json();
        addLog("SYSTEM", `Failed to scale deployment: ${errData.detail}`, "error");
      }
    } catch (err) {
      addLog("SYSTEM", "Failed to contact backend API.", "error");
    }
  };

  // Simulate pushing VAD mic button
  const toggleVoiceSession = () => {
    if (currentStep === "idle") {
      setCurrentStep("listening");
      addLog("SYSTEM", "Mock microphone active. Listening for speech...", "info");
      // Simulate speech after 2.5 seconds
      setTimeout(() => {
        setInputText("Check the status of production pods");
      }, 1000);
    } else {
      setCurrentStep("idle");
      addLog("SYSTEM", "Microphone deactivated.", "info");
    }
  };

  return (
    <main className="min-h-screen bg-[#060818] text-[#e2e8f0] p-6 font-sans selection:bg-cyan-500 selection:text-black">
      {/* Background gradients */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-10 right-1/4 w-[600px] h-[600px] bg-cyan-500/5 rounded-full blur-[140px] pointer-events-none" />

      {/* Header */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center border-b border-white/10 pb-6 mb-8 gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6 text-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">Voice SRE Supervisor</h1>
            <p className="text-xs text-slate-400">Agentic Infrastructure Supervisor (LangGraph + FastAPI)</p>
          </div>
        </div>

        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/60 border border-white/5">
            <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
            <span className="text-xs text-slate-300">Backend: {isConnected ? "CONNECTED" : "OFFLINE"}</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/60 border border-white/5">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
            <span className="text-xs text-slate-300">Mode: MOCK SIMULATOR</span>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Left Column: Voice Control & Live Terminal Logs */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          
          {/* Voice Interface Card */}
          <div className="bg-slate-900/40 border border-white/10 rounded-2xl p-6 backdrop-blur-xl flex flex-col items-center relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none" />
            
            <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase mb-6 self-start">Voice Telemetry Supervisor</h2>
            
            {/* Pulsing Visualizer Circle */}
            <div className="relative w-48 h-48 flex items-center justify-center mb-8">
              {currentStep === "listening" && (
                <>
                  <div className="absolute inset-0 rounded-full bg-cyan-500/25 animate-ping" />
                  <div className="absolute inset-4 rounded-full bg-cyan-400/20 animate-pulse" />
                </>
              )}
              {currentStep === "executing" && (
                <>
                  <div className="absolute inset-0 rounded-full bg-indigo-500/25 animate-spin" style={{ animationDuration: "3s" }} />
                  <div className="absolute inset-4 rounded-full bg-indigo-400/20 animate-pulse" />
                </>
              )}
              {currentStep === "reasoning" && (
                <div className="absolute inset-2 rounded-full border-2 border-dashed border-cyan-500/50 animate-spin" style={{ animationDuration: "6s" }} />
              )}
              {currentStep === "synthesizing" && (
                <>
                  <div className="absolute inset-0 rounded-full bg-emerald-500/20 animate-pulse" />
                  <div className="absolute inset-6 rounded-full border border-emerald-400/30 animate-ping" />
                </>
              )}

              <button
                onClick={toggleVoiceSession}
                className={`w-36 h-36 rounded-full flex flex-col items-center justify-center transition-all duration-500 shadow-2xl relative z-10 ${
                  currentStep === "listening"
                    ? "bg-cyan-500 text-black scale-105"
                    : currentStep === "executing"
                    ? "bg-indigo-600 text-white"
                    : currentStep === "synthesizing"
                    ? "bg-emerald-500 text-black scale-105"
                    : "bg-slate-800 hover:bg-slate-700/80 border border-white/10 hover:border-cyan-500/30 text-cyan-400 hover:scale-102"
                }`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  {currentStep === "listening" ? (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  ) : currentStep === "executing" ? (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                  )}
                </svg>
                <span className="text-[11px] tracking-wider uppercase font-semibold">
                  {currentStep === "listening" ? "Listening..." : currentStep === "executing" ? "Executing..." : currentStep === "synthesizing" ? "Speaking..." : "Push to Talk"}
                </span>
              </button>
            </div>

            {/* Voice synthesis transcript */}
            <div className="w-full min-h-[4rem] text-center px-4 mb-4">
              {voiceSynthesisText ? (
                <p className="text-slate-200 text-sm italic font-medium leading-relaxed">
                  &ldquo;{voiceSynthesisText}&rdquo;
                </p>
              ) : (
                <p className="text-slate-500 text-xs italic">
                  {currentStep === "listening" ? "Ask a query about pods or nodes status..." : "Click button or type query below to communicate."}
                </p>
              )}
            </div>

            {/* Input field */}
            <div className="w-full flex gap-2">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type command (e.g. 'check pods', 'restart db-postgres-0')..."
                className="flex-1 bg-slate-950 border border-white/10 rounded-xl px-4 py-2 text-sm text-[#e2e8f0] placeholder:text-slate-600 focus:outline-none focus:border-cyan-500 transition-colors"
              />
              <button
                onClick={submitQuery}
                className="bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-sm px-4 py-2 rounded-xl transition-all shadow-md shadow-cyan-500/10 hover:shadow-cyan-500/20"
              >
                Send
              </button>
            </div>
          </div>

          {/* War Room Reasoning Logs */}
          <div className="flex-1 bg-slate-950/70 border border-white/10 rounded-2xl p-5 flex flex-col min-h-[22rem]">
            <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase mb-4">War Room Visualization</h2>
            
            <div className="flex-1 bg-slate-950 border border-white/5 rounded-xl p-4 overflow-y-auto font-mono text-[11px] leading-relaxed flex flex-col gap-2 max-h-[24rem]">
              {terminalLogs.length === 0 ? (
                <div className="text-slate-600 italic">No logs recorded. Visualizer waiting for pipeline execution...</div>
              ) : (
                terminalLogs.map((log, idx) => (
                  <div key={idx} className="flex gap-2">
                    <span className="text-slate-500">[{log.timestamp}]</span>
                    <span className={`font-bold ${
                      log.type === "success" ? "text-emerald-400" :
                      log.type === "warning" ? "text-amber-400" :
                      log.type === "error" ? "text-rose-400" :
                      log.type === "action" ? "text-indigo-400" : "text-cyan-400"
                    }`}>
                      [{log.node}]
                    </span>
                    <span className="text-slate-300">{log.message}</span>
                  </div>
                ))
              )}
              <div ref={terminalEndRef} />
            </div>
          </div>
        </div>

        {/* Right Column: Cluster Telemetry */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          
          {/* Node Metrics Card */}
          <div className="bg-slate-900/40 border border-white/10 rounded-2xl p-6 backdrop-blur-xl">
            <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase mb-4">Cluster Nodes</h2>
            
            <div className="flex flex-col gap-4">
              {nodes.length === 0 ? (
                <div className="text-slate-500 italic py-4">No node metrics found...</div>
              ) : (
                nodes.map((node, idx) => (
                  <div key={idx} className="bg-slate-950/60 border border-white/5 rounded-xl p-4 flex flex-col gap-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-cyan-400" />
                        <span className="font-semibold text-sm">{node.name}</span>
                      </div>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-bold tracking-wide uppercase border border-emerald-500/10">
                        {node.status}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <div className="flex justify-between mb-1.5 text-slate-400">
                          <span>CPU Allocation</span>
                          <span className="font-medium text-slate-200">{node.cpu_usage}</span>
                        </div>
                        <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-gradient-to-r from-cyan-500 to-indigo-500 h-full rounded-full" style={{ width: "38%" }} />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between mb-1.5 text-slate-400">
                          <span>Memory Allocation</span>
                          <span className="font-medium text-slate-200">{node.memory_usage}</span>
                        </div>
                        <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full" style={{ width: "52%" }} />
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Pod List Card */}
          <div className="bg-slate-900/40 border border-white/10 rounded-2xl p-6 backdrop-blur-xl flex-1 flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-sm font-semibold tracking-wider text-slate-400 uppercase">Production Pods</h2>
              <span className="text-xs text-slate-500">Auto-refreshing every 3s</span>
            </div>

            <div className="flex-1 overflow-y-auto max-h-[30rem] pr-1 flex flex-col gap-3">
              {pods.length === 0 ? (
                <div className="text-slate-500 italic py-8 text-center">No pods found in namespace production.</div>
              ) : (
                pods.map((pod, idx) => (
                  <div key={idx} className="bg-slate-950/60 hover:bg-slate-950/90 border border-white/5 hover:border-cyan-500/20 rounded-xl p-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 transition-all">
                    
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-xs text-slate-100">{pod.name}</span>
                        <span className="text-[10px] bg-slate-900 border border-white/5 text-slate-400 px-1.5 py-0.25 rounded-md">
                          {pod.namespace}
                        </span>
                      </div>
                      <div className="flex gap-4 text-[10px] text-slate-500">
                        <span>IP: <span className="text-slate-400 font-mono">{pod.ip}</span></span>
                        <span>CPU: <span className="text-slate-400">{pod.cpu_usage}</span></span>
                        <span>Mem: <span className="text-slate-400">{pod.memory_usage}</span></span>
                        <span>Restarts: <span className={`font-bold ${pod.restarts > 0 ? "text-amber-400" : "text-slate-400"}`}>{pod.restarts}</span></span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 self-stretch md:self-auto justify-between md:justify-start border-t md:border-t-0 border-white/5 pt-2 md:pt-0">
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold tracking-wide border uppercase ${
                        pod.status === "Running" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/10" :
                        pod.status === "Pending" ? "bg-amber-500/10 text-amber-400 border-amber-500/10" :
                        "bg-rose-500/10 text-rose-400 border-rose-500/10 animate-pulse"
                      }`}>
                        {pod.status}
                      </span>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => triggerRestart(pod.name, pod.namespace)}
                          className="bg-slate-900 border border-white/10 hover:border-indigo-500 hover:text-indigo-400 text-xs px-2.5 py-1.5 rounded-lg transition-all"
                        >
                          Restart
                        </button>
                        <button
                          onClick={() => {
                            setScalingPod(pod);
                            setTargetReplicas(pods.filter(p => p.name.split("-")[0] === pod.name.split("-")[0]).length);
                          }}
                          className="bg-slate-900 border border-white/10 hover:border-cyan-500 hover:text-cyan-400 text-xs px-2.5 py-1.5 rounded-lg transition-all"
                        >
                          Scale
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

        </div>

      </div>

      {/* Scaling Modal */}
      {scalingPod && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#0b0f19] border border-white/15 rounded-2xl max-w-md w-full p-6 relative shadow-2xl">
            <h3 className="text-base font-semibold mb-2">Scale Deployment</h3>
            <p className="text-xs text-slate-400 mb-4">
              Adjust replica configuration for deployment: <strong className="text-cyan-400">{scalingPod.name.split("-")[0]}</strong>
            </p>
            
            <div className="flex items-center gap-4 mb-6">
              <span className="text-xs text-slate-500">Replicas:</span>
              <button 
                onClick={() => setTargetReplicas(Math.max(1, targetReplicas - 1))}
                className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 font-bold transition-all"
              >
                -
              </button>
              <span className="text-base font-semibold w-6 text-center">{targetReplicas}</span>
              <button 
                onClick={() => setTargetReplicas(targetReplicas + 1)}
                className="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 font-bold transition-all"
              >
                +
              </button>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setScalingPod(null)}
                className="bg-slate-900 border border-white/10 hover:bg-slate-850 px-4 py-2 rounded-xl text-xs transition-all"
              >
                Cancel
              </button>
              <button
                onClick={triggerScale}
                className="bg-cyan-500 hover:bg-cyan-400 text-black font-semibold px-4 py-2 rounded-xl text-xs transition-all"
              >
                Apply Scaling
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
