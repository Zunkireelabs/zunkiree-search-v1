import React from 'react';
import { ResultsPanelProps, Source } from '../types';

// Document Icon SVG
const DocumentIcon = () => (
  <svg className="zk-source-link__icon" viewBox="0 0 16 16" fill="currentColor">
    <path d="M4 1.75C4 .784 4.784 0 5.75 0h5.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0114.25 16H5.75A1.75 1.75 0 014 14.25V1.75zm1.75-.25a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V4.664a.25.25 0 00-.073-.177l-2.914-2.914a.25.25 0 00-.177-.073H5.75z" />
  </svg>
);

// Error Icon SVG
const ErrorIcon = () => (
  <svg className="zk-error__icon" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="24" cy="24" r="20" />
    <path d="M24 14v12M24 34h.01" strokeLinecap="round" />
  </svg>
);

// Loading Skeleton
const LoadingSkeleton: React.FC = () => (
  <div className="zk-loading">
    <div className="zk-skeleton zk-skeleton--line" />
    <div className="zk-skeleton zk-skeleton--line" />
    <div className="zk-skeleton zk-skeleton--line" />
  </div>
);

// Source Link Component
const SourceLink: React.FC<{ source: Source }> = ({ source }) => (
  <a
    href={source.url}
    target="_blank"
    rel="noopener noreferrer"
    className="zk-source-link"
  >
    <DocumentIcon />
    {source.title}
  </a>
);

// Error State Component
const ErrorState: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <div className="zk-error">
    <ErrorIcon />
    <div className="zk-error__title">Something went wrong</div>
    <div className="zk-error__message">{message}</div>
    <button className="zk-error__retry" onClick={onRetry}>
      Try again
    </button>
  </div>
);

export const ResultsPanel: React.FC<ResultsPanelProps & { onRetry?: () => void }> = ({
  result,
  isLoading,
  error,
  onSuggestionClick,
  showSources,
  onRetry,
}) => {
  // Don't render if no content to show
  if (!isLoading && !result && !error) {
    return null;
  }

  return (
    <div className="zk-results-panel" role="region" aria-label="Search results" aria-live="polite">
      {/* Loading State */}
      {isLoading && <LoadingSkeleton />}

      {/* Error State */}
      {error && !isLoading && (
        <ErrorState message={error.message} onRetry={onRetry || (() => {})} />
      )}

      {/* Results */}
      {result && !isLoading && !error && (
        <div className="zk-result-card">
          {/* Answer Content */}
          <div className="zk-result-content">
            {result.answer}
          </div>

          {/* Sources */}
          {showSources && result.sources && result.sources.length > 0 && (
            <div className="zk-sources">
              <div className="zk-sources__label">Sources</div>
              {result.sources.map((source, index) => (
                <SourceLink key={index} source={source} />
              ))}
            </div>
          )}

          {/* Follow-up Suggestions */}
          {result.suggestions && result.suggestions.length > 0 && (
            <div className="zk-follow-up">
              <div className="zk-follow-up__label">Related questions</div>
              {result.suggestions.map((suggestion, index) => (
                <button
                  key={index}
                  className="zk-chip"
                  onClick={() => onSuggestionClick(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ResultsPanel;
