import React, { useCallback, useMemo } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { usePolling } from '../hooks/usePolling';
import { formatBytes } from '../utils/vaclabChartOptions';
import Reveal from '../components/Reveal';
import Meter from '../components/vaclab/Meter';
import NodeRow from '../components/vaclab/NodeRow';

const POLL_INTERVAL_MS = 12000;

// Sums a metric block (cpu/memory/storage, each shaped {used_*, capacity_*})
// across every node that reports it, skipping nodes where that particular
// metric is missing rather than treating them as zero.
function sumMetric(nodes, key, usedField, capacityField) {
    let used = 0;
    let capacity = 0;
    let reporting = 0;
    nodes.forEach((node) => {
        const block = node[key];
        if (!block) return;
        used += block[usedField];
        capacity += block[capacityField];
        reporting += 1;
    });
    if (reporting === 0) return null;
    return { used, capacity, percent: capacity > 0 ? (used / capacity) * 100 : 0 };
}

function ResourcesPage() {
    const fetchNodes = useCallback(
        (signal) => axios.get(`${API_BASE_URL}/vaclab/nodes`, { signal }).then((res) => res.data),
        []
    );
    const { data, error, loading } = usePolling(fetchNodes, POLL_INTERVAL_MS);

    const totals = useMemo(() => {
        if (!data) return null;
        return {
            cpu: sumMetric(data.nodes, 'cpu', 'used_cores', 'capacity_cores'),
            memory: sumMetric(data.nodes, 'memory', 'used_bytes', 'capacity_bytes'),
            storage: sumMetric(data.nodes, 'storage', 'used_bytes', 'capacity_bytes'),
        };
    }, [data]);

    return (
        <div>
            <section className="bg-base-200 border-b border-base-100 px-4 lg:px-8 py-14 md:py-20">
                <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                    VacLab
                </span>
                <h1 className="text-4xl md:text-5xl font-bold mt-5 tracking-tight">Resources</h1>
                <p className="text-base-content-secondary text-lg font-light mt-3 max-w-2xl">
                    Live CPU, memory, storage and network usage across the cluster nodes.
                </p>
            </section>

            <section className="bg-base-300 py-12 px-4 lg:px-8">
                <div className="max-w-5xl mx-auto">
                    {error && !data ? (
                        <div className="alert alert-error text-error-content text-sm">Error loading node data: {error}</div>
                    ) : loading && !data ? (
                        <div className="flex items-center justify-center py-24">
                            <span className="loading loading-spinner loading-lg text-primary"></span>
                        </div>
                    ) : (
                        <>
                            <p className="text-base-content-tertiary text-sm mb-6">{data.nodes.length} nodes</p>

                            <div className="card bg-base-200 border border-base-100 px-5 py-4 mb-6">
                                <h2 className="font-mono text-xs uppercase tracking-widest text-base-content-tertiary mb-3">
                                    Cluster capacity
                                </h2>
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                    <Meter
                                        label="CPU"
                                        percent={totals.cpu?.percent ?? null}
                                        usedText={totals.cpu ? `${totals.cpu.used.toFixed(1)} / ${totals.cpu.capacity.toFixed(0)} cores` : 'no data'}
                                    />
                                    <Meter
                                        label="Memory"
                                        percent={totals.memory?.percent ?? null}
                                        usedText={totals.memory ? `${formatBytes(totals.memory.used)} / ${formatBytes(totals.memory.capacity)}` : 'no data'}
                                    />
                                    <Meter
                                        label="Storage"
                                        percent={totals.storage?.percent ?? null}
                                        usedText={totals.storage ? `${formatBytes(totals.storage.used)} / ${formatBytes(totals.storage.capacity)}` : 'no data'}
                                    />
                                </div>
                            </div>

                            <div className="flex flex-col gap-4">
                                {data.nodes.map((node) => (
                                    <Reveal key={node.hostname}>
                                        <NodeRow node={node} />
                                    </Reveal>
                                ))}
                            </div>
                        </>
                    )}
                </div>
            </section>
        </div>
    );
}

export default ResourcesPage;
