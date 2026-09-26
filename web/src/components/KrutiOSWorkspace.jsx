import React from 'react';
import { Sparkles, Database, Search, ShieldCheck, Terminal, ArrowUpRight, CheckSquare, Layers } from 'lucide-react';

export default function KrutiOSWorkspace({ onSelectPreset }) {
  const presets = [
    {
      title: 'Technical Research & Architecture Synthesis',
      category: 'Research Agent',
      icon: Search,
      color: 'var(--accent-cyan)',
      prompt: 'Perform comprehensive web research on Model Context Protocol (MCP) and distributed consensus algorithms, extract key patterns, and synthesize an executive report.',
      tools: ['web_search', 'web_fetch', 'fs_write']
    },
    {
      title: 'DuckDB Telemetry & SQL Analytics',
      category: 'Data & Analytics',
      icon: Database,
      color: 'var(--accent-purple)',
      prompt: 'Inspect database schema for system_metrics, execute SQL query to find services with high CPU/latency, compute statistical summary, and return insights.',
      tools: ['db_schema', 'db_query', 'data_stats']
    },
    {
      title: 'Sandboxed Filesystem Report Generation',
      category: 'File Operations',
      icon: Terminal,
      color: 'var(--accent-indigo)',
      prompt: 'Inspect workspace directory tree, write structured agent benchmark report to disk, and verify file integrity using fs_stat.',
      tools: ['fs_list', 'fs_write', 'fs_read', 'fs_stat']
    },
    {
      title: 'Security Taint Analysis & Policy Audit',
      category: 'Security Agent',
      icon: ShieldCheck,
      color: 'var(--accent-emerald)',
      prompt: 'Audit shell execution permissions and verify that dangerous commands (e.g., rm -rf, access to .env) are blocked while safe sandboxed operations proceed.',
      tools: ['shell_exec', 'fs_read', 'calc_eval']
    }
  ];

  return (
    <div>
      <div className="glass-panel" style={{ padding: '28px', marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <div style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-purple))', padding: '8px', borderRadius: '10px' }}>
            <Sparkles size={22} color="#fff" />
          </div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>Personal AI OS Workspace ("KrutiOS")</h2>
        </div>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: '850px' }}>
          Welcome to your personal autonomous agent command center. Select an enterprise workflow template below or define customized autonomous sub-goals leveraging the full AgentOS tool substrate.
        </p>
      </div>

      <div className="preset-grid">
        {presets.map((preset, idx) => {
          const Icon = preset.icon;
          return (
            <div
              key={idx}
              className="glass-panel preset-card"
              onClick={() => onSelectPreset(preset.prompt)}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div className="preset-icon-box" style={{ background: `${preset.color}22`, color: preset.color }}>
                    <Icon size={22} />
                  </div>
                  <span style={{ fontSize: '0.75rem', background: 'rgba(255,255,255,0.06)', padding: '3px 8px', borderRadius: '6px', color: 'var(--text-muted)' }}>
                    {preset.category}
                  </span>
                </div>

                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: '12px 0 8px 0' }}>
                  {preset.title}
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '16px' }}>
                  {preset.prompt}
                </p>
              </div>

              <div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '14px' }}>
                  {preset.tools.map((t) => (
                    <span key={t} style={{ fontSize: '0.72rem', background: 'rgba(99,102,241,0.15)', color: 'var(--accent-indigo)', padding: '2px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)' }}>
                      {t}
                    </span>
                  ))}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: preset.color, fontSize: '0.85rem', fontWeight: 600 }}>
                  <span>Launch Workflow</span>
                  <ArrowUpRight size={16} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
