import React, { useLayoutEffect } from 'react';
import { useLocation } from 'react-router-dom';

// Resets scroll to the top of the new page and replays a subtle fade/rise-in
// animation on every route change, so navigating between menu items reads as
// an intentional transition instead of an abrupt content swap.
function PageTransition({ children }) {
    const location = useLocation();

    useLayoutEffect(() => {
        window.scrollTo(0, 0);
    }, [location.pathname]);

    return (
        <div key={location.pathname} className="animate-page-in">
            {children}
        </div>
    );
}

export default PageTransition;
