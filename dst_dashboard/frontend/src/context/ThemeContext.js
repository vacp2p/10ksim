import React, { createContext, useContext, useLayoutEffect, useState } from 'react';

const STORAGE_KEY = 'dst-dashboard-theme';
const LIGHT = 'dst';
const DARK = 'dst-dark';

const ThemeContext = createContext(null);

function getInitialTheme() {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === LIGHT || stored === DARK) return stored;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? DARK : LIGHT;
}

export function ThemeProvider({ children }) {
    const [theme, setTheme] = useState(getInitialTheme);

    useLayoutEffect(() => {
        document.body.setAttribute('data-theme', theme);
        window.localStorage.setItem(STORAGE_KEY, theme);
    }, [theme]);

    const toggleTheme = () => setTheme((t) => (t === LIGHT ? DARK : LIGHT));

    return (
        <ThemeContext.Provider value={{ theme, isDark: theme === DARK, toggleTheme }}>
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme() {
    return useContext(ThemeContext);
}
