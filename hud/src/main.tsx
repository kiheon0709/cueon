import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './styles.css';

// ?device=xreal: on a full-screen display glasses (black = transparent), draw the HUD as a small
// panel low and to the right, roughly where Ray-Ban Display shows it.
const device = new URLSearchParams(location.search).get('device');
if (device) document.documentElement.dataset.device = device;

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root mount element');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
