from io import BytesIO
import sys
from pathlib import Path
import unittest
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from processing import prepare, settings


class FillTests(unittest.TestCase):
    def test_only_selected_connected_region_changes_and_original_stays_intact(self):
        original=Image.new('RGBA',(100,80),'white')
        draw=ImageDraw.Draw(original)
        draw.rectangle((10,10,30,60),fill='red')
        draw.rectangle((60,10,80,60),fill='red')
        before=original.tobytes()
        result,stats=prepare(original,dict(colors=3,fill_edits=[dict(x=.2,y=.3,color='#0000ff')]))
        self.assertEqual(result.getpixel((20,30)),(0,0,255,255))
        self.assertEqual(result.getpixel((70,30)),(255,0,0,255))
        self.assertEqual(result.getpixel((0,0)),(255,255,255,255))
        self.assertEqual(original.tobytes(),before)
        self.assertEqual(stats['colors'],3)

    def test_transparent_hole_and_diagonal_regions(self):
        original=Image.new('RGBA',(20,20),'white')
        draw=ImageDraw.Draw(original)
        draw.rectangle((5,5,10,10),fill=(0,0,0,0))
        original.putpixel((11,11),(0,0,0,0))
        result,_=prepare(original,dict(colors=2,fill_edits=[dict(x=.3,y=.3,color='#ff0000')]))
        self.assertEqual(result.getpixel((5,5)),(255,0,0,255))
        self.assertEqual(result.getpixel((11,11))[3],0)
        self.assertEqual(result.getpixel((0,0)),(255,255,255,255))

    def test_sequential_fills_and_removing_last_operation(self):
        original=Image.new('RGBA',(40,20),'white')
        ImageDraw.Draw(original).rectangle((0,0,19,19),fill='red')
        fills=[dict(x=.1,y=.5,color='#0000ff'),dict(x=.9,y=.5,color='#00ff00')]
        result,_=prepare(original,dict(colors=3,fill_edits=fills))
        self.assertEqual(result.getpixel((5,5)),(0,0,255,255))
        self.assertEqual(result.getpixel((35,5)),(0,255,0,255))
        undone,_=prepare(original,dict(colors=3,fill_edits=fills[:-1]))
        self.assertEqual(undone.getpixel((35,5)),(255,255,255,255))

    def test_new_fill_color_increases_actual_color_count(self):
        original=Image.new('RGBA',(30,20),'white')
        draw=ImageDraw.Draw(original)
        draw.rectangle((0,0,5,19),fill='red')
        draw.rectangle((20,0,25,19),fill='red')
        result,stats=prepare(original,dict(colors=2,fill_edits=[dict(x=.05,y=.5,color='#0000ff')]))
        self.assertEqual(stats['colors'],3)
        self.assertEqual(stats['settings']['colors'],2)
        self.assertEqual(result.getpixel((1,10)),(0,0,255,255))
        self.assertEqual(result.getpixel((21,10)),(255,0,0,255))

    def test_invalid_fill_requests_are_rejected(self):
        for fill in (None,{},dict(x=1,y=0,color='#ffffff'),dict(x=float('nan'),y=0,color='#ffffff'),
                     dict(x=True,y=0,color='#ffffff'),dict(x=0,y=0,color='red')):
            with self.subTest(fill=fill),self.assertRaises(ValueError):
                settings(dict(fill_edits=[fill]))
        with self.assertRaises(ValueError):
            settings(dict(fill_edits=[dict(x=0,y=0,color='#ffffff')]*101))


if __name__=='__main__':unittest.main()
