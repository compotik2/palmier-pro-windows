import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import assert from 'node:assert/strict';

const child=spawn(process.env.PALMIER_TEST_PYTHON || 'python',[fileURLToPath(new URL('../scripts/mcp_test_host.py',import.meta.url))],{stdio:['pipe','pipe','inherit']});
const lines=createInterface({input:child.stdout});
const timeout=setTimeout(()=>{child.kill();process.exitCode=1;console.error('SDK verification timeout');},60000);
const client=new Client({name:'palmier-sdk-verification',version:'1.0.0'});
let persisted;
try {
  const [line]=await once(lines,'line');
  const host=JSON.parse(line);
  await client.connect(new StreamableHTTPClientTransport(new URL(host.url)));
  const inventory=await client.listTools();
  assert.equal(inventory.tools.length,20);
  async function call(name,args={}) {
    const result=await client.callTool({name,arguments:args});
    assert.equal(result.isError,false,JSON.stringify(result));
    return JSON.parse(result.content[0].text);
  }
  const media=await call('get_media');
  const added=await call('add_clips',{entries:[{mediaRef:media.assets[0].id,startFrame:0,endFrame:60}]});
  await call('split_clips',{splits:[{clipId:added.clipIds[0],atFrame:30}]});
  let timeline=await call('get_timeline');
  assert.deepEqual(timeline.tracks[0].clips.map(c=>c.frames),[[0,30],[30,60]]);
  await call('undo');
  timeline=await call('get_timeline');
  assert.deepEqual(timeline.tracks[0].clips.map(c=>c.frames),[[0,60]]);
  const invalid=await client.callTool({name:'detect_beats',arguments:{}});
  assert.equal(invalid.isError,true);
  const job=await call('export_project',{outputPath:host.outputPath,codec:'H.264'});
  let current;
  for (let i=0;i<300;i++) {
    current=(await call('manage_exports',{action:'list'})).exports.find(j=>j.jobId===job.jobId);
    if (!['queued','running'].includes(current.status)) break;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert.equal(current.status,'done',JSON.stringify(current));
  assert.equal(current.progress,100);
  console.log(JSON.stringify({sdk:'1.32.1',protocolNegotiated:true,toolCount:inventory.tools.length,splitReadback:true,undoReadback:true,unsupportedToolError:true,exportJobDone:true},null,2));
  const next=once(lines,'line');
  child.stdin.end('stop\n');
  const [saved]=await next;
  persisted=JSON.parse(saved);
  assert.equal(persisted.savedClips,1);
  assert.ok(Math.abs(persisted.export.duration-2)<.1);
  console.log(JSON.stringify({independentExportProbe:true,persistenceReadback:true},null,2));
} finally {
  await client.close();
  if (!child.stdin.writableEnded) child.stdin.end('stop\n');
  if (child.exitCode===null) await once(child,'exit');
  clearTimeout(timeout);
}
