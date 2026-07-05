import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import ReactECharts from 'echarts-for-react';
import Sidebar from '../components/Sidebar';
import { API_BASE_URL } from '../config';

function HomePage() {
    const [familiesData, setFamiliesData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedCategory, setSelectedCategory] = useState('all');
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        fetchFamilies();
    }, []);

    const fetchFamilies = async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/experiments/families`);
            setFamiliesData(response.data);
            setLoading(false);
        } catch (err) {
            setError(err.message);
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="App">
                <Sidebar 
                    isCollapsed={sidebarCollapsed}
                    onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
                />
                <div className={`main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
                    <div className="container">
                        <div className="loading">Loading experiments...</div>
                    </div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="App">
                <Sidebar 
                    isCollapsed={sidebarCollapsed}
                    onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
                />
                <div className={`main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
                    <div className="container">
                        <div className="error">Error loading experiments: {error}</div>
                    </div>
                </div>
            </div>
        );
    }

    const totalExperiments = familiesData?.total_experiments || 0;
    const totalFamilies = familiesData?.total_families || 0;

    const allExperiments = [];
    familiesData?.families?.forEach((family) => {
        family.experiments?.forEach((exp) => {
            allExperiments.push({
                ...exp,
                family: family.name
            });
        });
    });

    const filteredExperiments = selectedCategory === 'all'
        ? allExperiments
        : allExperiments.filter(exp => exp.family === selectedCategory);

    return (
        <div className="App">
            <Sidebar 
                isCollapsed={sidebarCollapsed}
                onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
            />
            <div className={`main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
                <div className="page-header">
                    <div className="header-content">
                        <h1 className="page-title">DST Dashboard</h1>
                        <p className="page-subtitle">Distributed Systems Testing Analytics</p>
                    </div>
                </div>

                <div className="container">
                    <div className="categories-section">
                        <h2 className="section-title">Categories</h2>
                        <div className="category-boxes">
                            <div 
                                className={`category-box ${selectedCategory === 'all' ? 'active' : ''}`}
                                onClick={() => setSelectedCategory('all')}
                            >
                                <span className="category-box-name">All Experiments</span>
                                <span className="category-box-count">{allExperiments.length}</span>
                            </div>
                            {familiesData?.families?.map((family) => (
                                <div
                                    key={family.name}
                                    className={`category-box ${selectedCategory === family.name ? 'active' : ''}`}
                                    onClick={() => setSelectedCategory(family.name)}
                                >
                                    <span className="category-box-name">{family.name}</span>
                                    <span className="category-box-count">{family.experiments?.length || 0}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="experiments-section">
                        <h2 className="section-title">
                            {selectedCategory === 'all' ? 'All Experiments' : `${selectedCategory} Experiments`}
                        </h2>
                        <div className="experiments-grid">
                            {filteredExperiments.map((experiment) => (
                                <div
                                    key={experiment.id}
                                    className="experiment-card"
                                    onClick={() => navigate(`/experiment/${experiment.id}`)}
                                >
                                    <div className="experiment-header-card">
                                        <h3 className="experiment-title">{experiment.title}</h3>
                                        {experiment.date && (
                                            <span className="experiment-date">
                                                📅 {new Date(experiment.date).toLocaleDateString('en-US', {
                                                    month: 'short',
                                                    day: 'numeric'
                                                })}
                                            </span>
                                        )}
                                    </div>

                                    {experiment.description && (
                                        <p className="experiment-description">{experiment.description}</p>
                                    )}

                                    <div className="experiment-meta">
                                        {experiment.github_repo && (
                                            <a
                                                href={experiment.github_repo}
                                                className="meta-link"
                                                onClick={(e) => e.stopPropagation()}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >
                                                <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                                                    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                                                </svg>
                                                GitHub
                                            </a>
                                        )}
                                        {experiment.github_pr && (
                                            <a
                                                href={experiment.github_pr}
                                                className="meta-link"
                                                onClick={(e) => e.stopPropagation()}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >
                                                🔀 PR
                                            </a>
                                        )}
                                        {experiment.docker_image && (
                                            <span className="meta-badge" title={experiment.docker_image}>
                                                🐳 {experiment.docker_image.split(':').pop()}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="overview-section">
                        <div className="hero-stats">
                            <div className="hero-stat-card">
                                <p className="hero-stat-value">{totalExperiments}</p>
                                <p className="hero-stat-label">Total Experiments</p>
                                <p className="hero-stat-date">Last updated {new Date().toLocaleDateString()}</p>
                            </div>
                            <div className="hero-stat-card">
                                <p className="hero-stat-value">{totalFamilies}</p>
                                <p className="hero-stat-label">Categories</p>
                                <p className="hero-stat-date">Last updated {new Date().toLocaleDateString()}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default HomePage;
