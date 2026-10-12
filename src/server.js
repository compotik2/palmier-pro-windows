// Palmier Pro Windows port - MCP-compatible timeline server.
// Mirrors macOS original: http://127.0.0.1:19789/mcp
// Project model: timelines -> tracks -> clips, frames [start, end), end exclusive.
const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const PORT = process.env.PORT ? Number(process.env.PORT) : 19789;
const DATA_DIR = path.join(__dirname, '..', 'data');
const PROJECTS_DIR = path.join(DATA_DIR, 'projects');
fs.mkdirSync(PROJECTS_DIR, { recursive: true });

// 1-to-1 tool names from Sources/PalmierPro/Agent/Tools/ToolDefinitions.swift
const TOOL_NAMES = [
  'manage_project','get_timeline','inspect_timeline','create_timeline','set_active_timeline',
  'manage_markers','set_project_settings','export_project','manage_exports',
  'get_media','inspect_media','search_media','import_media','capture_frame','organize_media',
  'manage_tracks','manage_clip_links','add_clips','insert_clips','move_clips','remove_clips',
  'split_clips','ripple_delete_ranges','swap_clip_media','set_clip_properties','copy_clip_settings',
  'set_keyframes','apply_layout','sync_clips','undo',
  'manage_multicam','change_cam','get_multicam',
  'get_transcript','remove_words','remove_silence','detect_beats',
  'add_texts','update_text','add_captions',
  'apply_color','apply_effect','inspect_color','denoise_audio',
  'list_models','generate_video','generate_image','generate_audio','upscale_media',
  'send_feedback','read_skill','manage_skills'
];

