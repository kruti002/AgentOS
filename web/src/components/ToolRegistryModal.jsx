import React, { useState, useEffect } from 'react';
import { Wrench, ShieldCheck, Play, CheckCircle2, AlertCircle } from 'lucide-react';

export default function ToolRegistryModal({ isOpen, onClose }) {
  const [tools, setTools] = useState([]);
  const [selectedTool, setSelectedTool] = useState(null);
  const [testArgs, setTestArgs] = useState('{}');
  const [execResult, setExecResult] = useState(null);
  const [executing, setExecuting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetch('/api/mcp/tools')
        .then((res) => res.json())
        .then((data) => {
          setTools(data);
          if (data.length > 0) {
            setSelectedTool(data[0]);
            initDefaultArgs(data[0]);
          }
        })
        .catch((err) => console.error(err));
    }
  }, [isOpen]);

  const initDefaultArgs = (tool) => {
    const defaults = {};
    if (tool?.parameters) {
      Object.entries(tool.parameters).forEach(([k, v]) => {
        defaults[k] = v.default !== null && v.default !== undefined ? v.default : (v.type === 'string' ? '' : v.type === 'array' ? [] : 0);
      });
    }
    if (tool?.name === 'calc_eval') defaults['expression'] = 'sqrt(144) + 12 * 4';
    if (tool?.name === 'web_search') defaults['query'] = 'Model Context Protocol specification';
    if (tool?.name === 'db_query') defaults['query'] = 'SELECT service_name, status FROM system_metrics LIMIT 3;';
    if (tool?.name === 'fs_list') defaults['path'] = '.';

    setTestArgs(JSON.stringify(defaults, null, 2));
    setExecResult(null);
  };

  const handleRunTool = async () => {
    if (!selectedTool) return;
    setExecuting(true);
    try {
      const parsedArgs = JSON.parse(testArgs);
      const res = await fetch('/api/mcp/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: selectedTool.name,
          arguments: parsedArgs
        })
      });
      const data = await res.json();
      setExecResult(data);
    } catch (e) {
      setExecResult({ success: false, error_message: String(e) });
    } finally {
      setExecuting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px' }}>
      <div className="glass-panel" style={{ width: '900px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-secondary)', border: '1px solid var(--border-glass)', padding: '24px', overflow: 'hidden' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '12px', borderBottom: '1px solid var(--border-glass)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Wrench size={22} color="var(--accent-cyan)" />
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>MCP Tool Gateway & Schema Registry</h3>
          </div>
          <button style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', fontSize: '1.2rem', cursor: 'pointer' }} onClick={onClose}>
            ✕
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '20px', flex: 1, overflow: 'hidden' }}>
          {/* Tool List Sidebar */}
          <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '8px' }}>
            {tools.map((t) => {
              const isSelected = selectedTool?.name === t.name;
              return (
                <div
                  key={t.name}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    background: isSelected ? 'rgba(99,102,241,0.2)' : 'rgba(0,0,0,0.25)',
                    border: `1px solid ${isSelected ? 'var(--accent-indigo)' : 'var(--border-glass)'}`,
                    cursor: 'pointer'
                  }}
                  onClick={() => {
                    setSelectedTool(t);
                    initDefaultArgs(t);
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: isSelected ? '#fff' : 'var(--text-primary)' }}>
                    {t.name}
                  </div>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                    <span style={{ fontSize: '0.7rem', color: 'var(--accent-cyan)', background: 'rgba(6,182,212,0.1)', padding: '1px 5px', borderRadius: '4px' }}>
                      {t.category}
                    </span>
                    <span style={{ fontSize: '0.7rem', color: t.risk_level === 'HIGH' ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}>
                      {t.risk_level}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Tool Inspector & Execution Sandbox */}
          {selectedTool && (
            <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <h4 style={{ fontSize: '1.1rem', color: 'var(--accent-indigo)' }}>{selectedTool.name}</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '4px' }}>{selectedTool.description}</p>
              </div>

              <div>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                  PARAMETERS SCHEMA:
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {Object.entries(selectedTool.parameters || {}).map(([pName, pSpec]) => (
                    <div key={pName} style={{ background: 'rgba(0,0,0,0.3)', padding: '8px 12px', borderRadius: '6px', fontSize: '0.82rem', display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                        {pName} {pSpec.required && <span style={{ color: 'var(--accent-rose)' }}>*</span>}
                      </span>
                      <span style={{ color: 'var(--text-muted)' }}>{pSpec.type} - {pSpec.description}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>TEST ARGUMENTS (JSON):</span>
                  <button className="btn-primary" style={{ padding: '4px 14px', fontSize: '0.8rem' }} onClick={handleRunTool} disabled={executing}>
                    <Play size={12} />
                    <span>{executing ? 'Running...' : 'Execute Tool'}</span>
                  </button>
                </div>
                <textarea
                  style={{ width: '100%', height: '80px', background: 'rgba(10,13,20,0.9)', border: '1px solid var(--border-glass)', borderRadius: '8px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '0.82rem', padding: '10px' }}
                  value={testArgs}
                  onChange={(e) => setTestArgs(e.target.value)}
                />
              </div>

              {execResult && (
                <div style={{ background: 'rgba(0,0,0,0.4)', border: `1px solid ${execResult.success ? 'var(--accent-emerald)' : 'var(--accent-rose)'}`, borderRadius: '8px', padding: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', color: execResult.success ? 'var(--accent-emerald)' : 'var(--accent-rose)', fontWeight: 600, marginBottom: '6px' }}>
                    {execResult.success ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                    <span>{execResult.success ? `Success (${execResult.execution_time_ms.toFixed(1)}ms)` : 'Tool Execution Error'}</span>
                  </div>
                  <pre style={{ fontSize: '0.78rem', color: '#cbd5e1', maxHeight: '120px', overflowY: 'auto' }}>
                    {execResult.success ? JSON.stringify(execResult.output, null, 2) : execResult.error_message}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
