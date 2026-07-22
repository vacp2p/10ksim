import React from 'react';
import { useInView } from '../hooks/useInView';

// Fades + rises a section in as it scrolls into view, and fades it back out
// when it scrolls back out of view - so scrolling up doesn't leave stale
// content stuck on screen. Distinct from useInView's lazy-load use elsewhere,
// which deliberately fires once so data isn't re-fetched on every pass.
function Reveal({ children, className = '', delay = 0 }) {
    const [ref, inView] = useInView({ rootMargin: '0px 0px -10% 0px', once: false });

    return (
        <div
            ref={ref}
            className={`transition-all duration-700 ease-out ${inView ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
                } ${className}`}
            style={delay ? { transitionDelay: `${delay}ms` } : undefined}
        >
            {children}
        </div>
    );
}

export default Reveal;
