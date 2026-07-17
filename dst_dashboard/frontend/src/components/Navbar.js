import React, { useEffect, useRef, useState } from 'react';
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
    { href: 'https://discord.com/channels/864066763682218004/1113778766657880127', label: 'Join us on Discord', icon: 'bi-discord' },
];

// Close grace period so moving the pointer from the trigger down into the
// menu (across the visual padding gap) doesn't get read as "left the menu".
const CLOSE_DELAY_MS = 150;

function Navbar() {
    const location = useLocation();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [vaclabOpen, setVaclabOpen] = useState(false);
    const { isDark, toggleTheme } = useTheme();
    const closeTimer = useRef(null);

    useEffect(() => () => clearTimeout(closeTimer.current), []);

    const openVaclab = () => {
        clearTimeout(closeTimer.current);
        setVaclabOpen(true);
    };
    const closeVaclabSoon = () => {
        closeTimer.current = setTimeout(() => setVaclabOpen(false), CLOSE_DELAY_MS);
    };

    const isActive = (to) => location.pathname === to;
    const isVaclabActive = VACLAB_LINKS.some((link) => location.pathname === link.to);

    return (
        <header className="bg-base-100 w-full fixed top-0 z-30 border-b border-base-200">
            <nav className="flex items-center justify-between py-3 max-w-7xl mx-auto px-4 lg:px-8">
                <Link to="/" className="flex items-center gap-3 shrink-0">
                    <span className="bg-[#f5f5ef] rounded-full p-1 flex items-center justify-center">
                        <img
                            src="https://raw.githubusercontent.com/vacp2p/vaclab-2/feat/add_lab_components/extras/vac-logo-light-no-bg.png"
                            alt="vaclab"
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
                        <li
                            className="relative"
                            onMouseEnter={openVaclab}
                            onMouseLeave={closeVaclabSoon}
                        >
                            <div
                                tabIndex={0}
                                role="button"
                                aria-expanded={vaclabOpen}
                                onFocus={openVaclab}
                                onBlur={closeVaclabSoon}
                                onClick={() => setVaclabOpen((open) => !open)}
                                className={`px-2 py-1 rounded transition-colors flex items-center gap-1 cursor-pointer select-none outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${isVaclabActive ? 'text-primary' : 'text-base-content-secondary hover:text-primary'
                                    }`}
                            >
                                vaclab
                                <i className={`bi bi-chevron-down text-xs transition-transform ${vaclabOpen ? 'rotate-180' : ''}`}></i>
                            </div>
                            <ul
                                className={`absolute right-0 top-full pt-2 w-48 z-40 transition-all duration-150 ${vaclabOpen
                                        ? 'opacity-100 translate-y-0 pointer-events-auto'
                                        : 'opacity-0 -translate-y-1 pointer-events-none'
                                    }`}
                            >
                                <div className="menu bg-base-200 rounded p-2 shadow-lg border border-base-300">
                                    {VACLAB_LINKS.map((link) => (
                                        <li key={link.to}>
                                            <Link to={link.to} onClick={() => setVaclabOpen(false)} className={isActive(link.to) ? 'text-primary' : ''}>
                                                <i className={`bi ${link.icon}`}></i>
                                                {link.label}
                                            </Link>
                                        </li>
                                    ))}
                                </div>
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
                        <li className="menu-title mt-2">vaclab</li>
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
