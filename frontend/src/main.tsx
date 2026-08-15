import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import { ChartPreviewPage } from './pages/ChartPreviewPage.tsx';

// Dev preview harness — open http://localhost:5173/#/chart-preview
const isChartPreview =
  typeof window !== 'undefined' && window.location.hash === '#/chart-preview';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isChartPreview ? <ChartPreviewPage /> : <App />}
  </StrictMode>,
);
