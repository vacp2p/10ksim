// Module-scoped (persists for the SPA session) cache of each experiment's
// fetched-but-not-yet-themed panel options. HomePage fully remounts on every
// route change (PageTransition keys the page tree by pathname), which would
// otherwise re-fetch and rebuild every thumbnail's chart data each time the
// user navigates back to Home. Theming is left out of the cache since it's a
// cheap, theme-reactive derivation (see ExperimentThumbnail's useMemo).
const cache = new Map();

export function getCachedRawOptions(experimentId) {
    return cache.get(experimentId);
}

export function setCachedRawOptions(experimentId, rawOptions) {
    cache.set(experimentId, rawOptions);
}
