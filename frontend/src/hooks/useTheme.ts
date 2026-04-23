import { useEffect } from 'react';

/**
 * Apply the theme from saved config.
 * Reads from localStorage on mount and whenever config changes.
 * Sets data-theme attribute on <html> which CSS picks up.
 */
export function useTheme() {
  useEffect(() => {
    applyThemeFromStorage();
  }, []);
}

export function applyThemeFromStorage() {
  try {
    const raw = localStorage.getItem('work-agents-config');
    if (raw) {
      const config = JSON.parse(raw);
      applyTheme(config.theme || 'dark');
    }
  } catch { /* ignore */ }
}

export function applyTheme(theme: 'dark' | 'light' | 'system') {
  const root = document.documentElement;

  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  } else {
    root.setAttribute('data-theme', theme);
  }
}
