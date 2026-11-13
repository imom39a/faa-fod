import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { loadApi } from './api';
import { createStateStore } from './store/stateStore';
import './styles.css';

const root = createRoot(document.getElementById('root')!);

void loadApi().then((api) => {
  const store = createStateStore(api, 1000);
  root.render(
    <StrictMode>
      <App api={api} store={store} />
    </StrictMode>,
  );
});
