import React, { useEffect, useRef, useState } from 'react';

export default function BlocklyEditor({
  onCodeChange,
  onSnapshotChange,
  initialSnapshot,
  isSyncingFromCode,
  workspaceRef,
}) {
  const containerRef = useRef(null);
  // Block→Python regeneration failure (e.g. a required input emptied by detaching its child) —
  // shown on the sync badge; the badge used to be hardcoded "Synchronized" even while sync stalled.
  const [syncError, setSyncError] = useState('');

  useEffect(() => {
    if (!containerRef.current) return;

    // Scratch3/MakeCode-style light theme for the zelos renderer.
    const getBlocklyTheme = () => {
      const base = window.Blockly.Themes.Zelos || window.Blockly.Themes.Classic;
      return window.Blockly.Theme.defineTheme('scratch_light', {
        'base': base,
        'componentStyles': {
          'workspaceBackgroundColour': '#fbfcff',
          'toolboxBackgroundColour': '#ffffff',
          'toolboxForegroundColour': '#42506e',
          'flyoutBackgroundColour': '#eef4ff',
          'flyoutForegroundColour': '#42506e',
          'flyoutOpacity': 1,
          'scrollbarColour': '#cfe1ff',
          'scrollbarOpacity': 0.8,
          'insertionMarkerColour': '#4d97ff',
          'insertionMarkerOpacity': 0.35,
          'cursorColour': '#4d97ff'
        },
        'blockStyles': {
          'logic_blocks': { 'colourPrimary': '#4C97FF' },
          'loop_blocks': { 'colourPrimary': '#FFAB19' },
          'math_blocks': { 'colourPrimary': '#59C059' },
          'text_blocks': { 'colourPrimary': '#5CB1D6' },
          'list_blocks': { 'colourPrimary': '#9966FF' },
          'variable_blocks': { 'colourPrimary': '#FF8C1A' },
          'procedure_blocks': { 'colourPrimary': '#FF6680' }
        }
      });
    };

    // The ir_* toolbox is built in JS (irToolbox.js) from the ir_* block table, not the
    // retired XML stub — blocklyToIr only understands ir_* types, so the palette must too.
    const toolbox = window.BlockPyIrToolbox;

    // Inject Blockly
    const ws = window.Blockly.inject(containerRef.current, {
      toolbox: toolbox,
      theme: getBlocklyTheme(),
      // Self-hosted media (icons + sounds) so Blockly never reaches static.blockly.com — works
      // offline. Vendored from the blockly npm package into public/vendor/blockly/media.
      media: '/vendor/blockly/media/',
      renderer: 'zelos',
      grid: {
        spacing: 20,
        length: 3,
        colour: 'rgba(0, 0, 0, 0.06)',
        snap: true
      },
      zoom: {
        controls: true,
        wheel: true,
        startScale: 0.85,
        maxScale: 3,
        minScale: 0.3,
        scaleSpeed: 1.2
      },
      trashcan: true
    });

    workspaceRef.current = ws;
    window.__blocklyWorkspace = ws;

    // Wire the Variables category's "Create variable…" button to Blockly's native variable
    // creation dialog (the toolbox button declares callbackkey 'IR_CREATE_VARIABLE').
    try {
      ws.registerButtonCallback('IR_CREATE_VARIABLE', () => {
        window.Blockly.Variables.createVariableButtonHandler(ws);
      });
    } catch (_) { /* non-fatal */ }

    // MakeCode-style toolbox: paint each category label in its own colour-bar hue.
    // Blockly puts the category colour on the row's left border (inline); copy it to the
    // label text so the palette reads like MakeCode (colored bar + colored label).
    const paintToolboxLabels = () => {
      const cats = containerRef.current?.querySelectorAll('.blocklyToolboxCategory') || [];
      cats.forEach((cat) => {
        const hue = getComputedStyle(cat).borderLeftColor;
        const label = cat.querySelector('.blocklyToolboxCategoryLabel');
        if (label && hue) label.style.color = hue;
      });
    };
    const paintTimer = setTimeout(paintToolboxLabels, 250);

    // Load initial snapshot if provided
    if (initialSnapshot) {
      try {
        window.Blockly.serialization.workspaces.load(initialSnapshot, ws);
      } catch (err) {
        console.error('Failed to load initial snapshot:', err);
      }
    }

    // Block -> Python via the CPython-3.12 ast single-IR pipeline (Pyodide):
    //   workspace JSON -> blocklyToIr -> irToPython. Async (Pyodide) + debounced so rapid edits
    // coalesce into one regeneration. The legacy Blockly.Python generator path is retired.
    let codeGenTimer = null;
    const regenerate = async () => {
      if (isSyncingFromCode.current) return;
      try {
        const snapshot = window.Blockly.serialization.workspaces.save(ws);
        const pyodide = await window.BlockPyAstBridge.getPyodide();
        const ir = window.BlockPyIR.blocklyToIr(snapshot);
        const code = await window.BlockPyAstBridge.irToPython(pyodide, ir);
        if (isSyncingFromCode.current) return; // a code->block sync may have started during await
        onCodeChange(code);
        onSnapshotChange(snapshot);
        setSyncError('');
      } catch (err) {
        // A block outside the IR vocabulary, or an invalid block state (detached required child,
        // bad identifier field), makes blocklyToIr throw. Surface it on the badge instead of
        // silently stalling sync while the badge claims "Synchronized".
        console.error('Error generating code on workspace change (IR path):', err);
        setSyncError(err && err.message ? err.message : String(err));
      }
    };

    const changeListener = (event) => {
      if (isSyncingFromCode.current) return;

      if (
        event.type === window.Blockly.Events.BLOCK_CREATE ||
        event.type === window.Blockly.Events.BLOCK_DELETE ||
        event.type === window.Blockly.Events.BLOCK_CHANGE ||
        event.type === window.Blockly.Events.BLOCK_MOVE
      ) {
        clearTimeout(codeGenTimer);
        codeGenTimer = setTimeout(regenerate, 200);
      }
    };

    ws.addChangeListener(changeListener);

    // Cleanup
    return () => {
      clearTimeout(paintTimer);
      clearTimeout(codeGenTimer);
      ws.removeChangeListener(changeListener);
      ws.dispose();
      workspaceRef.current = null;
      if (window.__blocklyWorkspace === ws) {
        window.__blocklyWorkspace = null;
      }
    };
  }, []);

  return (
    <div className="blockly-card">
      <div className="panel-header">
        <div className="panel-title-group">
          <i className="fa-solid fa-cubes icon-purple"></i>
          <h3>Visual Block Workspace</h3>
        </div>
        <div
          id="sync-indicator"
          className={`badge ${syncError ? 'badge-error' : 'badge-success'}`}
          title={syncError ? `Block → Python sync failed: ${syncError}` : 'Block ↔ Python synced'}
        >
          <i className={`fa-solid ${syncError ? 'fa-triangle-exclamation' : 'fa-rotate'}`}></i>
          {' '}{syncError ? 'Sync error — fix the highlighted block' : 'Synchronized'}
        </div>
      </div>
      <div 
        ref={containerRef} 
        id="blockly-div" 
        style={{ width: '100%', height: 'calc(100% - 48px)', minHeight: '380px' }}
      ></div>
    </div>
  );
}
