const FORMATTERS = {
    __BYTES_FORMATTER__: (value) => {
        if (value >= 1073741824) return (value / 1073741824).toFixed(2) + ' GB/s';
        if (value >= 1048576) return (value / 1048576).toFixed(2) + ' MB/s';
        if (value >= 1024) return (value / 1024).toFixed(2) + ' KB/s';
        return value.toFixed(2) + ' B/s';
    },
    __MS_FORMATTER__: (value) => {
        if (value >= 1000) return (value / 1000).toFixed(2) + ' s';
        return value.toFixed(2) + ' ms';
    },
    __SECONDS_FORMATTER__: (value) => {
        if (value >= 3600) return (value / 3600).toFixed(2) + ' h';
        if (value >= 60) return (value / 60).toFixed(2) + ' m';
        return value.toFixed(2) + ' s';
    },
    __PERCENT_FORMATTER__: (value) => value.toFixed(2) + '%',
    __NUMBER_FORMATTER__: (value) => {
        if (value >= 1000000000) return (value / 1000000000).toFixed(2) + 'B';
        if (value >= 1000000) return (value / 1000000).toFixed(2) + 'M';
        if (value >= 1000) return (value / 1000).toFixed(2) + 'K';
        return value.toFixed(0);
    },
};

function injectFormatters(option) {
    const yAxisMarker = option.yAxis?.axisLabel?.formatter;
    if (yAxisMarker && FORMATTERS[yAxisMarker]) {
        option.yAxis.axisLabel.formatter = FORMATTERS[yAxisMarker];
    }
    const tooltipMarker = option.tooltip?.valueFormatter;
    if (tooltipMarker && FORMATTERS[tooltipMarker]) {
        option.tooltip.valueFormatter = FORMATTERS[tooltipMarker];
    }
    return option;
}

const CHART_PALETTES = {
    light: {
        tooltipBg: '#f5f5ef',
        tooltipBorder: '#dbddd7',
        text: '#152521',
        axisLabel: '#475651',
        axisLine: '#b8bdb8',
        splitLine: '#eceee4',
        toolboxBorder: '#848e88',
        legendInactive: '#dbddd7',
    },
    dark: {
        tooltipBg: '#1b2420',
        tooltipBorder: '#2f3b35',
        text: '#f5f5ef',
        axisLabel: '#b8bdb8',
        axisLine: '#3a4540',
        splitLine: '#222b26',
        toolboxBorder: '#848e88',
        legendInactive: '#3a4540',
    },
};

// Panel options are generated server-side with colors tuned for a dark background.
// Re-theme them here so charts stay legible on whichever DST/VacLab theme is active,
// and hide the chart's own title since the card header above it already shows it.
function applyChartTheme(option, isDark) {
    const palette = isDark ? CHART_PALETTES.dark : CHART_PALETTES.light;

    if (option.title) {
        option.title = { ...option.title, show: false };
    }
    if (option.tooltip) {
        option.tooltip.backgroundColor = palette.tooltipBg;
        option.tooltip.borderColor = palette.tooltipBorder;
        option.tooltip.textStyle = { ...option.tooltip.textStyle, color: palette.text };
        if (option.tooltip.axisPointer?.lineStyle) {
            option.tooltip.axisPointer.lineStyle.color = palette.axisLine;
        }
    }
    if (option.legend) {
        option.legend.textStyle = { ...option.legend.textStyle, color: palette.axisLabel };
        option.legend.pageTextStyle = { ...option.legend.pageTextStyle, color: palette.axisLabel };
        option.legend.pageIconInactiveColor = palette.legendInactive;
    }
    if (option.toolbox) {
        option.toolbox.iconStyle = { ...option.toolbox.iconStyle, borderColor: palette.toolboxBorder };
    }
    ['xAxis', 'yAxis'].forEach((axisKey) => {
        const axis = option[axisKey];
        if (!axis) return;
        if (axis.axisLabel) axis.axisLabel.color = palette.axisLabel;
        if (axis.axisLine?.lineStyle) axis.axisLine.lineStyle.color = palette.axisLine;
        if (axis.splitLine?.lineStyle) axis.splitLine.lineStyle.color = palette.splitLine;
        if (axis.nameTextStyle) axis.nameTextStyle.color = palette.axisLabel;
    });
    return option;
}

// Builds a ready-to-render ECharts option from the raw server-provided panel
// option: injects real formatter functions in place of the string markers
// (functions can't survive JSON), and re-themes colors for the active theme.
export function buildChartOption(rawOption, isDark) {
    const option = JSON.parse(JSON.stringify(rawOption));
    injectFormatters(option);
    applyChartTheme(option, isDark);
    return option;
}

function stripAxisChrome(axis) {
    if (!axis) return axis;
    const strip = (a) => ({
        ...a,
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
    });
    return Array.isArray(axis) ? axis.map(strip) : strip(axis);
}

// A small, chrome-free variant for card/thumbnail previews: same data and
// series colors as the real chart, but no axes, legend, toolbox or tooltip -
// just the shape of the data at a glance.
export function buildThumbnailOption(rawOption, isDark) {
    const option = buildChartOption(rawOption, isDark);
    return {
        ...option,
        grid: { left: 4, right: 4, top: 6, bottom: 4, containLabel: false },
        legend: { show: false },
        toolbox: { show: false },
        tooltip: { show: false },
        xAxis: stripAxisChrome(option.xAxis),
        yAxis: stripAxisChrome(option.yAxis),
    };
}
