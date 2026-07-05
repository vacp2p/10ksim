import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';
import HomePage from './pages/HomePage';
import ExperimentPage from './pages/ExperimentPage';

function App() {
    return ( <
        Router >
        <
        div className = "App" >
        <
        Routes >
        <
        Route path = "/"
        element = { < HomePage / > }
        /> <
        Route path = "/experiment/:experimentId"
        element = { < ExperimentPage / > }
        /> <
        /Routes> <
        /div> <
        /Router>
    );
}

export default App;