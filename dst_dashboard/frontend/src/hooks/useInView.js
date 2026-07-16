import { useEffect, useRef, useState } from 'react';

// Reports whether an element has scrolled into (or near) the viewport, then
// stops observing — used to defer mounting expensive chart instances until
// they're actually about to be seen.
export function useInView({ rootMargin = '200px' } = {}) {
    const ref = useRef(null);
    const [inView, setInView] = useState(false);

    useEffect(() => {
        const node = ref.current;
        if (!node || inView) return undefined;

        if (typeof IntersectionObserver === 'undefined') {
            setInView(true);
            return undefined;
        }

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setInView(true);
                    observer.disconnect();
                }
            },
            { rootMargin }
        );

        observer.observe(node);
        return () => observer.disconnect();
    }, [inView, rootMargin]);

    return [ref, inView];
}
