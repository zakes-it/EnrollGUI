# -*- coding: utf-8 -*-
#
#  AppDelegate.py
#  EnrollGui
#
#  Created by mike on 10/25/15.
#  Copyright (c) 2015 PowerHouse. All rights reserved.
#

from objc import YES, NO, IBOutlet
import PyObjCTools

from Foundation import *
from AppKit import *



class AppDelegate(NSObject):
    '''NSApplicationDelegate method
    Sent by the default notification center immediately before the
    application object is initialized.'''
    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return True

    MyWindowController = IBOutlet()

    def applicationWillFinishLaunching_(self, sender):
        #        NSMenu.setMenuBarVisible_(NO)
        NSApp.activateIgnoringOtherApps_(YES)

    def applicationDidFinishLaunching_(self, sender):
        '''NSApplicationDelegate method
        Sent by the default notification center after the application has
        been launched and initialized but before it has received its first
        event.'''
            
        # Prevent automatic relaunching at login on Lion+
        if NSApp.respondsToSelector_('disableRelaunchOnLogin'):
            NSApp.disableRelaunchOnLogin()
                
        # show the default initial view
        self.MyWindowController.startApp()
