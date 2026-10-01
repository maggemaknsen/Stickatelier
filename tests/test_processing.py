import sys
from pathlib import Path
import unittest
from io import BytesIO
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from processing import components, prepare, decode, png, settings, demo

class PreparationTests(unittest.TestCase):
    def test_color_cap_and_hard_alpha(self):
        for n in (1,2,4,6,16,24):
            image,stats = prepare(demo(),dict(colors=n,remove_bg=True,smooth=1),600)
            rgba=np.array(image)
            self.assertLessEqual(len(np.unique(rgba[rgba[:,:,3]>0,:3],axis=0)),n)
            self.assertLessEqual(stats['colors'],n)
            self.assertTrue(set(np.unique(rgba[:,:,3])) <= {0,255})

    def test_existing_exact_colors_preserved(self):
        im=Image.new('RGBA',(40,40),'#112233')
        ImageDraw.Draw(im).rectangle((20,0,39,39),fill='#ff8844')
        result,_=prepare(im,dict(colors=4),100)
        self.assertTrue(np.array_equal(np.array(im),np.array(result)))

    def test_manual_recolor_preserves_geometry_transparency_and_original(self):
        im=Image.new('RGBA',(80,40),'#fefaf7')
        ImageDraw.Draw(im).rectangle((40,0,79,39),fill='#e99169')
        im.putpixel((0,0),(20,30,40,0))
        before=np.array(im).copy()
        _,base=prepare(im,dict(colors=2),100)
        edit=dict(base=base['base_palette'],map={'#e99169':'#123456'})
        result,stats=prepare(im,dict(colors=2,palette_edit=edit),100)
        self.assertEqual(result.getpixel((60,20)),(18,52,86,255))
        self.assertEqual(result.getpixel((20,20)),(254,250,247,255))
        self.assertEqual(result.getpixel((0,0)),(0,0,0,0))
        self.assertEqual(stats['colors'],2)
        self.assertEqual(stats['settings']['palette_edit'],edit)
        self.assertTrue(np.array_equal(before,np.array(im)))

    def test_manual_merge_uses_selected_target_and_combines_shares(self):
        im=Image.new('RGBA',(80,40),'#fefaf7')
        ImageDraw.Draw(im).rectangle((40,0,79,39),fill='#e99169')
        _,base=prepare(im,dict(colors=2),100)
        # First chosen color is orange; the second (off-white) takes orange.
        edit=dict(base=base['base_palette'],map={'#fefaf7':'#e99169'})
        result,stats=prepare(im,dict(colors=2,palette_edit=edit),100)
        self.assertEqual(stats['palette'],[dict(hex='#e99169',share=100.0)])
        self.assertEqual(stats['colors'],1)
        self.assertTrue((np.array(result)[:,:,:3]==[233,145,105]).all())

    def test_manual_replacements_do_not_cascade_or_block_color_swaps(self):
        im=Image.new('RGBA',(60,30),'#ff0000')
        ImageDraw.Draw(im).rectangle((30,0,59,29),fill='#0000ff')
        for mapping,right in [({'#ff0000':'#0000ff','#0000ff':'#00ff00'},(0,255,0,255)),
                              ({'#ff0000':'#0000ff','#0000ff':'#ff0000'},(255,0,0,255))]:
            result,stats=prepare(im,dict(colors=2,palette_edit=dict(base=['#ff0000','#0000ff'],map=mapping)),100)
            self.assertEqual(result.getpixel((10,10)),(0,0,255,255))
            self.assertEqual(result.getpixel((40,10)),right)
            self.assertEqual(stats['colors'],2)

    def test_manual_palette_survives_export_resolution(self):
        im=demo().resize((1800,1300),Image.Resampling.BICUBIC)
        _,base=prepare(im,dict(colors=4,remove_bg=True),600)
        edit=dict(base=base['base_palette'],map={base['base_palette'][0]:'#c012ab',base['base_palette'][1]:base['base_palette'][2]})
        expected={edit['map'].get(c,c) for c in edit['base']}
        for edge in (600,1800):
            result,stats=prepare(im,dict(colors=4,remove_bg=True,palette_edit=edit),edge)
            self.assertLessEqual(stats['colors'],3)
            self.assertEqual(stats['base_palette'],edit['base'])
            self.assertTrue({c['hex'] for c in stats['palette']} <= expected)
            self.assertIn('#c012ab',{c['hex'] for c in stats['palette']})
            restored=Image.open(BytesIO(png(result,100)))
            self.assertTrue(np.array_equal(np.array(restored),np.array(result)))

    def test_invalid_palette_changes_rejected(self):
        invalid=[[],{},dict(base=[],map={}),dict(base=['red'],map={}),
                 dict(base=['#123456','#123456'],map={}),dict(base=['#123456'],map={'#abcdef':'#ffffff'}),
                 dict(base=['#123456'],map={'#123456':'bad'}),dict(base=['#123456'],map=[]),
                 dict(base=['#aabbcc'],map={'#aabbcc':'#ffffff','#AABBCC':'#123456'}),
                 dict(base=['#123456','#abcdef','#ffffff'],map={})]
        for edit in invalid:
            with self.subTest(edit=edit):
                with self.assertRaises(ValueError):settings(dict(colors=2,palette_edit=edit))
        normalized=settings(dict(palette_edit=dict(base=['#ABCDEF'],map={'#ABCDEF':'#1234AB'})))
        self.assertEqual(normalized['palette_edit'],dict(base=['#abcdef'],map={'#abcdef':'#1234ab'}))

    def test_rare_logo_color_outside_sampling_grid_preserved(self):
        im=Image.new('RGBA',(400,400),'#112233')
        # More than 80k pixels triggers a stride-2 sample. Index 1 is skipped.
        im.putpixel((1,0),(255,136,68,255))
        result,stats=prepare(im,dict(colors=2),400)
        self.assertEqual(result.getpixel((1,0)),(255,136,68,255))
        self.assertEqual(stats['colors'],2)
        self.assertTrue(np.array_equal(np.array(im),np.array(result)))

    def test_background_only_border_connected(self):
        im=Image.new('RGBA',(100,100),'white')
        d=ImageDraw.Draw(im);d.rectangle((20,20,80,80),fill='blue');d.rectangle((40,40,60,60),fill='white')
        result,_=prepare(im,dict(colors=2,remove_bg=True),100)
        self.assertEqual(result.getpixel((0,0))[3],0)
        self.assertEqual(result.getpixel((50,50)),(255,255,255,255))

    def test_transparent_hidden_colors_use_no_slots(self):
        im=Image.new('RGBA',(50,50),(255,0,0,0))
        ImageDraw.Draw(im).rectangle((10,10,40,40),fill=(0,255,0,255))
        result,stats=prepare(im,dict(colors=1),100)
        self.assertEqual(stats['palette'][0]['hex'],'#00ff00')

    def test_small_island_removed(self):
        im=Image.new('RGBA',(100,100),(0,0,0,0))
        ImageDraw.Draw(im).point((50,50),fill='blue')
        ImageDraw.Draw(im).rectangle((10,10,30,30),fill='red')
        result,stats=prepare(im,dict(colors=2,width_mm=100,detail_mm=2),100)
        self.assertEqual(result.getpixel((50,50))[3],0)
        self.assertEqual(result.getpixel((20,20))[3],255)

    def test_components_merge_runs_and_keep_diagonals_separate(self):
        m=np.array([[1,0,1],[1,1,1],[0,0,0],[1,0,0],[0,1,0]],dtype=bool)
        labels=components(m)
        self.assertEqual(labels[0,0],labels[0,2])
        self.assertNotEqual(labels[3,0],labels[4,1])

    def test_size_and_export_dpi(self):
        result,stats=prepare(Image.new('RGBA',(400,200),'red'),dict(width_mm=80),300)
        self.assertEqual(stats['height_mm'],40)
        restored=Image.open(BytesIO(png(result,80)))
        self.assertAlmostEqual(restored.width/restored.info['dpi'][0]*25.4,80,places=1)

    def test_original_unchanged_and_no_upscale(self):
        im=demo();before=np.array(im).copy()
        result,_=prepare(im,dict(smooth=2,detail_mm=.5,remove_bg=True),2000)
        self.assertEqual(result.size,im.size)
        self.assertTrue(np.array_equal(before,np.array(im)))

    def test_long_side_controls_portrait_landscape_square_and_narrow_portrait(self):
        for size, expected in [((200,400),(80,160)), ((400,200),(160,80)),
                               ((300,300),(160,160)), ((20,400),(8,160))]:
            for edge in (300,2400):
                with self.subTest(size=size,edge=edge):
                    result,stats=prepare(Image.new('RGBA',size,'red'),dict(long_side_mm=160),edge)
                    self.assertAlmostEqual(stats['width_mm'],expected[0])
                    self.assertAlmostEqual(stats['height_mm'],expected[1])
                    self.assertEqual(stats['long_side_mm'],160)
                    # Resolved settings retain the chosen long side.
                    self.assertEqual(settings(stats['settings'])['long_side_mm'],160)
                    restored=Image.open(BytesIO(png(result,stats['width_mm'])))
                    self.assertAlmostEqual(max(restored.size)/restored.info['dpi'][0]*25.4,160,delta=0.2)

    def test_invalid_long_side_rejected(self):
        for value in (0,9,261,400,float('nan'),float('inf')):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):settings(dict(long_side_mm=value))

    def test_bad_values_and_bad_image(self):
        for raw in ({'colors':0},{'colors':100},{'width_mm':float('nan')},{'background':'oops'},{'remove_bg':'true'}):
            with self.assertRaises(ValueError):settings(raw)
        with self.assertRaises(ValueError):decode(b'not an image')

    def test_empty_image_rejected(self):
        with self.assertRaises(ValueError):prepare(Image.new('RGBA',(100,100),'white'),dict(remove_bg=True),100)

if __name__=='__main__':unittest.main()
