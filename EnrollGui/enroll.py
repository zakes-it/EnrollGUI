#! /usr/bin/env python

"""
enroll
Created by Michael Zakes on 2008-11-18.
Functions and script for enrolling a client computer with a Munki Web Admin 2
(MWA2) server from the command line or a GUI app.
"""

# TODO:
# -add more items to this list

import argparse
import subprocess
import os
import sys
import re
import json
import getpass
import time
from urlparse import urljoin

import logging
# !!!!!!! DEBUG level logging prints passwords to stdout in plaintext!!!!!!!!!
logging.basicConfig(
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
	level=logging.WARNING)

logging.debug('Importing requests from vendor dir...')
# Add vendor directory to module search path
parent_dir = os.path.abspath(os.path.dirname(__file__))
vendor_dir = os.path.join(parent_dir, 'vendor')
sys.path.append(vendor_dir)
import requests
import warnings
# add munki library module
# requires munki to be installed
# https://github.com/munki/munki
munkiDir = '/usr/local/munki'
logging.debug('Importing munkilib from munki install path: {}'.format(munkiDir))
sys.path.append(munkiDir)
import munkilib.munkicommon


version = '0.3'
bundle_id = 'MunkiEnrollGUI'
app_plist = munkilib.munkicommon.Preferences(bundle_id)
# define subcommands for cli subparser
sub_help = {
	'get-client': 'request a client manifest from a MWA2 server',
	'get-roles': 'request a list of available roles from a MWA2 server',
	'create': 'create a new client mainfest using the MWA2 api',
	'update': 'update client manifest on the Munki server'
}
# define application function arguments to be used with thecli and GUI when
# making function calls
class Defaults(object):
	arguments  = {
		#cli arguments
		'server': {
			'parser_flags': ('-s', '--server'),
			'parser_kwargs': {
				'help': 'the URL of your mwa2 api server',
				'dest': 'server',
				'required': False},
			'key': 'MWA2_ServerURL',
			'default': 'http://localhost:8080' },
		'headers': {
			'parser_flags': ('-a', '--additional-headers'),
			'parser_kwargs': {
				'help': 'additional http headers needed for mwa2 api calls',
						'dest': 'headers',
				'required': False},
				'key': 'MWA2_AdditionalHttpHeaders',
				'default': {} },
		'mwa2_user': {
			'parser_flags': ('-u', '--mwa2-username'),
			'parser_kwargs': {
				'help': 'username for mwa2 api calls',
					'dest': 'mwa2_user',
					'required': False},
				'key': 'MWA2_Username',
				'default': 'test' },
		'mwa2_pass': {
			'parser_flags': ('-p', '--mwa2-password'),
			'parser_kwargs': {
				'help': 'password for mwa2 api calls, read from stdin if '
						'not provided',
				'dest': 'mwa2_pass',
				'required': False},
			'key': 'MWA2_Password',
			'default': '' },
		'path': {
			'parser_flags': ('-P', '--clients-path'),
			'parser_kwargs': {
				'help': 'relative directory path to client manifest files '
						'on the munki repo',
				'dest': 'path',
				'required': False},
			'key': 'RepoClientsPath',
			'default': 'clients' },
		'user': {
			'parser_flags': ('-U', '--user'),
			'parser_kwargs': {
				'help': 'value for client manifest username key',
				'dest': 'user',
				'required': False},
			'default': None },
		'hostname': {
			'parser_flags': ('-n', '--hostname'),
			'parser_kwargs': {
				'help': 'the client hostname',
				'dest': 'hostname',
				'required': True} },
		'ext': {
			'parser_flags': ('-e', '--extension'),
			'parser_kwargs': {
				'help': 'client manifest filename extension',
				'dest': 'ext',
				'required': False},
			'key': 'ClientFilenameExtension',
			'default': '.plist' },
		'role': {
			'parser_flags': ('-r', '--role'),
			'parser_kwargs': {
				'help': 'inclided manifest file the client should use for '
						'software updates',
				'dest': 'role',
				'required': True} },
		'catalog': {
			'parser_flags': ('-c', '--catalog'),
			'parser_kwargs': {
				'help': 'catalog for the client manifest',
				'dest': 'catalog',
				'required': False},
			'key': 'ClientCatalog',
			'default': 'production' },
		'role_dirs': {
			'parser_flags': ('-r', '--role-directories'),
			'parser_kwargs': {
				'help': 'list of relative paths to manifests suitable for '
				'use as "included manifests"',
				'dest': 'role_dirs',
				'required': False},
			'key': 'RepoIncludedManifestsPaths',
			'default': ['roles'] },
		'write_host': {
			'parser_flags': ('-H', '--write-hostname'),
			'parser_kwargs': {
				'help': 'write the client hostname to the client manifest '
						'file',
				'dest': 'write_host',
				'action': 'store_true'},
			'key': 'WriteHostnameToManifest',
			'default': True },
		# GUI use only
		'secure_munki_plist': {
			'key': 'UseSecureMunkiPlist',
			'default': True },
		'munki_installatstartup': {
			'key': 'RunMunkiAfterEnroll',
			'default': True
		}}

	def __init__(self, bundle_id):
		self.app_plist = munkilib.munkicommon.Preferences(bundle_id)
		
	def getPref(self, pref):
		"""
		Return a preference value. Checks the application plist first, then
		falls back to internal defaults.
		"""
		logging.debug("Looking up missing argument from application preferences: "
						"{}".format(pref))
		return self.app_plist.get(
			self.arguments[pref]['key'], default=self.arguments[pref]['default'])
	
	def getFlag(self, arg):
		return self.arguments[arg]['parser_flags']
		
	def getKwargs(self, arg):
		return self.arguments[arg]['parser_kwargs']
		
	def getKeys(self):
		return self.arguments.keys()


