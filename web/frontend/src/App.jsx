import React, { useState, useEffect } from 'react';
import {
  Briefcase,
  Clock,
  Settings,
  Plus,
  Compass,
  FileText,
  ShieldAlert,
  UserCheck,
  Trash2,
  History,
  Search,
  Sun,
  Moon
} from 'lucide-react';
import ChatView from './components/ChatView';
import TrackerView from './components/TrackerView';
import OpportunitiesView from './components/OpportunitiesView';
import ProfileView from './components/ProfileView';
import OnboardingModal from './components/OnboardingModal';
import SettingsModal from './components/SettingsModal';
import AutomateModal from './components/AutomateModal';
import ErrorBoundary from './components/ErrorBoundary';
import { getProfile, listSessions, createSession, getSessionMessages, deleteSession, getOpportunitiesStats } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState("chat"); // "chat" | "tracker" | "opportunities" | "profile"
  const [opportunitiesCount, setOpportunitiesCount] = useState(0);
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [profile, setProfile] = useState(null);

  // Theme Management (Light / Dark)
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('app-theme') || 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('app-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'));
  };

  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState("ai");
  const [isAutomateOpen, setIsAutomateOpen] = useState(false);

  // Initialize profile and session list
  useEffect(() => {
    async function init() {
      try {
        const profRes = await getProfile();
        if (profRes.has_profile) {
          setProfile(profRes.profile);
        } else {
          // Open onboarding on first visit
          setIsOnboardingOpen(true);
        }

        const sessList = await listSessions();
        setSessions(sessList);
        if (sessList.length > 0) {
          setCurrentSession(sessList[0]);
          const msgs = await getSessionMessages(sessList[0].id);
          setMessages(msgs);
        }

        const oppStats = await getOpportunitiesStats();
        if (oppStats && oppStats.total_opportunities) {
          setOpportunitiesCount(oppStats.total_opportunities);
        }
      } catch (err) {
        console.error("Initialization error:", err);
      }
    }
    init();
  }, []);

  const refreshSessions = async () => {
    try {
      const sessList = await listSessions();
      setSessions(sessList);
    } catch (e) {
      console.error("Failed to refresh sessions:", e);
    }
  };

  const handleSelectSession = async (sess) => {
    if (currentSession?.id === sess.id && activeTab === "chat") return;
    setCurrentSession(sess);
    setActiveTab("chat");
    try {
      const msgs = await getSessionMessages(sess.id);
      setMessages(msgs);
    } catch (e) {
      console.error("Failed to load messages for session:", e);
    }
  };

  const handleNewSession = async () => {
    try {
      const newSess = await createSession("New Search");
      setSessions((prev) => [newSess, ...prev]);
      setCurrentSession(newSess);
      setMessages([]);
      setActiveTab("chat");
    } catch (e) {
      console.error("Failed to create new session:", e);
    }
  };

  const handleDeleteSession = async (e, sessId) => {
    e.stopPropagation();
    try {
      await deleteSession(sessId);
      const remaining = sessions.filter((s) => s.id !== sessId);
      setSessions(remaining);

      // If the currently active session was deleted, switch to another or create a fresh one
      if (currentSession?.id === sessId) {
        if (remaining.length > 0) {
          handleSelectSession(remaining[0]);
        } else {
          handleNewSession();
        }
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const handleNewMessage = async (msg) => {
    setMessages((prev) => [...prev, msg]);
    // Refresh sessions list to pick up auto-generated titles
    refreshSessions();
    // Refresh opportunities badge count
    try {
      const oppStats = await getOpportunitiesStats();
      if (oppStats && oppStats.total_opportunities) {
        setOpportunitiesCount(oppStats.total_opportunities);
      }
    } catch (e) {}
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        {/* Brand Header */}
        <div className="sidebar-brand">
          <div className="brand-logo">
            <Compass size={20} color="var(--accent-gold)" />
            <span className="brand-title">Navigator</span>
            <span className="badge-pro">PRO</span>
          </div>
          <button
            type="button"
            className="btn-theme-toggle"
            onClick={toggleTheme}
            title={theme === 'dark' ? "Switch to Warm Light Theme" : "Switch to Dark Theme"}
            aria-label="Toggle light/dark theme"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>

        {/* New Search Action */}
        <div className="sidebar-action">
          <button className="btn-new-search" onClick={handleNewSession}>
            <Plus size={16} />
            <span>New Search</span>
          </button>
        </div>

        {/* Primary Navigation */}
        <div className="nav-section">
          <button
            className={`nav-button ${activeTab === 'tracker' ? 'active' : ''}`}
            onClick={() => setActiveTab('tracker')}
          >
            <Briefcase size={17} strokeWidth={2} />
            <span>Application Tracker</span>
          </button>

          <button
            className={`nav-button ${activeTab === 'opportunities' ? 'active' : ''}`}
            onClick={() => setActiveTab('opportunities')}
          >
            <Compass size={17} strokeWidth={2} />
            <span>Total Job Opportunities</span>
            {opportunitiesCount > 0 && (
              <span className="nav-count-pill">{opportunitiesCount}</span>
            )}
          </button>

          <button
            className={`nav-button ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
          >
            <UserCheck size={17} strokeWidth={2} />
            <span>Candidate Profile</span>
          </button>

          <button
            className="nav-button"
            onClick={() => setIsAutomateOpen(true)}
          >
            <Clock size={17} strokeWidth={2} />
            <span>Nightly Automate</span>
          </button>

          <button
            className="nav-button"
            onClick={() => {
              setSettingsTab("ai");
              setIsSettingsOpen(true);
            }}
          >
            <Settings size={17} strokeWidth={2} />
            <span>Settings & Vault</span>
          </button>
        </div>

        {/* Claude-Style Recent Chats & Search History */}
        <div className="sidebar-history-section">
          <div className="history-section-header">
            <span className="history-label">Recent Searches</span>
            <span className="history-count">{sessions.length}</span>
          </div>

          <div className="history-sessions-list">
            {sessions.length === 0 ? (
              <div className="history-empty-note">No search history yet</div>
            ) : (
              sessions.map((sess) => {
                const isSelected = currentSession?.id === sess.id && activeTab === 'chat';
                return (
                  <div
                    key={sess.id}
                    className={`history-session-item ${isSelected ? 'active' : ''}`}
                    onClick={() => handleSelectSession(sess)}
                    title={sess.title || "Career Search"}
                  >
                    <div className="session-item-main">
                      <Search size={13} strokeWidth={2} className="session-item-icon" />
                      <span className="session-item-title">
                        {sess.title || "Career Search"}
                      </span>
                    </div>

                    <button
                      className="btn-delete-session"
                      onClick={(e) => handleDeleteSession(e, sess.id)}
                      title="Delete chat session"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Profile Badge */}
        <div className="sidebar-profile">
          <div
            className={`profile-card ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveTab('profile')}
            title="Click to view & edit Candidate Profile"
            style={{ cursor: 'pointer' }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="profile-role">{profile?.role || "Set Target Role"}</span>
              <UserCheck size={14} color="var(--accent-gold)" />
            </div>
            <div className="profile-meta">
              <span>{profile?.location || "Any location"}</span>
              <span>•</span>
              <span>{profile?.seniority?.toUpperCase() || "MID"}</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content View */}
      <main className="main-content">
        <ErrorBoundary title="View Error">
          {activeTab === 'chat' ? (
            <ChatView
              session={currentSession}
              messages={messages}
              onNewMessage={handleNewMessage}
              onOpenOnboarding={() => setActiveTab('profile')}
              onOpenSettings={(tab) => {
                setSettingsTab(tab || "ai");
                setIsSettingsOpen(true);
              }}
              profile={profile}
            />
          ) : activeTab === 'opportunities' ? (
            <OpportunitiesView onOpenChat={() => setActiveTab('chat')} />
          ) : activeTab === 'tracker' ? (
            <TrackerView />
          ) : (
            <ProfileView onProfileUpdated={(newProf) => setProfile(newProf)} />
          )}
        </ErrorBoundary>
      </main>

      {/* Modals */}
      <OnboardingModal
        isOpen={isOnboardingOpen}
        onClose={() => setIsOnboardingOpen(false)}
        onComplete={(newProf) => setProfile(newProf)}
        initialProfile={profile}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        initialTab={settingsTab}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <AutomateModal
        isOpen={isAutomateOpen}
        onClose={() => setIsAutomateOpen(false)}
      />
    </div>
  );
}
