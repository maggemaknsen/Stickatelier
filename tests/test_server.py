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
from unittest.mock import patch
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from processing import png

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        password_file=Path(cls.temp.name)/'password.txt'
        password_file.write_text('local-test-password',encoding='utf-8')
        with patch.dict(os.environ,ATELIER_DATA=cls.temp.name,ATELIER_PASSWORD_FILE=str(password_file),ATELIER_COOKIE_SECURE='false'):
            spec=importlib.util.spec_from_file_location('atelier_http_test_server',ROOT/'app/server.py')
            cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
        cls.http=cls.module.ThreadingHTTPServer(('127.0.0.1',0),cls.module.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.temp.cleanup()

    def setUp(self):
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

    def test_width_change_reaches_preview_and_export_and_out_of_range_is_rejected(self):
        p=self.source()
        for width in (80,150,260):
            with self.subTest(width=width):
                request=dict(id=p['id'],settings=dict(width_mm=width))
                preview=json.load(self.post('/api/preview',request))
                self.assertEqual(preview['stats']['width_mm'],width)
                self.assertEqual(preview['stats']['height_mm'],width/2)
                response=self.post('/api/export',request)
                self.assertEqual(response.headers['Content-Type'],'image/png')
                self.assertIn('.png',response.headers['Content-Disposition'])
                image=Image.open(BytesIO(response.read()))
                self.assertAlmostEqual(image.width/image.info['dpi'][0]*25.4,width,delta=0.2)
        for route in ('/api/preview','/api/export'):
            with self.subTest(route=route):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    self.post(route,dict(id=p['id'],settings=dict(width_mm=400)))
                self.assertEqual(e.exception.code,400)

    def test_portrait_long_side_preview_and_export(self):
        p=json.load(self.post('/api/upload',png(Image.new('RGBA',(100,200),'red')),{'X-Filename':'portrait-test.png'}))
        chosen=dict(long_side_mm=160)
        request=dict(id=p['id'],settings=chosen)
        preview=json.load(self.post('/api/preview',request))
        self.assertEqual((preview['stats']['width_mm'],preview['stats']['height_mm']),(80,160))
        im=Image.open(BytesIO(self.post('/api/export',request).read()))
        self.assertAlmostEqual(im.height/im.info['dpi'][1]*25.4,160,delta=0.2)
        for route in ('/api/preview','/api/export'):
            with self.subTest(route=route):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    self.post(route,dict(id=p['id'],settings=dict(long_side_mm=400)))
                self.assertEqual(e.exception.code,400)

    def test_import_is_new_project_and_parent_unchanged(self):
        p=self.source();before=self.client.open(self.base+'/api/original?id='+p['id']).read()
        variant=json.load(self.post('/api/upload',png(Image.new('RGBA',(90,60),'green')),
                                   {'X-Filename':'returned.png'}))
        self.assertNotEqual(variant['id'],p['id'])
        # Preserve metadata of a variant created by an older version.
        variant.update(parent_id=p['id'],kind='chatgpt-edit')
        (self.module.project(variant['id'])/'meta.json').write_text(json.dumps(variant),encoding='utf-8')
        self.assertEqual(self.client.open(self.base+'/api/original?id='+p['id']).read(),before)
        stored=json.load(self.client.open(self.base+'/api/project?id='+variant['id']))
        self.assertEqual(stored,variant)
        generated=json.load(self.post('/api/upload',png(Image.new('RGBA',(90,60),'blue'))))
        self.assertNotIn('parent_id',generated)

    def test_removed_workshop_routes_are_unavailable(self):
        for path in ('/api/ai/status','/api/ai/models','/auth/callback?code=unused'):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.client.open(self.base+path)
                self.assertEqual(error.exception.code,404)
        for path in ('/api/ai/handoff','/api/ai/connect','/api/ai/disconnect','/api/ai/suggest'):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.post(path,{})
                self.assertEqual(error.exception.code,404)
        self.assertFalse(hasattr(self.module,'AI'))
        self.assertFalse((Path(self.temp.name)/'private').exists())
        page=self.client.open(self.base).read().decode()
        for text in ('KI-Werkstatt','ChatGPT','aiWorkbench','accountDialog'):
            self.assertNotIn(text,page)
        self.assertNotIn('/api/ai/',self.client.open(self.base+'/app.js').read().decode())

    def test_palette_changes_reach_export_without_overwriting_original(self):
        p=self.source()
        before=self.client.open(self.base+'/api/original?id='+p['id']).read()
        chosen=dict(colors=2,width_mm=80,palette_edit=dict(base=['#ffffff','#ff0000'],map={'#ff0000':'#0000ff'}))
        request=dict(id=p['id'],settings=chosen)
        json.load(self.post('/api/preview',request))
        image=Image.open(BytesIO(self.post('/api/export',request).read()))
        self.assertEqual(image.getpixel((120,40)),(0,0,255,255))
        self.assertEqual(self.client.open(self.base+'/api/original?id='+p['id']).read(),before)

    def test_cross_origin_and_invalid_project_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/demo',{}, {'Origin':'https://evil.example'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('/api/preview',dict(id='../private',settings={}))
        self.assertEqual(error.exception.code,400)

    def test_short_side_over_frame_limit_remains_previewable_and_exportable(self):
        p=json.load(self.post('/api/upload',png(Image.new('RGBA',(100,200),'red'))))
        request=dict(id=p['id'],settings=dict(short_side_mm=180))
        preview=json.load(self.post('/api/preview',request))
        self.assertEqual((preview['stats']['width_mm'],preview['stats']['height_mm']),(180,360))
        self.assertTrue(preview['stats']['frame_exceeded'])
        exported=Image.open(BytesIO(self.post('/api/export',request).read()))
        self.assertAlmostEqual(exported.width/exported.info['dpi'][0]*25.4,180,delta=.2)

    def test_fill_preview_equals_png_export_at_large_resolution(self):
        original=Image.new('RGBA',(2500,1300),'white')
        draw=ImageDraw.Draw(original)
        draw.rectangle((200,200,600,1000),fill='red')
        draw.rectangle((1800,200,2200,1000),fill='red')
        p=json.load(self.post('/api/upload',png(original)))
        request=dict(id=p['id'],settings=dict(colors=4,long_side_mm=160,
            fill_edits=[dict(x=.16,y=.5,color='#0000ff')]))
        preview=json.load(self.post('/api/preview',request))
        shown=Image.open(BytesIO(base64.b64decode(preview['image'].split(',')[1])))
        exported=Image.open(BytesIO(self.post('/api/export',request).read()))
        self.assertEqual(shown.size,exported.size)
        self.assertEqual(shown.tobytes(),exported.tobytes())
        self.assertEqual(exported.getpixel((384,600)),(0,0,255,255))
        self.assertEqual(exported.getpixel((1920,600)),(255,0,0,255))
        self.assertEqual([f.suffix for f in self.module.project(p['id']).glob('export-*')],['.png'])

if __name__=='__main__':unittest.main()
