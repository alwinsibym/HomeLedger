import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(os.name == "nt", "Windows only")
class TestTaskbarIdentity(unittest.TestCase):
    def test_sets_properties_on_a_real_window(self):
        import tkinter
        from homeledger import winshell
        root = tkinter.Tk()
        root.title("HomeLedger test window")
        root.update()
        try:
            hwnd = winshell._find_window()
            self.assertTrue(hwnd, "window not found by title")
            self.assertTrue(winshell._set_props(hwnd, sys.executable))
            self.assertEqual(winshell._find_windows(), [])   # a Tk window is not a browser window: never mistaken for HomeLedger
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
