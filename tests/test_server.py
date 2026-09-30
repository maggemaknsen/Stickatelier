import base64
from http.cookiejar import CookieJar
from io import BytesIO
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from processing import png

class LocalAnalysisFixture:
    """No credentials and no OpenAI calls. Only used by the test server."""
    def __init__(self):self.last=None
    def status(self):return dict(connected=True,email='Lokaler UI-Test',plan_enabled=True)
    def models(self):return [dict(id='local-test-model',name='Lokaler Test · simulierte Analyse')]
    def suggest(self,original,model,current,mode,goal,prepared,stats):
        from analysis import parse_analysis
        self.last=dict(original=original,prepared=prepared,stats=stats,model=model)
        return parse_analysis(json.dumps(dict(explanation='Simulierte Analyse für den lokalen Oberflächentest.',
            findings=[dict(title='Testdaten: kleine Flächen',detail='Diese Beobachtung dient nur dem UI-Test.',severity='medium')],
            warnings=['Testdaten, keine reale Motivanalyse.'],settings=dict(colors=2,smooth=0),
            edit_prompt='Unwichtige Punkte vereinfachen und Schrift bewahren.')),current)

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        password_file=Path(cls.temp.name)/'password.txt'
        password_file.write_text('local-test-password',encoding='utf-8')
        with patch.dict(os.environ,ATELIER_DATA=cls.temp.name,ATELIER_PASSWORD_FILE=str(password_file),ATELIER_COOKIE_SECURE='false'):
            spec=importlib.util.spec_from_file_location('atelier_http_test_server',ROOT/'app/server.py')
            cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
        cls.module.AI=LocalAnalysisFixture()
        cls.http=cls.module.ThreadingHTTPServer(('127.0.0.1',0),cls.module.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.temp.cleanup()

    def setUp(self):
        self.module.AI.last=None
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        self.client.open(self.base).read()
        json.load(self.post('/auth/login',dict(password='local-test-password')))

    def post(self,path,body,headers=None):
        data=body if isinstance(body,bytes) else json.dumps(body).encode()
        return self.client.open(urllib.request.Request(self.base+path,data,{'X-Atelier':'1',**(headers or {})}))

    def source(self):
        im=Image.new('RGBA',(160,80),'#ffffff')
        ImageDraw.Draw(im).rectangle((80,0,159,79),fill='#ff0000')
        im.putpixel((0,0),(0,0,0,0))
        return json.load(self.post('/api/upload',png(im),{'X-Filename':'local-test.png'}))

    def test_generate_handoff_works_without_project_or_ai(self):
        result=json.load(self.post('/api/ai/handoff',dict(action='generate',goal='Ein Blatt',settings=dict(colors=3,width_mm=80))))
        self.assertIsNone(result['image']);self.assertIsNone(result['source_id'])
        self.assertIn('Höchstens 3',result['prompt']);self.assertIn('80 mm',result['prompt'])
        self.assertIsNone(self.module.AI.last)

    def test_width_change_reaches_preview_and_export_and_out_of_range_is_rejected(self):
        p=self.source()
        for width in (80,150,260):
            with self.subTest(width=width):
                request=dict(id=p['id'],settings=dict(width_mm=width))
                preview=json.load(self.post('/api/preview',request))
                self.assertEqual(preview['stats']['width_mm'],width)
                self.assertEqual(preview['stats']['height_mm'],width/2)
                with zipfile.ZipFile(BytesIO(self.post('/api/export',request).read())) as package:
                    exported=json.loads(package.read('einstellungen.json'))
                    self.assertEqual(exported['width_mm'],width)
                    image=Image.open(BytesIO(package.read('motiv-vorbereitet.png')))
                    self.assertAlmostEqual(image.width/image.info['dpi'][0]*25.4,width,delta=0.2)
        for route in ('/api/preview','/api/export'):
            with self.subTest(route=route):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    self.post(route,dict(id=p['id'],settings=dict(width_mm=400)))
                self.assertEqual(e.exception.code,400)

    def test_reference_uses_current_palette_original_remains_available(self):
        p=self.source()
        chosen=dict(colors=2,width_mm=80,palette_edit=dict(base=['#ffffff','#ff0000'],map={'#ff0000':'#0000ff'}))
        raw=dict(action='edit',id=p['id'],goal='Details vereinfachen',settings=chosen)
        result=json.load(self.post('/api/ai/handoff',raw))
        im=Image.open(BytesIO(base64.b64decode(result['image'].split(',')[1])))
        self.assertEqual(im.getpixel((120,40)),(0,0,255,255))
        self.assertIn('#0000FF',result['prompt'])
        self.assertAlmostEqual(im.width/im.info['dpi'][0]*25.4,80,places=1)
        raw['image_source']='original'
        original=json.load(self.post('/api/ai/handoff',raw))
        im=Image.open(BytesIO(base64.b64decode(original['image'].split(',')[1])))
        self.assertEqual(im.getpixel((120,40)),(255,0,0,255))

    def test_portrait_long_side_preview_export_analysis_and_both_reference_sources(self):
        p=json.load(self.post('/api/upload',png(Image.new('RGBA',(100,200),'red')),{'X-Filename':'portrait-test.png'}))
        chosen=dict(long_side_mm=160)
        request=dict(id=p['id'],settings=chosen)
        preview=json.load(self.post('/api/preview',request))
        self.assertEqual((preview['stats']['width_mm'],preview['stats']['height_mm']),(80,160))
        with zipfile.ZipFile(BytesIO(self.post('/api/export',request).read())) as package:
            exported=json.loads(package.read('einstellungen.json'))
            self.assertEqual(exported['settings']['long_side_mm'],160)
            im=Image.open(BytesIO(package.read('motiv-vorbereitet.png')))
            self.assertAlmostEqual(im.height/im.info['dpi'][1]*25.4,160,delta=0.2)
        analysis=json.load(self.post('/api/ai/suggest',{**request,'model':'local-test-model'}))
        self.assertEqual(analysis['settings']['long_side_mm'],160)
        self.assertEqual(analysis['settings']['width_mm'],80)
        for source in ('original','prepared'):
            result=json.load(self.post('/api/ai/handoff',{**request,'action':'edit','goal':'Vereinfachen','image_source':source}))
            self.assertIn('lange Seite der gesamten Bildfläche: 160 mm',result['prompt'])
            im=Image.open(BytesIO(base64.b64decode(result['image'].split(',')[1])))
            self.assertAlmostEqual(im.height/im.info['dpi'][1]*25.4,160,delta=0.2)
        for route in ('/api/preview','/api/export','/api/ai/handoff'):
            with self.subTest(route=route):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    self.post(route,dict(id=p['id'],settings=dict(long_side_mm=400),action='edit',goal='x'))
                self.assertEqual(e.exception.code,400)

    def test_import_is_new_project_and_parent_unchanged(self):
        p=self.source();before=self.client.open(self.base+'/api/original?id='+p['id']).read()
        variant=json.load(self.post('/api/upload',png(Image.new('RGBA',(90,60),'green')),
                                   {'X-Filename':'returned.png','X-Atelier-Kind':'chatgpt-edit','X-Atelier-Source':p['id']}))
        self.assertNotEqual(variant['id'],p['id']);self.assertEqual(variant['parent_id'],p['id'])
        self.assertEqual(variant['kind'],'chatgpt-edit')
        self.assertEqual(self.client.open(self.base+'/api/original?id='+p['id']).read(),before)
        stored=json.load(self.client.open(self.base+'/api/project?id='+variant['id']))
        self.assertEqual(stored,variant)
        generated=json.load(self.post('/api/upload',png(Image.new('RGBA',(90,60),'blue')),{'X-Atelier-Kind':'chatgpt-generate'}))
        self.assertNotIn('parent_id',generated)

    def test_invalid_parent_or_handoff_rejected(self):
        for path,body,headers in [('/api/upload',png(Image.new('RGBA',(20,20),'red')),{'X-Atelier-Kind':'chatgpt-edit','X-Atelier-Source':'../private'}),
                                 ('/api/upload',png(Image.new('RGBA',(20,20),'red')),{'X-Atelier-Kind':'chatgpt-edit'}),
                                 ('/api/ai/handoff',dict(action='edit',id='../private',goal='x'),{}),
                                 ('/api/ai/handoff',dict(action='generate',goal='x'),{'Origin':'https://evil.example'})]:
            with self.subTest(path=path,headers=headers):
                with self.assertRaises(urllib.error.HTTPError) as e:self.post(path,body,headers)
                self.assertIn(e.exception.code,(400,403))

    def test_analysis_sees_original_prepared_palette_and_dimensions(self):
        p=self.source()
        chosen=dict(colors=3,width_mm=80,palette_edit=dict(base=['#ffffff','#ff0000'],map={'#ff0000':'#0000ff'}))
        result=json.load(self.post('/api/ai/suggest',dict(id=p['id'],settings=chosen,model='local-test-model',mode='logo')))
        self.assertEqual(result['settings']['colors'],2);self.assertEqual(result['settings']['width_mm'],80)
        self.assertEqual(result['findings'][0]['severity'],'medium')
        recorded=self.module.AI.last
        self.assertEqual(Image.open(BytesIO(recorded['original'])).getpixel((120,40)),(255,0,0,255))
        self.assertEqual(Image.open(BytesIO(recorded['prepared'])).getpixel((120,40)),(0,0,255,255))
        self.assertEqual(recorded['stats']['width_mm'],80)

if __name__=='__main__':unittest.main()
