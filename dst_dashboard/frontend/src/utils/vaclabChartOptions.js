import { formatBytes } from './chartOptions';

// Network throughput/capacity is conventionally quoted in bits/sec (Mbps,
// Gbps - matching how NICs are marketed and how node_network_speed_bytes'
// round values like 5,000,000,000 B/s = 40Gbps are meant to be read), unlike
// storage/memory which stays byte-based. SI (base-1000) units, not binary -
// "Gbps" always means 10^9 bits/sec in networking.
export function formatBitsPerSec(bytesPerSec) {
    const bits = bytesPerSec * 8;
    if (bits >= 1e9) return (bits / 1e9).toFixed(2) + ' Gbps';
    if (bits >= 1e6) return (bits / 1e6).toFixed(2) + ' Mbps';
    if (bits >= 1e3) return (bits / 1e3).toFixed(2) + ' Kbps';
    return bits.toFixed(0) + ' bps';
}

// Mirrors the success/warning/error hex values from tailwind.config.js's dst
// / dst-dark daisyUI themes. ECharts options can't consume CSS custom
// properties, so the same status colors used by daisyUI classes elsewhere in
// the app (text-success, bg-warning, etc.) are duplicated here as plain hex.
const STATUS_HEX = {
    light: { good: '#2f9e6b', warning: '#ffd328', critical: '#e40014', unknown: '#b8bdb8' },
    dark: { good: '#2f9e6b', warning: '#ffd328', critical: '#fb2c36', unknown: '#3a4540' },
};

const SWITCH_HEX = { light: '#5f797c', dark: '#9ea5a0' };

export function getUsageStatus(percent) {
    if (percent === null || percent === undefined) return 'unknown';
    if (percent >= 90) return 'critical';
    if (percent >= 70) return 'warning';
    return 'good';
}

export function getStatusHex(status, isDark) {
    const palette = isDark ? STATUS_HEX.dark : STATUS_HEX.light;
    return palette[status] || palette.unknown;
}

function textInk(isDark) {
    return isDark ? '#f5f5ef' : '#152521';
}

