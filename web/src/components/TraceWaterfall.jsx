import React, { useState, useEffect } from 'react';
import { Activity, RefreshCw, Layers, Shield, Wrench, Sparkles, Cpu, Clock } from 'lucide-react';

export default function TraceWaterfall({ traces, onRefresh, onClear }) {
  const [selectedSpan, setSelectedSpan] = useState(null);

  const getCategoryColor = (category) => {
    switch (category) {
      case 'llm': return 'var(--accent-purple)';
      case 'tool': return 'var(--accent-cyan)';
      case 'security': return 'var(--accent-rose)';
      case 'healing': return 'var(--accent-amber)';
      case 'orchestrator': return 'var(--accent-indigo)';
      default: return 'var(--text-secondary)';
    }
  };

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'llm': return Sparkles;
      case 'tool': return Wrench;
      case 'security': return Shield;
      case 'healing': return RefreshCw;
      default: return Cpu;
    }
  };

  const spans = traces?.spans || [];

  return (
    <div>
      <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Activity size={22} color="var(--accent-cyan)" />
            <span>OpenTelemetry Distributed Trace Waterfall</span>
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '4px' }}>
            Real-time span telemetry capturing planner latency, MCP tool invocations, policy evaluations, and self-healing loops.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="nav-tab-btn" style={{ background: 'rgba(255,255,255,0.06)' }} onClick={onRefresh}>
            <RefreshCw size={14} />
            <span>Refresh Spans</span>
          </button>
          <button className="nav-tab-btn" style={{ background: 'rgba(244,63,94,0.1)', color: 'var(--accent-rose)' }} onClick={onClear}>
            <span>Clear Traces</span>
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: selectedSpan ? '1fr 380px' : '1fr', gap: '20px' }}>
        {/* Waterfall List */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          {spans.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              No OpenTelemetry traces recorded yet. Run a task in the Agent Console to generate live distributed traces.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {spans.map((span) => {
                const Icon = getCategoryIcon(span.category);
                const color = getCategoryColor(span.category);
                const isSelected = selectedSpan?.span_id === span.span_id;
                const isChild = !!span.parent_span_id;

                return (
                  <div
                    key={span.span_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px 16px',
                      borderRadius: '10px',
                      background: isSelected ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.25)',
                      border: `1px solid ${isSelected ? color : 'var(--border-glass)'}`,
                      marginLeft: isChild ? '24px' : '0',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                    onClick={() => setSelectedSpan(span)}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ color }}>
                        <Icon size={16} />
                      </div>
                      <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{span.name}</span>
                      <span style={{ fontSize: '0.75rem', background: `${color}22`, color, padding: '2px 8px', borderRadius: '4px', textTransform: 'uppercase' }}>
                        {span.category}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <span style={{ fontSize: '0.8rem', color: span.status === 'OK' ? 'var(--accent-emerald)' : 'var(--accent-rose)', fontWeight: 600 }}>
                        {span.status}
                      </span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>
                        {span.duration_ms ? `${span.duration_ms.toFixed(1)} ms` : '< 1 ms'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Span Inspector Drawer */}
        {selectedSpan && (
          <div className="glass-panel" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h4 style={{ fontSize: '1rem', color: getCategoryColor(selectedSpan.category) }}>
                Span Inspector
              </h4>
              <button
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1.1rem' }}
                onClick={() => setSelectedSpan(null)}
              >
                ✕
              </button>
            </div>

            <div style={{ fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Span ID:</span>{' '}
                <span style={{ fontFamily: 'var(--font-mono)' }}>{selectedSpan.span_id}</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Parent Span ID:</span>{' '}
                <span style={{ fontFamily: 'var(--font-mono)' }}>{selectedSpan.parent_span_id || 'root'}</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Category:</span>{' '}
                <span>{selectedSpan.category}</span>
              </div>
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Duration:</span>{' '}
                <span style={{ color: 'var(--accent-cyan)' }}>{selectedSpan.duration_ms?.toFixed(2)} ms</span>
              </div>

              <div style={{ marginTop: '10px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Attributes:</span>
                <pre style={{ background: 'rgba(0,0,0,0.5)', padding: '10px', borderRadius: '8px', fontSize: '0.78rem', color: '#cbd5e1', marginTop: '6px', maxHeight: '180px', overflowY: 'auto' }}>
                  {JSON.stringify(selectedSpan.attributes, null, 2)}
                </pre>
              </div>

              {selectedSpan.events?.length > 0 && (
                <div style={{ marginTop: '10px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Span Events:</span>
                  <pre style={{ background: 'rgba(0,0,0,0.5)', padding: '10px', borderRadius: '8px', fontSize: '0.78rem', color: '#cbd5e1', marginTop: '6px' }}>
                    {JSON.stringify(selectedSpan.events, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
