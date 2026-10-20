"""Offline contract tests, including an HTTP/SSE fake OpenAI-compatible server."""
import copy
import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import benchmark as b


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/auth-route/v1/models':
            self.send_error(401); return
        if self.path == '/html/v1/models':
            data=b'<html>Sign in</html>'
            self.send_response(200); self.send_header('Content-Type','text/html')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        if self.path not in ('/v1/models','/llama-route/v1/models','/qwen-route/models','/multi/v1/models'):
            self.send_error(404); return
        models=[{'id':'fake-model','max_model_len':8192}]
        if self.path == '/multi/v1/models':
            models.append({'id':'other-model'})
        data=json.dumps({'data':models}).encode()
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        messages=payload['messages']; prompt=messages[-1].get('content','') or ''
        if prompt == 'rate-limit':
            data=b'{"error":"too many requests; key=mock-secret-value"}'
            self.send_response(429); self.send_header('Content-Length',str(len(data))); self.end_headers()
            self.wfile.write(data); return
        if prompt == 'context-error':
            data=b'{"error":"maximum context token limit exceeded"}'
            self.send_response(400); self.send_header('Content-Length',str(len(data))); self.end_headers()
            self.wfile.write(data); return
        if payload.get('tools'):
            msg={'content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'lookup_act','arguments':'{"act_id":"LR-TEST-17"}'}}]}
            reason='tool_calls'
        elif messages[-1]['role']=='tool':
            msg={'content':'{"status":"draft"}'}; reason='stop'
        elif 'count' in prompt and ('integer' in prompt or '7' in prompt):
            msg={'content':'{"count":7}'}; reason='stop'
        elif 'verification_code' in prompt:
            import re
            value=re.search(r'has verification_code ([a-f0-9]+)',prompt).group(1)
            msg={'content':json.dumps({'verification_code':value})}; reason='stop'
        elif prompt == 'reasoning-only':
            msg={'content':None,'reasoning_content':'PRIVATE REASONING ONLY'}; reason='stop'
        elif prompt == 'empty':
            msg={'content':''}; reason='stop'
        elif prompt == 'inline-only':
            msg={'content':'<think>PRIVATE ONLY</think>'}; reason='stop'
        elif prompt == 'inline-thinking':
            msg={'content':'<think>PRIVATE INTERNAL TEXT</think>{"result":42}'}; reason='stop'
        elif prompt == 'unfinished-thinking':
            msg={'content':'<think>PRIVATE UNFINISHED TEXT'}; reason='length'
        elif prompt == 'length-result':
            msg={'content':'{"result":42}'}; reason='length'
        else:
            msg={'content':'{"result":42}'}; reason='stop'
        usage={'prompt_tokens':90,'completion_tokens':12,'total_tokens':102}
        if payload.get('stream'):
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
            def event(obj):
                self.wfile.write(('data: '+json.dumps(obj)+'\n\n').encode()); self.wfile.flush()
            self.wfile.write(b': heartbeat\n\n')
            event({'choices':[{'index':0,'delta':{'role':'assistant'}}]})
            if prompt == 'broken-stream':
                event({'choices':[{'index':0,'delta':{'content':'partial'}}]}); return
            if prompt != 'empty':
                event({'choices':[{'index':0,'delta':{'reasoning_content':'PRIVATE SERVER REASONING'}}]})
            time.sleep(.003)
            event({'choices':[{'index':0,'delta':{'content':msg.get('content') or ''}}]})
            event({'choices':[{'index':0,'delta':{},'finish_reason':reason}]})
            if payload.get('stream_options'):
                event({'choices':[],'usage':usage})
            self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
        else:
            data=json.dumps({'choices':[{'index':0,'message':msg,'finish_reason':reason}],'usage':usage}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)


class ThreadedServer(socketserver.ThreadingMixIn,http.server.HTTPServer):
    daemon_threads=True


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadedServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.model={'name':'fake','base_url':f'http://127.0.0.1:{cls.server.server_port}/v1','model':'fake-model'}
        cls.cfg={'models':[cls.model],'timeout_seconds':2,'max_output_tokens':64}
        cls.api=b.API(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def test_nonstream_and_usage(self):
        r=self.api.chat(self.model,[{'role':'user','content':'hello'}],streaming=False)
        self.assertTrue(r['ok']); self.assertIsNone(r['ttft_content_seconds'])
        self.assertEqual(r['usage']['completion_tokens'],12)
        self.assertGreater(r['completion_tokens_per_second_e2e'],0)

    def test_stream_ttft_excludes_role_and_records_reasoning_without_text(self):
        r=self.api.chat(self.model,[{'role':'user','content':'hello'}])
        self.assertTrue(r['ok']); self.assertTrue(r['stream_received'])
        self.assertGreater(r['ttft_content_seconds'],r['ttft_any_seconds'])
        self.assertTrue(r['reasoning_observed']); self.assertNotIn('PRIVATE',json.dumps(r))
        self.assertEqual(r['content'],'{"result":42}')

    def test_missing_usage_not_fabricated(self):
        m={**self.model,'stream_usage':False}
        r=self.api.chat(m,[{'role':'user','content':'hello'}])
        self.assertTrue(r['ok']); self.assertIsNone(r['completion_tokens_per_second_e2e'])

    def test_broken_stream_is_failure(self):
        r=self.api.chat(self.model,[{'role':'user','content':'broken-stream'}])
        self.assertFalse(r['ok']); self.assertEqual(r['error_kind'],'transport_or_protocol')

    def test_http_error_redacts_key(self):
        m={**self.model,'api_key_env':'LR_TEST_KEY'}
        with patch.dict(os.environ,{'LR_TEST_KEY':'mock-secret-value'}):
            api=b.API({'models':[m]})
            r=api.chat(m,[{'role':'user','content':'rate-limit'}])
        self.assertFalse(r['ok']); self.assertEqual(r['error_kind'],'rate_limited')
        self.assertNotIn('mock-secret-value',json.dumps(r))

    def test_context_rejection_not_hallucination(self):
        r=self.api.chat(self.model,[{'role':'user','content':'context-error'}])
        self.assertEqual(r['error_kind'],'context_rejected')

    def test_inline_thinking_removed_and_not_strict_json(self):
        r=self.api.chat(self.model,[{'role':'user','content':'inline-thinking'}],streaming=False)
        self.assertNotIn('PRIVATE',json.dumps(r)); self.assertIsNone(r['ttft_content_seconds'])
        self.assertFalse(b.score(r,{'expected':{'result':42}})['json_valid'])

    def test_unfinished_thinking_not_saved(self):
        r=self.api.chat(self.model,[{'role':'user','content':'unfinished-thinking'}],streaming=False)
        self.assertNotIn('PRIVATE',json.dumps(r)); self.assertTrue(r['truncated'])

    def test_length_finish_never_passes(self):
        case={'id':'x','category':'test','prompt':'length-result','expected':{'result':42}}
        r=b.record(self.api,self.model,'smoke',case,streaming=False)
        self.assertTrue(r['result']['truncated']); self.assertFalse(r['score']['exact_match'])

    def test_strict_boolean_and_schema(self):
        case={'expected':{'relevant':True}}
        r={'ok':True,'content':'{"relevant":1}'}
        self.assertFalse(b.score(r,case)['schema_valid'])
        self.assertFalse(b.score(r,case)['exact_match'])
        r['content']='{"relevant":true,"extra":"unexpected"}'
        self.assertFalse(b.score(r,case)['schema_valid'])
        r['content']='```json\n{"relevant":true}\n```'
        self.assertFalse(b.score(r,case)['json_valid'])

    def test_wrong_citation_or_quote_fails(self):
        case={'expected':{'source_id':'DOC-A','quote':'Keep records.'}}
        r={'ok':True,'content':'{"source_id":"DOC-A","quote":"Retain records."}'}
        self.assertFalse(b.score(r,case)['exact_match'])
        self.assertEqual(b.score(r,case)['field_accuracy'],.5)

    def test_multilabel_order_insensitive_but_no_duplicates(self):
        self.assertTrue(b.matches(['HSE','HR'],['HR','HSE']))
        self.assertFalse(b.matches(['HSE','HSE'],['HSE']))

    def test_context_case_reproducible_no_answer_leak_outside_archive(self):
        c=b.context_case(4000,'middle',42)
        self.assertEqual(c,b.context_case(4000,'middle',42))
        value=c['expected']['verification_code']
        self.assertEqual(c['prompt'].count(value),1)
        self.assertNotIn(value,c['prompt'].split('<archive>')[0])
        r=b.record(self.api,self.model,'context',c,target_characters=4000,position='middle')
        self.assertTrue(r['score']['exact_match'])

    def test_capabilities_include_tool_roundtrip(self):
        rows=list(b.capability_cases(self.api,self.model))
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r.get('capability_pass',r.get('score',{}).get('exact_match')) for r in rows))

    def test_failure_included_in_effective_recall(self):
        rows=[{'model':'m','suite':'quality','category':'relevance','expected':{'relevant':True},
               'result':{'ok':False,'total_seconds':1,'usage':{}},
               'score':{'exact_match':False,'json_valid':False,'schema_valid':False,'field_accuracy':0,'predicted':None}}]
        s=b.summarise(rows)['m']['quality']
        self.assertEqual(s['relevance']['recall'],0)
        self.assertEqual(s['transport_error_rate'],1)

    def test_optional_auth_does_not_invent_key(self):
        m={**self.model,'api_key_env':'LR_OPTIONAL_KEY','api_key_required':False}
        with patch.dict(os.environ,{'LR_OPTIONAL_KEY':''}):
            self.assertNotIn('Authorization',self.api.headers(m))
        with patch.dict(os.environ,{'LR_OPTIONAL_KEY':'real-key'}):
            self.assertEqual(self.api.headers(m)['Authorization'],'Bearer real-key')

    def test_company_environment_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config.json'
            model={**self.model,'model':'auto','model_env':'LR_OVERRIDE_MODEL','base_url_env':'LR_OVERRIDE_URL'}
            p.write_text(json.dumps({'models':[model]}))
            with patch.dict(os.environ,{'LR_OVERRIDE_MODEL':'exact-checkpoint','LR_OVERRIDE_URL':self.model['base_url']}):
                loaded=b.config_load(p)['models'][0]
            self.assertEqual(loaded['model'],'exact-checkpoint')
            self.assertEqual(loaded['base_url'],self.model['base_url'])

    def test_cli_discovers_model_before_smoke(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            base=self.model['base_url'].removesuffix('/v1')
            model={**self.model,'base_url':base+'/llama-route','model':'auto','detect_api_base':True}
            config=root/'config.json'; config.write_text(json.dumps({'models':[model],'max_output_tokens':64}))
            cmd=[sys.executable,str(b.ROOT/'benchmark.py'),'--config',str(config),'--env-file',str(root/'missing.env'),
                 '--suite','smoke','--warmup','0','--output',str(root/'reports')]
            run=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            report=next((root/'reports').iterdir())
            data=json.loads((report/'run.json').read_text())
            self.assertEqual(data['models'][0]['model'],'fake-model')
            self.assertTrue(data['models'][0]['resolution']['api_base_verified'])

    def test_discover_exact_model_id_and_v1_prefix(self):
        base=self.model['base_url'].removesuffix('/v1')
        m={**self.model,'base_url':base+'/llama-route','model':'auto','detect_api_base':True}
        resolved,diag=self.api.resolve(m)
        self.assertTrue(diag['ok']); self.assertEqual(resolved['model'],'fake-model')
        self.assertEqual(resolved['base_url'],base+'/llama-route/v1')
        self.assertTrue(resolved['resolution']['api_base_verified'])

    def test_discover_prefix_that_strips_v1(self):
        base=self.model['base_url'].removesuffix('/v1')
        m={**self.model,'base_url':base+'/qwen-route','model':'auto','detect_api_base':True}
        resolved,diag=self.api.resolve(m)
        self.assertTrue(diag['ok']); self.assertEqual(resolved['base_url'],base+'/qwen-route')
        self.assertEqual(len(diag['probes']),2)

    def test_multiple_models_do_not_silently_choose_one(self):
        base=self.model['base_url'].removesuffix('/v1')
        resolved,diag=self.api.resolve({**self.model,'base_url':base+'/multi','model':'auto','detect_api_base':True})
        self.assertIsNone(resolved); self.assertFalse(diag['ok'])
        self.assertIn('exactly one',diag['error'])

    def test_html_login_page_not_valid_model_discovery(self):
        base=self.model['base_url'].removesuffix('/v1')
        resolved,diag=self.api.resolve({**self.model,'base_url':base+'/html','model':'auto','detect_api_base':True})
        self.assertIsNone(resolved); self.assertFalse(diag['ok'])

    def test_auth_failure_stops_route_probing(self):
        base=self.model['base_url'].removesuffix('/v1')
        resolved,diag=self.api.resolve({**self.model,'base_url':base+'/auth-route','model':'auto','detect_api_base':True})
        self.assertIsNone(resolved); self.assertEqual(len(diag['probes']),1)
        self.assertEqual(diag['probes'][0]['http_status'],401)

    def test_explicit_model_can_test_chat_if_models_endpoint_disabled(self):
        base=self.model['base_url'].removesuffix('/v1')
        resolved,diag=self.api.resolve({**self.model,'base_url':base+'/no-list','detect_api_base':True})
        self.assertTrue(diag['ok']); self.assertFalse(diag['api_base_verified'])
        self.assertEqual(resolved['model'],'fake-model')

    def test_reasoning_only_is_not_network_failure_or_final_answer(self):
        for streaming in (True,False):
            r=self.api.chat(self.model,[{'role':'user','content':'reasoning-only'}],streaming=streaming)
            self.assertTrue(r['transport_ok']); self.assertFalse(r['ok'])
            self.assertFalse(r['final_answer_available']); self.assertEqual(r['error_kind'],'reasoning_only')
            self.assertNotIn('PRIVATE',json.dumps(r))

    def test_empty_response_separate_from_reasoning_only(self):
        r=self.api.chat(self.model,[{'role':'user','content':'empty'}],streaming=False)
        self.assertFalse(r['ok']); self.assertTrue(r['transport_ok'])
        self.assertEqual(r['error_kind'],'empty_response')

    def test_inline_thinking_only_is_not_an_answer(self):
        r=self.api.chat(self.model,[{'role':'user','content':'inline-only'}],streaming=False)
        self.assertFalse(r['ok']); self.assertEqual(r['error_kind'],'reasoning_only')
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_report_distinguishes_network_from_reasoning_only(self):
        response=self.api.chat(self.model,[{'role':'user','content':'reasoning-only'}])
        row={'model':'m','suite':'smoke','case_id':'x','result':response}
        summary=b.summarise([row])['m']['smoke']
        self.assertEqual(summary['transport_successes'],1)
        self.assertEqual(summary['transport_error_rate'],0)
        self.assertEqual(summary['usable_responses'],0)
        self.assertEqual(summary['reasoning_only_responses'],1)

    def test_csv_formula_protection(self):
        self.assertEqual(b.csv_safe('=1+1'), "'=1+1")
        self.assertEqual(b.csv_safe('ordinary text'), 'ordinary text')

    def test_config_blocks_payload_override(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config.json'
            p.write_text(json.dumps({'models':[{**self.model,'request_options':{'stream':False}}]}))
            with self.assertRaises(ValueError):b.config_load(p)

    def test_dotenv_not_executed_or_overriding_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'.env'; p.write_text('LR_TEST_VALUE="$(do-not-execute)"\nLR_KEEP=replace\n')
            with patch.dict(os.environ,{'LR_KEEP':'original'},clear=False):
                os.environ.pop('LR_TEST_VALUE',None); b.load_env(p)
                self.assertEqual(os.environ['LR_TEST_VALUE'],'$(do-not-execute)')
                self.assertEqual(os.environ['LR_KEEP'],'original'); os.environ.pop('LR_TEST_VALUE')

    def test_end_to_end_cli_and_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); config=root/'config.json'; output=root/'reports'
            config.write_text(json.dumps(self.cfg))
            command=[sys.executable,str(b.ROOT/'benchmark.py'),'--config',str(config),'--env-file',str(root/'absent.env'),
                     '--suite','smoke,quality,context,concurrency,capabilities,latency,stability,review,dummy,rag','--context-chars','1000',
                     '--workers','1,2','--requests-per-worker','1','--samples','2','--max-output-tokens','4096','--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=40)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            run=next(output.iterdir())
            data=json.loads((run/'summary.json').read_text())
            self.assertEqual(data['metadata']['status'],'completed')
            self.assertEqual(data['metadata']['models'][0]['max_output_tokens'],4096)
            self.assertEqual(data['models']['fake']['dummy']['requests'],12)
            self.assertEqual(data['models']['fake']['rag']['requests'],16)
            self.assertIn('retrieved',data['models']['fake']['rag']['by_mode'])
            self.assertTrue((run/'comparison.html').exists()); self.assertTrue((run/'results.csv').exists())
            self.assertTrue((run/'human_review.csv').exists()); self.assertTrue((run/'fake'/'results.jsonl').exists())
            self.assertTrue(data['models']['fake']['context']['by_input_characters']['1000']['all_positions_passed'])
            self.assertNotIn('PRIVATE',(run/'results.jsonl').read_text())


if __name__=='__main__':
    unittest.main()
