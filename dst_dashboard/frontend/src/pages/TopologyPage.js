import React, { Suspense, lazy, useCallback, useMemo } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { usePolling } from '../hooks/usePolling';
import { useTheme } from '../context/ThemeContext';
import { buildTopologyOption } from '../utils/vaclabChartOptions';

const ReactECharts = lazy(() => import('echarts-for-react'));

const POLL_INTERVAL_MS = 12000;
const GRAPH_HEIGHT = 520;

const STATUS_LEGEND = [
    { label: 'Healthy', dotClass: 'bg-success' },
    { label: 'Elevated usage', dotClass: 'bg-warning' },
    { label: 'Critical usage', dotClass: 'bg-error' },
    { label: 'No recent data', dotClass: 'bg-base-content-tertiary' },
];

function GraphSkeleton() {
    return (
        <div className="animate-pulse" style={{ height: GRAPH_HEIGHT }}>
            <div className="h-full w-full rounded bg-base-300/60" />
        </div>
    );
}

function TopologyPage() {
    const { isDark } = useTheme();
    const fetchNodes = useCallback(
        (signal) => axios.get(`${API_BASE_URL}/vaclab/nodes`, { signal }).then((res) => res.data),
        []
    );
    const { data, error, loading } = usePolling(fetchNodes, POLL_INTERVAL_MS);

    const option = useMemo(
        () => (data ? buildTopologyOption(data.nodes, data.switch, isDark) : null),
        [data, isDark]
    );

    return (
        <div>
            <section className="bg-base-200 border-b border-base-100 px-4 lg:px-8 py-14 md:py-20">
                <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                    VacLab
                </span>
                <h1 className="text-4xl md:text-5xl font-bold mt-5 tracking-tight">Network</h1>
                <p className="text-base-content-secondary text-lg font-light mt-3 max-w-2xl">
                    All vaclab nodes reach each other through a single Cilium Geneve overlay - shown here
                    as a hub connecting each node, with live bandwidth usage.
                </p>
            </section>

            <section className="bg-base-300 py-12 px-4 lg:px-8">
                <div className="max-w-5xl mx-auto">
                    {error && !option ? (
                        <div className="alert alert-error text-error-content text-sm">Error loading topology: {error}</div>
                    ) : loading && !option ? (
                        <div className="flex items-center justify-center py-24">
                            <span className="loading loading-spinner loading-lg text-primary"></span>
                        </div>
                    ) : (
                        <div className="card bg-base-200 border border-base-100 p-4">
                            <Suspense fallback={<GraphSkeleton />}>
                                <ReactECharts
                                    option={option}
                                    style={{ height: GRAPH_HEIGHT, width: '100%' }}
                                    opts={{ renderer: 'canvas' }}
                                    notMerge={true}
                                    lazyUpdate={true}
                                />
                            </Suspense>
                            <div className="flex flex-wrap gap-x-6 gap-y-2 justify-center border-t border-base-100 mt-2 pt-4">
                                {STATUS_LEGEND.map((item) => (
                                    <span key={item.label} className="flex items-center gap-2 text-xs text-base-content-tertiary">
                                        <span className={`inline-block w-2 h-2 rounded-full ${item.dotClass}`}></span>
                                        {item.label}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}

export default TopologyPage;
