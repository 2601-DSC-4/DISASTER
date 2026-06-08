import React from 'react';
import { createRoot } from 'react-dom/client';
import { AlertTriangle, Activity, Gauge, ServerCog, MapPin } from 'lucide-react';
import './styles.css';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App icons={{ AlertTriangle, Activity, Gauge, ServerCog, MapPin }} />
  </React.StrictMode>
);
