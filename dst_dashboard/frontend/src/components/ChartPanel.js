import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { useInView } from '../hooks/useInView';
import { buildChartOption } from '../utils/chartOptions';

const ReactECharts = lazy(() => import('echarts-for-react'));

const CHART_HEIGHT = 350;

function ChartSkeleton() {
    return (
        <div className="animate-pulse" style={{ height: CHART_HEIGHT }}>
            <div className="h-full w-full rounded bg-base-300/60" />
        </div>
    );
}

// Each panel only knows its own name/title upfront (from the experiment's panel
// list). The actual chart data + option is fetched independently, in parallel
// with any other panel, the moment this card scrolls near the viewport.
function ChartPanel({ experimentId, panelMeta, isDark }) {
    const [ref, inView] = useInView();
    const [panelData, setPanelData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!inView) return;
        let cancelled = false;

        axios
            .get(`${API_BASE_URL}/experiments/${experimentId}/panels/${panelMeta.name}`)
            .then((res) => {
                if (!cancelled) setPanelData(res.data);
            })
            .catch((err) => {
                if (!cancelled) setError(err.response?.data?.detail || err.message);
            });

        return () => {
            cancelled = true;
        };
    }, [inView, experimentId, panelMeta.name]);

    const option = useMemo(
        () => (panelData?.option ? buildChartOption(panelData.option, isDark) : null),
        [panelData, isDark]
    );

    return (
        <div
            ref={ref}
            className="card bg-base-200 border border-base-100 overflow-hidden hover:ring hover:ring-primary/30 transition-shadow"
        >
            <div className="bg-base-100 px-5 py-4 border-b border-base-300">
                <h3 className="font-mono text-sm uppercase tracking-widest">{panelMeta.title}</h3>
            </div>
            <div className="p-4">
                {error ? (
                    <div className="alert alert-error text-error-content text-sm">Error: {error}</div>
                ) : option ? (
                    <Suspense fallback={<ChartSkeleton />}>
                        <ReactECharts
                            option={option}
                            style={{ height: CHART_HEIGHT, width: '100%' }}
                            opts={{ renderer: 'canvas' }}
                            notMerge={true}
                            lazyUpdate={true}
                        />
                    </Suspense>
                ) : (
                    <ChartSkeleton />
                )}
            </div>
        </div>
    );
}

export default ChartPanel;
