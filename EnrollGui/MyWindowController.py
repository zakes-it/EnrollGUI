# -*- coding: utf-8 -*-
#
#  MyWindowController.py
#  EnrollGui
#
#  Created by mike on 10/26/15.
#  Copyright (c) 2015 PowerHouse. All rights reserved.
#
'''Controller for the main window'''

from objc import YES, NO, IBAction, IBOutlet, nil
from PyObjCTools import AppHelper
from Foundation import *
from AppKit import *
from SystemConfiguration import SCDynamicStoreCopyConsoleUser

from time import sleep

import enroll, sys


class EmptyObj(object):
	""" used for passing argument objects to enroll """
	pass


class CustomWindow(NSWindow):
	""" this is here so the window can become active """
	def canBecomeKeyWindow(self):
		return True


class MyWindowController(NSObject):
	# set outlets for the interface elements
	window = objc.IBOutlet()
	
	progressIndicator = objc.IBOutlet()
	userTxtFld = objc.IBOutlet()
	hostnameTxtFld = objc.IBOutlet()
	enrollButton = objc.IBOutlet()
	reloadButton = objc.IBOutlet()
	# a combo box is used because pop up menus do not render at the login window
	manifestCmbBx = objc.IBOutlet() 
	credentialsButton = objc.IBOutlet()
	systemSerialLbl = objc.IBOutlet()
	manifestDetailToggle = objc.IBOutlet()
	manifestDetailTxtVw = objc.IBOutlet()
	
	authSheetWindow = objc.IBOutlet()
	authSheetLoginButton = objc.IBOutlet()
	
	errorWindow = objc.IBOutlet()
	statusTxtLbl = objc.IBOutlet()
	confirmErrorButton = objc.IBOutlet()
	
	
	# set global vars
	appMode = 'enroll'
	retryMode = 'client'
	availableRoles = {}
	client = {}
	
	# set enroll prefs not handled in getAppPrefs
	serial = None
	identifier = None
	user = None
	hostname = None
	role = None
	
	
	def awakeFromNib(self):
		NSLog("awoke from nib")
	
	
	def enlargeWindow(self):
		NSLog("Main window size: {}".format(self.window.frame().size))
		winRect = self.window.frame()
		winRect.size.height = 480
		winRect.origin.y = winRect.origin.y - 256
		NSLog("Setting new main window size: {}".format(winRect))
		self.window.setFrame_display_(winRect, True)
	
	
	def collapseWindow(self):
		NSLog("Main window size: {}".format(self.window.frame().size))
		winRect = self.window.frame()
		winRect.size.height = 180
		winRect.origin.y = winRect.origin.y + ( self.window.frame().size.height - 180 )
		NSLog("Setting new main window size: {}".format(winRect))
		self.window.setFrame_display_(winRect, True)
	
	
	def userLoggedIn(self):
		cfuser = SCDynamicStoreCopyConsoleUser(None, None, None)
		if cfuser[0] == 'loginwindow' or cfuser[0] == None:
			NSLog("No user logged in.")
			return False
		NSLog("{} is logged in and running the app.".format(cfuser[0]))
		return True


	def bringFrontCenter(self):
		""" bring the app to the front so it shows over the login window """
		if self.window:
			NSLog("window is present")
			self.window.becomeMainWindow()
			self.window.center()
			# needed so the window can show over the loginwindow
			self.window.setCanBecomeVisibleWithoutLogin_(True)
			self.errorWindow.setCanBecomeVisibleWithoutLogin_(True)
			self.authSheetWindow.setCanBecomeVisibleWithoutLogin_(True)
			self.window.setLevel_(NSScreenSaverWindowLevel - 1)
			self.window.orderFrontRegardless()
	

	def getAppPrefs(self):
		for key in enroll.arguments.keys():
			NSLog("Getting app defaults for key: {}".format(key))
			if key not in ('hostname', 'user', 'role'):
				setattr(self, key, enroll.getPreference(key))
		self.serial = enroll.getSerial()
		self.systemSerialLbl.setStringValue_(self.serial)
		NSLog("Server: {}".format(self.server))

	
	def evalHostName(self):
		""" check the provided hostname and allow enroll to proceed if it is valid """
		try:
			enroll.checkHostname(self.hostnameTxtFld.stringValue())
			return True
		except ValueError as e:
			self.runErrorSheet(e.message)
			return False


	def evalManifestSelection(self):
		selection = self.manifestCmbBx.objectValueOfSelectedItem()
		if not selection:
			self.runErrorSheet("You must select a client manifest.")
			return False
		return True


	def evalEnrollConditions(self):
		""" allow user to procede to enroll if hostname and role are valid """
		if self.evalManifestSelection() and self.evalHostName():
			return True
		else:
			return False


	def onManifestSelected(self):
		""" display the role manifest details in the text box when it is selected and note a valid selection has been made """
		selection = self.manifestCmbBx.objectValueOfSelectedItem()
		NSLog("You selected: {}".format(selection))
		if selection:
			p = enroll.pprint(self.availableRoles[selection])
			self.manifestDetailTxtVw.setString_(p)
	

	@objc.signature('v@:')
	def lookupClient(self):
		""" notify the user a client lookup is in progress and begin lookup """
		self.progressIndicator.startAnimation_(self)
		try:
			self.client, self.identifier = enroll.getClient(
				server=self.server,
				headers=self.headers,
				mwa2_user=self.mwa2_user,
				mwa2_pass=self.mwa2_pass,
				path=self.path,
				ext=self.ext
			)
		except Exception as e:
			NSLog("Received error: {}".format(str(e)))
			self.runErrorSheet("Error: {}".format(e))
		else:
			self.progressIndicator.stopAnimation_(self)
			if self.client:
				# the server returned a client, configure the computer with the client info returned
				self.runErrorSheet("Enrolling with existing client manifest in the Munki repo...\nComputer will restart shortly.")
				if 'hostname' in self.client:
					self.hostname = self.client['hostname']
				else:
					self.hostname = self.identifier.split('/')[-1].split('.')[0]
				#give enough time to read status text before proceding
				NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(3.0, self, self.enrollUsingClient, None, False)
			else:
				# no existing clients, make one using the GUI
				self.retryMode = 'roles'
				self.enrollButton.setEnabled_(True)
				self.populateRoles()


	@objc.signature('v@:')
	def enrollUsingClient(self):
		""" set the computer hostname and munki config using the existing client info """
		try:
			enroll.writeClientId(identifier=self.identifier)
		except Exception as e:
			self.runErrorSheet(str(e))
		else:
			try:
				enroll.setHostname(self.hostname)
			except Exception as e:
				self.runErrorSheet(str(e))
			else:
				NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(4.0, self, self.rebootMe, None, False)


	@objc.signature('v@:')
	def rebootMe(self):
		""" remove the enroll app LaunchAgent, set munki to run on startup and reboot """
		try:
			enroll.reboot()
		except Exception as e:
			self.runErrorSheet("Error with final steps before reboot: {}".format(e))


	def enableInputFields(self):
		self.userTxtFld.setEnabled_(True)
		self.hostnameTxtFld.setEnabled_(True)
		self.manifestCmbBx.setEnabled_(True)


	def populateRoles(self):
		""" request a dictionary of role manifests from the enroll server and add them to the combobox"""
		self.progressIndicator.startAnimation_(self)
		try:
			self.availableRoles = enroll.getRoles(
				server=self.server,
				mwa2_user=self.mwa2_user,
				mwa2_pass=self.mwa2_pass,
				headers=self.headers,
				role_dirs=self.role_dirs
			)
			self.manifestCmbBx.addItemsWithObjectValues_(self.availableRoles.keys())
			self.enableInputFields()
		except:
			self.runErrorSheet("Failed to get manifest roles from the server.")
		self.progressIndicator.stopAnimation_(self)
		self.reloadButton.setEnabled_(True)
			

	#
	# refactor me
	#
	def makeEnrollRequest(self):
		self.role = self.manifestCmbBx.objectValueOfSelectedItem()
		self.hostname = self.hostnameTxtFld.stringValue()
		self.user = self.userTxtFld.stringValue()
		try:
			self.identifier = enroll.createClient(
				server=self.server,
				mwa2_user=self.mwa2_user,
				mwa2_pass=self.mwa2_pass,
				headers=self.headers,
				path=self.path,
				ext=self.ext,
				user=self.user,
				hostname=self.hostname,
				role=self.role,
				catalog=self.catalog,
				write_host=self.write_host
			)
			NSLog("\n\n\n{}\n\n\n".format(self.identifier))
		except Exception as e:
			self.runErrorSheet("Enroll failed.\n{}".format(e.message))
			self.resetAndRetryEnroll()
		else:
			NSLog("Enrolled manifest file on server: {}".format(self.identifier))
			NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(2.0, self, self.lookupClient, None, False)


	def updateClient(self):
		NSLog("Client update requested.")
		pass


	def clearRoles(self):
		self.availableRoles = {}
		selection = self.manifestCmbBx.indexOfSelectedItem()
		#if selection:
		self.manifestCmbBx.deselectItemAtIndex_(selection)
		self.manifestCmbBx.removeAllItems()
		self.manifestDetailTxtVw.setString_('')


	def resetAndRetryEnroll(self):
		self.retryMode = 'client'
		self.clearRoles()
		#give enough time to read status text before proceding
		NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(4.0, self, self.initEnrollSession, None, False)


	def isEnrolled(self):
		clientID = enroll.getClientId()
		NSLog("Client Identifier: {}".format(clientID))
		return True if clientID else False


	def controlTextDidEndEditing_(self, notification):
		if notification.object() is self.hostnameTxtFld:
			#NSLog("Hostname changed")
			pass
			#HostName = self.hostnameTxtFld.stringValue()
			#self.evalHostName(HostName)
		else:
			#NSLog("User name changed")
			pass


	@objc.IBAction
	def toggleShowManifestDetail_(self, sender):
		NSLog("Manifest toggle initiated: {}".format(sender))
		NSLog("Button toggle state: {}".format(sender.state()))
		if sender.state() == 1:
			self.enlargeWindow()
		else:
			self.collapseWindow()


	def runErrorSheet(self, error):
		NSLog("runModalForWindow: error")
		self.statusTxtLbl.setStringValue_(error)
		self.statusTxtLbl.sizeToFit()
		NSApp.beginSheet_modalForWindow_modalDelegate_didEndSelector_contextInfo_(
				self.errorWindow, self.window, self, 'didEndSheet:returnCode:contextInfo:', None)


	@objc.IBAction
	def runAuthSheet_(self, sender):
		NSLog("runModalForWindow: auth")
		NSApp.beginSheet_modalForWindow_modalDelegate_didEndSelector_contextInfo_(
				self.authSheetWindow, self.window, self, 'didEndSheet:returnCode:contextInfo:', None)


	@objc.IBAction
	def dismissErrorSheet_(self, sender):
		NSApp.endSheet_(sender.window())
	
	
	@objc.IBAction
	def dismissAuthSheet_(self, sender):
		NSApp.endSheet_(sender.window())


	@objc.signature('v@:@ii')
	def didEndSheet_returnCode_contextInfo_(self, sheet, returnCode, contextInfo):
		# Dismiss the sheet
		sheet.orderOut_(self)
	
	
	@objc.IBAction
	def onCmbBxChange_(self, sender):
		NSLog("ComboBox changed")
		self.onManifestSelected()
	
	
	@objc.IBAction
	def reload_(self, sender):
		NSLog("Reload button clicked")
		self.reloadButton.setEnabled_(False)
		self.clearRoles()
		self.lookupClient()
	
	
	@objc.IBAction
	def enroll_(self, sender):
		NSLog("Enroll button clicked")
		if self.appMode == 'enroll':
			if self.evalEnrollConditions():
				#pass
				self.lockdownButtons()
				self.makeEnrollRequest()
		else:
			self.updateClient()


	def lockdownButtons(self):
		self.userTxtFld.setEnabled_(False)
		self.hostnameTxtFld.setEnabled_(False)
		self.manifestCmbBx.setEnabled_(False)
		self.enrollButton.setEnabled_(False)
		self.reloadButton.setEnabled_(False)


	@objc.signature('v@:')
	def initEnrollSession(self):
		NSLog("enroll session called")
		if self.progressIndicator:
			NSLog("progress indicator present")
			self.progressIndicator.setUsesThreadedAnimation_(True)
			self.progressIndicator.setDisplayedWhenStopped_(False)
		# lock down interface while checking for client on the server
		self.lockdownButtons()
		self.lookupClient()


	def disableClose(self):
		closeButton = self.window.standardWindowButton_(NSWindowCloseButton)
		closeButton.setEnabled_(False)


	def startApp(self):
		self.window.setTitle_("Munki Enroll")
		self.collapseWindow()
		if not self.userLoggedIn():
			self.disableClose()
			self.bringFrontCenter()
			self.credentialsButton.setHidden_(True)
		else:
			self.authSheetLoginButton.setEnabled_(True)
		self.getAppPrefs()
		if self.isEnrolled():
			self.enrollButton.setTitle_("Update")
			self.appMode = 'update'
		else:
			self.initEnrollSession()