import React, { useState, useEffect, useRef } from 'react';
import {
  Bot,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Send,
  Square,
  Play,
  Loader2,
  ExternalLink,
  ShieldCheck,
  MessageSquare,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { respondToApplyQuestion, stopApplySession } from '../api';
import ErrorBoundary from './ErrorBoundary';

function LiveApplyProgressInner({
  active = false,
  sessionId = null,
  platform = null,
  events = [],
  initialStatus = null,
  initialJobs = [],
  initialPendingQuestion = null,
  collapsible = true,
  defaultExpanded = true,
  onResumeSession = null,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [questionInput, setQuestionInput] = useState('');
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [stoppingSession, setStoppingSession] = useState(false);
  const [answeredQuestions, setAnsweredQuestions] = useState({});
  const logEndRef = useRef(null);

  const safeEvents = Array.isArray(events) ? events : [];
  const isIndeed = platform === 'indeed' || (typeof sessionId === 'string' && sessionId.includes('indeed')) || safeEvents.some(e => e?.platform === 'indeed');
  const platformName = isIndeed ? 'Indeed' : 'LinkedIn';

  // Auto-scroll to latest event
  useEffect(() => {
    if (expanded && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [safeEvents, expanded]);

  // Extract stats from events
  const batchStart = safeEvents.find(e => e?.type === 'apply_batch_start');
  const batchComplete = safeEvents.find(e => e?.type === 'apply_batch_complete' || e?.type === 'apply_complete');
  const loginEvent = safeEvents.filter(e => e?.type === 'apply_login').slice(-1)[0];
  const pendingQuestion = safeEvents.filter(e => e?.type === 'apply_needs_input').slice(-1)[0] || initialPendingQuestion;
  const errorEvent = safeEvents.filter(e => e?.type === 'apply_error').slice(-1)[0];
  const stoppedEvent = safeEvents.filter(e => e?.type === 'apply_stopped').slice(-1)[0];

  // Count statuses from events
  const appliedCount = safeEvents.filter(e => e?.type === 'apply_job_done' && e?.status === 'applied').length;
  const totalJobs = batchStart?.total || batchComplete?.total || (Array.isArray(initialJobs) ? initialJobs.length : 0);

  // Build per-job status map starting from initialJobs if provided
  const jobStatusMap = {};
  if (Array.isArray(initialJobs)) {
    for (const j of initialJobs) {
      if (!j) continue;
      const jid = j.id || j.job_id;
      if (!jid) continue;
      jobStatusMap[jid] = {
        company: j.company || 'Unknown Company',
        title: j.title || 'Job Opening',
        status: j.status || 'queued',
        message: j.message || (j.fitness_score ? `${j.fitness_score}% Fit` : 'Queued'),
      };
    }
  }

  for (const evt of safeEvents) {
    if (!evt) continue;
    const jid = evt.job_id;
    if (!jid) continue;
    if (evt.type === 'apply_job_start') {
      jobStatusMap[jid] = { company: evt.company || jobStatusMap[jid]?.company || '', title: evt.title || jobStatusMap[jid]?.title || '', status: 'in_progress', message: evt.message || '' };
    } else if (evt.type === 'apply_job_done') {
      jobStatusMap[jid] = { company: evt.company || jobStatusMap[jid]?.company || '', title: evt.title || jobStatusMap[jid]?.title || '', status: evt.status || 'applied', message: evt.message || '' };
    } else if (evt.type === 'apply_job_error') {
      jobStatusMap[jid] = { company: evt.company || jobStatusMap[jid]?.company || '', title: evt.title || jobStatusMap[jid]?.title || '', status: 'error', message: evt.message || '' };
    }
  }

  const currentQuestionKey = pendingQuestion ? (pendingQuestion.question || pendingQuestion.field_name) : null;
  const isCurrentQuestionAnswered = currentQuestionKey && !!answeredQuestions[currentQuestionKey];

  // Check if subsequent event arrived after this question
  const questionIndex = pendingQuestion ? safeEvents.findLastIndex(e => e?.type === 'apply_needs_input') : -1;
  const hasProgressAfterQuestion = questionIndex >= 0 && safeEvents.slice(questionIndex + 1).some(e =>
    e?.type === 'apply_input_resolved' || e?.type === 'apply_job_progress' || e?.type === 'apply_job_done' || e?.type === 'apply_job_error'
  );

  const handleSubmitAnswer = async () => {
    if (!questionInput.trim() || !sessionId) return;
    const ans = questionInput.trim();
    const qKey = currentQuestionKey || 'q';
    setSubmittingAnswer(true);
    setAnsweredQuestions(prev => ({ ...prev, [qKey]: ans }));

    try {
      await respondToApplyQuestion(sessionId, ans);
      setQuestionInput('');
    } catch (e) {
      console.error('Failed to submit answer:', e);
    } finally {
      setSubmittingAnswer(false);
    }
  };

  const handleStop = async () => {
    if (!sessionId) return;
    setStoppingSession(true);
    try {
      await stopApplySession(sessionId);
    } catch (e) {
      console.error('Failed to stop session:', e);
    } finally {
      setStoppingSession(false);
    }
  };

  const isComplete = !active && (initialStatus === 'completed' || !!batchComplete);
  const hasError = !active && (initialStatus === 'error' || !!errorEvent);
  const isStopped = !active && (initialStatus === 'stopped' || !!stoppedEvent);
  const isWaitingForInput = !!pendingQuestion && !isComplete && !isCurrentQuestionAnswered && !hasProgressAfterQuestion;

  return (
    <div className="apply-progress-container">
      {/* Header */}
      <div
        className="apply-progress-header"
        onClick={() => collapsible && setExpanded(!expanded)}
        style={{ cursor: collapsible ? 'pointer' : 'default' }}
      >
        <div className="apply-header-left">
          <div className="apply-header-icon">
            {isComplete ? (
              <CheckCircle2 size={18} color="var(--accent-emerald)" />
            ) : hasError ? (
              <XCircle size={18} color="var(--accent-red)" />
            ) : isStopped ? (
              <AlertCircle size={18} color="var(--accent-gold)" />
            ) : (
              <Bot size={18} color="var(--accent-gold)" className={active ? 'animate-pulse' : ''} />
            )}
          </div>
          <div className="apply-header-title">
            <span className="apply-header-text">
              {isComplete
                ? `${platformName} Auto-Apply — Complete`
                : hasError
                  ? `${platformName} Auto-Apply — Error`
                  : isStopped
                    ? `${platformName} Auto-Apply — Paused`
                    : `${platformName} Auto-Apply Agent`}
            </span>
            {isIndeed ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="#2164f4" style={{ marginLeft: '0.3rem' }}>
                <path d="M12.5 3a2.5 2.5 0 0 0-2.5 2.5v13a2.5 2.5 0 0 0 5 0v-13A2.5 2.5 0 0 0 12.5 3zM6 8a2 2 0 0 0-2 2v8a2 2 0 0 0 4 0v-8a2 2 0 0 0-2-2zm12 3a2 2 0 0 0-2 2v5a2 2 0 0 0 4 0v-5a2 2 0 0 0-2-2z"/>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="#0a66c2" style={{ marginLeft: '0.3rem' }}><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg>
            )}
          </div>
        </div>

        <div className="apply-header-right">
          {totalJobs > 0 && (
            <span className="apply-stats-pill">
              {appliedCount}/{totalJobs} applied
            </span>
          )}
          {active && !isComplete && !isStopped && (
            <button
              className="apply-stop-btn"
              onClick={(e) => { e.stopPropagation(); handleStop(); }}
              disabled={stoppingSession}
              title="Stop auto-apply"
            >
              <Square size={12} />
              <span>{stoppingSession ? 'Stopping...' : 'Stop'}</span>
            </button>
          )}
          {collapsible && (
            expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />
          )}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div className="apply-progress-body">
          {/* Login status */}
          {loginEvent && (
            <div className={`apply-status-row ${loginEvent.success ? 'success' : 'error'}`}>
              <ShieldCheck size={14} />
              <span>{loginEvent.message || (loginEvent.success ? 'Login successful' : 'Login failed')}</span>
            </div>
          )}

          {/* Job progress list */}
          {Object.entries(jobStatusMap).length > 0 && (
            <div className="apply-jobs-list">
              {Object.entries(jobStatusMap).map(([jid, data]) => (
                <div key={jid} className={`apply-job-row ${data?.status || 'queued'}`}>
                  <div className="apply-job-status-icon">
                    {data?.status === 'applied' ? (
                      <CheckCircle2 size={14} color="var(--accent-emerald)" />
                    ) : data?.status === 'in_progress' ? (
                      <Loader2 size={14} color="var(--accent-gold)" className="animate-spin" />
                    ) : data?.status === 'error' ? (
                      <XCircle size={14} color="var(--accent-red)" />
                    ) : (
                      <AlertCircle size={14} color="var(--text-muted)" />
                    )}
                  </div>
                  <div className="apply-job-info">
                    <span className="apply-job-company">{data?.company}</span>
                    <span className="apply-job-title">{data?.title}</span>
                  </div>
                  <div className="apply-job-status-badge" data-status={data?.status}>
                    {data?.status === 'applied' ? 'Applied ✓' :
                     data?.status === 'in_progress' ? 'Applying...' :
                     data?.status === 'error' ? 'Error' :
                     data?.status === 'skipped' ? 'Skipped' :
                     data?.status === 'manual_required' ? 'Manual' :
                     data?.status === 'queued' ? 'Queued' :
                     data?.status}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Question prompt (active waiting) */}
          {isWaitingForInput && pendingQuestion && (
            <div className="apply-question-prompt">
              <div className="apply-question-header">
                <MessageSquare size={14} color="var(--accent-gold)" />
                <span>Agent needs your input</span>
              </div>
              <div className="apply-question-text">
                {pendingQuestion.question || `Please provide: ${pendingQuestion.field_name || 'information'}`}
              </div>
              {pendingQuestion.job_title && (
                <div className="apply-question-context">
                  For: {pendingQuestion.job_title}
                </div>
              )}
              <div className="apply-question-input-row">
                <input
                  type="text"
                  className="apply-question-input"
                  placeholder="Type your answer..."
                  value={questionInput}
                  onChange={(e) => setQuestionInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSubmitAnswer()}
                  disabled={submittingAnswer}
                  autoFocus
                />
                <button
                  className="apply-question-submit"
                  onClick={handleSubmitAnswer}
                  disabled={!questionInput.trim() || submittingAnswer}
                >
                  {submittingAnswer ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                </button>
              </div>
            </div>
          )}

          {/* Question submitted banner (resuming) */}
          {isCurrentQuestionAnswered && !hasProgressAfterQuestion && !isComplete && (
            <div style={{
              background: "rgba(16, 185, 129, 0.08)",
              border: "1px solid rgba(16, 185, 129, 0.25)",
              borderRadius: "8px",
              padding: "0.75rem 1rem",
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
              marginTop: "0.5rem"
            }}>
              <CheckCircle2 size={16} color="var(--accent-emerald)" style={{ flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: "0.83rem", fontWeight: 600, color: "var(--text-main)" }}>
                  Answer recorded: <span style={{ color: "var(--accent-emerald)" }}>"{answeredQuestions[currentQuestionKey]}"</span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.2rem" }}>
                  <Loader2 size={12} className="animate-spin" color="var(--accent-gold)" />
                  Continuing application...
                </div>
              </div>
            </div>
          )}

          {/* Event log */}
          <div className="apply-events-log">
            {safeEvents
              .filter(e => e && e.message && e.type !== 'apply_init')
              .slice(-15)
              .map((evt, idx) => {
                const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                return (
                  <div key={idx} className={`apply-event-line ${evt.type?.includes('error') ? 'error' : evt.type?.includes('done') || evt.type?.includes('resolved') ? 'success' : 'info'}`}>
                    <span className="apply-event-time">[{time}]</span>
                    <span className="apply-event-text">{evt?.message}</span>
                  </div>
                );
              })}
            <div ref={logEndRef} />
          </div>

          {/* Error display */}
          {(hasError || errorEvent) && (
            <div className="apply-error-banner">
              <XCircle size={14} />
              <span>{errorEvent?.message || (typeof initialStatus === 'string' && initialStatus !== 'error' ? initialStatus : 'Auto-apply encountered an issue')}</span>
            </div>
          )}

          {/* Stopped / Interrupted Banner with Resume CTA */}
          {isStopped && (
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: "var(--bg-secondary)",
              padding: "0.7rem 0.9rem",
              borderRadius: "8px",
              border: "1px solid var(--border-subtle)",
              marginTop: "0.5rem",
              flexWrap: "wrap",
              gap: "0.5rem"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <AlertCircle size={16} color="var(--accent-gold)" />
                <span style={{ fontSize: "0.82rem", color: "var(--text-main)", fontWeight: 500 }}>
                  Apply session paused or stopped.
                </span>
              </div>
              {onResumeSession && (
                <button
                  className="btn-primary"
                  onClick={onResumeSession}
                  style={{
                    padding: "0.4rem 0.85rem",
                    fontSize: "0.8rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    cursor: "pointer"
                  }}
                >
                  <Play size={13} /> Resume {platformName} Apply
                </button>
              )}
            </div>
          )}

          {/* Completion summary */}
          {isComplete && (batchComplete?.result || batchComplete) && (
            <div className="apply-summary-banner">
              <CheckCircle2 size={16} color="var(--accent-emerald)" />
              <div className="apply-summary-stats">
                <span className="apply-stat applied">✅ {batchComplete?.result?.applied ?? batchComplete?.applied ?? 0} Applied</span>
                <span className="apply-stat skipped">⏭️ {batchComplete?.result?.skipped ?? batchComplete?.skipped ?? 0} Skipped</span>
                <span className="apply-stat errors">❌ {batchComplete?.result?.errors ?? batchComplete?.errors ?? 0} Errors</span>
              </div>
            </div>
          )}

          {/* Waiting indicator */}
          {active && !isComplete && !hasError && !isWaitingForInput && !isCurrentQuestionAnswered && safeEvents.length > 0 && (
            <div className="apply-waiting-row">
              <Loader2 size={14} className="animate-spin" color="var(--accent-gold)" />
              <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                {safeEvents.slice(-1)[0]?.message || 'Processing...'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function LiveApplyProgress(props) {
  return (
    <ErrorBoundary fallback={null}>
      <LiveApplyProgressInner {...props} />
    </ErrorBoundary>
  );
}
