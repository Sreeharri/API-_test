import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import benchmark as b
import dummy_tests as d

class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases={c['id']:c for c in d.load('dummy_workflow_cases.json')['cases']}
        cls.quality={c['id']:c for c in d.load('legal_radar_cases.json')}
        cls.rag=d.load('dummy_rag_cases.json')

    def output(self,case):
        obj=copy.deepcopy(case['expected'])
        obj['summary']='Human review required. '+case['source_text'].split('\n')[0]
        for task in obj['tasks']:
            task['title']=task['action'];task['description']=task['evidence_quote']
        return obj

    def result(self,obj):return {'ok':True,'content':json.dumps(obj),'truncated':False}

    def test_alias_preserves_strict_failure(self):
        score=b.score(self.result({'plants':['Plant A']}),self.quality['reason-conditional'])
        self.assertFalse(score['exact_match']);self.assertTrue(score['normalized_match'])
        self.assertEqual(score['normalized_predicted'],{'plants':['A']})
        self.assertTrue(score['normalizations_applied'])

    def test_alias_does_not_correct_wrong_answer(self):
        self.assertFalse(b.score(self.result({'plants':['Plant B']}),self.quality['reason-conditional'])['normalized_match'])

    def test_no_fuzzy_evidence_id_repair(self):
        case=self.quality['task-grounded'];obj=copy.deepcopy(case['expected']);obj['evidence_id']='DOC-TASK-3'
        score=b.score(self.result(obj),case)
        self.assertFalse(score['normalized_match']);self.assertFalse(score['exact_match'])

    def test_citation_alias_uses_known_source_only(self):
        case=self.quality['rag-cross-language']
        self.assertTrue(b.score(self.result({'years':7,'source_id':'[DOC-DE § 12]'}),case)['normalized_match'])
        self.assertFalse(b.score(self.result({'years':7,'source_id':'DOC-FAKE'}),case)['normalized_match'])

    def test_truncated_correct_json_cannot_pass_normalized(self):
        r=self.result({'plants':['Plant A']});r['truncated']=True
        self.assertFalse(b.score(r,self.quality['reason-conditional'])['normalized_match'])

    def test_good_structured_workflow_all_cases(self):
        for case in self.cases.values():
            with self.subTest(case=case['id']):
                out=d.grade_workflow(self.result(self.output(case)),case)
                self.assertTrue(out['exact_match'],out['checks'])
                self.assertTrue(out['human_review_required'])

    def test_draft_cannot_create_binding_task(self):
        case=self.cases['draft-only'];obj=self.output(case)
        obj['tasks']=self.output(self.cases['crane-duty'])['tasks']
        self.assertFalse(d.grade_workflow(self.result(obj),case)['exact_match'])

    def test_irrelevant_cannot_create_task(self):
        case=self.cases['irrelevant-fishing'];obj=self.output(case)
        obj['tasks']=self.output(self.cases['crane-duty'])['tasks']
        self.assertFalse(d.grade_workflow(self.result(obj),case)['checks']['task_fields'])

    def test_invented_due_date_fails(self):
        case=self.cases['missing-deadline'];obj=self.output(case);obj['tasks'][0]['due_date']='2027-12-31'
        self.assertFalse(d.grade_workflow(self.result(obj),case)['exact_match'])

    def test_wrong_evidence_quote_fails(self):
        case=self.cases['crane-duty'];obj=self.output(case);obj['tasks'][0]['evidence_quote']='Inspect every week.'
        out=d.grade_workflow(self.result(obj),case)
        self.assertFalse(out['checks']['evidence_quotes']);self.assertFalse(out['exact_match'])

    def test_summary_sanity_does_not_claim_faithfulness(self):
        case=self.cases['crane-duty'];obj=self.output(case);obj['summary']='Human review required. Invented unsupported claim.'
        out=d.grade_workflow(self.result(obj),case)
        self.assertTrue(out['checks']['summary_sanity'])
        self.assertTrue(out['human_review_required'])
        self.assertIn('human review',out['score_scope'])

    def test_rag_historical_filter_does_not_retrieve_future_version(self):
        docs=d.retrieve('crane inspection interval',self.rag['documents'],'2027-06-01',8)
        self.assertNotIn('RAG-CRANE-NEW',{x['id'] for x in docs})
        self.assertIn('RAG-CRANE-OLD',{x['id'] for x in docs})

    def test_rag_recall_measured_without_injecting_gold_documents(self):
        for case in self.rag['cases']:
            ids={x['id'] for x in d.retrieve(case['question'],self.rag['documents'],case['as_of'],3)}
            self.assertTrue(set(case['expected_source_ids'])<=ids,(case['id'],ids))

    def test_oracle_grounded_answers_pass(self):
        for case in self.rag['cases']:
            docs=[x for x in self.rag['documents'] if x['id'] in case['expected_source_ids']]
            out=d.grade_rag(self.result(case['expected']),case,docs)
            self.assertTrue(out['exact_match'],(case['id'],out['checks']))

    def test_correct_rag_answer_with_fake_source_fails(self):
        case=self.rag['cases'][0];obj=copy.deepcopy(case['expected']);obj['citations']=['FAKE']
        self.assertFalse(d.grade_rag(self.result(obj),case,self.rag['documents'])['exact_match'])

    def test_correct_rag_answer_without_evidence_fails(self):
        case=self.rag['cases'][0];obj=copy.deepcopy(case['expected']);obj['supporting_quotes']=[]
        self.assertFalse(d.grade_rag(self.result(obj),case,self.rag['documents'])['exact_match'])

    def test_unknown_fine_requires_abstention(self):
        case=next(c for c in self.rag['cases'] if c['id']=='missing-fine')
        obj={'status':'ANSWER','answer':10000,'citations':['RAG-ENERGY'],'supporting_quotes':['No monetary fine is specified.']}
        self.assertFalse(d.grade_rag(self.result(obj),case,self.rag['documents'])['exact_match'])

    def test_expected_answers_not_in_prompt(self):
        case=self.cases['crane-duty']
        prompt=d.workflow_prompt(case,d.load('dummy_workflow_cases.json')['routing'])
        self.assertNotIn('expected',prompt[1]['content'])
        case=self.rag['cases'][0]
        self.assertNotIn('expected',d.rag_prompt(case,self.rag['documents'])[1]['content'])

if __name__=='__main__':unittest.main()
