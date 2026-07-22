import React from 'react';
import { useNavigate } from 'react-router-dom';
import ExperimentThumbnail from './ExperimentThumbnail';

// Rendered as a grid item, so it must be h-full itself (a Grid item's default
// stretch only reaches its direct child) and use flex-col so the footer badges
// line up at the same baseline across cards with different description lengths.
// showThumbnail adds a lazy-loaded preview of the experiment's first result
// panel above the text - used on the homepage; the full Experiments list
// stays text-only since rendering a chart per card there would be a lot of
// extra requests for a page that's meant for fast scanning, not browsing.
function ExperimentCard({ experiment, showThumbnail = false }) {
    const navigate = useNavigate();
    const goToDetail = () => navigate(`/experiment/${experiment.id}`);

    return (
        <div
            role="link"
            tabIndex={0}
            onClick={goToDetail}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    goToDetail();
                }
            }}
            className="card h-full flex flex-col overflow-hidden bg-base-200 border border-base-100 hover:border-secondary hover:-translate-y-1 transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
        >
            {showThumbnail && <ExperimentThumbnail experimentId={experiment.id} />}
            <div className="card-body p-6 flex flex-col grow">
                <div className="grow">
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
                </div>

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
    );
}

export default ExperimentCard;
