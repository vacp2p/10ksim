import React, { Suspense, lazy, useEffect, useState } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { useInView } from '../hooks/useInView';
import { buildThumbnailOption } from '../utils/chartOptions';
import { useTheme } from '../context/ThemeContext';

const ReactECharts = lazy(() => import('echarts-for-react'));

const THUMB_HEIGHT = 152;
const MAX_PANELS = 4;
const ROTATE_INTERVAL_MS = 15000;

function ThumbnailSkeleton() {
    return (
        <div className="animate-pulse w-full" style={{ height: THUMB_HEIGHT }}>
            <div className="h-full w-full bg-base-300/60" />
        </div>
    );
}

// A quick "glance" preview of an experiment's results, rendered only once the
// card scrolls near the viewport. Fetches up to MAX_PANELS panels once (not
// re-fetched on re-scroll - useInView's default `once` gating), then cycles
// through whichever came back, crossfading every few seconds so a card with
// several panels doesn't just sit on the first one forever.
function ExperimentThumbnail({ experimentId }) {
    const { isDark } = useTheme();
    const [ref, inView] = useInView();
    const [options, setOptions] = useState([]);
    const [index, setIndex] = useState(0);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        if (!inView) return;
        let cancelled = false;

        axios
            .get(`${API_BASE_URL}/experiments/${experimentId}`)
            .then((res) => {
                const panels = (res.data?.panels || []).slice(0, MAX_PANELS);
                if (!panels.length) {
                    if (!cancelled) setFailed(true);
                    return null;
                }
                return Promise.all(
                    panels.map((panel) =>
                        axios
                            .get(`${API_BASE_URL}/experiments/${experimentId}/panels/${panel.name}`)
                            .then((res) => res.data?.option)
                            .catch(() => null)
                    )
                );
            })
            .then((rawOptions) => {
                if (cancelled || !rawOptions) return;
                const built = rawOptions.filter(Boolean).map((raw) => buildThumbnailOption(raw, isDark));
                if (built.length) {
                    setOptions(built);
                } else {
                    setFailed(true);
                }
            })
            .catch(() => {
                if (!cancelled) setFailed(true);
            });

        return () => {
            cancelled = true;
        };
    }, [inView, experimentId, isDark]);

    useEffect(() => {
        if (options.length <= 1) return undefined;
        const id = setInterval(() => {
            setIndex((i) => (i + 1) % options.length);
        }, ROTATE_INTERVAL_MS);
        return () => clearInterval(id);
    }, [options.length]);

    const currentOption = options[index] || null;

    return (
        <div ref={ref} className="bg-base-100 border-b border-base-100 shrink-0 overflow-hidden" style={{ height: THUMB_HEIGHT }}>
            {currentOption ? (
                <Suspense fallback={<ThumbnailSkeleton />}>
                    <div key={index} className="h-full w-full animate-page-in">
                        <ReactECharts
                            option={currentOption}
                            style={{ height: THUMB_HEIGHT, width: '100%' }}
                            opts={{ renderer: 'canvas' }}
                            notMerge={true}
                            lazyUpdate={true}
                        />
                    </div>
                </Suspense>
            ) : failed ? (
                <div className="h-full w-full flex items-center justify-center text-base-content-tertiary">
                    <i className="bi bi-bar-chart-line text-2xl"></i>
                </div>
            ) : (
                <ThumbnailSkeleton />
            )}
        </div>
    );
}

export default ExperimentThumbnail;
