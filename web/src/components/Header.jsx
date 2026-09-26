import React from 'react';
import { ShieldCheck, Cpu, Terminal, Sparkles, Activity, Layers, PlayCircle, BarChart3, Wrench } from 'lucide-react';

export default function Header({ activeTab, setActiveTab, systemHealth, onOpenToolsModal }) {
  const tabs = [
    { id: 'console', label: 'Agent Console & DAG', icon: Terminal },
    { id: 'healing', label: 'Self-Healing Engine', icon: ShieldCheck },
    { id: 'observability', label: 'OpenTelemetry Traces', icon: Activity },
    { id: 'benchmark', label: 'Benchmark Studio', icon: BarChart3 },
    { id: 'workspace', label: 'Personal OS (KrutiOS)', icon: Sparkles },
  ];

  return (
    <header className="header-nav">
      <div className="brand-group">
        <div className="logo-badge">
          <Cpu size={24} />
        </div>
        <div>
          <div className="brand-title">AgentOS</div>
          <div className="brand-subtitle">Resilient Control Plane</div>
        </div>
      </div>

      <div className="nav-tabs">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              className={`nav-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      <div className="header-actions">
        <button
          className="nav-tab-btn"
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border-glass)' }}
          onClick={onOpenToolsModal}
        >
          <Wrench size={16} />
          <span>MCP Tools (6)</span>
        </button>

        <div className="system-status-pill">
          <span className="status-dot-pulse" />
          <span>{systemHealth?.status ? 'Runtime Active' : 'Connecting...'}</span>
        </div>
      </div>
    </header>
  );
}