errors = {
	11: ( 'input error',
		'Required variable was not provided: {}'),
	21: ( 'hostname error',
		'Hostname is too short.'),
	22: ( 'hostname error',
		'Hostname too long. DNS hostnames must be 15 characters or less.'),
	23: ( 'hostname error',
		'Hostname contains illegal character. Use alphanumerics and hyphens'
		'only.'),
	31: ( 'server error',
		'Server rejected the connection. Make sure the MWA2 service is'
		'running.'),
	32: ( 'server error',
		'Server request unauthorized. Check username and password.'),
	33: ( 'server error',
		'Client manifest creation request failed. The requested manifest alredy'
		'exists.'),
	34: ( 'update error',
		 'You are trying to update a client that does not exist on the'
		 'server.'),
	41: ( 'network error',
		'Error sending the request to the server: {}'),
	42: ( 'network error',
		 'Server connection timeout{}'),
	51: ( 'rename error',
		'Error setting hostname: {}')
}


class EnrollException(Exception):
	"""
	app specific exception
	"""
	pass


class ClientId(object):
	defaults = Defaults(bundle_id)
	
	def __init__(self):
		if self.defaults.getPref('secure_munki_plist'):
			self.plist = munkilib.munkicommon.SecureManagedInstallsPreferences()
		else:
			self.plist = munkilib.munkicommon.ManagedInstallsPreferences()

	def get(self):
		"""
		Read client identifier string from munki plist if it exists
		"""
		return self.plist['ClientIdentifier']

	def write(self, identifier):
		"""
		Write the client manifest path to the ClientIdentifier key in the munki
		configuration file.
		"""
		logging.debug("Writing {} to {}".format(identifier, self.plist))
		self.plist['ClientIdentifier'] = identifier

	def remove(self):
		"""
		Clear the client identifier from the managed installs plist
		"""
		del self.plist['ClientIdentifier']


