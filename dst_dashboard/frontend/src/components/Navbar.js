import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../context/ThemeContext';

const NAV_LINKS = [
    { to: '/', label: 'Home' },
    { to: '/experiments', label: 'Experiments' },
];

const VACLAB_LINKS = [
    { to: '/vaclab/topology', label: 'Network', icon: 'bi-diagram-3' },
    { to: '/vaclab/networks', label: 'Resources', icon: 'bi-hdd-network' },
];

const ICON_LINKS = [
    { href: 'https://github.com/vacp2p/10ksim', label: '10ksim on GitHub', icon: 'bi-github' },
];

function Navbar() {
    const location = useLocation();
    const [mobileOpen, setMobileOpen] = useState(false);
    const { isDark, toggleTheme } = useTheme();

    const isActive = (to) => location.pathname === to;
    const isVaclabActive = VACLAB_LINKS.some((link) => location.pathname === link.to);

    return (
        <header className="bg-base-100 w-full fixed top-0 z-30 border-b border-base-200">
            <nav className="flex items-center justify-between py-3 max-w-7xl mx-auto px-4 lg:px-8">
                <Link to="/" className="flex items-center gap-3 shrink-0">
                    <span className="bg-[#f5f5ef] rounded-full p-1 flex items-center justify-center">
                        <img
                            src="https://raw.githubusercontent.com/vacp2p/vaclab-2/feat/add_lab_components/extras/vac-logo-light-no-bg.png"
                            alt="VacLab"
                            className="h-7 w-7 object-contain"
                        />
                    </span>
                    <span className="font-mono text-lg font-medium tracking-tight">DST Dashboard</span>
                </Link>

                <div className="hidden lg:block">
                    <ul className="menu menu-horizontal p-0 gap-2 font-mono text-sm items-center">
                        {NAV_LINKS.map((link) => (
                            <li key={link.to}>
                                <Link
                                    to={link.to}
                                    className={`px-2 py-1 rounded transition-colors ${isActive(link.to) ? 'text-primary' : 'text-base-content-secondary hover:text-primary'
                                        }`}
                                >
                                    {link.label}
                                </Link>
                            </li>
                        ))}
                        <li className="dropdown dropdown-hover dropdown-end">
                            <div
                                tabIndex={0}
                                role="button"
                                className={`px-2 py-1 rounded transition-colors flex items-center gap-1 ${isVaclabActive ? 'text-primary' : 'text-base-content-secondary hover:text-primary'
                                    }`}
                            >
                                VacLab
                                <i className="bi bi-chevron-down text-xs"></i>
                            </div>
                            <ul tabIndex={0} className="dropdown-content menu bg-base-200 rounded-lg mt-2 w-48 p-2 shadow-lg z-40">
                                {VACLAB_LINKS.map((link) => (
                                    <li key={link.to}>
                                        <Link to={link.to} className={isActive(link.to) ? 'text-primary' : ''}>
                                            <i className={`bi ${link.icon}`}></i>
                                            {link.label}
                                        </Link>
                                    </li>
                                ))}
                            </ul>
                        </li>
                        <li className="w-px self-stretch bg-base-300 my-1"></li>
                        {ICON_LINKS.map((link) => (
                            <li key={link.href}>
                                <a
                                    href={link.href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    title={link.label}
                                    className="btn btn-ghost btn-sm btn-square text-base-content-secondary hover:text-primary"
                                >
                                    <i className={`bi ${link.icon} text-base`}></i>
                                </a>
                            </li>
                        ))}
                        <li>
                            <button
                                type="button"
                                onClick={toggleTheme}
                                title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
                                aria-label="Toggle color theme"
                                className="btn btn-ghost btn-sm btn-square text-base-content-secondary hover:text-primary"
                            >
                                <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon-stars'} text-base`}></i>
                            </button>
                        </li>
                    </ul>
                </div>

                <div className="flex items-center gap-1 lg:hidden">
                    <button
                        type="button"
                        onClick={toggleTheme}
                        title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
                        aria-label="Toggle color theme"
                        className="btn btn-square btn-ghost"
                    >
                        <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon-stars'} text-lg`}></i>
                    </button>
                    <button
                        type="button"
                        aria-label="Toggle menu"
                        className="btn btn-square btn-ghost shrink-0"
                        onClick={() => setMobileOpen((open) => !open)}
                    >
                        <i className="bi bi-list text-xl"></i>
                    </button>
                </div>
            </nav>

            {mobileOpen && (
                <div className="lg:hidden bg-base-100 border-t border-base-200 px-4 py-4">
                    <ul className="menu w-full font-mono text-sm gap-1">
                        {NAV_LINKS.map((link) => (
                            <li key={link.to}>
                                <Link to={link.to} onClick={() => setMobileOpen(false)} className={isActive(link.to) ? 'text-primary' : ''}>
                                    {link.label}
                                </Link>
                            </li>
                        ))}
                        <li className="menu-title mt-2">VacLab</li>
                        {VACLAB_LINKS.map((link) => (
                            <li key={link.to}>
                                <Link to={link.to} onClick={() => setMobileOpen(false)} className={isActive(link.to) ? 'text-primary' : ''}>
                                    <i className={`bi ${link.icon}`}></i>
                                    {link.label}
                                </Link>
                            </li>
                        ))}
                        <li className="menu-title mt-2">Resources</li>
                        {ICON_LINKS.map((link) => (
                            <li key={link.href}>
                                <a href={link.href} target="_blank" rel="noopener noreferrer" onClick={() => setMobileOpen(false)}>
                                    <i className={`bi ${link.icon}`}></i>
                                    {link.label}
                                </a>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </header>
    );
}

export default Navbar;
