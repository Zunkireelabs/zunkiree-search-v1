// Types for Zunkiree Search Widget v2

export type EmbedMode = 'hero' | 'inline' | 'floating';
export type BorderRadiusStyle = 'rounded' | 'pill';

export interface WidgetConfig {
  // Required
  siteId: string;

  // API
  apiUrl: string;

  // Display Mode
  mode: EmbedMode;

  // Appearance
  brandName: string;
  primaryColor: string;
  placeholderText: string;

  // Features
  showPoweredBy: boolean;
  showQuickActions: boolean;
  quickActions: string[];
  showSources: boolean;

  // Style
  borderRadius: BorderRadiusStyle;
}

export interface SearchResult {
  answer: string;
  suggestions: string[];
  sources?: Source[];
}

export interface Source {
  title: string;
  url: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  sources?: Source[];
  suggestions?: string[];
}

export type SearchState = 'idle' | 'focused' | 'loading' | 'results' | 'error';

export interface SearchError {
  code: string;
  message: string;
}

// Props interfaces
export interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder: string;
  isLoading: boolean;
  mode: EmbedMode;
  borderRadius: BorderRadiusStyle;
  primaryColor: string;
}

export interface ResultsPanelProps {
  result: SearchResult | null;
  isLoading: boolean;
  error: SearchError | null;
  onSuggestionClick: (suggestion: string) => void;
  showSources: boolean;
}

export interface QuickActionsProps {
  actions: string[];
  onActionClick: (action: string) => void;
}

export interface PoweredByProps {
  show: boolean;
}
