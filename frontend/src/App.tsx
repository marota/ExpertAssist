import { useState } from 'react';
import './App.css';
import ConfigurationPanel from './components/ConfigurationPanel';
import VisualizationPanel from './components/VisualizationPanel';
import ActionFeed from './components/ActionFeed';
import { AnalysisResult } from './types';

function App() {
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);

  const handleAnalysisRun = (result: AnalysisResult) => {
    setAnalysisResult(result);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'Arial, sans-serif' }}>
      <header style={{ padding: '0.5rem', borderBottom: '1px solid #ddd', backgroundColor: '#333', color: 'white' }}>
        <h1 style={{ margin: 0, fontSize: '1.2rem' }}>Expert_op4grid Recommender Interface</h1>
      </header>

      <ConfigurationPanel onAnalysisRun={handleAnalysisRun} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: '25%', borderRight: '1px solid #ddd', overflowY: 'auto', backgroundColor: '#f4f4f4' }}>
          <ActionFeed actions={analysisResult?.actions || {}} />
        </div>
        <div style={{ width: '75%', backgroundColor: '#fff', position: 'relative' }}>
          <VisualizationPanel pdfUrl={analysisResult?.pdf_url || null} />
        </div>
      </div>
    </div>
  );
}

export default App;
