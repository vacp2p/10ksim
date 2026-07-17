import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import Navbar from './components/Navbar';
import Footer from './components/Footer';
import PageLoader from './components/PageLoader';
import PageTransition from './components/PageTransition';

const HomePage = lazy(() => import('./pages/HomePage'));
const ExperimentsPage = lazy(() => import('./pages/ExperimentsPage'));
const ExperimentPage = lazy(() => import('./pages/ExperimentPage'));
const ComingSoonPage = lazy(() => import('./pages/ComingSoonPage'));

function App() {
    return (
        <ThemeProvider>
            <Router>
                <div className="min-h-screen flex flex-col bg-base-300">
                    <Navbar />
                    <main className="grow flex flex-col pt-16">
                        <Suspense fallback={<PageLoader />}>
                            <PageTransition>
                                <Routes>
                                    <Route path="/" element={<HomePage />} />
                                    <Route path="/experiments" element={<ExperimentsPage />} />
                                    <Route path="/experiment/:experimentId" element={<ExperimentPage />} />
                                    <Route
                                        path="/vaclab/topology"
                                        element={<ComingSoonPage title="Topology" description="Interactive network topology visualization is coming soon." />}
                                    />
                                    <Route
                                        path="/vaclab/networks"
                                        element={<ComingSoonPage title="Networks" description="Live network explorer is coming soon." />}
                                    />
                                </Routes>
                            </PageTransition>
                        </Suspense>
                    </main>
                    <Footer />
                </div>
            </Router>
        </ThemeProvider>
    );
}

export default App;
