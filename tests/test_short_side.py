from io import BytesIO
from pathlib import Path
import sys
import unittest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from processing import prepare, png, settings


class ShortSideTests(unittest.TestCase):
    def test_short_side_sets_portrait_landscape_square_and_narrow_sizes(self):
        for size,expected in [((100,200),(100,200)),((200,100),(200,100)),
                              ((100,100),(100,100)),((20,200),(100,1000))]:
            with self.subTest(size=size):
                result,stats=prepare(Image.new('RGBA',size,'red'),dict(short_side_mm=100))
                self.assertEqual((stats['width_mm'],stats['height_mm']),expected)
                self.assertEqual(stats['short_side_mm'],100)
                self.assertEqual(settings(stats['settings'])['short_side_mm'],100)
                exported=Image.open(BytesIO(png(result,stats['width_mm'])))
                self.assertAlmostEqual(min(exported.size)/exported.info['dpi'][0]*25.4,100,delta=.2)

    def test_frame_limit_warns_without_rejecting_large_sizes(self):
        for size,short,warning in [((80,130),160,False),((130,80),160,False),
                                  ((100,100),160,False),((100,100),161,True),
                                  ((100,200),160,True),((20,200),100,True),
                                  ((100,200),180,True),((100,100),400,True)]:
            with self.subTest(size=size,short=short):
                _,stats=prepare(Image.new('RGBA',size,'red'),dict(short_side_mm=short))
                self.assertEqual(stats['frame_exceeded'],warning)
                self.assertEqual(any('Zu groß für den Stickrahmen' in message for message in stats['notices']),warning)

    def test_short_side_overrides_legacy_size_and_rejects_invalid_values(self):
        selected=settings(dict(short_side_mm=180,long_side_mm=80))
        self.assertEqual(selected['short_side_mm'],180)
        self.assertIsNone(selected['long_side_mm'])
        for value in (0,9,-1,float('nan'),float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError):
                settings(dict(short_side_mm=value))


if __name__=='__main__':unittest.main()
