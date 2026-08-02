import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { flattenExperiments, sortByDateDesc } from '../utils/experiments';
import Reveal from '../components/Reveal';
import ExperimentCard from '../components/ExperimentCard';

const FEATURED_COUNT = 6;

function ExperimentCardSkeleton() {
    return (
        <div className="card h-full overflow-hidden bg-base-200 border border-base-100 animate-pulse">
            <div className="h-[152px] bg-base-300/60" />
            <div className="card-body p-6">
                <div className="h-4 w-2/3 bg-base-300/70 rounded mb-3" />
                <div className="h-3 w-full bg-base-300/60 rounded mb-2" />
                <div className="h-3 w-4/5 bg-base-300/60 rounded mb-6" />
                <div className="h-5 w-20 bg-base-300/60 rounded" />
            </div>
        </div>
    );
}

function HomePage() {
    const [stats, setStats] = useState({ totalExperiments: 0, totalFamilies: 0 });
    const [latestExperiments, setLatestExperiments] = useState([]);
    const [loadingLatest, setLoadingLatest] = useState(true);

    useEffect(() => {
        axios
            .get(`${API_BASE_URL}/experiments/families`)
            .then((res) => {
                setStats({
                    totalExperiments: res.data?.total_experiments || 0,
                    totalFamilies: res.data?.total_families || 0,
                });
                const all = flattenExperiments(res.data);
                setLatestExperiments(sortByDateDesc(all).slice(0, FEATURED_COUNT));
            })
            .catch(() => {})
            .finally(() => setLoadingLatest(false));
    }, []);

    return (
        <div>
            {/* Hero */}
            <section className="bg-base-200 px-4 py-24 md:py-32 text-center">
                <div className="max-w-4xl mx-auto">
                    <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                        VacLab DST Dashboard
                    </span>
                    <h1 className="text-4xl md:text-6xl font-bold mt-6 mb-6 leading-tight tracking-tight">
                        Evaluating Distributed Systems at Scale
                    </h1>
                    <p className="text-xl md:text-2xl text-base-content-secondary max-w-3xl mx-auto leading-relaxed font-light mb-10">
                        We build tooling and infrastructure to measure the performance of peer-to-peer network protocols,
                        identify bottlenecks and propose improvements.
                    </p>
                    <Link to="/experiments" className="btn btn-primary btn-lg gap-3">
                        Explore Experiments
                        <svg width="1em" height="1em" viewBox="0 0 12 11" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                            <path d="M0.499979 9.66667L8.49998 1.66667L1.33331 1.66667V0L11.3333 0V10H9.66665V2.83333L1.66665 10.8333L0.499979 9.66667Z" />
                        </svg>
                    </Link>
                </div>
            </section>

            {/* Stats bar */}
            <section className="bg-base-300 py-14 md:py-20 px-4">
                <div className="max-w-2xl mx-auto flex flex-row justify-around text-center">
                    <Reveal className="flex flex-col items-center">
                        <i className="bi bi-activity text-3xl text-primary mb-2"></i>
                        <div className="font-mono font-medium text-4xl md:text-5xl">{stats.totalExperiments}</div>
                        <div className="text-base-content-secondary text-sm mt-2">Experiments</div>
                    </Reveal>
                    <div className="border-l border-base-100" />
                    <Reveal delay={120} className="flex flex-col items-center">
                        <i className="bi bi-folder2 text-3xl text-primary mb-2"></i>
                        <div className="font-mono font-medium text-4xl md:text-5xl">{stats.totalFamilies}</div>
                        <div className="text-base-content-secondary text-sm mt-2">Projects</div>
                    </Reveal>
                </div>
            </section>

            {/* Latest experiments */}
            <section className="bg-base-200 py-16 md:py-24 px-4 lg:px-8 border-t border-base-100">
                <div className="max-w-7xl mx-auto">
                    <Reveal className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-10">
                        <div>
                            <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                                Results
                            </span>
                            <h2 className="text-3xl md:text-4xl font-bold mt-4 tracking-tight">Latest experiments</h2>
                        </div>
                        <Link to="/experiments" className="btn btn-outline btn-sm gap-2 self-start sm:self-auto">
                            View all experiments
                            <svg width="1em" height="1em" viewBox="0 0 12 11" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                                <path d="M0.499979 9.66667L8.49998 1.66667L1.33331 1.66667V0L11.3333 0V10H9.66665V2.83333L1.66665 10.8333L0.499979 9.66667Z" />
                            </svg>
                        </Link>
                    </Reveal>

                    {loadingLatest ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                            {Array.from({ length: 3 }).map((_, i) => (
                                <ExperimentCardSkeleton key={i} />
                            ))}
                        </div>
                    ) : latestExperiments.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">
                            {latestExperiments.map((experiment, index) => (
                                <Reveal key={experiment.id} delay={(index % 3) * 80} className="h-full">
                                    <ExperimentCard experiment={experiment} showThumbnail />
                                </Reveal>
                            ))}
                        </div>
                    ) : null}
                </div>
            </section>
        </div>
    );
}

export default HomePage;