class MWA2API(object):
	"""
	wrapper for API HTTP calls that handles logging and errors
	"""
	def __init__(self, uri, headers=None):
		self.baseuri = urljoin(uri, 'api/manifests/')
		self.headers = headers
	
	def setAuth(self, user, passw):
		self.auth = (user,passw)
		
	def get(self, path, params=None):
		"""
		Make a GET request for the manifest resource at the given path on the 
		server returning the result as JSON or None if the resource does not 
		exist
		"""
		fulluri = urljoin(self.baseuri, path)
		try:
			# ignore cert errors
			with warnings.catch_warnings():
				warnings.simplefilter("ignore")
				request = requests.get(fulluri, auth=self.auth,
									headers=self.headers, params=params)
		except requests.exceptions.Timeout:
			logging.error("Server connection timeout")
			onError(42,'')
		except requests.exceptions.RequestException as e:
			logging.error("Server connection error: {}".format(e))
			onError(41, e)
		except Exception as e:
			raise EnrollException("Server GET error: {}".format(e))
		if request.status_code == 200:
			logging.debug("Got response from server: {}".format(request.json()))
			return request.json()
		elif request.status_code == 404:
			return None
		elif request.status_code == 401:
			logging.error("Server returned HTTP 401 unauthorized.")
			onError(32)
		
	def post(self, path, json):
		"""
		Makes a JSON POST request to the manifest at the given path on the api 
		server, returning the result as JSON or None if the resource does not 
		exist
		"""
		fulluri = urljoin(self.baseuri, path)
		try:
			request = requests.post(fulluri, auth=self.auth, 
									headers=self.headers, json=json)
		except requests.exceptions.Timeout:
			logging.error("Server connection timeout")
			onError(42,'')
		except requests.exceptions.RequestException as e:
			logging.error("Server connection error: {}".format(e))
			onError(41, e)
		if request.status_code == 200 or request.status_code == 201:
			logging.debug("Server post successful: {}".format(request.json()))
			return request.json()
		elif request.status_code == 401:
			logging.error("Server returned HTTP 401 unauthorized.")
			onError(32)
		elif request.status_code == 409:
			logging.error("Server returned HTTP 409 resource conflict.")
			onError(33)
		return None
		
	def put(self, path, json):
		fulluri = urljoin(self.baseuri, path)
		try:
			request = requests.put(fulluri, auth=self.auth,
									headers=self.headers, json=json)
		except requests.exceptions.Timeout:
			logging.error("Server connection timeout")
			onError(42,'')
		except requests.exceptions.RequestException as e:
			logging.error("Server connection error: {}".format(e))
			onError(41, e)
		if request.status_code == 200 or request.status_code == 201:
			logging.debug("Server post successful: {}".format(request.json()))
			return request.json()
		elif request.status_code == 401:
			logging.error("Server returned HTTP 401 unauthorized.")
			onError(32)
		return None


