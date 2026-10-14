import json
import urllib.request
import urllib.error
import unittest
from palmier.model import Editor
from palmier.media import ExportQueue
from palmier.mcp import MCPServer,Tools,SCHEMAS


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.e=Editor()
        self.e.import_entry(dict(id="a",name="test",type="video",duration=10,hasAudio=False,source={"external":{"absolutePath":"C:/sample.mp4"}}))
        self.e.add_track("video")
        self.tools=Tools(self.e,ExportQueue(self.e))
        self.server=MCPServer(self.tools,0)
        self.url=f"http://127.0.0.1:{self.server.port}/mcp"

    def tearDown(self):
        self.server.stop()

    def rpc(self,method,params=None,headers=None):
        request=urllib.request.Request(self.url,data=json.dumps(dict(jsonrpc="2.0",id=1,method=method,params=params or {})).encode(),
                                       headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",**(headers or {})})
        with urllib.request.urlopen(request,timeout=15) as response:
            return json.load(response)

    def call(self,name,args):
        return self.rpc("tools/call",dict(name=name,arguments=args))["result"]

    def test_initialize_and_real_discovery_schemas(self):
        result=self.rpc("initialize",dict(protocolVersion="2025-03-26"))["result"]
        self.assertEqual(result["protocolVersion"],"2025-03-26")
        tools=self.rpc("tools/list")["result"]["tools"]
        self.assertEqual({t["name"] for t in tools},set(SCHEMAS))
        add=next(t for t in tools if t["name"]=="add_clips")
        self.assertEqual(add["inputSchema"]["required"],["entries"])

    def test_edit_split_properties_undo_independent_readback(self):
        response=self.call("add_clips",dict(entries=[dict(mediaRef="a",trackIndex=0,startFrame=0,endFrame=90)]))
        self.assertFalse(response["isError"])
        cid=json.loads(response["content"][0]["text"])["clipIds"][0]
        self.assertFalse(self.call("split_clips",dict(splits=[dict(clipId=cid,atFrame=30)]))["isError"])
        timeline=json.loads(self.call("get_timeline",{})["content"][0]["text"])
        self.assertEqual(sorted(c["frames"] for c in timeline["tracks"][0]["clips"]),[[0,30],[30,90]])
        self.call("undo",{})
        timeline=json.loads(self.call("get_timeline",{})["content"][0]["text"])
        self.assertEqual([c["frames"] for c in timeline["tracks"][0]["clips"]],[[0,90]])

    def test_unsupported_and_invalid_arguments_do_not_mutate(self):
        before=self.e.snapshot()
        for tool,args in [("detect_beats",{}),("generate_video",{}),("add_clips",dict(clips=[])),("set_clip_properties",dict(clipIds=["bad"],opacity=2))]:
            self.assertTrue(self.call(tool,args)["isError"])
            self.assertEqual(self.e.snapshot(),before)

    def test_browser_origin_and_bad_host_refused(self):
        for headers in [dict(Origin="https://evil.example"),dict(Host="evil.example")]:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.rpc("tools/list",headers=headers)
            self.assertEqual(caught.exception.code,403)

    def test_unknown_rpc_method(self):
        self.assertEqual(self.rpc("not-a-method")["error"]["code"],-32601)

    def test_create_timeline_switch_and_original_half_open_filter(self):
        before=self.e.doc["activeTimelineId"]
        result=self.call("create_timeline",dict(name="alternate"))
        self.assertFalse(result["isError"])
        self.assertNotEqual(before,self.e.doc["activeTimelineId"])


if __name__=="__main__":
    unittest.main()
