import React from 'react';
import { Link } from 'react-router-dom';
import { API_BASE_URL } from '../config';

const FOOTER_COLUMNS = [
    {
        title: 'Explore',
        links: [
            { label: 'Experiments', to: '/experiments' },
            { label: 'Topology', to: '/vaclab/topology' },
            { label: 'Networks', to: '/vaclab/networks' },
        ],
    },
    {
        title: 'Tools',
        links: [
            { label: '10ksim', href: 'https://github.com/vacp2p/10ksim' },
            { label: 'vaclab', href: 'https://github.com/vacp2p/vaclab-2' },
        ],
    },
    {
        title: 'Docs',
        links: [
            { label: 'API Reference', href: `${API_BASE_URL}/api/docs` },
            { label: 'README', href: 'https://github.com/vacp2p/10ksim/blob/master/dst_dashboard/README.md' },
        ],
    },
    {
        title: 'Social',
        links: [
            { label: 'GitHub', href: 'https://github.com/vacp2p', icon: 'bi-github' },
            { label: 'Discord', href: 'https://discord.com/channels/864066763682218004/1113778766657880127', icon: 'bi-discord' },
            { label: 'vac.dev', href: 'https://vac.dev', icon: 'bi-globe' },
        ],
    },
];

function Footer() {
    return (
        <footer className="bg-base-300 text-base-content-secondary px-4 lg:px-8 py-12 mt-auto border-t border-base-100">
            <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 font-mono text-sm">
                {FOOTER_COLUMNS.map((column) => (
                    <nav key={column.title}>
                        <h6 className="text-xs uppercase tracking-widest text-base-content-tertiary mb-3">
                            {column.title}
                        </h6>
                        <ul className="space-y-2">
                            {column.links.map((link) => (
                                <li key={link.label}>
                                    {link.to ? (
                                        <Link to={link.to} className="link link-hover">
                                            {link.label}
                                        </Link>
                                    ) : (
                                        <a
                                            href={link.href}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="link link-hover inline-flex items-center gap-2"
                                        >
                                            {link.icon && <i className={`bi ${link.icon}`}></i>}
                                            {link.label}
                                        </a>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </nav>
                ))}
            </div>
            <div className="max-w-7xl mx-auto mt-10 pt-6 border-t border-base-100 text-xs text-base-content-tertiary font-mono">
                &copy; {new Date().getFullYear()} vaclab. DST Dashboard — Distributed Systems Testing Analytics.
            </div>
        </footer>
    );
}

export default Footer;