class MWA2Server(object):
	"""
	Server wrapper for interracting with client manifests
	"""
	# can't use __init__ here because we have to declare a server instance before we get our client variables
	def setAPI(self, api):
		self.api = api
		
	def getClient(self, path, ext):
		"""
		Requests a client manifest from the given path on a MWA2 server using the
		current Mac's serial and the provided file extension
		"""
		logging.debug('getClient args: {}'.format(locals()))
		serial = getSerial()
		file_name = serial + ext
		logging.debug("Looking for client with filename: {}".format(file_name))
		request = self.api.get(path=urljoin(path,file_name))
		if request is not None:
			if __name__ == "__main__":
				pprint({path + file_name:request})
			return request, path + file_name
		logging.info("Client matching filename not found on server.")
		return None, None

	def getRoles(self, role_dirs):
		"""
		Returns all the manifests matching the path filters defined in the 
		'RepoIncludedManifestPaths' array on a MWA2 server.
		"""
		logging.debug('getRoles args: {}'.format(locals()))
		roles = {}
		request = self.api.get(path='',params={'api_fields': 'filename'})
		if request is None:
			raise EnrollException("Failed to retreive roles from server.")
		else:
			logging.debug("Received roles from server: {}".format(request))
			matches = [i['filename'] for i in request if any(
				[True for filter in role_dirs if i['filename'].startswith(filter)])]
			logging.debug("Manifests matching config path filters: "
							"{}".format(matches))
			for manifest_file in matches:
				logging.debug("Requesting role manifest from the server: "
								"{}".format(manifest_file))
				roles[manifest_file] = self.api.get(path=manifest_file)
			
		if __name__ == "__main__":
			pprint(roles)
		return roles

	def createClient(self, path, ext, user, hostname, role, catalog, write_host):
		"""Creates a new client manifest on a MWA2 server."""
		logging.debug('createClient args: {}'.format(locals()))
		serial = getSerial()
		file_name = serial + ext
		data = {
			'catalogs': [catalog],
			'included_manifests': [role],
			'managed_installs': [],
			'managed_uninstalls': [],
			'managed_updates': [],
			'optional_installs': []
		}
		if user:
			data['user'] = user
		if write_host:
			data['display_name'] = hostname
		full_path = path + '/' + file_name
		if self.api.post(path=full_path, json=data):
			return path + file_name
		return None

	def updateClient(self, path, ext, user=None, hostname=None):
		"""
		Updates hostname or username fields for a client manifest on a MWA2
		server.
		"""
		logging.debug('updateClient args: {}'.format(locals()))
		client = self.getClient(path=path, ext=ext)
		if not client[0]:
			onError(34)
		data = client[0]
		if user:
			data["user"] = user
		if hostname:
			data["display_name"] = hostname
		logging.debug("New client keys: {}".format(data))
		print "about to post updated client to server"
		client_id = ClientId()
		request = self.api.put(path=client_id.get(), json=data)
		print "client update completed"
		return request


def onError(errorNum, var=None):
	"""
	Error handler. Log the error and exit if called from the command line or
	raise an exception if used as an import
	"""
	if __name__ == '__main__':
		if var:
			logging.error(errors[errorNum][1].format(var))
		else:
			logging.error(errors[errorNum][1])
		sys.exit(errorNum)
	
	if 10 < errorNum < 20:
		raise InputError(errors[errorNum][1].format(var))
	elif 20 < errorNum < 30:
		raise ValueError(errors[errorNum][1])
	elif 30 < errorNum < 40:
		raise EnrollException(errors[errorNum][1])
	elif 40 < errorNum < 50:
		raise EnrollException(errors[errorNum][1].format(var))
	elif 50 < errorNum < 60:
		raise EnrollException(errors[errorNum][1].format(var))


def prepFunctionArgs(args, defaults, server):
	"""
	fills in missing arguments from defaults where needed and uses those to
	set up the server instance passed in to start making API calls. Returns
	the function defined in the argparse vars and arguments to be sent to that function
	"""
	func = args.pop('func')
	passw = args.pop('mwa2_pass')
	for key, value in args.items():
		if key == 'hostname':
			checkHostname(value)
		if value is None and key not in ('user'):
			args[key] = defaults.getPref(key)
	if passw is None:
		if args['mwa2_user'] == defaults.getPref('mwa2_user'):
			passw = defaults.getPref('mwa2_pass')
		elif __name__ == '__main__':
			passw = getpass.getpass()
		else:
			raise InputError("No API server connection password provided.")
	apisrv = MWA2API(uri=args.pop('server'), headers=args.pop('headers'))
	apisrv.setAuth(user=args.pop('mwa2_user'), passw=passw)
	server.setAPI(apisrv)
	return args, func


def getSerial():
	"""
	Return the system serial number
	"""
	serial = munkilib.munkicommon.getMachineFacts()['serial_number']
	logging.info('Read system Serial: {}'.format(serial))
	return serial


def getCurrentHostname():
	"""
	Return the hostname the computer is currently using
	"""
	currentHostname = munkilib.munkicommon.getMachineFacts()['hostname']
	logging.info('Current system hostname: {}'.format(currentHostname))
	return currentHostname


