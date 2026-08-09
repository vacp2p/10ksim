import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { useInView } from '../hooks/useInView';
import { buildThumbnailOption } from '../utils/chartOptions';
import { getCachedRawOptions, setCachedRawOptions } from '../utils/thumbnailCache';
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
// card scrolls near the viewport. Some panels are tiny pre-aggregated stats;
// others (raw per-message timeseries) can be tens of MB, and some panels can
// simply error out server-side. So every panel (up to MAX_PANELS) is fetched
// independently and concurrently - first paint shows whichever succeeds
// first, regardless of position, rather than waiting on or being blocked by
// any one specific panel. Only if every attempted panel fails does the whole
// thumbnail fall back to the "failed" placeholder.
function ExperimentThumbnail({ experimentId }) {
    const { isDark } = useTheme();
    const [ref, inView] = useInView();
    const cached = getCachedRawOptions(experimentId);
    const [rawOptions, setRawOptions] = useState(cached || []);
    const [index, setIndex] = useState(0);
    const [visible, setVisible] = useState(true);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        if (!inView || cached) return;
        const controller = new AbortController();

        const fetchPanelOption = (panelName) =>
            axios
                .get(`${API_BASE_URL}/experiments/${experimentId}/panels/${panelName}`, {
                    signal: controller.signal,
                })
                .then((res) => res.data?.option)
                .catch(() => null);

        axios
            .get(`${API_BASE_URL}/experiments/${experimentId}`, { signal: controller.signal })
            .then((res) => {
                const panels = (res.data?.panels || []).slice(0, MAX_PANELS);
                if (!panels.length) {
                    setFailed(true);
                    return;
                }

                const accumulated = [];
                let settledCount = 0;

                panels.forEach((panel) => {
                    fetchPanelOption(panel.name).then((option) => {
                        if (controller.signal.aborted) return;
                        settledCount += 1;
                        if (option) {
                            accumulated.push(option);
                            setCachedRawOptions(experimentId, [...accumulated]);
                            setRawOptions([...accumulated]);
                        } else if (settledCount === panels.length && accumulated.length === 0) {
                            setFailed(true);
                        }
                    });
                });
            })
            .catch(() => {
                if (!controller.signal.aborted) setFailed(true);
            });

        return () => {
            controller.abort();
        };
        // `cached` is intentionally excluded: it's only a mount-time "was this
        // already cached" gate. Fetching a panel populates the cache, which
        // would flip `cached` truthy and re-trigger this effect - and its
        // cleanup aborts the very controller the other panel fetches are
        // still using, killing them mid-flight.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [inView, experimentId]);

    // Re-theming on a dark/light toggle is just recoloring already-fetched
    // data, so it's a cheap useMemo rather than something the fetch effect
    // above needs to re-run for.
    const options = useMemo(
        () => rawOptions.map((raw) => buildThumbnailOption(raw, isDark)),
        [rawOptions, isDark]
    );

    // Rotates by updating the *same* mounted chart's option (echarts-for-react
    // diffs and calls setOption in place) rather than remounting it - keeps
    // the canvas/echarts instance alive instead of re-creating it every tick.
    // The brief opacity dip in between is a plain CSS crossfade, not a remount.
    useEffect(() => {
        if (options.length <= 1) return undefined;
        let hideTimeout;
        const intervalId = setInterval(() => {
            setVisible(false);
            hideTimeout = setTimeout(() => {
                setIndex((i) => (i + 1) % options.length);
                setVisible(true);
            }, 200);
        }, ROTATE_INTERVAL_MS);
        return () => {
            clearInterval(intervalId);
            clearTimeout(hideTimeout);
        };
    }, [options.length]);

    const currentOption = options[index] || null;

    return (
        <div ref={ref} className="bg-base-100 border-b border-base-100 shrink-0 overflow-hidden" style={{ height: THUMB_HEIGHT }}>
            {currentOption ? (
                <Suspense fallback={<ThumbnailSkeleton />}>
                    <div className={`h-full w-full transition-opacity duration-200 ${visible ? 'opacity-100' : 'opacity-0'}`}>
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
