import { useState, useCallback } from 'react';
import './App.css';
import ConfigurationPanel from './components/ConfigurationPanel';
import VisualizationPanel from './components/VisualizationPanel';
import ActionFeed from './components/ActionFeed';
import { api } from './api';
import type { ActionDetail, AnalysisResult, DiagramData } from './types';

function App() {
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [actionDiagram, setActionDiagram] = useState<DiagramData | null>(null);
  const [actionDiagramLoading, setActionDiagramLoading] = useState(false);
  const [disconnectedElement, setDisconnectedElement] = useState<string | null>(null);
  const [actionViewMode, setActionViewMode] = useState<'network' | 'delta'>('network');

  const handleAnalysisRun = (result: AnalysisResult, element: string) => {
    setAnalysisResult(result);
    setDisconnectedElement(element);
    // Clear any previously selected action when a new analysis runs
    setSelectedActionId(null);
    setActionDiagram(null);
    setActionViewMode('network');
  };

  // Fetch diagram for currently selected action (flow_deltas always included)
  const fetchDiagram = useCallback(async (actionId: string) => {
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

  const handleActionSelect = useCallback(async (actionId: string | null) => {
    setSelectedActionId(actionId);

    if (actionId === null) {
      setActionDiagram(null);
      return;
    }

    fetchDiagram(actionId);
  }, [fetchDiagram]);

  const handleDeselectAction = useCallback(() => {
    setSelectedActionId(null);
    setActionDiagram(null);
  }, []);

  const handleManualActionAdded = useCallback((actionId: string, detail: ActionDetail) => {
    setAnalysisResult(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        actions: {
          ...prev.actions,
          [actionId]: detail,
        },
      };
    });
    // Auto-select the newly added action
    setSelectedActionId(actionId);
  }, []);

  const handleViewModeChange = useCallback((mode: 'network' | 'delta') => {
    setActionViewMode(mode);
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
            actionScores={analysisResult?.action_scores}
            linesOverloaded={analysisResult?.lines_overloaded || []}
            selectedActionId={selectedActionId}
            onActionSelect={handleActionSelect}
            disconnectedElement={disconnectedElement}
            onManualActionAdded={handleManualActionAdded}
            actionViewMode={actionViewMode}
            onViewModeChange={handleViewModeChange}
          />
        </div>
        <div style={{ width: '75%', backgroundColor: '#fff', position: 'relative' }}>
          <VisualizationPanel
            pdfUrl={analysisResult?.pdf_url || null}
            actionDiagram={actionDiagram}
            actionDiagramLoading={actionDiagramLoading}
            selectedActionId={selectedActionId}
            onDeselectAction={handleDeselectAction}
            linesOverloaded={analysisResult?.lines_overloaded || []}
            selectedActionDetail={selectedActionId && analysisResult?.actions ? analysisResult.actions[selectedActionId] ?? null : null}
            actionViewMode={actionViewMode}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