# Hostname renaming should now be handled by imagr
def checkHostname(hostname):
	"""
	Raises an error if the hostname does not meet DNS spec
	"""
	if len(hostname) < 3:
		onError(21)
	elif len(hostname) > 16:
		onError(22)
	elif not re.match(r'[a-zA-Z0-9][a-zA-Z0-9\-]+[a-zA-Z0-9]$',hostname):
		onError(23)


def pprint(data):
	"""
	Pretty prints a formatted json string with indentation and sorted keys.
	"""
	pretty = json.dumps(data,sort_keys=True,indent=4)
	if __name__ == '__main__':
		print(pretty)
	else:
		return(pretty)




# Library function for GUI
def setHostname(hostname):
	"""Sets the computer hostname across all available fields"""
	for i in ('HostName', 'LocalHostName', 'ComputerName'):
		logging.info('Setting {} to "{}"...'.format(i, hostname))
		try:
			subprocess.call(['/usr/sbin/scutil', '--set', i, hostname])
		except subprocess.CalledProcessError as e:
			logging.error("Rename subprocess error:\n{}".format(e))
			onError(51, i)


# Library function for GUI
def removeLaunchAgent():
	"""
	Removes the launch agent that runs the EnrollGUI app at boot.
	"""
	try:
		os.remove('/Library/LaunchAgents/com.company.munki.EnrollGUI.plist')
	except:
		pass
	

# Library function for GUI
def runMunki():
	"""
	Removes the EnrollGUI launch agent, configures munki to run an update check
	at the next boot, blocking login and restarts the computer immediately.
	"""
	f = open('/Users/Shared/.com.googlecode.munki.checkandinstallatstartup', 'w')
	f.close()
	time.sleep(5)


# 	system reboot not needed to run munki from loginwindow
def rebootMe():
	dummy_retcode = subprocess.call(['/sbin/shutdown', '-r', 'now'])

	
def handleArguments():
	"""
	Parse command line arguments and execute the function defined in the 
	sub-command verb.
	"""
	server = MWA2Server()
	defaults = Defaults(bundle_id)
	parser_args = {
		'get-client': ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'ext', 'path'),
		'get-roles': ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'role_dirs'),
		'create': ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'ext', 'path', 
				'role', 'hostname', 'user', 'catalog', 'write_host'),
		'update': ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'user', 
				'hostname', 'path', 'ext') }
	parser = argparse.ArgumentParser(
		description="""Enroll a computer with a munki server or update existing 
			system information on the server.""")
	subparsers = parser.add_subparsers(help='sub-command help')
	parser.add_argument('-v', '--version',
						action='version',
						version='%(prog)s ' + version)
	
	client_parser = subparsers.add_parser('get-client', help=sub_help['get-client'])
	for arg in parser_args['get-client']:
		client_parser.add_argument(*defaults.getFlag(arg),
								**defaults.getKwargs(arg))
	client_parser.set_defaults(func=server.getClient)
	
	role_parser = subparsers.add_parser('get-roles', help=sub_help['get-roles'])
	for arg in parser_args['get-roles']:
		role_parser.add_argument(*defaults.getFlag(arg),
								**defaults.getKwargs(arg))
	role_parser.set_defaults(func=server.getRoles)
	
	create_parser = subparsers.add_parser('create', help=sub_help['create'])
	for arg in parser_args['create']:
		create_parser.add_argument(*defaults.getFlag(arg),
								**defaults.getKwargs(arg))
	create_parser.set_defaults(func=server.createClient)
	
	update_parser = subparsers.add_parser('update', help=sub_help['update'])
	for arg in parser_args['update']:
		update_parser.add_argument(*defaults.getFlag(arg),
								**defaults.getKwargs(arg))
	update_parser.set_defaults(func=server.updateClient)
	
	args, func = prepFunctionArgs(vars(parser.parse_args()), defaults, server)
	logging.debug("about to call server function {} with args: {}".format(func,args))
	func(**args)


def main():
	"""
	Run as a command line program
	"""
	handleArguments()


if __name__ == "__main__":
	main()
