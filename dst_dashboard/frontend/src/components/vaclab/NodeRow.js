import React from 'react';
import { formatBytes, formatBitsPerSec } from '../../utils/vaclabChartOptions';
import Meter from './Meter';

function networkUsedText(network) {
    if (!network) return 'no data';
    const used = formatBitsPerSec(network.used_bytes_per_sec);
    if (!network.capacity_bytes_per_sec) return used;
    return `${used} / ${formatBitsPerSec(network.capacity_bytes_per_sec)}`;
}

function NodeRow({ node }) {
    return (
        <div className="card bg-base-200 border border-base-100 px-5 py-4 flex flex-col md:flex-row md:items-center gap-4">
            <div className="flex items-center gap-3 md:w-40 shrink-0">
                <i className="bi bi-hdd-rack text-2xl text-primary"></i>
                <div className="min-w-0">
                    <div className="font-mono font-semibold truncate">{node.short_name}</div>
                    <div className="text-xs text-base-content-tertiary truncate" title={node.hostname}>
                        {node.hostname}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 grow">
                <Meter
                    label="CPU"
                    percent={node.cpu?.used_percent ?? null}
                    usedText={node.cpu ? `${node.cpu.used_cores.toFixed(1)} / ${node.cpu.capacity_cores} cores` : 'no data'}
                />
                <Meter
                    label="Memory"
                    percent={node.memory?.used_percent ?? null}
                    usedText={node.memory ? `${formatBytes(node.memory.used_bytes)} / ${formatBytes(node.memory.capacity_bytes)}` : 'no data'}
                />
                <Meter
                    label="Storage"
                    percent={node.storage?.used_percent ?? null}
                    usedText={node.storage ? `${formatBytes(node.storage.used_bytes)} / ${formatBytes(node.storage.capacity_bytes)}` : 'no data'}
                />
                <Meter
                    label="Network"
                    percent={node.network?.used_percent ?? null}
                    usedText={networkUsedText(node.network)}
                />
            </div>

            <div className="md:w-24 shrink-0 text-right">
                <div className="text-lg font-mono font-semibold">{node.pod_count}</div>
                <div className="text-xs text-base-content-tertiary uppercase tracking-wider">pods</div>
            </div>
        </div>
    );
}

export default NodeRow;
