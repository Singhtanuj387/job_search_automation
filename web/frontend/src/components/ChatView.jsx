import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  Sparkles,
  ExternalLink,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  BookmarkPlus,
  Paperclip,
  Briefcase,
  Download,
  Package,
  FileText,
  FileCheck,
  Terminal,
  Clock,
  ShieldCheck,
  Key,
} from 'lucide-react';
import { sendMessage, sendMessageStream, addToTracker, startLinkedInApply, startIndeedApply, startSeekApply, getActiveApplySession, reconnectApplySession, respondToApplyQuestion } from '../api';
import FormattedMessage from './FormattedMessage';
import JobResultsTable from './JobResultsTable';
import LiveWebSearch from './LiveWebSearch';
import LiveApplyProgress from './LiveApplyProgress';

const ALL_SEARCH_PLATFORMS = [
  { source: 'linkedin', domain: 'linkedin.com/jobs' },
  { source: 'naukri', domain: 'naukri.com' },
  { source: 'instahyre', domain: 'instahyre.com' },
  { source: 'cutshort', domain: 'cutshort.io' },
  { source: 'weworkremotely', domain: 'weworkremotely.com' },
  { source: 'hirist', domain: 'hirist.tech' },
  { source: 'indeed', domain: 'in.indeed.com' },
  { source: 'wellfound', domain: 'wellfound.com' },
  { source: 'greenhouse', domain: 'boards.greenhouse.io' },
  { source: 'lever', domain: 'jobs.lever.co' },
  { source: 'foundit', domain: 'foundit.in' },
  { source: 'shine', domain: 'shine.com' },
  { source: 'glassdoor', domain: 'glassdoor.co.in' },
  { source: 'timesjobs', domain: 'timesjobs.com' },
  { source: 'arbeitnow', domain: 'arbeitnow.com' },
  { source: 'jobicy', domain: 'jobicy.com' },
  { source: 'remotive', domain: 'remotive.com' },
  { source: 'seek', domain: 'seek.com.au' },
  { source: 'career_jsonld', domain: 'careers.company.com' },
];

