import { useEffect, useRef, useState } from 'react';

// Refetches fetchFn on a fixed interval for as long as the component stays
// mounted - used by the vaclab pages to keep node stats "live". Follows the
// same cancelled-flag + AbortController cleanup pattern used throughout the
// app's other fetch effects (ChartPanel, ExperimentThumbnail).
export function usePolling(fetchFn, intervalMs) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const fetchFnRef = useRef(fetchFn);
    fetchFnRef.current = fetchFn;

    useEffect(() => {
        let cancelled = false;
        const controller = new AbortController();

        const tick = () => {
            fetchFnRef
                .current(controller.signal)
                .then((result) => {
                    if (cancelled) return;
                    setData(result);
                    setError(null);
                    setLoading(false);
                })
                .catch((err) => {
                    if (cancelled || err.code === 'ERR_CANCELED') return;
                    setError(err.response?.data?.detail || err.message);
                    setLoading(false);
                });
        };

        tick();
        const intervalId = setInterval(tick, intervalMs);
        return () => {
            cancelled = true;
            controller.abort();
            clearInterval(intervalId);
        };
    }, [intervalMs]);

    return { data, error, loading };
}
