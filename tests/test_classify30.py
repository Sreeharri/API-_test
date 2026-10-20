import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import classify_30_test as c

class Category30Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog,cls.cases=c.dataset();cls.ids=[x['id'] for x in cls.catalog['categories']]
    def gold(self,case):
        return {'category_ids':case['expected']['category_ids'][:],'status':case['expected']['status'],
                'summary':case['text'],'evidence_quote':case['text'],'dates':case['expected']['dates'][:],'review_required':True}
    def response(self,obj):return {'ok':True,'content':json.dumps(obj),'truncated':False}
    def test_exactly_30_balanced_categories(self):
        self.assertEqual(len(self.ids),30);self.assertEqual(len(self.cases),70)
        counts={id:0 for id in self.ids}
        for case in self.cases:
            if case['kind']=='single_label':counts[case['expected']['category_ids'][0]]+=1
        self.assertTrue(all(x==2 for x in counts.values()))
    def test_all_fixture_gold_decisions_pass(self):
        for case in self.cases:
            score=c.evaluate(self.response(self.gold(case)),case,self.ids)
            self.assertTrue(score['classification_correct'],case['id'])
            self.assertTrue(score['exact_match'],case['id'])
    def test_wrong_valid_category_fails(self):
        case=self.cases[0];obj=self.gold(case);obj['category_ids']=[self.ids[1]]
        self.assertFalse(c.evaluate(self.response(obj),case,self.ids)['classification_correct'])
    def test_unknown_or_duplicate_category_is_invalid(self):
        case=self.cases[0]
        for labels in (['OTHER'],[self.ids[0],self.ids[0]],[{}]):
            obj=self.gold(case);obj['category_ids']=labels
            score=c.evaluate(self.response(obj),case,self.ids)
            self.assertFalse(score['schema_valid']);self.assertFalse(score['classification_correct'])
    def test_summary_invented_date_fails_separately(self):
        case=self.cases[0];obj=self.gold(case);obj['summary']='Required by 2099-01-01.'
        score=c.evaluate(self.response(obj),case,self.ids)
        self.assertTrue(score['classification_correct']);self.assertFalse(score['summary_sanity_pass'])
    def test_summary_sanity_is_not_faithfulness_verification(self):
        case=self.cases[0];obj=self.gold(case);obj['summary']='A made-up source claim without a date.'
        score=c.evaluate(self.response(obj),case,self.ids)
        self.assertTrue(score['summary_sanity_pass']);self.assertTrue(score['human_review_required'])
    def test_missing_quote_fails(self):
        case=self.cases[0];obj=self.gold(case);obj['evidence_quote']=''
        self.assertFalse(c.evaluate(self.response(obj),case,self.ids)['quote_supported'])
    def test_unknown_scope_is_review_not_forced_category(self):
        case=next(x for x in self.cases if x['id']=='unknown-annex');obj=self.gold(case)
        self.assertEqual(obj['status'],'REVIEW');self.assertEqual(obj['category_ids'],[])
        self.assertTrue(c.evaluate(self.response(obj),case,self.ids)['classification_correct'])
    def test_prompt_has_no_expected_labels_metadata(self):
        messages=c.prompt(self.cases[0],self.catalog['categories'])
        user=json.loads(messages[1]['content'])
        self.assertEqual(set(user),{'categories','summary_language','text'})
        self.assertEqual(len(user['categories']),30)
    def test_metrics_distinguish_classification_from_summary(self):
        case=self.cases[0];obj=self.gold(case);obj['summary']='Must be done by 2099-01-01.'
        score=c.evaluate(self.response(obj),case,self.ids)
        row={'model':'test','case_id':case['id'],'category':case['kind'],'expected':case['expected'],
             'result':{'ok':True,'total_seconds':1},'score':score}
        result=c.metrics([row],self.catalog['categories'])['test']
        self.assertEqual(result['classification_accuracy'],1)
        self.assertEqual(result['summary_sanity_pass_rate'],0)
    def test_cli_fake_server_writes_reports(self):
        from test_benchmark import Handler,ThreadedServer
        server=ThreadedServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);config=root/'config.json'
                config.write_text(json.dumps({'models':[{'name':'fake','model':'fake-model','base_url':f'http://127.0.0.1:{server.server_port}/v1'}]}))
                cmd=[sys.executable,str(c.ROOT/'classify_30_test.py'),'--config',str(config),'--env-file',str(root/'no.env'),
                     '--models','fake','--limit','2','--output',str(root/'reports')]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                report=next((root/'reports').iterdir())
                for file in ('classification30.html','classification_summary.json','summary_review.csv','confusion.csv','results.jsonl'):
                    self.assertTrue((report/file).exists(),file)
                data=json.loads((report/'classification_summary.json').read_text())
                self.assertEqual(data['models']['fake']['requests'],2)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
