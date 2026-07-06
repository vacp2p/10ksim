import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { API_BASE_URL } from '../config';

function HomePage() {
    const [stats, setStats] = useState({ totalExperiments: 0, totalFamilies: 0 });

    useEffect(() => {
        axios
            .get(`${API_BASE_URL}/experiments/families`)
            .then((res) => {
                setStats({
                    totalExperiments: res.data?.total_experiments || 0,
                    totalFamilies: res.data?.total_families || 0,
                });
            })
            .catch(() => {});
    }, []);

    return (
        <div>
            {/* Hero */}
            <section className="bg-base-200 px-4 py-24 md:py-32 text-center">
                <div className="max-w-4xl mx-auto">
                    <span className="text-secondary font-mono text-sm uppercase tracking-widest border-b border-secondary/40 pb-1">
                        VacLab DST Dashboard
                    </span>
                    <h1 className="text-4xl md:text-6xl font-bold mt-6 mb-6 leading-tight">
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
            <section className="bg-base-300 py-10 px-4">
                <div className="max-w-2xl mx-auto flex flex-row justify-around text-center">
                    <div className="flex flex-col items-center">
                        <i className="bi bi-activity text-3xl text-primary mb-2"></i>
                        <div className="font-mono font-medium text-4xl md:text-5xl">{stats.totalExperiments}</div>
                        <div className="text-base-content-secondary text-sm mt-2">Experiments</div>
                    </div>
                    <div className="border-l border-base-100" />
                    <div className="flex flex-col items-center">
                        <i className="bi bi-folder2 text-3xl text-primary mb-2"></i>
                        <div className="font-mono font-medium text-4xl md:text-5xl">{stats.totalFamilies}</div>
                        <div className="text-base-content-secondary text-sm mt-2">Projects</div>
                    </div>
                </div>
            </section>
        </div>
    );
}

export default HomePage;
