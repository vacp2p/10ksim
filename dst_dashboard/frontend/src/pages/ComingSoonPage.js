import React from 'react';

function ComingSoonPage({ title, description }) {
    return (
        <div className="flex flex-col items-center justify-center text-center px-4 py-24 min-h-[60vh]">
            <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1 mb-6">
                VacLab
            </span>
            <h1 className="text-3xl md:text-4xl font-bold mb-4">{title}</h1>
            <p className="text-base-content-secondary text-lg font-light max-w-xl">
                {description || `${title} is coming soon.`}
            </p>
        </div>
    );
}

export default ComingSoonPage;
