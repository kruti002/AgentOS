import React from 'react';
import { Play, CheckCircle2, AlertTriangle, ShieldAlert, Sparkles, RefreshCw, TerminalSquare, ArrowRight, XCircle, Check, X, Users } from 'lucide-react';

export default function TrajectoryDAG({
  goal,
  setGoal,
  onRunTask,
  isRunning,
  activeState,
  streamingText,
  pendingApproval,
  onApprove,
  onCancel,
  multiAgent,
  setMultiAgent,
}) {
  return (
    <div>
      {/* Prompt Console Bar */}
      <div className="glass-panel console-box">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-cyan)', fontSize: '0.85rem', fontWeight: 600 }}>
            <TerminalSquare size={16} />
            <span>AUTONOMOUS AGENT DISPATCH CONTROL</span>
          </div>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={!!multiAgent}
              onChange={(e) => setMultiAgent(e.target.checked)}
              disabled={isRunning}
            />
            <Users size={14} />
            <span>Multi-agent delegation</span>
          </label>
        </div>

        <div className="prompt-input-row">
          <textarea
            className="prompt-textarea"
            placeholder="Enter an autonomous goal (e.g., 'Query system_metrics for the highest-latency service and write a summary report')"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            disabled={isRunning}
            rows={2}
          />
          <button
            className="btn-primary"
            onClick={onRunTask}
            disabled={isRunning || !goal.trim()}
          >
            {isRunning ? (
              <>
                <RefreshCw size={18} className="animate-spin" />
                <span>Executing...</span>
              </>
            ) : (
              <>
                <Play size={18} />
                <span>{multiAgent ? 'Delegate to Agents' : 'Run AgentOS Task'}</span>
              </>
            )}
          </button>
          {isRunning && !multiAgent && (
            <button className="btn-danger" onClick={onCancel} title="Cancel task">
              <XCircle size={18} />
              <span>Cancel</span>
            </button>
          )}
        </div>
      </div>

      {/* Human-in-the-loop approval banner */}
      {pendingApproval && (
        <div className="glass-panel approval-banner">
          <div className="approval-banner-head">
            <ShieldAlert size={18} color="var(--accent-amber)" />
            <span>Human approval required</span>
          </div>
          <div className="approval-banner-body">
            <div>
              Tool <code>{pendingApproval.tool_name}</code> — {pendingApproval.reason}
            </div>
            <pre className="approval-args">{JSON.stringify(pendingApproval.arguments, null, 2)}</pre>
          </div>
          <div className="approval-banner-actions">
            <button className="btn-approve" onClick={() => onApprove(pendingApproval.approval_id, true)}>
              <Check size={16} /> Approve
            </button>
            <button className="btn-deny" onClick={() => onApprove(pendingApproval.approval_id, false)}>
              <X size={16} /> Deny
            </button>
          </div>
        </div>
      )}

      {/* Live streaming answer (before final_output settles) */}
      {isRunning && streamingText && (
        <div className="glass-panel" style={{ padding: '20px', marginTop: '16px' }}>
          <h3 style={{ fontSize: '1rem', marginBottom: '10px', color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={16} />
            <span>Streaming answer…</span>
          </h3>
          <div style={{ background: 'rgba(10, 13, 20, 0.85)', padding: '16px', borderRadius: '10px', lineHeight: 1.6, whiteSpace: 'pre-wrap', fontSize: '0.92rem' }}>
            {streamingText}
            <span className="stream-cursor">▋</span>
          </div>
        </div>
      )}

      {/* Trajectory Stream & Waterfall DAG */}
      {activeState && (
        <div style={{ marginTop: '24px' }}>
          {/* Metrics summary banner */}
          <div className="metrics-row">
            <div className="glass-panel metric-card">
              <div className="metric-label">
                <span>Task Status</span>
                <CheckCircle2 size={16} color="var(--accent-emerald)" />
              </div>
              <div className="metric-value" style={{ textTransform: 'capitalize', color: activeState.status === 'completed' ? 'var(--accent-emerald)' : 'var(--accent-cyan)' }}>
                {activeState.status}
              </div>
              <div className="metric-subtext">Phase: {activeState.current_phase}</div>
            </div>

            <div className="glass-panel metric-card">
              <div className="metric-label">
                <span>Tokens & Cost</span>
                <Sparkles size={16} color="var(--accent-purple)" />
              </div>
              <div className="metric-value">{activeState.total_tokens || 0}</div>
              <div className="metric-subtext">${(activeState.total_cost_usd || 0).toFixed(6)} USD</div>
            </div>

            <div className="glass-panel metric-card">
              <div className="metric-label">
                <span>Self-Healing Interventions</span>
                <AlertTriangle size={16} color="var(--accent-amber)" />
              </div>
              <div className="metric-value" style={{ color: (activeState.healing_events?.length > 0) ? 'var(--accent-amber)' : '#fff' }}>
                {activeState.healing_events?.length || 0}
              </div>
              <div className="metric-subtext">{activeState.recovered_count || 0} Anomalies Auto-Healed</div>
            </div>

            <div className="glass-panel metric-card">
              <div className="metric-label">
                <span>Total Latency</span>
                <RefreshCw size={16} color="var(--accent-cyan)" />
              </div>
              <div className="metric-value">{(activeState.total_duration_ms || 0).toFixed(0)} ms</div>
              <div className="metric-subtext">{activeState.history?.length || 0} Executed Steps</div>
            </div>
          </div>

          {/* Structured Step Flow */}
          <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ArrowRight size={18} color="var(--accent-indigo)" />
              <span>Execution Trajectory & Policy Trace</span>
            </h3>

            <div className="trajectory-stream-container">
              {activeState.history?.map((step, idx) => {
                const isHealed = step.healing_events && step.healing_events.length > 0;
                const isBlocked = step.policy_decision === 'blocked';
                const isSuccess = step.tool_result?.success;

                let cardClass = 'step-card';
                if (isHealed) cardClass += ' step-healed';
                else if (isBlocked) cardClass += ' step-blocked';
                else if (isSuccess) cardClass += ' step-success';

                return (
                  <div key={idx} className={`glass-panel ${cardClass}`}>
                    <div className="step-header">
                      <div className="step-title-group">
                        <span className="step-badge">STEP {step.step_index}</span>
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                          {step.phase.toUpperCase()}
                        </span>
                        {step.tool_call && (
                          <span style={{ fontSize: '0.78rem', background: 'rgba(99,102,241,0.2)', padding: '2px 8px', borderRadius: '4px', color: 'var(--accent-indigo)', fontFamily: 'var(--font-mono)' }}>
                            tool: {step.tool_call.tool_name}
                          </span>
                        )}
                      </div>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {step.duration_ms ? `${step.duration_ms.toFixed(1)}ms` : ''}
                      </span>
                    </div>

                    <div className="step-thought">{step.thought}</div>

                    {step.policy_decision && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', marginBottom: '10px', color: isBlocked ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}>
                        <ShieldAlert size={14} />
                        <span>Security Check: {step.policy_decision.toUpperCase()} - {step.policy_reason}</span>
                      </div>
                    )}

                    {step.tool_call && (
                      <div className="tool-invocation-box">
                        <div style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>// Tool Arguments</div>
                        <pre style={{ color: 'var(--accent-cyan)' }}>{JSON.stringify(step.tool_call.arguments, null, 2)}</pre>
                        {step.tool_result && (
                          <>
                            <div style={{ color: 'var(--text-muted)', margin: '8px 0 4px 0' }}>// Result Payload</div>
                            <pre style={{ color: step.tool_result.success ? '#cbd5e1' : 'var(--accent-rose)', maxHeight: '180px', overflowY: 'auto' }}>
                              {step.tool_result.success
                                ? (typeof step.tool_result.output === 'object' ? JSON.stringify(step.tool_result.output, null, 2) : step.tool_result.output)
                                : step.tool_result.error_message}
                            </pre>
                          </>
                        )}
                      </div>
                    )}

                    {isHealed && step.healing_events.map((h, hIdx) => (
                      <div key={hIdx} className="healing-badge">
                        <AlertTriangle size={14} />
                        <span>Self-Healed Anomaly [{h.failure_type}]: {h.action_taken} ({h.recovery_time_ms.toFixed(1)}ms)</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Multi-agent sub-results */}
          {activeState.sub_results && activeState.sub_results.length > 0 && (
            <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
              <h3 style={{ fontSize: '1.1rem', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Users size={18} color="var(--accent-purple)" />
                <span>Sub-Agent Results</span>
              </h3>
              {activeState.sub_results.map((r, idx) => (
                <div key={idx} className="glass-panel step-card step-success" style={{ marginBottom: '12px' }}>
                  <div className="step-header">
                    <span className="step-badge">AGENT {idx + 1}</span>
                    <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{r.sub_goal}</span>
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#cbd5e1', whiteSpace: 'pre-wrap', marginTop: '8px' }}>{r.output}</div>
                </div>
              ))}
            </div>
          )}

          {/* Final Output Report */}
          {activeState.final_output && (
            <div className="glass-panel" style={{ padding: '24px' }}>
              <h3 style={{ fontSize: '1.1rem', marginBottom: '14px', color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <CheckCircle2 size={18} />
                <span>Synthesized Task Output</span>
              </h3>
              <div style={{ background: 'rgba(10, 13, 20, 0.85)', padding: '20px', borderRadius: '12px', lineHeight: 1.6, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-main)', fontSize: '0.95rem' }}>
                {activeState.final_output}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