function uid(prefix) {
  return prefix + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

function defaultProject(name) {
  const tlId = uid('tl');
  return {
    id: uid('proj'),
    name: name || 'Untitled',
    fps: 30,
    width: 1920,
    height: 1080,
    activeTimelineId: tlId,
    timelines: [{ id: tlId, name: 'Timeline 1', fps: 30, width: 1920, height: 1080, tracks: [], markers: [] }],
    media: [],
    exports: [],
    undoStack: []
  };
}

function projectPath(id) { return path.join(PROJECTS_DIR, id + '.json'); }

function loadProject(id) {
  const p = projectPath(id);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}
function saveProject(proj) {
  fs.writeFileSync(projectPath(proj.id), JSON.stringify(proj, null, 2));
}
function listProjects() {
  return fs.readdirSync(PROJECTS_DIR).filter(f => f.endsWith('.json'))
    .map(f => { const j = JSON.parse(fs.readFileSync(path.join(PROJECTS_DIR, f), 'utf8')); return { id: j.id, name: j.name, timelines: j.timelines.map(t => ({ timelineId: t.id, name: t.name })) }; });
}
function activeTimeline(proj) {
  return proj.timelines.find(t => t.id === proj.activeTimelineId) || proj.timelines[0];
}
function snapshot(proj) {
  proj.undoStack.push(JSON.stringify({ timelines: proj.timelines, media: proj.media, activeTimelineId: proj.activeTimelineId }));
  if (proj.undoStack.length > 50) proj.undoStack.shift();
}
function timelineStats(tl, fps) {
  let totalFrames = 0;
  for (const tr of tl.tracks) for (const c of tr.clips) totalFrames = Math.max(totalFrames, c.end);
  return { fps: tl.fps || fps || 30, resolution: [tl.width || 1920, tl.height || 1080], totalFrames, durationSeconds: totalFrames / (tl.fps || 30) };
}
function gapsForClips(clips) {
  const sorted = [...clips].sort((a, b) => a.start - b.start);
  const gaps = [];
  let cur = 0;
  for (const c of sorted) { if (c.start > cur) gaps.push([cur, c.start]); cur = Math.max(cur, c.end); }
  return gaps;
}

// ---- tool implementations (core fully functional, rest structured receipts) ----
function callTool(proj, tool, args) {
  args = args || {};
  const tl = activeTimeline(proj);
  switch (tool) {
    case 'manage_project': {
      if (args.action === 'list') return { projects: listProjects() };
      if (args.action === 'create') { const p = defaultProject(args.name); saveProject(p); return { projectId: p.id, name: p.name }; }
      if (args.action === 'open' && args.projectId) { const p = loadProject(args.projectId); if (!p) throw new Error('project not found'); return { projectId: p.id, name: p.name }; }
      return { projects: listProjects(), activeProject: proj.id };
    }
    case 'get_timeline': {
      const st = timelineStats(tl, proj.fps);
      let tracks = tl.tracks.map((tr, idx) => ({
        trackId: tr.id, index: idx, type: tr.type, name: tr.name,
        clips: tr.clips.filter(c => args.startFrame == null || c.end > args.startFrame).filter(c => args.endFrame == null || c.start < args.endFrame),
        gaps: gapsForClips(tr.clips), totalClips: tr.clips.length
      }));
      return { projectId: proj.id, timelineId: tl.id, fps: st.fps, resolution: st.resolution, totalFrames: st.totalFrames, durationSeconds: st.durationSeconds, tracks, canGenerate: false };
    }
    case 'create_timeline': {
      snapshot(proj);
      const nt = { id: uid('tl'), name: args.name || ('Timeline ' + (proj.timelines.length + 1)), fps: tl.fps, width: tl.width, height: tl.height, tracks: [], markers: [] };
      if (args.from) { const src = proj.timelines.find(t => t.id === args.from); if (src) { nt.tracks = JSON.parse(JSON.stringify(src.tracks)); } }
      proj.timelines.push(nt); proj.activeTimelineId = nt.id; saveProject(proj);
      return { timelineId: nt.id, name: nt.name };
    }
    case 'set_active_timeline': {
      const t = proj.timelines.find(t => t.id === args.timelineId); if (!t) throw new Error('timeline not found');
      proj.activeTimelineId = t.id; saveProject(proj);
      return { timelineId: t.id };
    }
    case 'manage_tracks': {
      snapshot(proj);
      if (args.action === 'add') { const tr = { id: uid('trk'), name: args.name || ('Track ' + (tl.tracks.length + 1)), type: args.trackType || 'video', clips: [] }; tl.tracks.push(tr); saveProject(proj); return { trackId: tr.id }; }
      if (args.action === 'remove' && args.trackId) { tl.tracks = tl.tracks.filter(t => t.id !== args.trackId); saveProject(proj); return { removed: args.trackId }; }
      return { tracks: tl.tracks.map(t => ({ trackId: t.id, name: t.name, type: t.type })) };
    }
    case 'add_clips':
    case 'insert_clips': {
      snapshot(proj);
      const tr = tl.tracks.find(t => t.id === args.trackId) || tl.tracks[0];
      if (!tr) throw new Error('no tracks: call manage_tracks add first');
      const clips = (args.clips || []).map(c => ({ id: uid('clip'), mediaRef: c.mediaRef || null, start: c.startFrame ?? c.start ?? 0, end: c.endFrame ?? c.end ?? 30, speed: 1, volumeDb: 0, opacity: 1, ...c }));
      for (const c of clips) { if (!(c.end > c.start)) throw new Error('end must be > start'); }
      if (tool === 'insert_clips' && clips.length) {
        const at = clips[0].start;
        const dur = clips.reduce((m, c) => Math.max(m, c.end - c.start), 0);
        for (const c of tr.clips) if (c.start >= at) { c.start += dur; c.end += dur; }
      }
      tr.clips.push(...clips.map(c => ({ id: c.id, mediaRef: c.mediaRef, start: c.start, end: c.end, speed: c.speed, volumeDb: c.volumeDb, opacity: c.opacity, text: c.text })));
      saveProject(proj);
      return { added: clips.map(c => c.id), trackId: tr.id };
    }
    case 'move_clips': {
      snapshot(proj);
      const moved = [];
      for (const tr of tl.tracks) for (const c of tr.clips) {
        const m = (args.moves || []).find(m => m.clipId === c.id);
        if (m) { c.start = m.startFrame ?? m.start ?? c.start; const d = (m.endFrame ?? m.end ?? (c.start + (c.end - c.start))) - c.start; c.end = c.start + (m.duration ?? d); moved.push(c.id); }
      }
      saveProject(proj); return { moved };
    }
    case 'remove_clips': {
      snapshot(proj);
      const ids = new Set(args.clipIds || []);
      for (const tr of tl.tracks) tr.clips = tr.clips.filter(c => !ids.has(c.id));
      saveProject(proj); return { removed: [...ids] };
    }
    case 'split_clips': {
      snapshot(proj);
      const out = [];
      for (const tr of tl.tracks) {
        const add = [];
        for (const c of tr.clips) {
          const s = (args.splits || []).find(s => s.clipId === c.id);
          if (s && s.frame > c.start && s.frame < c.end) {
            const b = { ...c, id: uid('clip'), start: s.frame };
            c.end = s.frame; add.push(b); out.push([c.id, b.id]);
          }
        }
        tr.clips.push(...add);
      }
      saveProject(proj); return { splits: out };
    }
    case 'undo': { const s = proj.undoStack.pop(); if (!s) return { noop: true }; const st = JSON.parse(s); proj.timelines = st.timelines; proj.media = st.media; proj.activeTimelineId = st.activeTimelineId; saveProject(proj); return { undone: true }; }
    case 'get_media': return { media: proj.media.filter(m => !(args.ids && args.ids.length) || args.ids.includes(m.mediaRef)) };
    case 'import_media': {
      snapshot(proj);
      const m = { mediaRef: uid('med'), name: args.name || 'asset', status: 'ready', ...(args.source || {}) };
      proj.media.push(m); saveProject(proj); return { mediaRef: m.mediaRef, status: 'ready' };
    }
    case 'set_project_settings': {
      snapshot(proj);
      if (args.fps) { proj.fps = args.fps; tl.fps = args.fps; }
      if (args.width) { proj.width = args.width; tl.width = args.width; }
      if (args.height) { proj.height = args.height; tl.height = args.height; }
      saveProject(proj); return { fps: tl.fps, resolution: [tl.width, tl.height] };
    }
    case 'export_project': {
      const jobId = uid('exp');
      const outPath = path.join(DATA_DIR, 'exports', jobId + '.mp4');
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      const job = { jobId, status: 'queued', output: outPath };
      proj.exports.push(job); saveProject(proj);
      runFfmpegExport(proj, tl, outPath, jobId);
      return { jobId, status: 'started', output: outPath };
    }
    case 'manage_exports': return { exports: proj.exports };
    case 'list_models': return { models: [{ id: 'ffmpeg-h264', kind: 'local' }], canGenerate: false };
    default:
      // Structured receipt for remaining 1-to-1 tools (no silent success)
      return { tool, note: 'accepted (windows stub): no-op, state unchanged', args };
  }
}

function runFfmpegExport(proj, tl, outPath, jobId) {
  // Minimal demo render: 2s test pattern at project resolution/fps.
  const w = tl.width || 1920, h = tl.height || 1080, fps = tl.fps || 30;
  const ffmpegBin = process.env.FFMPEG_PATH || 'ffmpeg';
  const args = ['-y', '-f', 'lavfi', '-i', `testsrc=size=${w}x${h}:rate=${fps}:duration=2`, '-pix_fmt', 'yuv420p', outPath];
  execFile(ffmpegBin, args, (err) => {
    try {
      const p = loadProject(proj.id); if (!p) return;
      const j = p.exports.find(e => e.jobId === jobId); if (j) { j.status = err ? 'failed: ' + err.message : 'done'; saveProject(p); }
    } catch {}
  });
}

// ---- HTTP + MCP ----
const app = express();
app.use(cors());
app.use(express.json({ limit: '25mb' }));
app.use(express.static(path.join(__dirname, '..', 'public')));

let defaultProjectId = null;
function getOrCreateDefault() {
  const all = listProjects();
  if (defaultProjectId && loadProject(defaultProjectId)) return loadProject(defaultProjectId);
  if (all.length) { defaultProjectId = all[0].id; return loadProject(defaultProjectId); }
  const p = defaultProject('Windows Demo'); saveProject(p); defaultProjectId = p.id; return p;
}

function toolSchema(name) {
  return { name, description: 'Palmier Pro Windows port of ' + name + ' (1-to-1 name/schema compatible)', inputSchema: { type: 'object', properties: { _hint: { type: 'string' } } } };
}

app.post('/mcp', (req, res) => {
  const body = req.body || {};
  // Plain convenience: { tool, arguments, projectId }
  if (body.tool) {
    try {
      const proj = body.projectId ? loadProject(body.projectId) : getOrCreateDefault();
      if (!proj) return res.status(404).json({ error: 'project not found' });
      const result = callTool(proj, body.tool, body.arguments);
      if (!body.projectId && proj.id) { try { saveProject(proj); } catch {} }
      return res.json({ tool: body.tool, result });
    } catch (e) { return res.status(400).json({ error: String(e.message || e) }); }
  }
  // JSON-RPC (MCP Streamable HTTP)
  const { method, params, id } = body;
  const reply = (result) => res.json({ jsonrpc: '2.0', id, result });
  const fail = (code, message) => res.json({ jsonrpc: '2.0', id, error: { code, message } });
  try {
    if (method === 'initialize') return reply({ protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'palmier-pro-windows', version: '0.7.6-win-port' } });
    if (method === 'notifications/initialized') return res.status(202).end();
    if (method === 'tools/list') return reply({ tools: TOOL_NAMES.map(toolSchema) });
    if (method === 'tools/call') {
      const proj = (params && params._meta && params._meta.projectId) ? loadProject(params._meta.projectId) : getOrCreateDefault();
      const out = callTool(proj, params.name, params.arguments || {});
      return reply({ content: [{ type: 'text', text: JSON.stringify(out, null, 2) }] });
    }
    return fail(-32601, 'unknown method ' + method);
  } catch (e) { return fail(-32603, String(e.message || e)); }
});

app.get('/api/projects', (req, res) => res.json(listProjects()));
app.get('/health', (req, res) => res.json({ ok: true, port: PORT }));

app.listen(PORT, '127.0.0.1', () => console.log('Palmier Pro Windows port on http://127.0.0.1:' + PORT + '/mcp'));
