# -*- coding: utf-8 -*-
#
#  main.py
#  EnrollGui
#
#  Created by mike on 10/25/15.
#  Copyright (c) 2015 PowerHouse. All rights reserved.
#

# import modules required by application
import objc
import Foundation
import AppKit

from PyObjCTools import AppHelper

# import modules containing classes required to start application and load MainMenu.nib
import AppDelegate
import MyWindowController


# pass control to AppKit
AppHelper.runEventLoop()
