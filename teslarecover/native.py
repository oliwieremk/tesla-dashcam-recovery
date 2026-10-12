"""Native macOS presentation; all menu updates are scheduled on the Cocoa thread."""
import logging
import sys


def update_menu(window):
    if sys.platform != 'darwin':
        return
    from PyObjCTools import AppHelper

    def apply():
        try:
            from webview.platforms.cocoa import BrowserView, info
            info['CFBundleName'] = 'Tesla Recovery'
            instance = BrowserView.instances.get(window.uid)
            if instance:
                BrowserView.app.setMainMenu_(instance._recreate_menus(instance.menu))
        except Exception:
            logging.exception('Could not refresh the native menu')
    AppHelper.callAfter(apply)
