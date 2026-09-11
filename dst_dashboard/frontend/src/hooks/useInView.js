import { useEffect, useRef, useState } from 'react';

// Reports whether an element has scrolled into (or near) the viewport.
// By default stops observing after the first hit — used to defer mounting
// expensive chart instances/fetches until they're actually about to be seen,
// without re-triggering (and re-fetching) every time the user scrolls past.
// Pass once:false for purely visual effects that should toggle both ways.
export function useInView({ rootMargin = '200px', once = true } = {}) {
    const ref = useRef(null);
    const [inView, setInView] = useState(false);

    useEffect(() => {
        const node = ref.current;
        if (!node) return undefined;

        if (typeof IntersectionObserver === 'undefined') {
            setInView(true);
            return undefined;
        }

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    setInView(true);
                    if (once) observer.disconnect();
                } else if (!once) {
                    setInView(false);
                }
            },
            { rootMargin }
        );

        observer.observe(node);
        return () => observer.disconnect();
    }, [rootMargin, once]);

    return [ref, inView];
}
