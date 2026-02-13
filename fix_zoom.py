
import os

file_path = 'standalone_interface.html'

with open(file_path, 'r') as f:
    lines = f.readlines()

new_zoom_logic = """            // Zoom Logic (Handles Inspect, N-1 Auto-Zoom)
            useEffect(() => {
                if (activeTab === 'overflow') return;

                // We need a slight delay to allow the resize/init above to settle
                const timer = setTimeout(() => {
                    const currentPZ = activeTab === 'n' ? nPZ : n1PZ;
                    const container = activeTab === 'n' ? nSvgContainerRef.current : n1SvgContainerRef.current;
                    const currentDiagram = activeTab === 'n' ? nDiagram : n1Diagram;

                    if (!currentPZ || !container || !currentDiagram?.metadata) return;

                    // Clear highlights
                    container.querySelectorAll('.nad-highlight').forEach(el => el.classList.remove('nad-highlight'));

                    // Check triggers
                    const queryChanged = inspectQuery !== lastZoomState.current.query;
                    const branchChanged = !inspectQuery && selectedBranch !== lastZoomState.current.branch;

                    if (!queryChanged && !branchChanged) return;

                    lastZoomState.current = { query: inspectQuery, branch: selectedBranch };

                    let targetId = inspectQuery || selectedBranch;

                    // If we cleared query/branch -> Reset
                    if (!targetId && queryChanged) {
                        handleManualReset();
                        return;
                    }

                    if (!targetId) return;

                    try {
                        const meta = typeof currentDiagram.metadata === 'string' ? JSON.parse(currentDiagram.metadata) : currentDiagram.metadata;
                        const nodes = meta.nodes || [];
                        const edges = meta.edges || [];
                        const points = [];

                        const addNodePointsBySvgId = (svgId) => {
                            const n = nodes.find(node => node.svgId === svgId);
                            if (n) points.push({ x: n.x, y: n.y });
                            return n;
                        };

                        const targetNode = nodes.find(n => n.equipmentId === targetId);
                        const targetEdge = edges.find(e => e.equipmentId === targetId);
                        let targetSvgId;

                        if (targetNode) {
                            targetSvgId = targetNode.svgId;
                            points.push({ x: targetNode.x, y: targetNode.y });
                            edges.forEach(e => {
                                if (e.node1 === targetNode.svgId || e.node2 === targetNode.svgId) {
                                    addNodePointsBySvgId(e.node1);
                                    addNodePointsBySvgId(e.node2);
                                }
                            });
                        } else if (targetEdge) {
                            targetSvgId = targetEdge.svgId;
                            const n1 = addNodePointsBySvgId(targetEdge.node1);
                            const n2 = addNodePointsBySvgId(targetEdge.node2);
                            if (n1) edges.forEach(e => { if (e.node1 === n1.svgId || e.node2 === n1.svgId) { addNodePointsBySvgId(e.node1); addNodePointsBySvgId(e.node2); } });
                            if (n2) edges.forEach(e => { if (e.node1 === n2.svgId || e.node2 === n2.svgId) { addNodePointsBySvgId(e.node1); addNodePointsBySvgId(e.node2); } });
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

                            const padding = 2.5; 
                            
                            // Calculate target viewBox directly
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

                            if (targetSvgId) {
                                const el = container.querySelector(`[id="${targetSvgId}"]`);
                                if (el) el.classList.add('nad-highlight');
                            }
                        }
                    } catch (e) { console.error('Zoom failed:', e); }

                }, 50); 

                return () => clearTimeout(timer);
            }, [activeTab, nDiagram, n1Diagram, inspectQuery, selectedBranch]);
"""

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "Zoom Logic (Handles Inspect, N-1 Auto-Zoom)" in line:
        start_idx = i
        break

if start_idx != -1:
    # Look for end of useEffect
    for i in range(start_idx, len(lines)):
        if "}, [activeTab, nDiagram, n1Diagram, inspectQuery, selectedBranch]);" in line: # This might fail if exact string doesn't match
             pass 
        # Better: find the next useEffect or renderVisualization
        if "const inspectableItems =" in lines[i]:
            end_idx = i - 1 # rough end
            # Refine end_idx by backtracking empty lines
            while lines[end_idx].strip() == "":
                end_idx -= 1
            break

# Alternative end finding: match the closing brace line
if start_idx != -1:
    brace_count = 0
    found_start = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        brace_count += line.count('{') - line.count('}')
        if '{' in line: found_start = True
        if found_start and brace_count == 0:
            end_idx = i + 1
            break

if start_idx != -1 and end_idx != -1:
    print(f"Replacing lines {start_idx+1} to {end_idx}")
    # Check if we are replacing correct block
    print("Old Block Start:", lines[start_idx][:50])
    print("Old Block End:", lines[end_idx-1][:50])
    
    new_lines = lines[:start_idx] + [new_zoom_logic + "\n"] + lines[end_idx:]
    
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    print("Success")
else:
    print("Could not find block")
    if start_idx != -1: print(f"Found start at {start_idx}")
    else: print("Did not find start")
