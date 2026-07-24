/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './public/index.html',
        './src/**/*.{js,jsx}',
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ['"DM Sans"', 'sans-serif'],
                mono: ['"DM Mono"', 'monospace'],
            },
            colors: {
                'base-content-secondary': 'var(--content-secondary)',
                'base-content-tertiary': 'var(--content-tertiary)',
            },
        },
    },
    plugins: [require('daisyui')],
    daisyui: {
        themes: [
            {
                dst: {
                    'base-100': '#f5f5ef',
                    'base-200': '#eceee4',
                    'base-300': '#dbddd7',
                    'base-content': '#152521',
                    primary: '#152521',
                    'primary-content': '#f5f5ef',
                    secondary: '#5f797c',
                    'secondary-content': '#f5f5ef',
                    accent: '#ffd328',
                    'accent-content': '#152521',
                    neutral: '#dbddd7',
                    'neutral-content': '#152521',
                    info: '#c6ebf7',
                    'info-content': '#152521',
                    success: '#2f9e6b',
                    'success-content': '#f5f5ef',
                    warning: '#ffd328',
                    'warning-content': '#152521',
                    error: '#e40014',
                    'error-content': '#f5f5ef',
                },
            },
            {
                'dst-dark': {
                    'base-100': '#1b2420',
                    'base-200': '#141a17',
                    'base-300': '#0d1210',
                    'base-content': '#f5f5ef',
                    primary: '#ffd328',
                    'primary-content': '#152521',
                    secondary: '#9ea5a0',
                    'secondary-content': '#152521',
                    accent: '#ffd328',
                    'accent-content': '#152521',
                    neutral: '#1f2a25',
                    'neutral-content': '#f5f5ef',
                    info: '#5f797c',
                    'info-content': '#f5f5ef',
                    success: '#2f9e6b',
                    'success-content': '#152521',
                    warning: '#ffd328',
                    'warning-content': '#152521',
                    error: '#fb2c36',
                    'error-content': '#152521',
                },
            },
        ],
        darkTheme: 'dst-dark',
    },
};
