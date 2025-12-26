import React, { useRef, useEffect } from 'react';
import { SearchBarProps } from '../types';

// Search Icon SVG
const SearchIcon = () => (
  <svg className="zk-search-icon" viewBox="0 0 20 20" fill="currentColor">
    <path
      fillRule="evenodd"
      d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
      clipRule="evenodd"
    />
  </svg>
);

// Clear Icon SVG
const ClearIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
    <path d="M9.53 3.53a.75.75 0 00-1.06-1.06L6 4.94 3.53 2.47a.75.75 0 00-1.06 1.06L4.94 6 2.47 8.47a.75.75 0 101.06 1.06L6 7.06l2.47 2.47a.75.75 0 101.06-1.06L7.06 6l2.47-2.47z" />
  </svg>
);

// Arrow Icon SVG
const ArrowIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path
      fillRule="evenodd"
      d="M2 8a.75.75 0 01.75-.75h8.69L8.22 4.03a.75.75 0 011.06-1.06l4.5 4.5a.75.75 0 010 1.06l-4.5 4.5a.75.75 0 01-1.06-1.06l3.22-3.22H2.75A.75.75 0 012 8z"
      clipRule="evenodd"
    />
  </svg>
);

export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  onSubmit,
  placeholder,
  isLoading,
  mode,
  borderRadius,
  primaryColor,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim() && !isLoading) {
      onSubmit();
    }
  };

  const handleClear = () => {
    onChange('');
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleClear();
    }
  };

  // Build class names
  const searchBarClasses = [
    'zk-search-bar',
    `zk-search-bar--${mode}`,
    borderRadius === 'pill' ? 'zk-search-bar--pill' : '',
  ].filter(Boolean).join(' ');

  const buttonClasses = [
    'zk-search-button',
    borderRadius === 'pill' ? 'zk-search-button--pill' : '',
  ].filter(Boolean).join(' ');

  return (
    <form onSubmit={handleSubmit} role="search" className={searchBarClasses}>
      <label htmlFor="zk-search-input" className="sr-only">
        Search
      </label>

      <SearchIcon />

      <input
        ref={inputRef}
        id="zk-search-input"
        type="search"
        className="zk-search-input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isLoading}
        autoComplete="off"
        aria-label="Search"
      />

      {value && !isLoading && (
        <button
          type="button"
          className="zk-search-clear"
          onClick={handleClear}
          aria-label="Clear search"
        >
          <ClearIcon />
        </button>
      )}

      <button
        type="submit"
        className={buttonClasses}
        disabled={!value.trim() || isLoading}
        aria-label={isLoading ? 'Searching...' : 'Search'}
      >
        {isLoading ? (
          <span className="zk-spinner" />
        ) : (
          <>
            <span className="zk-search-button__text">Search</span>
            <ArrowIcon />
          </>
        )}
      </button>
    </form>
  );
};

export default SearchBar;
