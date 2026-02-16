import { useState, useCallback } from 'react';
import './App.css';
import ConfigurationPanel from './components/ConfigurationPanel';
import VisualizationPanel from './components/VisualizationPanel';
import ActionFeed from './components/ActionFeed';
import { api } from './api';
import type { AnalysisResult, DiagramData } from './types';

function App() {
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [actionDiagram, setActionDiagram] = useState<DiagramData | null>(null);
  const [actionDiagramLoading, setActionDiagramLoading] = useState(false);

  const handleAnalysisRun = (result: AnalysisResult) => {
    setAnalysisResult(result);
    // Clear any previously selected action when a new analysis runs
    setSelectedActionId(null);
    setActionDiagram(null);
  };

  const handleActionSelect = useCallback(async (actionId: string | null) => {
    setSelectedActionId(actionId);

    if (actionId === null) {
      setActionDiagram(null);
      return;
    }

    setActionDiagramLoading(true);
    setActionDiagram(null);
    try {
      const diagram = await api.getActionVariantDiagram(actionId);
      setActionDiagram(diagram);
    } catch (err) {
      console.error('Failed to fetch action variant diagram:', err);
      setActionDiagram(null);
    } finally {
      setActionDiagramLoading(false);
    }
  }, []);

  const handleDeselectAction = useCallback(() => {
    setSelectedActionId(null);
    setActionDiagram(null);
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'Arial, sans-serif' }}>
      <header style={{ padding: '0.5rem', borderBottom: '1px solid #ddd', backgroundColor: '#333', color: 'white' }}>
        <h1 style={{ margin: 0, fontSize: '1.2rem' }}>Expert_op4grid Recommender Interface</h1>
      </header>

      <ConfigurationPanel onAnalysisRun={handleAnalysisRun} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: '25%', borderRight: '1px solid #ddd', overflowY: 'auto', backgroundColor: '#f4f4f4' }}>
          <ActionFeed
            actions={analysisResult?.actions || {}}
            linesOverloaded={analysisResult?.lines_overloaded || []}
            selectedActionId={selectedActionId}
            onActionSelect={handleActionSelect}
          />
        </div>
        <div style={{ width: '75%', backgroundColor: '#fff', position: 'relative' }}>
          <VisualizationPanel
            pdfUrl={analysisResult?.pdf_url || null}
            actionDiagram={actionDiagram}
            actionDiagramLoading={actionDiagramLoading}
            selectedActionId={selectedActionId}
            onDeselectAction={handleDeselectAction}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
