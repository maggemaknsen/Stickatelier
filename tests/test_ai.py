import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from analysis import parse_analysis
from chatgpt import ChatGPT
from handoff import handoff_request, make_prompt
from processing import settings

def response():
    return dict(explanation='Einige kleine Flächen sollten geprüft werden.',
                findings=[dict(title='Feine Details',detail='Die kleinen Punkte im Motiv prüfen.',severity='medium')],
                warnings=['Ein Probestick ist erforderlich.'],settings=dict(colors=3,smooth=0),
                edit_prompt='Kleine Punkte vereinfachen; die Schrift bewahren.')

class HandoffTests(unittest.TestCase):
    def test_generate_prompt_without_existing_image(self):
        r=handoff_request(dict(action='generate',goal='Ein Fuchs mit einem Blatt',style='emblem',settings=dict(colors=4,width_mm=80)))
        prompt=make_prompt(r)
        self.assertIn('Erzeuge ein neues Motiv.',prompt)
        self.assertIn('Ein Fuchs mit einem Blatt',prompt)
        self.assertIn('Höchstens 4',prompt)
        self.assertIn('80 mm',prompt)
        self.assertIn('transparentem Hintergrund',prompt)
        self.assertNotIn('Referenzpalette',prompt)

    def test_edit_prompt_respects_options_and_actual_palette(self):
        raw=dict(action='edit',goal='Sterne entfernen',transparent=False,preserve_text=True,settings=dict(colors=2))
        prompt=make_prompt(handoff_request(raw),dict(palette=[dict(hex='#e99169',share=20)]))
        self.assertIn('Referenzbild',prompt)
        self.assertIn('Schrift',prompt)
        self.assertIn('#E99169',prompt)
        self.assertIn('weißen Hintergrund',prompt)
        raw['preserve_text']=False
        self.assertNotIn('Vorhandene Schrift',make_prompt(handoff_request(raw)))

    def test_long_side_is_explicit_in_generation_prompt(self):
        prompt=make_prompt(handoff_request(dict(action='generate',goal='Ein Blatt',settings=dict(long_side_mm=160))))
        self.assertIn('lange Seite der gesamten Bildfläche: 160 mm',prompt)
        self.assertNotIn('Stickbreite',prompt)

    def test_bad_handoff_parameters_rejected(self):
        bad=[dict(action='bad',goal='x'),dict(action='edit',goal=' '),dict(action='generate',goal='x'*3001),
             dict(action='generate',goal='x',style='bad'),dict(action='edit',goal='x',image_source='../private'),
             dict(action='generate',goal='x',transparent='true'),dict(action='generate',goal=42),
             dict(action='generate',goal='x',settings=dict(colors=0))]
        for raw in bad:
            with self.subTest(raw=str(raw)[:80]):
                with self.assertRaises(ValueError):handoff_request(raw)

class AnalysisTests(unittest.TestCase):
    def test_model_cannot_raise_color_cap_change_size_or_inject_palette(self):
        raw=response();raw['settings'].update(colors=20,width_mm=10,long_side_mm=10,palette_edit={'bad':'value'},unknown='ignored')
        current=settings(dict(colors=4,width_mm=120,long_side_mm=160,palette_edit=dict(base=['#112233'],map={'#112233':'#ffffff'})))
        result=parse_analysis(json.dumps(raw),current)
        self.assertEqual(result['settings']['colors'],4)
        self.assertEqual(result['settings']['width_mm'],120)
        self.assertEqual(result['settings']['long_side_mm'],160)
        self.assertIsNone(result['settings']['palette_edit'])
        self.assertNotIn('unknown',result['settings'])
        self.assertEqual(result['findings'][0]['severity'],'medium')

    def test_markdown_wrapper_and_text_lengths(self):
        raw=response();raw['explanation']='a'*3000;raw['edit_prompt']='b'*4000
        result=parse_analysis('```json\n'+json.dumps(raw)+'\n```',settings({}))
        self.assertEqual(len(result['explanation']),2000)
        self.assertEqual(len(result['edit_prompt']),2500)

    def test_invalid_model_results_are_not_applied(self):
        bad=['oops','[]','{}']
        for key,value in [('settings',[]),('explanation',42),('warnings','string'),('edit_prompt',{}),
                          ('findings',[dict(title='x',detail='y',severity='invented')]),
                          ('settings',dict(colors=1.5)),('settings',dict(colors=0)),
                          ('settings',dict(smooth=99)),('settings',dict(remove_bg='yes'))]:
            raw=response();raw[key]=value;bad.append(json.dumps(raw))
        for output in bad:
            with self.subTest(output=output[:80]):
                with self.assertRaises(ValueError):parse_analysis(output,settings({}))

    def run_stream(self,events):
        class Stream:
            def __enter__(self):return iter([('data: '+json.dumps(e)+'\n\n').encode() for e in events])
            def __exit__(self,*args):pass
        with tempfile.TemporaryDirectory() as directory:
            provider=ChatGPT(directory)
            with patch.object(provider,'models',return_value=[dict(id='local-test-model')]),patch.object(provider,'access',return_value='test-token-not-a-credential'),patch('chatgpt.urllib.request.urlopen',return_value=Stream()) as network:
                result=provider.suggest(b'original','local-test-model',settings(dict(colors=4)),'logo','Schrift erhalten',b'prepared',dict(palette=[]))
                request=network.call_args.args[0]
                payload=json.loads(request.data)
                self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
                self.assertFalse(payload['store'])
                self.assertTrue(payload['stream'])
                self.assertEqual(sum(c['type']=='input_image' for c in payload['input'][0]['content']),2)
                return result

    def test_completed_stream_analyzes_two_images(self):
        output=json.dumps(response())
        result=self.run_stream([dict(type='response.output_text.delta',delta=output[:40]),dict(type='response.output_text.delta',delta=output[40:]),dict(type='response.completed')])
        self.assertEqual(result['settings']['colors'],3)
        self.assertIn('Kleine Punkte',result['edit_prompt'])

    def test_interrupted_or_failed_stream_is_not_success(self):
        delta=dict(type='response.output_text.delta',delta=json.dumps(response()))
        for events in ([delta],[delta,dict(type='response.failed')],[delta,dict(type='response.incomplete')]):
            with self.subTest(events=events[-1]['type']):
                with self.assertRaises(ValueError):self.run_stream(events)

if __name__=='__main__':unittest.main()
