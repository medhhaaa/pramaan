import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import './i18n/index.js'; // explicit: a plain './i18n' resolves to the old i18n.jsx file
import App from './App.jsx';
import './styles/theme.css';
import './styles/app.css';
import { applyTheme, getTheme } from './lib/theme.js';

applyTheme(getTheme());

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {import.meta.env.VITE_ROUTER === 'memory' ? (
      <MemoryRouter>
        <App />
      </MemoryRouter>
    ) : (
      <BrowserRouter>
        <App />
      </BrowserRouter>
    )}
  </React.StrictMode>,
);
