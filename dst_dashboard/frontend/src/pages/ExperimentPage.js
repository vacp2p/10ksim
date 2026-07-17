import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { useTheme } from '../context/ThemeContext';
import ChartPanel from '../components/ChartPanel';
import PageLoader from '../components/PageLoader';

function ExperimentPage() {
    const { experimentId } = useParams();
    const { isDark } = useTheme();
    const [experiment, setExperiment] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        axios
            .get(`${API_BASE_URL}/experiments/${experimentId}`)
            .then((res) => {
                setExperiment(res.data);
                setLoading(false);
            })
            .catch((err) => {
                setError(err.message);
                setLoading(false);
            });
    }, [experimentId]);

    if (loading) {
        return <PageLoader />;
    }

    if (error) {
        return (
            <div className="max-w-3xl mx-auto my-12 px-4">
                <div className="alert alert-error text-error-content">Error: {error}</div>
            </div>
        );
    }

    return (
        <div>
            <div className="bg-base-200 border-b border-base-100 px-4 lg:px-8 py-16">
                <div className="max-w-7xl mx-auto">
                    <Link
                        to="/experiments"
                        className="btn btn-sm btn-ghost gap-2 mb-6 -ml-2 text-base-content-secondary hover:text-primary"
                    >
                        &larr; Back to Experiments
                    </Link>
                    <div className="text-secondary font-mono text-sm uppercase tracking-widest mb-3">
                        {experiment.family}
                    </div>
                    <h1 className="text-3xl md:text-4xl font-bold mb-4 leading-tight tracking-tight">{experiment.title}</h1>
                    {experiment.description && (
                        <p className="text-base-content-secondary text-lg font-light max-w-3xl mb-6">
                            {experiment.description}
                        </p>
                    )}
                    <div className="flex flex-wrap gap-2">
                        {experiment.github_repo && (
                            <a
                                href={experiment.github_repo}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-sm btn-neutral gap-2"
                            >
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
                                </svg>
                                GitHub
                            </a>
                        )}
                        {experiment.github_pr && (
                            <a
                                href={experiment.github_pr}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-sm btn-neutral gap-2"
                            >
                                PR
                            </a>
                        )}
                        {experiment.docker_image && (
                            <span className="badge badge-outline badge-lg text-base-content-tertiary">
                                {experiment.docker_image}
                            </span>
                        )}
                        {experiment.date && (
                            <span className="badge badge-outline badge-lg text-base-content-tertiary">
                                {new Date(experiment.date).toLocaleDateString()}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            <div className="bg-base-300 px-4 lg:px-8 py-12">
                <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {experiment.panels.map((panelMeta) => (
                        <ChartPanel
                            key={panelMeta.name}
                            experimentId={experimentId}
                            panelMeta={panelMeta}
                            isDark={isDark}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}

export default ExperimentPage;
