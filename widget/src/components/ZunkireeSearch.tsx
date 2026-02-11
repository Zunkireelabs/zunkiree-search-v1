import React, { useState, useEffect, useCallback } from 'react';
import { SearchBar } from './SearchBar';
import { ResultsPanel } from './ResultsPanel';
import { QuickActions } from './QuickActions';
import { PoweredBy } from './PoweredBy';
import { getStyles } from '../styles';
import {
  WidgetConfig,
  SearchResult,
  SearchError,
  EmbedMode,
  BorderRadiusStyle,
} from '../types';

interface ZunkireeSearchProps {
  siteId: string;
  apiUrl: string;
  mode?: EmbedMode;
  borderRadius?: BorderRadiusStyle;
}

// Default configuration
const DEFAULT_CONFIG: Omit<WidgetConfig, 'siteId' | 'apiUrl'> = {
  mode: 'hero',
  brandName: 'Search',
  primaryColor: '#2563EB',
  placeholderText: 'What would you like to know?',
  showPoweredBy: true,
  showQuickActions: true,
  quickActions: [],
  showSources: true,
  borderRadius: 'rounded',
};

export const ZunkireeSearch: React.FC<ZunkireeSearchProps> = ({
  siteId,
  apiUrl,
  mode: modeProp,
  borderRadius: borderRadiusProp,
}) => {
  // State
  const [config, setConfig] = useState<WidgetConfig>({
    ...DEFAULT_CONFIG,
    siteId,
    apiUrl,
    mode: modeProp || DEFAULT_CONFIG.mode,
    borderRadius: borderRadiusProp || DEFAULT_CONFIG.borderRadius,
  });
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<SearchError | null>(null);
  const [stylesInjected, setStylesInjected] = useState(false);

  // Inject styles
  useEffect(() => {
    if (stylesInjected) return;

    const styleId = 'zunkiree-search-styles';
    let styleEl = document.getElementById(styleId) as HTMLStyleElement;

    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = styleId;
      document.head.appendChild(styleEl);
    }

    styleEl.textContent = getStyles(config.primaryColor);
    setStylesInjected(true);
  }, [config.primaryColor, stylesInjected]);

  // Fetch configuration from API
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/widget/config/${siteId}`);
        if (response.ok) {
          const data = await response.json();
          setConfig((prev) => ({
            ...prev,
            brandName: data.brand_name || prev.brandName,
            primaryColor: data.primary_color || prev.primaryColor,
            placeholderText: data.placeholder_text || prev.placeholderText,
            quickActions: data.quick_actions || prev.quickActions,
            showPoweredBy: data.show_powered_by ?? prev.showPoweredBy,
            showSources: data.show_sources ?? prev.showSources,
          }));

          // Update styles with new primary color
          const styleEl = document.getElementById('zunkiree-search-styles');
          if (styleEl && data.primary_color) {
            styleEl.textContent = getStyles(data.primary_color);
          }
        }
      } catch (err) {
        console.warn('Failed to fetch widget config, using defaults');
      }
    };

    fetchConfig();
  }, [apiUrl, siteId]);

  // Search handler
  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    setResult(null);

    const payload = { site_id: siteId, question: query };
    console.log('[Zunkiree] Request payload:', payload);

    try {
      const response = await fetch(`${apiUrl}/api/v1/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error('[Zunkiree] Error response:', response.status, errorData);
        throw new Error(errorData.error?.message || 'Search failed');
      }

      const data = await response.json();
      setResult({
        answer: data.answer,
        suggestions: data.suggestions || [],
        sources: data.sources || [],
      });
    } catch (err) {
      setError({
        code: 'SEARCH_ERROR',
        message: err instanceof Error ? err.message : 'An error occurred',
      });
    } finally {
      setIsLoading(false);
    }
  }, [apiUrl, siteId, query]);

  // Handle suggestion click
  const handleSuggestionClick = useCallback((suggestion: string) => {
    setQuery(suggestion);
    // Auto-submit after a short delay
    setTimeout(() => {
      handleSearch();
    }, 100);
  }, [handleSearch]);

  // Handle quick action click
  const handleQuickActionClick = useCallback((action: string) => {
    setQuery(action);
  }, []);

  // Retry handler
  const handleRetry = useCallback(() => {
    handleSearch();
  }, [handleSearch]);

  // Container class based on mode
  const containerClass = `zk-widget zk-container zk-container--${config.mode}`;

  return (
    <div className={containerClass}>
      {/* Search Bar */}
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={handleSearch}
        placeholder={config.placeholderText}
        isLoading={isLoading}
        mode={config.mode}
        borderRadius={config.borderRadius}
        primaryColor={config.primaryColor}
      />

      {/* Powered By Badge */}
      <PoweredBy show={config.showPoweredBy} />

      {/* Quick Actions (shown when no results) */}
      {!result && !isLoading && !error && config.showQuickActions && (
        <QuickActions
          actions={config.quickActions}
          onActionClick={handleQuickActionClick}
        />
      )}

      {/* Results Panel */}
      <ResultsPanel
        result={result}
        isLoading={isLoading}
        error={error}
        onSuggestionClick={handleSuggestionClick}
        showSources={config.showSources}
        onRetry={handleRetry}
      />
    </div>
  );
};

export default ZunkireeSearch;
