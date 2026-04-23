import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Pipelines from './pages/Pipelines';
import PipelineDetail from './pages/PipelineDetail';
import Agents from './pages/Agents';
import SettingsPage from './pages/Settings';
import AppSettings from './pages/AppSettings';
import { useTheme } from './hooks/useTheme';

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchInterval: false, retry: false, refetchOnWindowFocus: false } },
});

function AppInner() {
  useTheme(); // Apply theme from saved config on mount
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/pipelines" element={<Pipelines />} />
          <Route path="/pipelines/:id" element={<PipelineDetail />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/connectors" element={<SettingsPage />} />
          <Route path="/settings" element={<AppSettings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