function svgToDataUri(svg) {
    return 'image://data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

// A small server-rack glyph, tinted by usage status - shape carries identity
// ("this is a node"), color carries status ("how loaded is it"), so the two
// never compete on the same visual channel.
function serverIcon(color) {
    return svgToDataUri(
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">` +
            `<rect x="1" y="1.5" width="14" height="5" rx="1.2" fill="${color}"/>` +
            `<rect x="1" y="9.5" width="14" height="5" rx="1.2" fill="${color}"/>` +
            `<circle cx="3.3" cy="4" r="0.75" fill="#fff" fill-opacity="0.9"/>` +
            `<circle cx="3.3" cy="12" r="0.75" fill="#fff" fill-opacity="0.9"/>` +
            `<rect x="6" y="3.4" width="7" height="1.2" rx="0.5" fill="#fff" fill-opacity="0.55"/>` +
            `<rect x="6" y="11.4" width="7" height="1.2" rx="0.5" fill="#fff" fill-opacity="0.55"/>` +
            `</svg>`
    );
}

// A hub/switch glyph (radiating links from a center point) representing the
// shared Cilium Geneve overlay every node connects through.
function switchIcon(color) {
    return svgToDataUri(
        `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">` +
            `<rect x="1.5" y="1.5" width="13" height="13" rx="3" fill="${color}"/>` +
            `<g stroke="#fff" stroke-opacity="0.7" stroke-width="0.7">` +
            `<line x1="8" y1="4" x2="8" y2="6.4"/>` +
            `<line x1="8" y1="9.6" x2="8" y2="12"/>` +
            `<line x1="4" y1="8" x2="6.4" y2="8"/>` +
            `<line x1="9.6" y1="8" x2="12" y2="8"/>` +
            `</g>` +
            `<circle cx="8" cy="8" r="1.8" fill="#fff" fill-opacity="0.95"/>` +
            `<circle cx="8" cy="4" r="1" fill="#fff" fill-opacity="0.75"/>` +
            `<circle cx="8" cy="12" r="1" fill="#fff" fill-opacity="0.75"/>` +
            `<circle cx="4" cy="8" r="1" fill="#fff" fill-opacity="0.75"/>` +
            `<circle cx="12" cy="8" r="1" fill="#fff" fill-opacity="0.75"/>` +
            `</svg>`
    );
}

// Edge width scales with usage *percent* of that link's own capacity, not
// raw throughput - real link speeds here range from 1Gbps to 50Gbps, so a
// magnitude-based width would make the busiest node on a 1Gbps link look
// thinner than an idle node on a 50Gbps link. Percent keeps "how stressed is
// this link" consistent regardless of the node's actual NIC speed.
function edgeWidthForPercent(percent) {
    if (percent === null || percent === undefined) return 1.5;
    return Math.max(1.5, Math.min(8, 1.5 + (percent / 100) * 6.5));
}

function networkStatus(network) {
    return network ? getUsageStatus(network.used_percent) : 'unknown';
}

function networkReadout(network) {
    if (!network) return 'no recent data';
    const used = formatBitsPerSec(network.used_bytes_per_sec);
    const capacity = network.capacity_bytes_per_sec ? ` / ${formatBitsPerSec(network.capacity_bytes_per_sec)}` : '';
    return `${used}${capacity}`;
}

// Precomputed fixed coordinates (switch at center, nodes on a circle around
// it) rather than layout: 'force' - force layout re-simulates and visibly
// drifts on every poll-driven refresh, which reads as "wobbly" rather than
// "live and stable".
export function buildTopologyOption(nodes, switchInfo, isDark) {
    const radius = 160;
    const angleStep = (2 * Math.PI) / Math.max(nodes.length, 1);

    const graphNodes = [
        {
            id: 'switch',
            name: switchInfo?.label || 'Overlay Switch',
            x: 0,
            y: 0,
            fixed: true,
            symbol: switchIcon(isDark ? SWITCH_HEX.dark : SWITCH_HEX.light),
            symbolSize: 46,
            label: { color: textInk(isDark) },
        },
        ...nodes.map((node, i) => {
            const status = networkStatus(node.network);
            return {
                id: node.hostname,
                name: node.short_name,
                x: radius * Math.cos(i * angleStep - Math.PI / 2),
                y: radius * Math.sin(i * angleStep - Math.PI / 2),
                fixed: true,
                symbol: serverIcon(getStatusHex(status, isDark)),
                symbolSize: 36,
                label: { color: textInk(isDark) },
            };
        }),
    ];

    const edges = nodes.map((node) => {
        const status = networkStatus(node.network);
        return {
            source: 'switch',
            target: node.hostname,
            lineStyle: {
                width: edgeWidthForPercent(node.network?.used_percent),
                color: getStatusHex(status, isDark),
                type: node.network ? 'solid' : 'dashed',
                opacity: node.network ? 0.85 : 0.4,
            },
        };
    });

    return {
        tooltip: {
            formatter: (params) => {
                if (params.dataType === 'edge') {
                    const node = nodes.find((n) => n.hostname === params.data.target);
                    if (!node) return `${params.data.target}<br/>no recent data`;
                    return `${node.short_name}<br/>${networkReadout(node.network)}`;
                }
                if (params.data.id === 'switch') return switchInfo?.label || 'Overlay Switch';
                const node = nodes.find((n) => n.hostname === params.data.id);
                if (!node) return params.name;
                return (
                    `${node.short_name}<br/>` +
                    `CPU ${node.cpu?.used_percent ?? '–'}% · ` +
                    `RAM ${node.memory?.used_percent ?? '–'}%<br/>` +
                    `Net ${networkReadout(node.network)}`
                );
            },
        },
        series: [
            {
                type: 'graph',
                layout: 'none',
                roam: true,
                symbolKeepAspect: true,
                edgeSymbol: ['none', 'none'],
                lineStyle: { curveness: 0 },
                label: { show: true, position: 'bottom', fontSize: 12 },
                data: graphNodes,
                edges,
            },
        ],
    };
}

export { formatBytes };
