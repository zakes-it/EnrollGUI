# -*- coding: utf-8 -*-
#
#  MyWindowController.py
#  EnrollGui
#
#  Created by mike on 10/26/15.
#  Copyright (c) 2015 PowerHouse. All rights reserved.
#
"""Controller for the main window"""

from objc import YES, NO, IBAction, IBOutlet, nil
from PyObjCTools import AppHelper
from Foundation import *
from AppKit import *
from SystemConfiguration import SCDynamicStoreCopyConsoleUser

from time import sleep

import enroll, sys, os


class CustomWindow(NSWindow):
	"""this is here so the window can become active"""
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
	clearIdButton = objc.IBOutlet()
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
	
	# set enroll prefs not handled in munki.getAppPrefs
	serial = enroll.getSerial()
	identifier = None
	defaults = enroll.Defaults(enroll.bundle_id)
	client_id = enroll.ClientId()
	
	
	def awakeFromNib(self):
		NSLog("awoke from nib")
	
	
	def enlargeWindow(self):
		"""expand app window to show manifest info"""
		#		NSLog("Main window size: {}".format(self.window.frame().size))
		winRect = self.window.frame()
		winRect.size.height = 480
		winRect.origin.y = winRect.origin.y - 256
		#		NSLog("Setting new main window size: {}".format(winRect))
		self.window.setFrame_display_(winRect, True)
	
	
	def collapseWindow(self):
		"""collapse app window to hide manifest info"""
		#		NSLog("Main window size: {}".format(self.window.frame().size))
		winRect = self.window.frame()
		winRect.size.height = 180
		winRect.origin.y = winRect.origin.y + (
				self.window.frame().size.height - 180 )
				#		NSLog("Setting new main window size: {}".format(winRect))
		self.window.setFrame_display_(winRect, True)
	
	
	def userLoggedIn(self):
		"""return true if a user is logged in to the console, else false"""
		cfuser = SCDynamicStoreCopyConsoleUser(None, None, None)
		if cfuser[0] == 'loginwindow' or cfuser[0] == None:
			NSLog("No user logged in.")
			return False
		NSLog("{} is logged in and running the app.".format(cfuser[0]))
		return True


	def check_admin_needed(self):
		if self.defaults.getPref('secure_munki_plist'):
			if os.geteuid() != 0:
				return True
		return False


	def bringFrontCenter(self):
		"""bring the app to the front so it shows over the login window """
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

	
	def evalHostName(self):
		"""display an error message if the hostname is invalid"""
		try:
			enroll.checkHostname(self.hostnameTxtFld.stringValue())
			return True
		except ValueError as e:
			self.runErrorSheet(e.message)
			return False


	def evalManifestSelection(self):
		"""display an error message if a manifest is not selected"""
		selection = self.manifestCmbBx.objectValueOfSelectedItem()
		if not selection:
			self.runErrorSheet("You must select a client manifest.")
			return False
		return True


	def evalEnrollConditions(self):
		"""allow user to procede with enroll if hostname and role are valid"""
		if self.evalManifestSelection() and self.evalHostName():
			return True
		else:
			return False


	def onManifestSelected(self):
		"""
		display the role manifest details in the text box when it is selected
		and note a valid selection has been made
		"""
		selection = self.manifestCmbBx.objectValueOfSelectedItem()
		NSLog("You selected: {}".format(selection))
		if selection:
			p = enroll.pprint(self.availableRoles[selection])
			self.manifestDetailTxtVw.setString_(p)
	

	@objc.signature('v@:')
	def lookupClient(self):
		"""notify the user a client lookup is in progress and begin lookup"""
		self.progressIndicator.startAnimation_(self)
		try:
			path = self.defaults.getPref('path')
			ext = self.defaults.getPref('ext')
			self.client, self.identifier = self.server.getClient(path=path, ext=ext)
		except Exception as e:
			NSLog("Received error: {}".format(str(e)))
			self.runErrorSheet("Error: {}".format(e))
		else:
			self.progressIndicator.stopAnimation_(self)
			if self.client and (self.appMode == 'enroll'):
				# the server returned a client, configure the computer with the
				# client info returned
				self.runErrorSheet("Client manifest matching serial found in"
								   " the Munki repo.\nSetting client ID locally"
								   " to complete enroll.")
				# give enough time to read status text before proceding
				NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
					3.0, self, self.completeClientEnroll, None, False)
			elif self.client and (self.appMode == 'update'):
				self.hostnameTxtFld.setStringValue_(enroll.getCurrentHostname())
				self.enrollButton.setEnabled_(True)
				self.populateRoles()
			else:
				# no existing clients, make one using the GUI
				self.hostnameTxtFld.setStringValue_(enroll.getCurrentHostname())
				self.retryMode = 'roles'
				self.enrollButton.setEnabled_(True)
				self.populateRoles()


	@objc.signature('v@:')
	def completeClientEnroll(self):
		"""
		set the computer hostname and munki config using the client info from  
		the computer manifest
		"""
		try:
			self.client_id.write(identifier=self.identifier)
			if 'display_name' in self.client:
				enroll.setHostname(self.client['display_name'])
			else:
				enroll.setHostname(self.identifier.split('/')[-1].split('.')[0])
			NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
					4.0, self, self.closeOut, None, False)
		except Exception as e:
			self.runErrorSheet(str(e))


	@objc.signature('v@:')
	def closeOut(self):
		"""
		remove the enroll app LaunchAgent and set munki to run on startup
		"""
		try:
			enroll.removeLaunchAgent()
		except Exception as e:
			self.runErrorSheet("Error removing EnrollGUI launch agent.".format(e))
		if self.defaults.getPref('munki_installatstartup'):
			try: enroll.runMunki()
			except Exception as e:
				self.runErrorSheet("Error setting Munki to start at login.".format(e))


	def enableInputFields(self):
		self.userTxtFld.setEnabled_(True)
		self.hostnameTxtFld.setEnabled_(True)
		self.manifestCmbBx.setEnabled_(True)


	def populateRoles(self):
		"""
		request a dictionary of role manifests from the enroll server and add 
		them to the manifest selection combobox
		"""
		self.progressIndicator.startAnimation_(self)
		try:
			role_dirs = self.defaults.getPref('role_dirs')
			self.availableRoles = self.server.getRoles(role_dirs=role_dirs)
			self.manifestCmbBx.addItemsWithObjectValues_(self.availableRoles.keys())
			self.enableInputFields()
		except Exception as e:
			self.runErrorSheet(str(e))
		self.progressIndicator.stopAnimation_(self)
		self.reloadButton.setEnabled_(True)
			

	#
	# refactor me
	#
	def makeEnrollRequest(self):
		try:
			path = self.defaults.getPref('path')
			ext = self.defaults.getPref('ext')
			catalog = self.defaults.getPref('catalog')
			write_host = self.defaults.getPref('write_host')
			self.identifier = self.server.createClient(
				path=path,
				ext=ext,
				user=self.userTxtFld.stringValue(),
				hostname=self.hostnameTxtFld.stringValue(),
				role=self.manifestCmbBx.objectValueOfSelectedItem(),
				catalog=catalog,
				write_host=write_host
			)
			NSLog("\n\n\n{}\n\n\n".format(self.identifier))
		except Exception as e:
			self.runErrorSheet("Enroll failed.\n{}".format(e.message))
			self.resetAndRetryEnroll()
		else:
			NSLog("Enrolled manifest file on server: {}".format(self.identifier))
			NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
					2.0, self, self.lookupClient, None, False)


	def updateClient(self):
		NSLog("Client update requested.")
		hostname = self.hostnameTxtFld.stringValue()
		user = self.userTxtFld.stringValue()
		path = self.defaults.getPref('path')
		ext = self.defaults.getPref('ext')
		try:
			self.identifier = self.server.updateClient(
				path=path,
				ext=ext,
				user=user,
				hostname=hostname
			)
		except Exception as e:
			self.runErrorSheet("Client update failed.\n{}".format(e.message))
			self.resetAndRetryEnroll()
		else:
			if hostname:
				enroll.setHostname(hostname)
			self.runErrorSheet("Client update succeded.\n")
			

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
		NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
				4.0, self, self.initEnrollSession, None, False)


	def isEnrolled(self):
		c_id = self.client_id.get()
		NSLog("Client Identifier: {}".format(c_id))
		return True if c_id else False


	def controlTextDidEndEditing_(self, notification):
		"""Useful for live evaluation of text fields"""
		if notification.object() is self.hostnameTxtFld:
			#NSLog("Hostname changed")
			pass
			#HostName = self.hostnameTxtFld.stringValue()
			#self.evalHostName(HostName)
		else:
			NSLog("User name changed")
			#pass


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
		self.userTxtFld.resignFirstResponder()
		if self.appMode == 'enroll':
			if self.evalEnrollConditions():
				self.lockdownButtons()
				self.makeEnrollRequest()
		else:
			if self.hostnameTxtFld.stringValue():
				if not self.evalHostName():
					return
			self.updateClient()


	@objc.IBAction
	def clearId_(self, sender):
		NSLog("Clear ID button clicked")
		self.clearIdButton.setEnabled_(False)
		self.client_id.remove()
		self.appMode = 'enroll'
		self.runErrorSheet("Client Identifier cleared.\n")
	
	
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


	def setupServer(self):
		NSLog("Setting up server instance...")
		uri = self.defaults.getPref('server')
		headers = self.defaults.getPref('headers')
		apisrv = enroll.MWA2API(uri=uri, headers=headers)
		user = self.defaults.getPref('mwa2_user')
		passw = self.defaults.getPref('mwa2_pass')
		apisrv.setAuth(user=user, passw=passw)
		self.server = enroll.MWA2Server()
		self.server.setAPI(apisrv)
		NSLog("Server instance setup done.")


	def startApp(self):
		self.window.setTitle_("Munki Enroll")
		self.collapseWindow()
		if not self.userLoggedIn():
			self.disableClose()
			self.bringFrontCenter()
			self.credentialsButton.setHidden_(True)
			self.clearIdButton.setHidden_(True)
		else:
			self.authSheetLoginButton.setEnabled_(True)
		self.systemSerialLbl.setStringValue_(self.serial)
		if self.check_admin_needed():
			self.lockdownButtons()
			self.runErrorSheet("Please run this app with root permissions.")
		else:
			self.setupServer()
			if self.isEnrolled():
				self.clearIdButton.setHidden_(False)
				self.enrollButton.setTitle_("Update")
				self.appMode = 'update'
				self.clearIdButton.setEnabled_(True)
			else:
				self.clearIdButton.setEnabled_(False)
			self.initEnrollSession()
