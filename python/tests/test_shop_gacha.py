import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QScrollArea
from morning_bloom.app import Window,SHOP_PAGE
from morning_bloom.content import BY_DESIGN
from morning_bloom.cosmetics import THEMES,POT_SKINS
from morning_bloom.model import Garden
from morning_bloom.storage import Store,SaveError

NOW=1_700_000_000

class ShopGacha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.time=patch('morning_bloom.app.time.time',return_value=NOW);self.time.start()
        self.store=Store(Path(self.temp.name)/'garden.json')
        self.garden=Garden(NOW)
        self.window=Window(self.store,self.garden)
        self.window.clock.stop();self.window.autosave.stop();self.window.show()
        self.window.pages.setCurrentIndex(SHOP_PAGE);self.app.processEvents()
    def tearDown(self):
        self.window.close();self.window.deleteLater();self.app.processEvents()
        self.time.stop();self.temp.cleanup()

    def test_gacha_card_balances_and_exchange_guide_are_first_visible_content(self):
        scroll=self.window.pages.widget(SHOP_PAGE).findChild(QScrollArea)
        for side in (320,384,520):
            self.window.setFixedSize(side,side);scroll.verticalScrollBar().setValue(0)
            self.app.processEvents()
            for widget in (self.window.gacha_balance,self.window.board_button,self.window.exchange_button,self.window.gacha_help):
                self.assertTrue(scroll.viewport().rect().contains(widget.mapTo(scroll.viewport(),widget.rect().bottomRight())),(side,widget.geometry()))
                self.assertTrue(scroll.viewport().rect().contains(widget.mapTo(scroll.viewport(),widget.rect().topLeft())))
        self.assertIn('주사위 0개',self.window.gacha_balance.text())
        self.assertIn('5개 받기 가능',self.window.gacha_weekly.text())
        self.assertIn('C 3 · B 8 · A 20 · S 40',self.window.gacha_help.text())
        self.assertEqual(self.garden.progression['week'],None)  # Browsing does not spend or claim.
        self.window.board_button.click();self.window.close_board()
        self.assertIn('주사위 5개',self.window.gacha_balance.text())
        self.assertNotIn('받기 가능',self.window.gacha_weekly.text())

    def test_real_rolls_add_background_and_skin_to_existing_shop_and_can_equip(self):
        self.window.board_button.click();board=self.window._board_window
        received=[]
        for category in ('garden','pot'):
            with patch('morning_bloom.board_model.secrets.randbelow',side_effect=[0,0,0]):board.roll()
            while board.animating:board.animation_step()
            reward=self.garden.progression['board']['last_result']
            self.assertEqual(reward['category'],category)
            received.append(reward['item_id'])
        self.window.close_board()
        self.assertIn('주사위 3개 · 꽃잎 2개',self.window.gacha_balance.text())
        for picker,key,button in ((self.window.theme_picker,received[0],self.window.apply_theme_button),
                                  (self.window.skin_picker,received[1],self.window.apply_skin_button)):
            self.assertIn(key,picker.buttons);self.assertEqual(picker.selected,key)
            self.assertFalse(picker.buttons[key].isHidden());self.assertTrue(button.isEnabled())
            button.click()
        self.assertEqual(self.garden.equipped_theme,received[0])
        self.assertEqual(self.garden.progression['slots'][0]['skin'],received[1])
        restored=self.store.load(NOW)
        self.assertEqual(restored.equipped_theme,received[0]);self.assertEqual(restored.equipped_skin,received[1])

    def select_exchange(self,item):
        board=self.window._board_window
        for index in range(board.items.count()):
            row=board.items.item(index)
            if tuple(row.data(Qt.UserRole))==(item['category'],item['item_id']):
                board.items.setCurrentRow(index);return board
        self.fail('Exchange item missing')

    def test_exchange_shortcut_opens_collection_and_adds_unlocked_background(self):
        self.garden.progression['petals']=3;self.window.refresh()
        self.window.exchange_button.click()
        self.assertEqual(self.window._board_window.tabs.currentIndex(),1)
        item=BY_DESIGN['G-C01'];board=self.select_exchange(item)
        self.assertTrue(board.exchange.isEnabled());board.exchange.click()
        self.window.close_board()
        self.assertIn(item['item_id'],self.window.theme_picker.buttons)
        self.assertEqual(self.garden.progression['petals'],0)
        self.assertIn('꽃잎 0개',self.window.gacha_balance.text())

    def test_failed_exchange_does_not_leave_phantom_cosmetic_in_shop(self):
        self.garden.progression['petals']=3;self.window.exchange_button.click()
        item=BY_DESIGN['G-C01'];board=self.select_exchange(item)
        with patch.object(self.store,'save',side_effect=SaveError('disk full')):board.exchange.click()
        self.window.close_board()
        self.assertNotIn(item['item_id'],self.window.theme_picker.buttons)
        self.assertEqual(self.garden.progression['petals'],3)

    def test_all_acquired_cosmetics_are_pageable_and_fit_small_windows(self):
        self.garden.owned_themes=list(THEMES);self.garden.owned_skins=list(POT_SKINS)
        self.window.refresh()
        self.assertEqual(len(self.window.theme_picker.buttons),83)
        self.assertEqual(len(self.window.skin_picker.buttons),45)
        for side in (320,384,520):
            self.window.setFixedSize(side,side)
            for picker,catalog in ((self.window.theme_picker,THEMES),(self.window.skin_picker,POT_SKINS)):
                picker.buttons[next(iter(catalog))].setChecked(True);picker.reveal_selected()
                seen=set()
                while True:
                    self.app.processEvents()
                    visible=[(key,b) for key,b in picker.buttons.items() if not b.isHidden()]
                    self.assertLessEqual(len(visible),3)
                    for key,button in visible:
                        seen.add(key);self.assertTrue(picker.rect().contains(button.geometry()))
                    if not picker.next.isEnabled():break
                    picker.next.click()
                self.assertEqual(seen,set(catalog))
        self.window.set_developer_mode(True)
        self.assertEqual(len(self.window.theme_picker.buttons),4)
        self.assertEqual(len(self.window.skin_picker.buttons),4)
        self.window.set_developer_mode(False)
        self.assertEqual(len(self.window.theme_picker.buttons),83)
