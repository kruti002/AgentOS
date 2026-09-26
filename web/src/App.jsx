import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import TrajectoryDAG from './components/TrajectoryDAG';
import SelfHealingVisualizer from './components/SelfHealingVisualizer';
import TraceWaterfall from './components/TraceWaterfall';
import BenchmarkStudio from './components/BenchmarkStudio';
import KrutiOSWorkspace from './components/KrutiOSWorkspace';
import ToolRegistryModal from './components/ToolRegistryModal';

export default function App() {
  const [activeTab, setActiveTab] = useState('console');
  const [systemHealth, setSystemHealth] = useState(null);
  const [goal, setGoal] = useState('Inspect system_metrics table in DuckDB, calculate the average latency of healthy services, and save the report to filesystem.');
  const [isRunning, setIsRunning] = useState(false);
  const [activeState, setActiveState] = useState(null);
  const [traces, setTraces] = useState({ spans: [], tree: [] });
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [isBenchmarkRunning, setIsBenchmarkRunning] = useState(false);
  const [isToolsModalOpen, setIsToolsModalOpen] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [pendingApproval, setPendingApproval] = useState(null);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [multiAgent, setMultiAgent] = useState(false);

  // Poll system health and traces
  useEffect(() => {
    fetchHealth();
    fetchTraces();
    fetchBenchmarkResults();

    const interval = setInterval(() => {
      fetchHealth();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      setSystemHealth(data);
    } catch (e) {
      console.error('Health check failed:', e);
    }
  };

  const fetchTraces = async () => {
    try {
      const res = await fetch('/api/observability/traces');
      const data = await res.json();
      setTraces(data);
    } catch (e) {
      console.error('Fetch traces failed:', e);
    }
  };

  const fetchBenchmarkResults = async () => {
    try {
      const res = await fetch('/api/benchmark/results');
      const data = await res.json();
      setBenchmarkData(data);
    } catch (e) {
      console.error('Fetch benchmark failed:', e);
    }
  };

  const handleRunTask = async () => {
    if (!goal.trim()) return;
    setIsRunning(true);
    setActiveState(null);
    setStreamingText('');
    setPendingApproval(null);

    // Multi-agent delegation runs synchronously and returns a merged report.
    if (multiAgent) {
      try {
        const res = await fetch('/api/agent/delegate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ goal })
        });
        const report = await res.json();
        setActiveState({
          status: 'completed',
          current_phase: 'synthesis',
          total_tokens: report.total_tokens,
          total_cost_usd: report.total_cost_usd,
          history: [],
          healing_events: [],
          plan: (report.sub_goals || []).map((sg) => ({ title: sg, assigned_tool: null })),
          final_output: report.final_output,
          sub_results: report.sub_results,
        });
      } catch (e) {
        console.error('Delegate error:', e);
      } finally {
        setIsRunning(false);
        fetchTraces();
      }
      return;
    }

    try {
      const res = await fetch('/api/agent/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal })
      });
      const data = await res.json();
      const taskId = data.task_id;
      setCurrentTaskId(taskId);

      // Listen to SSE Stream
      const eventSource = new EventSource(`/api/stream/${taskId}`);

      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);

          switch (payload.event_type) {
            case 'TOKEN':
              // Live-build the streamed final answer.
              setStreamingText((prev) => prev + (payload.payload?.delta || ''));
              break;
            case 'APPROVAL_REQUIRED':
              setPendingApproval(payload.payload);
              fetchTaskState(taskId);
              break;
            case 'APPROVAL_RESOLVED':
              setPendingApproval(null);
              fetchTaskState(taskId);
              break;
            case 'COMPLETED':
            case 'FAILED':
            case 'CANCELLED':
              eventSource.close();
              setIsRunning(false);
              setPendingApproval(null);
              fetchTaskState(taskId);
              fetchTraces();
              break;
            default:
              fetchTaskState(taskId);
          }
        } catch (err) {
          console.error('SSE parse error:', err);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        setIsRunning(false);
        fetchTaskState(taskId);
        fetchTraces();
      };

    } catch (e) {
      console.error('Run task error:', e);
      setIsRunning(false);
    }
  };

  const handleApprove = async (approvalId, approved) => {
    if (!currentTaskId || !approvalId) return;
    try {
      await fetch('/api/agent/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: currentTaskId, approval_id: approvalId, approved })
      });
      setPendingApproval(null);
    } catch (e) {
      console.error('Approve error:', e);
    }
  };

  const handleCancel = async () => {
    if (!currentTaskId) return;
    try {
      await fetch(`/api/agent/cancel/${currentTaskId}`, { method: 'POST' });
    } catch (e) {
      console.error('Cancel error:', e);
    }
  };

  const fetchTaskState = async (taskId) => {
    try {
      const res = await fetch(`/api/agent/state/${taskId}`);
      const data = await res.json();
      setActiveState(data);
    } catch (e) {
      console.error('Fetch state error:', e);
    }
  };

  const handleRunBenchmark = async (limit) => {
    setIsBenchmarkRunning(true);
    try {
      const res = await fetch(`/api/benchmark/run?limit=${limit}`, { method: 'POST' });
      const data = await res.json();
      setBenchmarkData(data);
    } catch (e) {
      console.error('Benchmark error:', e);
    } finally {
      setIsBenchmarkRunning(false);
    }
  };

  const handleClearTraces = async () => {
    try {
      await fetch('/api/observability/traces', { method: 'DELETE' });
      setTraces({ spans: [], tree: [] });
    } catch (e) {
      console.error('Clear traces error:', e);
    }
  };

  const handleSelectPreset = (presetPrompt) => {
    setGoal(presetPrompt);
    setActiveTab('console');
  };

  return (
    <div className="app-container">
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        systemHealth={systemHealth}
        onOpenToolsModal={() => setIsToolsModalOpen(true)}
      />

      <main className="main-content">
        {activeTab === 'console' && (
          <TrajectoryDAG
            goal={goal}
            setGoal={setGoal}
            onRunTask={handleRunTask}
            isRunning={isRunning}
            activeState={activeState}
            streamingText={streamingText}
            pendingApproval={pendingApproval}
            onApprove={handleApprove}
            onCancel={handleCancel}
            multiAgent={multiAgent}
            setMultiAgent={setMultiAgent}
          />
        )}

        {activeTab === 'healing' && <SelfHealingVisualizer />}

        {activeTab === 'observability' && (
          <TraceWaterfall
            traces={traces}
            onRefresh={fetchTraces}
            onClear={handleClearTraces}
          />
        )}

        {activeTab === 'benchmark' && (
          <BenchmarkStudio
            benchmarkData={benchmarkData}
            onRunBenchmark={handleRunBenchmark}
            isRunning={isBenchmarkRunning}
          />
        )}

        {activeTab === 'workspace' && (
          <KrutiOSWorkspace onSelectPreset={handleSelectPreset} />
        )}
      </main>

      <ToolRegistryModal
        isOpen={isToolsModalOpen}
        onClose={() => setIsToolsModalOpen(false)}
      />
    </div>
  );
}
