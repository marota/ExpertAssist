import { useState, useEffect, useLayoutEffect, useCallback, useMemo, useRef } from 'react';
import './App.css';
import ConfigurationPanel from './components/ConfigurationPanel';
import VisualizationPanel from './components/VisualizationPanel';
import ActionFeed from './components/ActionFeed';
import { api } from './api';
import { usePanZoom } from './hooks/usePanZoom';
import { processSvg, buildMetadataIndex, applyOverloadedHighlights, applyActionTargetHighlights, applyDeltaVisuals } from './utils/svgUtils';
import type { ActionDetail, AnalysisResult, DiagramData, ViewBox, MetadataIndex, TabId } from './types';

function App() {
  // ===== Configuration State =====
  const [networkPath, setNetworkPath] = useState(
    localStorage.getItem('networkPath') || '/home/marotant/dev/Expert_op4grid_recommender/data/bare_env_20240828T0100Z_dijon_only'
  );
  const [actionPath, setActionPath] = useState(
    localStorage.getItem('actionPath') || '/home/marotant/dev/Expert_op4grid_recommender/data/action_space/reduced_model_actions_20240828T0100Z_new_dijon.json'
  );
  const [branches, setBranches] = useState<string[]>([]);
  const [voltageLevels, setVoltageLevels] = useState<string[]>([]);
  const [selectedBranch, setSelectedBranch] = useState('');
  const [configLoading, setConfigLoading] = useState(false);
  const [error, setError] = useState('');

  // Nominal voltage filter state
  const [nominalVoltageMap, setNominalVoltageMap] = useState<Record<string, number>>({});
  const [uniqueVoltages, setUniqueVoltages] = useState<number[]>([]);
  const [voltageRange, setVoltageRange] = useState<[number, number]>([0, 400]);

  // ===== Analysis State =====
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [infoMessage, setInfoMessage] = useState('');

  // ===== Visualization State =====
  const [activeTab, setActiveTab] = useState<TabId>('n');
  const activeTabRef = useRef<TabId>(activeTab);
  useLayoutEffect(() => { activeTabRef.current = activeTab; }, [activeTab]);
  const prevTabRef = useRef<TabId>(activeTab);

  const [nDiagram, setNDiagram] = useState<DiagramData | null>(null);
  const [n1Diagram, setN1Diagram] = useState<DiagramData | null>(null);
  const [n1Loading, setN1Loading] = useState(false);

  // Action variant diagram state
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);
  const [actionDiagram, setActionDiagram] = useState<DiagramData | null>(null);
  const [actionDiagramLoading, setActionDiagramLoading] = useState(false);

  // Delta visualization mode
  const [actionViewMode, setActionViewMode] = useState<'network' | 'delta'>('network');

  const [originalViewBox, setOriginalViewBox] = useState<ViewBox | null>(null);
  const [inspectQuery, setInspectQuery] = useState('');

  // Independent Refs for N, N-1, and Action Variant
  const nSvgContainerRef = useRef<HTMLDivElement>(null);
  const n1SvgContainerRef = useRef<HTMLDivElement>(null);
  const actionSvgContainerRef = useRef<HTMLDivElement>(null);

  // Native Pan/Zoom Instances
  const nPZ = usePanZoom(nSvgContainerRef, nDiagram?.originalViewBox, activeTab === 'n');
  const n1PZ = usePanZoom(n1SvgContainerRef, n1Diagram?.originalViewBox, activeTab === 'n-1');
  const actionPZ = usePanZoom(actionSvgContainerRef, actionDiagram?.originalViewBox, activeTab === 'action');

  // Zoom state tracking
  const lastZoomState = useRef({ query: '', branch: '' });
  // Captured viewBox to re-apply after the action diagram loads
  const actionSyncSourceRef = useRef<ViewBox | null>(null);

  // Persist paths to localStorage
  useEffect(() => { localStorage.setItem('networkPath', networkPath); }, [networkPath]);
  useEffect(() => { localStorage.setItem('actionPath', actionPath); }, [actionPath]);

  // ===== Config Loading =====
  const handleLoadConfig = useCallback(async () => {
    setConfigLoading(true);
    setError('');
    setInfoMessage('');
    setNDiagram(null);
    setN1Diagram(null);
    setResult(null);
    setSelectedActionId(null);
    setActionDiagram(null);
    setActiveTab('n');
    lastZoomState.current = { query: '', branch: '' };

    try {
      await api.updateConfig({ network_path: networkPath, action_file_path: actionPath });

      const [branchesList, vlRes, nomVRes] = await Promise.all([
        api.getBranches(),
        api.getVoltageLevels(),
        api.getNominalVoltages(),
      ]);

      setBranches(branchesList);
      setVoltageLevels(vlRes);
      setSelectedBranch('');

      // Set up nominal voltage filter
      setNominalVoltageMap(nomVRes.mapping);
      setUniqueVoltages(nomVRes.unique_kv);
      if (nomVRes.unique_kv.length > 0) {
        setVoltageRange([nomVRes.unique_kv[0], nomVRes.unique_kv[nomVRes.unique_kv.length - 1]]);
      }

      // Fetch base diagram
      fetchBaseDiagram(vlRes.length);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError('Failed to load config: ' + (e.response?.data?.detail || e.message));
    } finally {
      setConfigLoading(false);
    }
  }, [networkPath, actionPath]);

  const fetchBaseDiagram = async (vlCount: number) => {
    try {
      const res = await api.getNetworkDiagram();
      const { svg, viewBox } = processSvg(res.svg, vlCount || 0);
      if (viewBox) setOriginalViewBox(viewBox);
      setNDiagram({ ...res, svg, originalViewBox: viewBox });
    } catch (err) {
      console.error('Failed to fetch diagram:', err);
    }
  };

  // ===== N-1 Diagram Fetching =====
  useEffect(() => {
    if (!selectedBranch) {
      setN1Diagram(null);
      return;
    }
    if (branches.length > 0 && !branches.includes(selectedBranch)) {
      return;
    }

    const fetchN1 = async () => {
      setN1Loading(true);
      setActiveTab('n-1');
      try {
        const res = await api.getN1Diagram(selectedBranch);
        const { svg, viewBox } = processSvg(res.svg, voltageLevels.length);
        setN1Diagram({ ...res, svg, originalViewBox: viewBox });
      } catch (err) {
        console.error('Failed to fetch N-1 diagram', err);
        setError(`Failed to fetch N-1 diagram for ${selectedBranch}`);
      } finally {
        setN1Loading(false);
      }
    };
    fetchN1();
  }, [selectedBranch, branches, voltageLevels.length]);

  // ===== Analysis =====
  const handleRunAnalysis = useCallback(async () => {
    if (!selectedBranch) return;
    setAnalysisLoading(true);
    setError('');
    setResult(null);
    setInfoMessage('');
    setSelectedActionId(null);
    setActionDiagram(null);
    setActiveTab('overflow');

    try {
      const response = await fetch('http://localhost:8000/api/run-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disconnected_element: selectedBranch }),
      });
      if (!response.ok) throw new Error('Analysis failed');
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop()!;
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            if (event.type === 'pdf') setResult(p => ({ ...p!, pdf_url: event.pdf_url } as AnalysisResult));
            else if (event.type === 'result') { setResult(event); if (event.message) setInfoMessage(event.message); }
            else if (event.type === 'error') setError('Analysis failed: ' + event.message);
          } catch (e) {
            console.error('Stream error:', e);
          }
        }
      }
    } catch (err: unknown) {
      setError('Analysis failed: ' + (err as Error).message);
    } finally {
      setAnalysisLoading(false);
    }
  }, [selectedBranch]);

  // ===== Action Selection =====
  const handleActionSelect = useCallback(async (actionId: string | null) => {
    if (actionId === selectedActionId) {
      // Deselect — return to N-1 tab
      setSelectedActionId(null);
      setActionDiagram(null);
      setActiveTab('n-1');
      return;
    }

    // Capture current viewBox for sync after diagram loads
    actionSyncSourceRef.current =
      (activeTabRef.current === 'action' ? actionPZ.viewBox : null)
      || n1PZ.viewBox || nPZ.viewBox;

    setSelectedActionId(actionId);
    setActionDiagram(null);
    if (actionId === null) return;

    setActionDiagramLoading(true);
    setActiveTab('action');
    try {
      const res = await api.getActionVariantDiagram(actionId);
      const { svg, viewBox } = processSvg(res.svg, voltageLevels.length);
      setActionDiagram({ ...res, svg, originalViewBox: viewBox });
    } catch (err) {
      console.error('Failed to fetch action variant diagram:', err);
      setError('Failed to fetch action variant diagram for ' + actionId);
    } finally {
      setActionDiagramLoading(false);
    }
  }, [selectedActionId, actionPZ.viewBox, n1PZ.viewBox, nPZ.viewBox, voltageLevels.length]);

  const handleManualActionAdded = useCallback((actionId: string, detail: ActionDetail) => {
    setResult(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        actions: {
          ...prev.actions,
          [actionId]: detail,
        },
      };
    });
    // Auto-select the newly added action (and fetch its diagram)
    handleActionSelect(actionId);
  }, [handleActionSelect]);

  const handleViewModeChange = useCallback((mode: 'network' | 'delta') => {
    setActionViewMode(mode);
  }, []);

  // ===== Asset Click (from action card badges) =====
  const handleAssetClick = useCallback((actionId: string, assetName: string) => {
    // Fill the inspect field so the header shows it and zoom is consistent
    setInspectQuery(assetName);
    if (actionId !== selectedActionId) {
      // Select the action; the zoom effect fires once its diagram loads
      handleActionSelect(actionId);
    } else {
      // Action already selected — just ensure we're on the action tab
      setActiveTab('action');
    }
  }, [selectedActionId, handleActionSelect]);

  // ===== Reset View =====
  const handleManualReset = useCallback(() => {
    setInspectQuery('');

    const currentPZ = activeTab === 'action' ? actionPZ : activeTab === 'n' ? nPZ : n1PZ;
    const currentDiagram = activeTab === 'action' ? actionDiagram : activeTab === 'n' ? nDiagram : n1Diagram;
    const viewBox = currentDiagram?.originalViewBox || originalViewBox;

    if (currentPZ && viewBox) {
      currentPZ.setViewBox(viewBox);
      lastZoomState.current = { query: '', branch: '' };
    }

    // Clear highlights
    const container = activeTab === 'action' ? actionSvgContainerRef.current
      : activeTab === 'n' ? nSvgContainerRef.current : n1SvgContainerRef.current;
    if (container) {
      container.querySelectorAll('.nad-highlight').forEach(el => el.classList.remove('nad-highlight'));
    }
  }, [activeTab, actionPZ, nPZ, n1PZ, actionDiagram, nDiagram, n1Diagram, originalViewBox]);

  // ===== Tab Synchronization =====
  useEffect(() => {
    const prevTab = prevTabRef.current;
    prevTabRef.current = activeTab;

    // Don't sync when coming from / going to overflow
    if (prevTab === 'overflow' || activeTab === 'overflow') return;

    const sourceVB = prevTab === 'n' ? nPZ.viewBox
      : prevTab === 'n-1' ? n1PZ.viewBox
        : prevTab === 'action' ? actionPZ.viewBox
          : null;
    if (!sourceVB) return;

    if (activeTab === 'n') nPZ.setViewBox(sourceVB);
    else if (activeTab === 'n-1') n1PZ.setViewBox(sourceVB);
    else if (activeTab === 'action') actionPZ.setViewBox(sourceVB);
  }, [activeTab, nPZ, n1PZ, actionPZ]);

  // Re-sync after action diagram loads
  useEffect(() => {
    if (actionDiagram && activeTab === 'action' && actionSyncSourceRef.current) {
      actionPZ.setViewBox(actionSyncSourceRef.current);
      actionSyncSourceRef.current = null;
    }
  }, [actionDiagram, activeTab, actionPZ]);

  // ===== Metadata Indices =====
  const nMetaIndex = useMemo(() => buildMetadataIndex(nDiagram?.metadata), [nDiagram?.metadata]);
  const n1MetaIndex = useMemo(() => buildMetadataIndex(n1Diagram?.metadata), [n1Diagram?.metadata]);
  const actionMetaIndex = useMemo(() => buildMetadataIndex(actionDiagram?.metadata), [actionDiagram?.metadata]);

  // ===== Highlights =====
  useEffect(() => {
    const overloadedLines = result?.lines_overloaded || [];

    // N-1 Tab Logic
    if (activeTab === 'n-1') {
      if (actionViewMode !== 'delta' && n1SvgContainerRef.current && n1MetaIndex && overloadedLines.length > 0) {
        applyOverloadedHighlights(n1SvgContainerRef.current, n1MetaIndex, overloadedLines);
      }
      applyDeltaVisuals(n1SvgContainerRef.current, n1Diagram, n1MetaIndex, actionViewMode === 'delta');
    }

    // Action Tab Logic
    if (activeTab === 'action') {
      applyDeltaVisuals(actionSvgContainerRef.current, actionDiagram, actionMetaIndex, actionViewMode === 'delta');

      const actionDetail = result?.actions?.[selectedActionId || ''];

      if (actionDetail) {
        if (actionViewMode !== 'delta') {
          const stillOverloaded: string[] = [];
          if (overloadedLines.length > 0 && actionDetail.rho_after) {
            overloadedLines.forEach((name, i) => {
              if (actionDetail.rho_after![i] != null && actionDetail.rho_after![i] > 1.0) {
                stillOverloaded.push(name);
              }
            });
          }
          if (actionDetail.max_rho != null && actionDetail.max_rho > 1.0 && actionDetail.max_rho_line) {
            if (!stillOverloaded.includes(actionDetail.max_rho_line)) {
              stillOverloaded.push(actionDetail.max_rho_line);
            }
          }
          if (actionSvgContainerRef.current && actionMetaIndex) {
            applyOverloadedHighlights(actionSvgContainerRef.current, actionMetaIndex, stillOverloaded);
          }
        }

        // Always highlight action targets (Yellow halo)
        if (actionSvgContainerRef.current) {
          applyActionTargetHighlights(actionSvgContainerRef.current, actionMetaIndex, actionDetail, selectedActionId);
        }
      } else {
        if (actionSvgContainerRef.current) {
          applyActionTargetHighlights(actionSvgContainerRef.current, null, null, null);
        }
      }
    }
  }, [n1Diagram, actionDiagram, n1MetaIndex, actionMetaIndex, result, selectedActionId, actionViewMode, activeTab]);

  // ===== Voltage Range Filter =====
  useEffect(() => {
    if (uniqueVoltages.length === 0 || Object.keys(nominalVoltageMap).length === 0) return;

    const [minKv, maxKv] = voltageRange;
    const isInRange = (vlId: string) => {
      const kv = nominalVoltageMap[vlId];
      return kv != null && kv >= minKv && kv <= maxKv;
    };

    const applyFilter = (container: HTMLElement | null, metaIndex: MetadataIndex | null) => {
      if (!container || !metaIndex) return;
      const { nodesByEquipmentId, nodesBySvgId, edgesByEquipmentId } = metaIndex;

      const idMap = new Map<string, HTMLElement>();
      container.querySelectorAll('[id]').forEach(el => idMap.set(el.id, el as HTMLElement));

      for (const [vlId, node] of nodesByEquipmentId) {
        const visible = isInRange(vlId);
        const show = visible ? '' : 'none';
        const el = idMap.get(node.svgId);
        if (el) el.style.display = show;
        if (node.legendSvgId) {
          const leg = idMap.get(node.legendSvgId as string);
          if (leg) leg.style.display = show;
        }
        if (node.legendEdgeSvgId) {
          const legE = idMap.get(node.legendEdgeSvgId as string);
          if (legE) legE.style.display = show;
        }
      }

      for (const [, edge] of edgesByEquipmentId) {
        const node1 = nodesBySvgId.get(edge.node1);
        const node2 = nodesBySvgId.get(edge.node2);
        const vl1InRange = node1 ? isInRange(node1.equipmentId) : true;
        const vl2InRange = node2 ? isInRange(node2.equipmentId) : true;
        const edgeVisible = vl1InRange || vl2InRange;
        const show = edgeVisible ? '' : 'none';

        const el = idMap.get(edge.svgId);
        if (el) el.style.display = show;
        if (edge.edgeInfo1?.svgId) {
          const ei = idMap.get(edge.edgeInfo1.svgId);
          if (ei) ei.style.display = show;
        }
        if (edge.edgeInfo2?.svgId) {
          const ei = idMap.get(edge.edgeInfo2.svgId);
          if (ei) ei.style.display = show;
        }
      }
    };

    applyFilter(nSvgContainerRef.current, nMetaIndex);
    applyFilter(n1SvgContainerRef.current, n1MetaIndex);
    applyFilter(actionSvgContainerRef.current, actionMetaIndex);
  }, [voltageRange, nDiagram, n1Diagram, actionDiagram, nMetaIndex, n1MetaIndex, actionMetaIndex, nominalVoltageMap, uniqueVoltages]);

  // ===== Zoom to Element =====
  const zoomToElement = useCallback((targetId: string) => {
    const currentPZ = activeTab === 'action' ? actionPZ : activeTab === 'n' ? nPZ : n1PZ;
    const container = activeTab === 'action' ? actionSvgContainerRef.current
      : activeTab === 'n' ? nSvgContainerRef.current : n1SvgContainerRef.current;
    const index = activeTab === 'action' ? actionMetaIndex : activeTab === 'n' ? nMetaIndex : n1MetaIndex;
    if (!currentPZ || !container || !index) return;

    try {
      const { nodesByEquipmentId, nodesBySvgId, edgesByEquipmentId, edgesByNode } = index;
      const points: { x: number; y: number }[] = [];

      const addNodePointsBySvgId = (svgId: string) => {
        const n = nodesBySvgId.get(svgId);
        if (n) points.push({ x: n.x, y: n.y });
        return n;
      };

      const targetNode = nodesByEquipmentId.get(targetId);
      const targetEdge = edgesByEquipmentId.get(targetId);
      let targetSvgId: string | undefined;

      if (targetNode) {
        targetSvgId = targetNode.svgId;
        points.push({ x: targetNode.x, y: targetNode.y });
        (edgesByNode.get(targetNode.svgId) || []).forEach(e => {
          addNodePointsBySvgId(e.node1);
          addNodePointsBySvgId(e.node2);
        });
      } else if (targetEdge) {
        targetSvgId = targetEdge.svgId;
        const n1 = addNodePointsBySvgId(targetEdge.node1);
        const n2 = addNodePointsBySvgId(targetEdge.node2);
        if (n1) (edgesByNode.get(n1.svgId) || []).forEach(e => { addNodePointsBySvgId(e.node1); addNodePointsBySvgId(e.node2); });
        if (n2) (edgesByNode.get(n2.svgId) || []).forEach(e => { addNodePointsBySvgId(e.node1); addNodePointsBySvgId(e.node2); });
      }

      if (points.length > 0) {
        const minX = Math.min(...points.map(p => p.x));
        const maxX = Math.max(...points.map(p => p.x));
        const minY = Math.min(...points.map(p => p.y));
        const maxY = Math.max(...points.map(p => p.y));

        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        const boxW = Math.max(maxX - minX, 50);
        const boxH = Math.max(maxY - minY, 50);

        const padding = 1.8;
        const screenW = container.getBoundingClientRect().width;
        const screenH = container.getBoundingClientRect().height;
        const screenAR = screenW / screenH;

        let targetW = boxW * padding;
        let targetH = boxH * padding;

        if (targetW / targetH > screenAR) {
          targetH = targetW / screenAR;
        } else {
          targetW = targetH * screenAR;
        }

        const targetX = centerX - targetW / 2;
        const targetY = centerY - targetH / 2;

        currentPZ.setViewBox({ x: targetX, y: targetY, w: targetW, h: targetH });

        // Highlight the target element
        container.querySelectorAll('.nad-highlight').forEach(el => el.classList.remove('nad-highlight'));
        if (targetSvgId) {
          const el = container.querySelector(`[id="${targetSvgId}"]`);
          if (el) el.classList.add('nad-highlight');
        }
      }
    } catch (e) {
      console.error('Zoom failed:', e);
    }
  }, [activeTab, actionPZ, nPZ, n1PZ, actionMetaIndex, nMetaIndex, n1MetaIndex]);

  // Auto-zoom to selected element
  useEffect(() => {
    if (activeTab === 'overflow') return;

    const queryChanged = inspectQuery !== lastZoomState.current.query;
    const branchChanged = !inspectQuery && selectedBranch !== lastZoomState.current.branch;

    if (!queryChanged && !branchChanged) return;

    const targetId = inspectQuery || selectedBranch;

    // Cleared inspect -> reset view
    if (!targetId && queryChanged) {
      lastZoomState.current = { query: inspectQuery, branch: selectedBranch };
      handleManualReset();
      return;
    }

    if (!targetId) return;

    // Branch changes should zoom on the N-1 tab, not N
    if (branchChanged && activeTab === 'n') return;

    // Only consume the zoom intent when the container has SVG content
    const container = activeTab === 'action' ? actionSvgContainerRef.current
      : activeTab === 'n' ? nSvgContainerRef.current : n1SvgContainerRef.current;
    if (!container || !container.querySelector('svg')) return;

    lastZoomState.current = { query: inspectQuery, branch: selectedBranch };
    zoomToElement(targetId);
  }, [activeTab, nDiagram, n1Diagram, actionDiagram, inspectQuery, selectedBranch, zoomToElement, handleManualReset]);

  // Inspectable items list
  const inspectableItems = useMemo(() =>
    [...branches, ...voltageLevels].sort(),
    [branches, voltageLevels]
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <header style={{ background: '#2c3e50', color: 'white', padding: '10px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Expert Recommender</h2>
        <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Standalone Interface v3.0 (Multi-Tab)</div>
      </header>

      <ConfigurationPanel
        networkPath={networkPath}
        actionPath={actionPath}
        onNetworkPathChange={setNetworkPath}
        onActionPathChange={setActionPath}
        branches={branches}
        selectedBranch={selectedBranch}
        onBranchChange={setSelectedBranch}
        inspectQuery={inspectQuery}
        onInspectQueryChange={setInspectQuery}
        inspectableItems={inspectableItems}
        onLoadConfig={handleLoadConfig}
        onRunAnalysis={handleRunAnalysis}
        onResetView={handleManualReset}
        configLoading={configLoading}
        analysisLoading={analysisLoading}
      />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: '25%', background: '#eee', borderRight: '1px solid #ccc', overflowY: 'auto' }}>
          <ActionFeed
            actions={result?.actions || {}}
            actionScores={result?.action_scores}
            linesOverloaded={result?.lines_overloaded || []}
            selectedActionId={selectedActionId}
            onActionSelect={handleActionSelect}
            onAssetClick={handleAssetClick}
            disconnectedElement={selectedBranch || null}
            onManualActionAdded={handleManualActionAdded}
            actionViewMode={actionViewMode}
            onViewModeChange={handleViewModeChange}
            analysisLoading={analysisLoading}
          />
        </div>
        <div style={{ flex: 1, background: 'white', display: 'flex', flexDirection: 'column' }}>
          <VisualizationPanel
            activeTab={activeTab}
            onTabChange={setActiveTab}
            nDiagram={nDiagram}
            n1Diagram={n1Diagram}
            n1Loading={n1Loading}
            actionDiagram={actionDiagram}
            actionDiagramLoading={actionDiagramLoading}
            selectedActionId={selectedActionId}
            result={result}
            analysisLoading={analysisLoading}
            nSvgContainerRef={nSvgContainerRef}
            n1SvgContainerRef={n1SvgContainerRef}
            actionSvgContainerRef={actionSvgContainerRef}
            uniqueVoltages={uniqueVoltages}
            voltageRange={voltageRange}
            onVoltageRangeChange={setVoltageRange}
          />
        </div>
      </div>
      {error && (
        <div style={{
          position: 'fixed', bottom: 20, right: 20,
          background: '#e74c3c', color: 'white',
          padding: '10px 20px', borderRadius: '4px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.2)', zIndex: 1000,
        }}>
          {error}
        </div>
      )}
      {infoMessage && (
        <div style={{
          position: 'fixed', bottom: 20, left: 20,
          background: '#3498db', color: 'white',
          padding: '10px 20px', borderRadius: '4px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.2)', zIndex: 1000,
        }}>
          {infoMessage}
        </div>
      )}
    </div>
  );
}

export default App;
