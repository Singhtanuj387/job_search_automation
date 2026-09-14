import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          margin: '1rem 0',
          padding: '1.25rem',
          background: 'var(--bg-secondary, #1a1d24)',
          border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.1))',
          borderRadius: '10px',
          color: 'var(--text-main, #ffffff)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <AlertCircle size={20} color="var(--accent-gold, #f59e0b)" />
            <span style={{ fontWeight: 600, fontSize: '0.92rem' }}>
              {this.props.title || 'Component Error'}
            </span>
          </div>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted, #94a3b8)', lineHeight: 1.5 }}>
            {this.state.error?.message || 'Something went wrong while rendering this section.'}
          </div>
          <div>
            <button
              onClick={this.handleReset}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                background: 'var(--accent-gold, #f59e0b)',
                color: '#000000',
                border: 'none',
                borderRadius: '6px',
                padding: '0.4rem 0.85rem',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <RefreshCw size={13} /> Retry
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
