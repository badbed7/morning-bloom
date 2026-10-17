import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from morning_bloom.app import Window
from morning_bloom.content import BY_DESIGN
from morning_bloom.storage import Store,SaveError
from morning_bloom.model import Garden
from morning_bloom.content import NEW_PLANTS
from morning_bloom.plant_catalog import plant_definition
from morning_bloom.flower_art import paint_collection_flower

NOW=1_700_000_000

class BoardInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.time=patch('morning_bloom.app.time.time',return_value=NOW);self.time.start()
        self.store=Store(Path(self.temp.name)/'garden.json')
        self.window=Window(self.store,Garden(NOW));self.window.clock.stop();self.window.autosave.stop()
        self.window.show();self.window.open_board();self.app.processEvents()
        self.board=self.window._board_window
    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.processEvents()
        self.time.stop();self.temp.cleanup()
    def finish_move(self):
        while self.board.animating:self.board.animation_step()
    def test_weekly_first_entry_and_portal_ui_survive_reopening(self):
        g=self.window.garden
        self.assertEqual(g.progression['tickets'],5)
        g.progression['board']['position']=7
        with patch('morning_bloom.board_model.secrets.randbelow',side_effect=[0,5,0]):self.board.roll_button.click()
        self.finish_move()
        self.assertIn('무료 스페셜',self.board.roll_button.text())
        self.assertFalse(self.board.special_center.isHidden())
        self.window.close_board();self.window.open_board();self.app.processEvents()
        self.board=self.window._board_window
        self.assertEqual(g.progression['tickets'],4)
        self.board.roll_button.click()
        self.assertEqual(g.progression['board']['last_result']['grade'],'S')
        self.assertEqual(g.progression['tickets'],4)
        self.assertEqual(self.store.load(NOW).progression['board']['completed'],1)
    def test_save_error_restores_wallet_and_exposes_retry(self):
        before=self.window.garden.to_dict()
        with patch.object(self.store,'save',side_effect=SaveError('disk full')):self.board.roll_button.click()
        self.assertEqual(self.window.garden.to_dict(),before)
        self.assertIn('저장하지 못했어요',self.board.result.text())
        self.assertTrue(self.board.roll_button.isEnabled())
    def test_all_150_icons_filters_and_equipment_slot_selection(self):
        self.assertEqual(self.board.items.count(),150)
        for index in range(150):self.assertFalse(self.board.items.item(index).icon().isNull())
        self.window.garden.coins=1000;self.window.garden.buy_pot()
        item=BY_DESIGN['P-A07'];self.window.garden.owned_skins.append(item['item_id'])
        self.board.sync();self.board.open_category('pot');self.board.slot.setCurrentIndex(1)
        for index in range(self.board.items.count()):
            row=self.board.items.item(index)
            if tuple(row.data(Qt.UserRole))==('pot',item['item_id']):self.board.items.setCurrentRow(index);break
        self.board.equip.click()
        self.assertEqual(self.window.garden.progression['slots'][1]['skin'],item['item_id'])
        self.assertEqual(self.window.garden.progression['slots'][0]['skin'],'terracotta')
    def test_board_fits_720_by_620_and_mode_switch_closes_it(self):
        self.board.resize(720,620);self.app.processEvents()
        for tab in range(3):
            self.board.tabs.setCurrentIndex(tab);self.app.processEvents()
            self.assertFalse(self.board.grab().isNull())
        self.assertTrue(self.window.set_developer_mode(True))
        self.assertIsNone(self.window._board_window)

    def test_new_plants_render_five_distinct_growth_stages(self):
        for species in NEW_PLANTS:
            frames=[]
            for stage in range(5):
                frame=QImage(180,200,QImage.Format_ARGB32_Premultiplied);frame.fill(Qt.transparent)
                p=QPainter(frame)
                paint_collection_flower(p,QRectF(0,0,180,200),plant_definition(species),stage=stage)
                p.end();frames.append(bytes(frame.bits()))
            self.assertEqual(len(set(frames)),5,species)

    def test_collection_picker_uses_the_harvested_flower_skin(self):
        g=self.window.garden
        g.collection=[dict(id='stored',species='daisy',harvested_at=NOW,base_sale_g=50,misted=False,bonus_g=0)]
        g.owned_skins.append('ivory');g.progression['flower_skins']['stored']='ivory'
        self.window.close_board();self.window.open_collection_picker()
        picker=self.window._collection_picker
        with patch('morning_bloom.collection_picker.paint_collection_flower',wraps=paint_collection_flower) as paint:
            picker._icon(g.collection[0])
        self.assertEqual(paint.call_args.kwargs['skin'],'ivory')
