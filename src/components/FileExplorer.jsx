import React, { useEffect, useState, useCallback } from 'react';

// VS Code-style file explorer over the real workspace folder on disk (server FS API at
// /api/fs/*). Clicking a file opens it (onOpenFile); New File / New Folder create inside the
// selected folder (or root); each row has a delete action. The workspace is the cwd for real
// Python, so files created here are exactly what cv2.imread()/open() see.
export default function FileExplorer({ activeFile, onOpenFile, onChanged, reloadToken }) {
  const [tree, setTree] = useState([]);
  const [root, setRoot] = useState('');
  const [expanded, setExpanded] = useState(() => new Set());
  const [selectedDir, setSelectedDir] = useState(''); // '' = workspace root
  const [creating, setCreating] = useState(null);      // 'file' | 'folder' | null
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch('/api/fs/tree');
      const j = await r.json();
      setTree(j.tree || []);
      setRoot(j.root || '');
    } catch (_) { /* backend not up yet */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh, reloadToken]);

  const toggle = (p) => {
    setExpanded((prev) => {
      const n = new Set(prev);
      n.has(p) ? n.delete(p) : n.add(p);
      return n;
    });
  };

  const joinPath = (dir, name) => (dir ? `${dir}/${name}` : name);

  const submitCreate = async () => {
    const name = newName.trim();
    if (!name) { setCreating(null); return; }
    const targetPath = joinPath(selectedDir, name);
    setBusy(true);
    try {
      if (creating === 'folder') {
        await fetch('/api/fs/mkdir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: targetPath }) });
        setExpanded((prev) => new Set(prev).add(selectedDir).add(targetPath));
      } else {
        await fetch('/api/fs/file', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: targetPath, content: '' }) });
        await refresh();
        onOpenFile && onOpenFile(targetPath);
      }
    } finally {
      setBusy(false);
      setCreating(null);
      setNewName('');
      refresh();
      onChanged && onChanged();
    }
  };

  const del = async (node, e) => {
    e.stopPropagation();
    if (!window.confirm(`"${node.name}" 을(를) 삭제할까요?${node.type === 'dir' ? '\n폴더와 그 안의 모든 파일이 지워집니다.' : ''}`)) return;
    setBusy(true);
    try {
      await fetch('/api/fs/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: node.path }) });
    } finally {
      setBusy(false);
      refresh();
      onChanged && onChanged();
    }
  };

  const iconFor = (node) => {
    if (node.type === 'dir') return expanded.has(node.path) ? 'fa-folder-open' : 'fa-folder';
    if (node.kind === 'image') return 'fa-image';
    if (node.ext === '.py') return 'fa-brands fa-python';
    return 'fa-file-lines';
  };

  const renderNodes = (nodes, depth) => nodes.map((node) => {
    const isActive = node.type === 'file' && node.path === activeFile;
    const isSelDir = node.type === 'dir' && node.path === selectedDir;
    const pad = 6 + depth * 14;
    return (
      <div key={node.path}>
        <div
          className={`fx-row${isActive ? ' fx-active' : ''}${isSelDir ? ' fx-seldir' : ''}`}
          style={{ paddingLeft: pad }}
          onClick={() => {
            if (node.type === 'dir') { toggle(node.path); setSelectedDir(node.path); }
            else { onOpenFile && onOpenFile(node.path); }
          }}
          title={node.path}
        >
          {node.type === 'dir' && (
            <i className={`fa-solid fa-chevron-${expanded.has(node.path) ? 'down' : 'right'} fx-caret`}></i>
          )}
          <i className={`${node.ext === '.py' ? '' : 'fa-solid '}${iconFor(node)} fx-icon`}></i>
          <span className="fx-name">{node.name}</span>
          <button className="fx-del" title="삭제" aria-label={`${node.name} 삭제`} onClick={(e) => del(node, e)}>
            <i className="fa-solid fa-xmark"></i>
          </button>
        </div>
        {node.type === 'dir' && expanded.has(node.path) && node.children && node.children.length > 0 && (
          renderNodes(node.children, depth + 1)
        )}
      </div>
    );
  });

  return (
    <div className="fx-card">
      {/* 팝업 헤더가 이미 "파일" 이라고 알려주므로 패널 제목을 또 쓰지 않는다.
          대신 실제로 누를 것들을 이름과 함께 놓는다(아이콘만 있으면 학생이 알 수 없다). */}
      <div className="bpy-ptools">
        <button className="btn btn-secondary btn-sm" disabled={busy}
          onClick={() => { setCreating('file'); setNewName(''); }}>
          <i className="fa-solid fa-file-circle-plus"></i> 새 파일
        </button>
        <button className="btn btn-secondary btn-sm" disabled={busy}
          onClick={() => { setCreating('folder'); setNewName(''); }}>
          <i className="fa-solid fa-folder-plus"></i> 새 폴더
        </button>
        <button className="btn btn-secondary btn-sm bpy-ico-btn" onClick={refresh}
          title="새로고침" aria-label="새로고침">
          <i className="fa-solid fa-rotate"></i>
        </button>
      </div>

      <div className="fx-target" title="새로 만드는 파일·폴더가 여기에 생깁니다">
        <i className="fa-solid fa-location-dot"></i>{' '}
        <span className="fx-target-lb">만들 위치</span>
        {selectedDir ? selectedDir + '/' : '워크스페이스 최상위'}
        {selectedDir && (
          <button className="fx-up" title="최상위로" aria-label="최상위로" onClick={() => setSelectedDir('')}>
            <i className="fa-solid fa-arrow-up-from-bracket"></i>
          </button>
        )}
      </div>

      {creating && (
        <div className="fx-create">
          <i className={`fa-solid ${creating === 'folder' ? 'fa-folder-plus' : 'fa-file-circle-plus'}`}></i>
          <input
            autoFocus
            className="fx-input"
            placeholder={creating === 'folder' ? '폴더 이름' : '파일 이름 (예: test.py)'}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submitCreate(); if (e.key === 'Escape') { setCreating(null); setNewName(''); } }}
          />
          <button className="btn btn-primary btn-xs" onClick={submitCreate} disabled={busy}>만들기</button>
          <button className="btn btn-secondary btn-xs" onClick={() => { setCreating(null); setNewName(''); }}
            title="취소" aria-label="취소">✕</button>
        </div>
      )}

      <div className="fx-tree">
        {tree.length === 0 ? (
          <div className="fx-empty">
            <i className="fa-regular fa-folder-open"></i>
            <b>아직 파일이 없습니다</b>
            <p>
              <b>새 파일</b> 을 눌러 만들어 보세요. 저장한 코드와, <b>TM</b> 패널에서
              <b> 저장</b> 한 모델 파일(<code>.npz</code>)이 여기에 나타납니다.
            </p>
          </div>
        ) : renderNodes(tree, 0)}
      </div>

      {root && <div className="fx-root" title={root}><span>폴더 위치</span>{root}</div>}
    </div>
  );
}