export default function ChatView({
  session,
  messages,
  onNewMessage,
  onOpenOnboarding,
  onOpenSettings,
  profile
}) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [savedJobs, setSavedJobs] = useState({});
  const [liveStreamSearch, setLiveStreamSearch] = useState({
    active: false,
    sources: [],
    tailoringMessage: null,
    eventsLog: [],
  });
  const [liveApplyState, setLiveApplyState] = useState({
    active: false,
    sessionId: null,
    events: [],
    status: null,
    initialJobs: [],
  });
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, liveStreamSearch, liveApplyState]);

  // Restore live apply session state on page refresh or component mount
  useEffect(() => {
    let isMounted = true;
    async function checkActiveApply() {
      try {
        const activeSess = await getActiveApplySession();
        if (!isMounted || !activeSess || !activeSess.session_id) return;

        const isRunning = activeSess.active || activeSess.status === 'running' || activeSess.status === 'waiting_for_input';
        setLiveApplyState({
          active: isRunning,
          sessionId: activeSess.session_id,
          events: activeSess.events || [],
          status: activeSess.status,
          initialJobs: activeSess.jobs || activeSess.results || [],
          pendingQuestion: activeSess.pending_question,
        });

        // If session is actively running, establish SSE stream reconnection
        if (isRunning) {
          reconnectApplySession(activeSess.session_id, (evt) => {
            if (!isMounted) return;
            setLiveApplyState(prev => {
              const isTerminal = evt.type === 'apply_complete' || evt.type === 'apply_stopped' || evt.type === 'apply_error';
              return {
                ...prev,
                events: [...prev.events, evt],
                sessionId: evt.session_id || prev.sessionId,
                active: !isTerminal,
                status: isTerminal ? (evt.type === 'apply_complete' ? 'completed' : 'stopped') : prev.status,
              };
            });
          }).catch(err => {
            console.warn("SSE reconnect ended:", err);
          });
        }
      } catch (err) {
        console.warn("Failed to query active apply session:", err);
      }
    }
    checkActiveApply();
    return () => { isMounted = false; };
  }, []);

  const handleSend = async (textToSend) => {
    const text = textToSend || input;
    if (!text.trim() || loading || !session) return;

    setInput("");
    setLoading(true);

    // Optimistically show user message
    onNewMessage({
      role: "user",
      content: text,
      created_at: new Date().toISOString()
    });

    const lowerText = text.toLowerCase().trim();
    // Exclude non-search commands first
    const isApplyIntent = lowerText.includes("apply") || lowerText.startsWith("/job-skill apply");
    const isNonSearchCommand = isApplyIntent ||
                               lowerText.startsWith("/job-skill status") ||
                               lowerText.startsWith("/job-skill help") ||
                               lowerText.startsWith("/job-skill automate") ||
                               lowerText.startsWith("/linkedin-login") ||
                               lowerText.startsWith("/indeed-login") ||
                               lowerText.startsWith("/seek-login");

    // If an apply session is actively waiting for input (e.g. Indeed OTP code or screening answer), route to apply agent directly
    const pendingInputEvent = liveApplyState.active && liveApplyState.sessionId &&
      liveApplyState.events?.filter(e => e.type === 'apply_needs_input').slice(-1)[0];
    const qIdx = pendingInputEvent ? liveApplyState.events?.findLastIndex(e => e.type === 'apply_needs_input') : -1;
    const hasResolvedAfter = qIdx >= 0 && liveApplyState.events?.slice(qIdx + 1).some(e => e.type === 'apply_input_resolved');

    if (pendingInputEvent && !hasResolvedAfter && !lowerText.startsWith('/')) {
      try {
        await respondToApplyQuestion(liveApplyState.sessionId, text.trim());
      } catch (err) {
        console.error('Failed to submit chat answer to apply agent:', err);
      }
    }

    // Only pre-populate search UI optimistically if it is an explicit search command
    const isExplicitSearch = !isNonSearchCommand && (
                             lowerText.startsWith("/job-skill search") ||
                             lowerText.startsWith("/search")
    );

    if (isExplicitSearch) {
      // Reset apply state so it doesn't override the search UI
      setLiveApplyState({ active: false, sessionId: null, events: [], status: null, initialJobs: [] });

      const defaultRole = profile?.role || 'Software Engineer';
      const defaultLoc = profile?.location && profile.location !== 'any' ? profile.location : 'Bangalore';
      const initialSources = ALL_SEARCH_PLATFORMS.map((p, idx) => ({
        source: p.source,
        domain: p.domain,
        site_query: `site:${p.domain} "${defaultRole}" ${defaultLoc}`.trim(),
        status: idx === 0 ? 'searching' : 'pending',
        count: 0,
        jobs: []
      }));

      const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      setLiveStreamSearch({
        active: true,
        tailoringMessage: null,
        sources: initialSources,
        eventsLog: [
          { time: `[${nowTime}]`, badge: 'SPIDER', text: `Queueing ${ALL_SEARCH_PLATFORMS.length} verified platforms for "${defaultRole}" in ${defaultLoc}...`, type: 'info' }
        ],
      });
    } else {
      // Keep search UI strictly disabled for general chat / questions
      setLiveStreamSearch({ active: false, sources: [], tailoringMessage: null, eventsLog: [] });
    }

    try {
      const assistantMsg = await sendMessageStream(session.id, text, (evt) => {
        const timeTag = `[${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}]`;

        if (evt.type === 'intent') {
          if (evt.intent === 'search') {
            const defaultRole = evt.intent_data?.role || profile?.role || 'Software Engineer';
            const defaultLoc = evt.intent_data?.location || profile?.location || 'Bangalore';
            const initialSources = ALL_SEARCH_PLATFORMS.map((p, idx) => ({
              source: p.source,
              domain: p.domain,
              site_query: `site:${p.domain} "${defaultRole}" ${defaultLoc}`.trim(),
              status: idx === 0 ? 'searching' : 'pending',
              count: 0,
              jobs: []
            }));
            setLiveApplyState({ active: false, sessionId: null, events: [], status: null, initialJobs: [] });
            setLiveStreamSearch({
              active: true,
              tailoringMessage: null,
              sources: initialSources,
              eventsLog: [
                { time: timeTag, badge: 'SPIDER', text: `Queueing ${ALL_SEARCH_PLATFORMS.length} verified platforms for "${defaultRole}" in ${defaultLoc}...`, type: 'info' }
              ],
            });
          } else {
            setLiveStreamSearch({ active: false, sources: [], tailoringMessage: null, eventsLog: [] });
          }
        } else if (evt.type === 'source_searching') {
          setLiveStreamSearch((prev) => {
            const exists = prev.sources.some(s => s.source === evt.source);
            let updated;
            if (exists) {
              updated = prev.sources.map(s => s.source === evt.source ? { ...s, status: 'searching', site_query: evt.site_query || s.site_query } : s);
            } else {
              updated = [...prev.sources, { source: evt.source, domain: evt.domain || `${evt.source}.com`, site_query: evt.site_query, status: 'searching', count: 0, jobs: [] }];
            }
            return {
              ...prev,
              sources: updated,
              eventsLog: [
                ...prev.eventsLog,
                { time: timeTag, badge: 'PROBE', text: `Spidering ${evt.domain || evt.source} for matching openings...`, type: 'info' }
              ]
            };
          });
        } else if (evt.type === 'source_results') {
          setLiveStreamSearch((prev) => {
            const exists = prev.sources.some(s => s.source === evt.source);
            let updated;
            if (exists) {
              updated = prev.sources.map(s => s.source === evt.source ? {
                ...s,
                status: 'done',
                count: evt.count,
                jobs: evt.jobs || [],
                site_query: evt.site_query || s.site_query,
              } : s);
            } else {
              updated = [...prev.sources, {
                source: evt.source,
                domain: evt.domain || `${evt.source}.com`,
                site_query: evt.site_query,
                status: 'done',
                count: evt.count,
                jobs: evt.jobs || []
              }];
            }
            return {
              ...prev,
              sources: updated,
              eventsLog: [
                ...prev.eventsLog,
                {
                  time: timeTag,
                  badge: 'MATCH',
                  text: `${(evt.source || 'platform').toUpperCase()}: Discovered ${evt.count} qualified positions`,
                  type: evt.count > 0 ? 'success' : 'muted'
                }
              ]
            };
          });
        } else if (evt.type === 'tailoring') {
          setLiveStreamSearch((prev) => ({
            ...prev,
            tailoringMessage: evt.message || 'Scoring candidate fitness across opportunities...',
            eventsLog: [
              ...prev.eventsLog,
              { time: timeTag, badge: 'FIT', text: evt.message || 'Scoring skills fitness & matching opportunities...', type: 'gold' }
            ]
          }));
        }
      });

      if (assistantMsg) {
        onNewMessage(assistantMsg);

        // If the assistant message indicates apply_ready, auto-start the apply session
        if (assistantMsg.metadata?.apply_ready) {
          const isIndeed = assistantMsg.metadata?.platform === 'indeed';
          const isSeek = assistantMsg.metadata?.platform === 'seek';
          const platformLabel = isSeek ? 'SEEK' : (isIndeed ? 'Indeed' : 'LinkedIn');
          const previewJobs = isSeek
            ? (assistantMsg.metadata.seek_jobs_preview || [])
            : isIndeed
            ? (assistantMsg.metadata.indeed_jobs_preview || [])
            : (assistantMsg.metadata.linkedin_jobs_preview || []);

          setLiveApplyState({
            active: true,
            sessionId: null,
            events: [],
            status: 'running',
            initialJobs: previewJobs,
            platform: isSeek ? 'seek' : (isIndeed ? 'indeed' : 'linkedin'),
          });
          try {
            const startFn = isSeek ? startSeekApply : (isIndeed ? startIndeedApply : startLinkedInApply);
            const applyResult = await startFn(25, (evt) => {
              setLiveApplyState((prev) => ({
                ...prev,
                sessionId: evt.session_id || prev.sessionId,
                events: [...prev.events, evt],
                status: evt.type === 'apply_complete' ? 'completed' : evt.type === 'apply_stopped' ? 'stopped' : 'running',
              }));
            });
            // Add summary message
            if (applyResult) {
              const r = applyResult.result || {};
              onNewMessage({
                role: 'assistant',
                content: `### ✅ ${platformLabel} Auto-Apply Session Complete\n\n` +
                  `**Applied:** ${r.applied || 0} | **Skipped:** ${r.skipped || 0} | **Errors:** ${r.errors || 0}\n\n` +
                  `All applied jobs have been added to your **Application Tracker**.`,
                created_at: new Date().toISOString(),
                metadata: { type: 'apply_complete', platform: isSeek ? 'seek' : (isIndeed ? 'indeed' : 'linkedin'), ...r },
              });
            }
          } catch (applyErr) {
            onNewMessage({
              role: 'assistant',
              content: `❌ ${platformLabel} Auto-apply error: ${applyErr.message}`,
              created_at: new Date().toISOString(),
            });
          } finally {
            setLiveApplyState((prev) => ({ ...prev, active: false }));
          }
        }
      }
    } catch (err) {
      onNewMessage({
        role: "assistant",
        content: `Sorry, an error occurred while processing your request: ${err.message}`,
        created_at: new Date().toISOString()
      });
    } finally {
      setLoading(false);
      setLiveStreamSearch({ active: false, sources: [], tailoringMessage: null, eventsLog: [] });
    }
  };

  const handleSaveToTracker = async (job) => {
    try {
      await addToTracker({
        job_id: job.source_job_id,
        company: job.company,
        title: job.title,
        location: job.location,
        apply_url: job.apply_url,
        status: "found",
        source: job.source
      });
      setSavedJobs((prev) => ({ ...prev, [job.source_job_id]: true }));
    } catch (e) {
      console.error(e);
    }
  };

  const skillCommands = [
    { cmd: "/job-skill search", label: "🔍 /job-skill search" },
    { cmd: "/job-skill apply linkedin", label: "🤖 /job-skill apply linkedin" },
    { cmd: "/job-skill apply indeed", label: "🤖 /job-skill apply indeed" },
    { cmd: "/job-skill apply seek", label: "🤖 /job-skill apply seek" },
    { action: "credentials", label: "🔐 Platform Credentials Vault" },
    { cmd: "/job-skill status", label: "📊 /job-skill status" },
    { cmd: "/job-skill automate", label: "⏰ /job-skill automate" },
    { cmd: "/job-skill help", label: "📖 /job-skill help" },
  ];

  const quickPrompts = [
    `Find ${profile?.role || 'React Developer'} jobs in ${profile?.location || 'Bangalore'}`,
    "What's the status of my applications?",
    "Show senior Python backend roles",
    "Schedule automated nightly job scan"
  ];

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((msg, index) => {
          const userInitial = profile?.name ? profile.name.trim().charAt(0).toUpperCase() : 'U';
          const hasJobs = Boolean(msg.metadata?.jobs && msg.metadata.jobs.length > 0);

          // Extract clean conversational intro when jobs table is present (prevents giant wall of 27 text paragraphs)
          let displayContent = msg.content;
          if (hasJobs && msg.role === 'assistant') {
            const lines = msg.content.split('\n');
            const introLines = [];
            for (const l of lines) {
              const trimmed = l.trim();
              if (
                trimmed.startsWith('|') ||
                trimmed.startsWith('# |') ||
                trimmed.startsWith('📦') ||
                trimmed.toLowerCase().includes('match analysis') ||
                /^\d+\.\s+\*\*/.test(trimmed)
              ) {
                break;
              }
              introLines.push(l);
            }
            const cleanIntro = introLines.join('\n').trim();
            if (cleanIntro) {
              displayContent = cleanIntro;
            }
          }

          return (
            <div key={index} className={`chat-message ${msg.role}`}>
              <div className={`chat-avatar ${msg.role}`}>
                {msg.role === 'user' ? userInitial : <Sparkles size={16} />}
              </div>
              <div className={`message-bubble ${hasJobs ? 'has-data-table' : ''}`}>
                {/* Clean formatted chat reply */}
                <FormattedMessage
                  content={displayContent}
                  stripTable={hasJobs}
                />

                {/* Live Web Discovery accordion (Claude-style) */}
                {msg.metadata?.search_sources && msg.metadata.search_sources.length > 0 && (
                  <LiveWebSearch
                    sources={msg.metadata.search_sources}
                    active={false}
                    collapsible={true}
                    defaultExpanded={false}
                  />
                )}

                {/* Clean, proper matrix table */}
                {hasJobs && (
                  <JobResultsTable
                    jobs={msg.metadata.jobs}
                    onSaveToTracker={handleSaveToTracker}
                    savedJobs={savedJobs}
                  />
                )}

                {/* Apply progress widget attached directly to the latest apply_ready assistant message */}
                {msg.metadata?.apply_ready && index === messages.findLastIndex(m => m.metadata?.apply_ready) && (
                  <div style={{ marginTop: "1rem" }}>
                    <LiveApplyProgress
                      active={liveApplyState.active}
                      sessionId={liveApplyState.sessionId || msg.metadata?.apply_session_id}
                      platform={liveApplyState.platform || msg.metadata?.platform}
                      events={liveApplyState.events}
                      initialStatus={liveApplyState.status || (liveApplyState.active ? 'running' : 'stopped')}
                      initialJobs={msg.metadata.seek_jobs_preview || msg.metadata.indeed_jobs_preview || msg.metadata.linkedin_jobs_preview || liveApplyState.initialJobs || []}
                      initialPendingQuestion={liveApplyState.pendingQuestion}
                      collapsible={true}
                      defaultExpanded={true}
                      onResumeSession={() => handleSend(msg.metadata?.platform === 'seek' ? '/job-skill apply seek' : (msg.metadata?.platform === 'indeed' ? '/job-skill apply indeed' : '/job-skill apply linkedin'))}
                    />
                  </div>
                )}

                {/* Apply progress (for completed apply sessions in history) */}
                {msg.metadata?.type === 'apply_complete' && (
                  <LiveApplyProgress
                    active={false}
                    collapsible={true}
                    defaultExpanded={false}
                    events={[{
                      type: 'apply_batch_complete',
                      result: {
                        applied: msg.metadata.applied || 0,
                        skipped: msg.metadata.skipped || 0,
                        errors: msg.metadata.errors || 0,
                      },
                      total: (msg.metadata.applied || 0) + (msg.metadata.skipped || 0) + (msg.metadata.errors || 0),
                      message: 'Auto-apply session complete',
                    }]}
                  />
                )}

                {/* Platform Credentials CTA banner if credentials are needed */}
                {msg.metadata?.needs_credentials && (
                  <div style={{
                    marginTop: "0.85rem",
                    padding: "0.85rem 1rem",
                    background: "rgba(217, 119, 6, 0.08)",
                    borderRadius: "8px",
                    border: "1px solid rgba(217, 119, 6, 0.3)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "0.75rem",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                      <ShieldCheck size={20} color="var(--accent-gold)" style={{ flexShrink: 0 }} />
                      <div>
                        <div style={{ fontSize: "0.88rem", fontWeight: 600, color: "var(--text-main)" }}>
                          Local Platform Credentials Vault
                        </div>
                        <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                          No passwords in chat. Stored locally with AES-256 encryption.
                        </div>
                      </div>
                    </div>
                    <button
                      className="btn-primary"
                      onClick={() => onOpenSettings && onOpenSettings('platforms')}
                      style={{
                        padding: "0.45rem 0.9rem",
                        fontSize: "0.82rem",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        cursor: "pointer",
                      }}
                    >
                      <Key size={14} /> Open Platform Credentials
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="chat-message assistant">
            <div className="chat-avatar assistant"><Sparkles size={16} /></div>
            <div className="message-bubble has-data-table" style={{ width: "100%" }}>
              {liveStreamSearch.active && liveStreamSearch.sources.length > 0 ? (
                <LiveWebSearch
                  sources={liveStreamSearch.sources}
                  active={true}
                  tailoringMessage={liveStreamSearch.tailoringMessage}
                  eventsLog={liveStreamSearch.eventsLog}
                  collapsible={false}
                  defaultExpanded={true}
                />
              ) : liveApplyState.active && !messages.some(m => m.metadata?.apply_ready) ? (
                <LiveApplyProgress
                  active={true}
                  sessionId={liveApplyState.sessionId}
                  events={liveApplyState.events}
                  collapsible={false}
                  defaultExpanded={true}
                />
              ) : (
                <div style={{ color: "var(--text-muted)", fontStyle: "italic", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem" }}>
                  <Sparkles size={16} className="animate-spin" color="var(--accent-gold)" />
                  <span>{liveStreamSearch.active ? "Searching 18+ verified platforms and scoring candidate fitness across opportunities..." : "Thinking & drafting response..."}</span>
                </div>
              )}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick suggestions & Input */}
      <div className="chat-input-area">
        {/* Commands Bar */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.4rem" }}>
          {skillCommands.map((c, idx) => (
            <button
              key={idx}
              className="prompt-chip"
              onClick={() => {
                if (c.action === 'credentials') {
                  onOpenSettings && onOpenSettings('platforms');
                } else {
                  handleSend(c.cmd);
                }
              }}
              style={{ fontSize: "0.75rem", padding: "0.25rem 0.55rem", borderColor: "rgba(217, 119, 6, 0.4)", color: "var(--accent-gold)" }}
            >
              {c.label}
            </button>
          ))}
        </div>

        {messages.length < 3 && (
          <div className="quick-prompts">
            {quickPrompts.map((p, idx) => (
              <button key={idx} className="prompt-chip" onClick={() => handleSend(p)}>
                {p}
              </button>
            ))}
          </div>
        )}

        <form className="input-box" onSubmit={(e) => { e.preventDefault(); handleSend(); }}>
          <button
            type="button"
            className="btn-icon-copy"
            onClick={onOpenOnboarding}
            title="Update Resume or Target Profile"
            style={{ marginRight: "0.25rem" }}
          >
            <Paperclip size={18} />
          </button>
          <button
            type="button"
            className="btn-icon-copy"
            onClick={() => onOpenSettings && onOpenSettings('platforms')}
            title="Platform Credentials Vault (LinkedIn, etc.)"
            style={{ marginRight: "0.25rem" }}
          >
            <Key size={17} color="var(--accent-gold)" />
          </button>
          <input
            className="chat-input"
            placeholder="Ask anything: 'Find React jobs in Bangalore', 'Check status', or paste a URL..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="btn-primary" disabled={loading || !input.trim()} style={{ padding: "0.5rem 0.85rem" }}>
            <Send size={15} />
          </button>
        </form>
      </div>
    </div>
  );
}
