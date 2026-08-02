import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { flattenExperiments } from '../utils/experiments';
import PageLoader from '../components/PageLoader';
import Reveal from '../components/Reveal';
import ExperimentCard from '../components/ExperimentCard';

function ExperimentsPage() {
    const [familiesData, setFamiliesData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedCategory, setSelectedCategory] = useState('all');
    const [query, setQuery] = useState('');

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
        return <PageLoader />;
    }

    if (error) {
        return (
            <div className="max-w-3xl mx-auto my-12 px-4">
                <div className="alert alert-error text-error-content">Error loading experiments: {error}</div>
            </div>
        );
    }

    const allExperiments = flattenExperiments(familiesData);

    const categoryFiltered = selectedCategory === 'all'
        ? allExperiments
        : allExperiments.filter((exp) => exp.family === selectedCategory);

    const normalizedQuery = query.trim().toLowerCase();
    const filteredExperiments = normalizedQuery
        ? categoryFiltered.filter((exp) => exp.title?.toLowerCase().includes(normalizedQuery))
        : categoryFiltered;

    return (
        <div>
            <section className="bg-base-200 border-b border-base-100 px-4 lg:px-8 py-14 md:py-20">
                <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                    Benchmarks
                </span>
                <h1 className="text-4xl md:text-5xl font-bold mt-5 tracking-tight">Experiments</h1>
                <p className="text-base-content-secondary text-lg font-light mt-3 max-w-2xl">
                    Browse experiments by category, or search for a specific run.
                </p>
            </section>

            {/* Filter bar: category pills + search, in one compact row */}
            <section className="sticky top-16 z-20 bg-base-200/95 backdrop-blur border-b border-base-100 px-4 lg:px-8 py-4">
                <div className="max-w-7xl mx-auto flex flex-col lg:flex-row lg:items-center gap-3">
                    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by category">
                        <button
                            type="button"
                            onClick={() => setSelectedCategory('all')}
                            className={`px-4 py-1.5 rounded text-sm font-medium border transition-colors ${selectedCategory === 'all'
                                    ? 'bg-primary text-primary-content border-primary'
                                    : 'border-base-300 text-base-content-secondary hover:border-secondary hover:text-primary'
                                }`}
                        >
                            All <span className="opacity-60">{allExperiments.length}</span>
                        </button>
                        {familiesData?.families?.map((family) => (
                            <button
                                type="button"
                                key={family.name}
                                onClick={() => setSelectedCategory(family.name)}
                                className={`px-4 py-1.5 rounded text-sm font-medium border transition-colors ${selectedCategory === family.name
                                        ? 'bg-primary text-primary-content border-primary'
                                        : 'border-base-300 text-base-content-secondary hover:border-secondary hover:text-primary'
                                    }`}
                            >
                                {family.name} <span className="opacity-60">{family.experiments?.length || 0}</span>
                            </button>
                        ))}
                    </div>
                    <label className="flex items-center gap-2 bg-base-100 border border-base-300 rounded px-4 py-1.5 w-full lg:w-64 lg:ml-auto shrink-0 focus-within:border-secondary transition-colors">
                        <i className="bi bi-search text-base-content-tertiary text-sm"></i>
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search experiments"
                            className="grow bg-transparent outline-none text-sm min-w-0"
                            aria-label="Search experiments"
                        />
                        {query && (
                            <button
                                type="button"
                                onClick={() => setQuery('')}
                                aria-label="Clear search"
                                className="text-base-content-tertiary hover:text-primary shrink-0"
                            >
                                <i className="bi bi-x-lg text-xs"></i>
                            </button>
                        )}
                    </label>
                </div>
            </section>

            {/* Experiments grid */}
            <section className="bg-base-300 py-12 px-4 lg:px-8">
                <div className="max-w-7xl mx-auto">
                    <p className="text-base-content-tertiary text-sm mb-6">
                        Showing {filteredExperiments.length} of {allExperiments.length} experiments
                    </p>
                    {filteredExperiments.length === 0 ? (
                        <div className="text-center py-16 text-base-content-tertiary">
                            <i className="bi bi-search text-3xl mb-3 block"></i>
                            No experiments match your search.
                        </div>
                    ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">
                        {filteredExperiments.map((experiment, index) => (
                            <Reveal key={experiment.id} delay={(index % 6) * 60} className="h-full">
                                <ExperimentCard experiment={experiment} />
                            </Reveal>
                        ))}
                    </div>
                    )}
                </div>
            </section>
        </div>
    );
}

export default ExperimentsPage;
