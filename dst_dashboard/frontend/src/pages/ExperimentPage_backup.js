import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import ReactECharts from 'echarts-for-react';
import Sidebar from '../components/Sidebar';
import { API_BASE_URL } from '../config';

function ExperimentPage() {
    const { experimentId } = useParams();
    const [experiment, setExperiment] = useState(null);
    const [panels, setPanels] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

    useEffect(() => {
        const fetchData = async() => {
            try {
                const expResponse = await axios.get(`${API_BASE_URL}/experiments/${experimentId}`);
                setExperiment(expResponse.data);

                const panelsResponse = await axios.get(`${API_BASE_URL}/experiments/${experimentId}/panels`);
                setPanels(panelsResponse.data.panels || []);
                setLoading(false);
            } catch (err) {
                setError(err.message);
                setLoading(false);
            }
        };
        fetchData();
    }, [experimentId]);

    if (loading) {
        return ( <
            div className = "App" >
            <
            Sidebar isCollapsed = { sidebarCollapsed }
            onToggle = {
                () => setSidebarCollapsed(!sidebarCollapsed) }
            /> <
            div className = { `main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}` } >
            <
            div className = "container" >
            <
            div className = "loading" > Loading experiment... < /div> <
            /div> <
            /div> <
            /div>
        );
    }

    if (error) {
        return ( <
            div className = "App" >
            <
            Sidebar isCollapsed = { sidebarCollapsed }
            onToggle = {
                () => setSidebarCollapsed(!sidebarCollapsed) }
            /> <
            div className = { `main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}` } >
            <
            div className = "container" >
            <
            div className = "error" > Error: { error } < /div> <
            /div> <
            /div> <
            /div>
        );
    }

    return ( <
        div className = "App" >
        <
        Sidebar isCollapsed = { sidebarCollapsed }
        onToggle = {
            () => setSidebarCollapsed(!sidebarCollapsed) }
        /> <
        div className = { `main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}` } >
        <
        div className = "page-header" >
        <
        div className = "header-content" >
        <
        div className = "experiment-category-label" > { experiment.family } < /div> <
        h1 className = "page-title" > { experiment.title } < /h1> {
            experiment.description && ( <
                p className = "page-subtitle" > { experiment.description } < /p>
            )
        } <
        div className = "experiment-meta-links" > {
            experiment.github_repo && ( <
                a href = { experiment.github_repo }
                className = "meta-link"
                target = "_blank"
                rel = "noopener noreferrer" >
                <
                svg width = "14"
                height = "14"
                viewBox = "0 0 16 16"
                fill = "currentColor" >
                <
                path d = "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" / >
                <
                /svg>
                GitHub <
                /a>
            )
        } {
            experiment.github_pr && ( <
                a href = { experiment.github_pr }
                className = "meta-link"
                target = "_blank"
                rel = "noopener noreferrer" >
                🔀PR <
                /a>
            )
        } {
            experiment.docker_image && ( <
                span className = "meta-badge" > 🐳{ experiment.docker_image } < /span>
            )
        } {
            experiment.date && ( <
                span className = "meta-badge" > 📅{ new Date(experiment.date).toLocaleDateString() } < /span>
            )
        } <
        /div> <
        /div> <
        /div>

        <
        div className = "container" >
        <
        div className = "panels-section" >
        <
        <div className="panels-grid">
            {panels.map((panel) => {
                // Process panel option to inject JavaScript formatters
                const processedOption = JSON.parse(JSON.stringify(panel.option));

                // Define formatter functions
                const bytesFormatter = (value) => {
                    if (value >= 1073741824) return (value / 1073741824).toFixed(2) + ' GB/s';
                    if (value >= 1048576) return (value / 1048576).toFixed(2) + ' MB/s';
                    if (value >= 1024) return (value / 1024).toFixed(2) + ' KB/s';
                    return value.toFixed(2) + ' B/s';
                };

                const msFormatter = (value) => {
                    if (value >= 1000) return (value / 1000).toFixed(2) + ' s';
                    return value.toFixed(2) + ' ms';
                };

                const secondsFormatter = (value) => {
                    if (value >= 3600) return (value / 3600).toFixed(2) + ' h';
                    if (value >= 60) return (value / 60).toFixed(2) + ' m';
                    return value.toFixed(2) + ' s';
                };

                const percentFormatter = (value) => {
                    return value.toFixed(2) + '%';
                };

                const numberFormatter = (value) => {
                    if (value >= 1000000000) return (value / 1000000000).toFixed(2) + 'B';
                    if (value >= 1000000) return (value / 1000000).toFixed(2) + 'M';
                    if (value >= 1000) return (value / 1000).toFixed(2) + 'K';
                    return value.toFixed(0);
                };

                // Replace formatter markers with actual functions
                if (processedOption.yAxis?.axisLabel?.formatter === '__BYTES_FORMATTER__') {
                    processedOption.yAxis.axisLabel.formatter = bytesFormatter;
                }
                if (processedOption.tooltip?.valueFormatter === '__BYTES_FORMATTER__') {
                    processedOption.tooltip.valueFormatter = bytesFormatter;
                }
                
                if (processedOption.yAxis?.axisLabel?.formatter === '__MS_FORMATTER__') {
                    processedOption.yAxis.axisLabel.formatter = msFormatter;
                }
                if (processedOption.tooltip?.valueFormatter === '__MS_FORMATTER__') {
                    processedOption.tooltip.valueFormatter = msFormatter;
                }
                
                if (processedOption.yAxis?.axisLabel?.formatter === '__SECONDS_FORMATTER__') {
                    processedOption.yAxis.axisLabel.formatter = secondsFormatter;
                }
                if (processedOption.tooltip?.valueFormatter === '__SECONDS_FORMATTER__') {
                    processedOption.tooltip.valueFormatter = secondsFormatter;
                }
                
                if (processedOption.yAxis?.axisLabel?.formatter === '__PERCENT_FORMATTER__') {
                    processedOption.yAxis.axisLabel.formatter = percentFormatter;
                }
                if (processedOption.tooltip?.valueFormatter === '__PERCENT_FORMATTER__') {
                    processedOption.tooltip.valueFormatter = percentFormatter;
                }
                
                if (processedOption.yAxis?.axisLabel?.formatter === '__NUMBER_FORMATTER__') {
                    processedOption.yAxis.axisLabel.formatter = numberFormatter;
                }
                if (processedOption.tooltip?.valueFormatter === '__NUMBER_FORMATTER__') {
                    processedOption.tooltip.valueFormatter = numberFormatter;
                }

                return (
                    <div key={panel.panel_name} className="panel-card">
                        <h3 className="panel-title">{panel.panel_title}</h3>
                        {panel.error ? (
                            <div className="panel-error">Error: {panel.error}</div>
                        ) : (
                            <ReactECharts 
                                option={processedOption}
                                style={{ height: '350px', width: '100%' }}
                                opts={{ renderer: 'canvas' }}
                                notMerge={true}
                                lazyUpdate={true}
                            />
                        )}
                    </div>
                );
            })}
        </div>
        </div>
        </div>
        </div>
        </div>
    );
}

export default ExperimentPage;