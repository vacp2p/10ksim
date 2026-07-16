import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API_BASE_URL } from '../config';

function ExperimentsPage() {
    const [familiesData, setFamiliesData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedCategory, setSelectedCategory] = useState('all');
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
        return <div className="text-center py-24 text-base-content-tertiary text-lg">Loading experiments...</div>;
    }

    if (error) {
        return (
            <div className="max-w-3xl mx-auto my-12 px-4">
                <div className="alert alert-error text-error-content">Error loading experiments: {error}</div>
            </div>
        );
    }

    const allExperiments = [];
    familiesData?.families?.forEach((family) => {
        family.experiments?.forEach((exp) => {
            allExperiments.push({
                ...exp,
                family: family.name,
            });
        });
    });

    const filteredExperiments = selectedCategory === 'all'
        ? allExperiments
        : allExperiments.filter((exp) => exp.family === selectedCategory);

    return (
        <div>
            <section className="bg-base-200 border-b border-base-100 px-4 lg:px-8 py-12">
                <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                    Data
                </span>
                <h1 className="text-3xl md:text-4xl font-bold mt-4">Experiments</h1>
                <p className="text-base-content-secondary text-lg font-light mt-2 max-w-2xl">
                    Browse benchmark runs by category and drill into individual experiment results.
                </p>
            </section>

            {/* Categories */}
            <section className="bg-base-200 py-10 px-4 lg:px-8 border-b border-base-100">
                <div className="max-w-7xl mx-auto">
                    <h2 className="font-mono text-xl uppercase tracking-widest mb-6">Categories</h2>
                    <div className="flex flex-wrap gap-3">
                        <button
                            type="button"
                            onClick={() => setSelectedCategory('all')}
                            className={`px-5 py-3 rounded-lg border text-center transition-colors ${selectedCategory === 'all'
                                    ? 'border-primary bg-base-100 text-primary'
                                    : 'border-base-100 bg-base-100/50 hover:border-secondary'
                                }`}
                        >
                            <div className="font-medium text-sm">All Experiments</div>
                            <div className="font-mono text-lg">{allExperiments.length}</div>
                        </button>
                        {familiesData?.families?.map((family) => (
                            <button
                                type="button"
                                key={family.name}
                                onClick={() => setSelectedCategory(family.name)}
                                className={`px-5 py-3 rounded-lg border text-center transition-colors ${selectedCategory === family.name
                                        ? 'border-primary bg-base-100 text-primary'
                                        : 'border-base-100 bg-base-100/50 hover:border-secondary'
                                    }`}
                            >
                                <div className="font-medium text-sm">{family.name}</div>
                                <div className="font-mono text-lg">{family.experiments?.length || 0}</div>
                            </button>
                        ))}
                    </div>
                </div>
            </section>

            {/* Experiments grid */}
            <section className="bg-base-300 py-12 px-4 lg:px-8">
                <div className="max-w-7xl mx-auto">
                    <h2 className="font-mono text-xl uppercase tracking-widest mb-6">
                        {selectedCategory === 'all' ? 'All Experiments' : `${selectedCategory} Experiments`}
                    </h2>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filteredExperiments.map((experiment) => (
                            <div
                                key={experiment.id}
                                onClick={() => navigate(`/experiment/${experiment.id}`)}
                                className="card bg-base-200 border border-base-100 hover:border-secondary hover:-translate-y-1 transition-all cursor-pointer"
                            >
                                <div className="card-body p-6">
                                    <div className="flex justify-between items-start gap-3">
                                        <h3 className="font-semibold leading-snug">{experiment.title}</h3>
                                        {experiment.date && (
                                            <span className="text-base-content-tertiary text-xs whitespace-nowrap">
                                                {new Date(experiment.date).toLocaleDateString('en-US', {
                                                    month: 'short',
                                                    day: 'numeric',
                                                })}
                                            </span>
                                        )}
                                    </div>

                                    {experiment.description && (
                                        <p className="text-base-content-secondary text-sm mt-2 line-clamp-2 font-light">
                                            {experiment.description}
                                        </p>
                                    )}

                                    <div className="flex flex-wrap gap-2 pt-4 mt-4 border-t border-base-100">
                                        {experiment.github_repo && (
                                            <a
                                                href={experiment.github_repo}
                                                onClick={(e) => e.stopPropagation()}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="badge badge-neutral gap-1"
                                            >
                                                <i className="bi bi-github"></i>
                                                GitHub
                                            </a>
                                        )}
                                        {experiment.github_pr && (
                                            <a
                                                href={experiment.github_pr}
                                                onClick={(e) => e.stopPropagation()}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="badge badge-neutral gap-1"
                                            >
                                                PR
                                            </a>
                                        )}
                                        {experiment.docker_image && (
                                            <span className="badge badge-outline text-base-content-tertiary" title={experiment.docker_image}>
                                                {experiment.docker_image.split(':').pop()}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
}

export default ExperimentsPage;
