import React from 'react';
import { getUsageStatus } from '../../utils/vaclabChartOptions';

const STATUS_BAR_CLASS = {
    good: 'bg-success',
    warning: 'bg-warning',
    critical: 'bg-error',
    unknown: 'bg-base-content-tertiary',
};

// A labeled usage bar: fill color always encodes status (good/warning/
// critical), and the numeric value is always printed as text alongside it -
// never color alone.
function Meter({ label, usedText, percent }) {
    const status = getUsageStatus(percent);
    return (
        <div className="min-w-0">
            <div className="flex items-baseline justify-between gap-2 text-xs mb-1">
                <span className="text-base-content-tertiary uppercase tracking-wider">{label}</span>
                {percent !== null && <span className="text-base-content-tertiary shrink-0">{percent.toFixed(0)}%</span>}
            </div>
            <div className="h-1.5 w-full rounded bg-base-300 overflow-hidden mb-1">
                <div
                    className={`h-full rounded ${STATUS_BAR_CLASS[status]}`}
                    style={{ width: `${Math.min(100, Math.max(percent ?? 0, 2))}%` }}
                />
            </div>
            <div className="font-mono text-[11px] text-base-content-secondary truncate" title={usedText}>
                {usedText}
            </div>
        </div>
    );
}

export default Meter;
