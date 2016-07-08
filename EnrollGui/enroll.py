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
import base64
import getpass
import time

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

# add munki library module
# requires munki to be installed
# https://github.com/munki/munki
munkiDir = '/usr/local/munki'
logging.debug('Importing munkilib from munki install path: {}'.format(munkiDir))
sys.path.append(munkiDir)
import munkilib.munkicommon


version = '0.1'
bundle_id = 'MunkiEnrollGUI'
app_plist = munkilib.munkicommon.Preferences(bundle_id)
# define subcommands for cli subparser
sub_help = {
	'get-client': 'request a client manifest from a MWA2 server',
	'get-roles': 'request a list of available roles from a MWA2 server',
	'create': 'create a new client mainfest using the MWA2 api',
	'update': 'update client manifest on the Munki server'
}
# define application function arguments to be used with the
# cli and GUI when making function calls
arguments = {
	#cli arguments
	'server': {
		'parser_flags': ('-s', '--server'),
		'parser_kwargs': {
			'help': 'the URL of your mwa2 api server',
			'dest': 'server',
			'required': True},
		'key': 'MWA2_ServerURL',
		'default': 'http://localhost:8080/api/manifests'
	},
	'headers': {
		'parser_flags': ('-a', '--additional-headers'),
		'parser_kwargs': {
			'help': 'additional http headers needed for mwa2 api calls',
			'dest': 'headers',
			'required': False},
		'key': 'MWA2_AdditionalHttpHeaders',
		'default': {}
	},
	'mwa2_user': {
		'parser_flags': ('-u', '--mwa2-username'),
		'parser_kwargs': {
			'help': 'username for mwa2 api calls',
			'dest': 'mwa2_user',
			'required': True},
		'key': 'MWA2_Username',
		'default': 'test'
	},
	'mwa2_pass': {
		'parser_flags': ('-p', '--mwa2-password'),
		'parser_kwargs': {
			'help': 'password for mwa2 api calls, read from stdin if not'
					'provided',
			'dest': 'mwa2_pass',
			'required': False},
		'key': 'MWA2_Password',
		'default': ''
	},
	'path': {
		'parser_flags': ('-P', '--clients-path'),
		'parser_kwargs': {
			'help': 'relative directory path to client manifest files on the'
					'munki repo',
			'dest': 'path',
			'required': False},
		'key': 'RepoClientsPath',
		'default': 'clients/'
	},
	'user': {
		'parser_flags': ('-U', '--user'),
		'parser_kwargs': {
			'help': 'value for client manifest username key',
			'dest': 'user',
			'required': False},
		'default': None
	},
	'hostname': {
		'parser_flags': ('-n', '--hostname'),
		'parser_kwargs': {
			'help': 'the client hostname',
			'dest': 'hostname',
			'required': True}
	},
	'ext': {
		'parser_flags': ('-e', '--extension'),
		'parser_kwargs': {
			'help': 'client manifest filename extension',
			'dest': 'ext',
			'required': False},
		'key': 'ClientFilenameExtension',
		'default': '.plist'
	},
	'role': {
		'parser_flags': ('-r', '--role'),
		'parser_kwargs': {
			'help': 'inclided manifest file the client should use for software'
					'updates',
			'dest': 'role',
			'required': True}
	},
	'catalog': {
		'parser_flags': ('-c', '--catalog'),
		'parser_kwargs': {
			'help': 'default catalog for the client manifest',
			'dest': 'catalog',
			'required': False},
		'key': 'ClientCatalog',
		'default': 'production'
	},
	'role_dirs': {
		'parser_flags': ('-r', '--role-directories'),
		'parser_kwargs': {
			'help': 'list of relative paths to manifests suitable for use as'
					'"included manifests"',
			'dest': 'role_dirs',
			'required': False},
		'key': 'RepoIncludedManifestsPaths',
		'default': ['roles/']
	},
	'write_host': {
		'parser_flags': ('-H', '--write-hostname'),
		'parser_kwargs': {
			'help': 'write the client hostname to the client manifest file',
			'dest': 'write_host',
			'action': 'store_true'},
		'key': 'WriteHostnameToManifest',
		'default': True
	},
	# GUI use only
	'secure_munki_plist': {
		'key': 'UseSecureMunkiPlist',
		'default': True
	},
	'munki_installatstartup': {
		'key': 'RunMunkiAfterEnroll',
		'default': True
	}
}

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
	51: ( 'rename error',
		'Error setting hostname: {}')
}


class EnrollException(Exception):
	pass


def onError(errorNum, var=None):
	"""Error handler"""
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


def getPreference(pref):
	"""
	Return a preference value. Checks the application plist first, then
	falls back to internal defaults.
	"""
	logging.debug("Looking up missing argument from application preferences: "
					"{}".format(pref))
	if pref == 'mwa2_pass' and __name__ == '__main__':
		return getpass.getpass()
	return app_plist.get(
		arguments[pref]['key'], default=arguments[pref]['default'])


def getSerial():
	"""Return the system serial number"""
	serial = munkilib.munkicommon.getMachineFacts()['serial_number']
	logging.info('Read system Serial: {}'.format(serial))
	return serial


def getCurrentHostname():
	"""Return the hostname the computer is currently using"""
	currentHostname = munkilib.munkicommon.getMachineFacts()['hostname']
	logging.info('Current system hostname: {}'.format(currentHostname))
	return currentHostname


def checkHostname(hostname):
	"""Raises an error if the hostname does not meet DNS spec"""
	if len(hostname) < 3:
		onError(21)
	elif len(hostname) > 16:
		onError(22)
	elif not re.match(r'[a-zA-Z0-9][a-zA-Z0-9\-]+[a-zA-Z0-9]$',hostname):
		onError(23)


def pprint(j):
	"""
	Pretty prints a formatted json string with indentation and sorted keys.
	"""
	pretty = json.dumps(j,sort_keys=True,indent=4)
	if __name__ == '__main__':
		print(pretty)
	else:
		return(pretty)


def serverGet(uri, auth, headers, params=None):
	"""
	Make a GET request against a mwa2 server returning the result as JSON or
	None
	"""
	try:
		request = requests.get(uri, auth=auth, headers=headers, params=params)
	except requests.exceptions.RequestException as e:
		logging.error("Server connection error: {}".format(e))
		onError(41, e)
	if request.status_code == 200:
		logging.debug("Got client from the server: {}".format(request.json()))
		return request.json()
	elif request.status_code == 404:
		return None
	elif request.status_code == 401:
		logging.error("Server returned HTTP 401 unauthorized.")
		onError(32)


def serverPost(uri, auth, headers, json):
	"""
	Make a POST request against a mwa2 server returning the result as JSON or
	None
	"""
	try:
		request = requests.post(uri, auth=auth, headers=headers, json=json)
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


def serverPatch(uri, auth, headers, json):
	"""
	Make a PATCH request against a mwa2 server to replace one or more keys 
	returning the result as JSON or None
	"""
	try:
		request = requests.patch(uri, auth=auth, headers=headers, json=json)
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


def getClient(server, mwa2_user, mwa2_pass, headers, path, ext):
	"""
	Requests a client manifest from a MWA2 server that may or may not exist.
	"""
	logging.debug('getClient args: {}'.format(locals()))
	credentials = (mwa2_user, mwa2_pass)
	serial = getSerial()
	file_name = serial + ext
	logging.debug("Looking for client with filename: {}".format(file_name))
	uri = server + '/' + path + file_name
	request = serverGet(uri, credentials, headers)
	if request is not None:
		return request, path + file_name
	logging.info("Client matching filename not found on server.")
	return None, None


def getRoles(server, mwa2_user, mwa2_pass, headers, role_dirs):
	"""
	Returns all the manifests matching the path filters defined in the 
	'RepoIncludedManifestPaths' array on a MWA2 server.
	"""
	logging.debug('getRoles args: {}'.format(locals()))
	credentials = (mwa2_user, mwa2_pass)
	roles = {}
	request = serverGet(server, credentials, headers,
						{'api_fields': 'filename'})
	if request is not None:
		logging.debug("Received roles from server: {}".format(request))
		matches = [i['filename'] for i in request if any(
			[True for filter in role_dirs if i['filename'].startswith(filter)])]
		logging.debug("Manifests matching config path filters: "
						"{}".format(matches))
		for manifest in matches:
			logging.debug("Requesting role manifest from the server: "
							"{}".format(manifest))
			uri = server + '/' + manifest
			roles[manifest] = serverGet(uri, credentials, headers)
	return roles


def createClient(server, mwa2_user, mwa2_pass , headers, path, ext,
					user, hostname, role, catalog, write_host):
	"""Creates a new client manifest on a MWA2 server."""
	logging.debug('createClient args: {}'.format(locals()))
	checkHostname(hostname)
	credentials = (mwa2_user, mwa2_pass)
	serial = getSerial()
	file_name = serial + ext
	uri = server + '/' + path + file_name
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
		data['hostname'] = hostname
	if serverPost(uri, credentials, headers, data):
		return path + file_name
	return None


def updateClient(server, mwa2_user, mwa2_pass, headers, path, ext, user, 
					hostname):
	"""
	Updates hostname or username fields for a client manifest on a MWA2
	server.
	"""
	logging.debug('updateClient args: {}'.format(locals()))
	client = getClient(server=server, mwa2_user=mwa2_user, mwa2_pass=mwa2_pass,
						headers=headers, path=path, ext=ext)
	if not client[0]:
		onError(34)
	data = {}
	if user:
		data["user"] = user
	if hostname:
		checkHostname(hostname)
		data["hostname"] = hostname
	logging.debug("New client keys: {}".format(data))
	clientId = getClientId()
	uri = server + '/' + clientId
	request = serverPatch(uri=uri, auth=(mwa2_user, mwa2_pass), headers=headers,
							json=data)
	return request


def setHostname(hostname):
	"""Sets the computer hostname across all available fields"""
	for i in ('HostName', 'LocalHostName', 'ComputerName'):
		logging.info('Setting {} to "{}"...'.format(i, hostname))
		try:
			subprocess.call(['/usr/sbin/scutil', '--set', i, hostname])
		except subprocess.CalledProcessError as e:
			logging.error("Rename subprocess error:\n{}".format(e))
			onError(51, i)


def writeClientId(identifier):
	"""
	Write the client manifest path to the ClientIdentifier key in the munki
	configuration file. 
	"""
	if getPreference('secure_munki_plist'):
		plist = munkilib.munkicommon.SecureManagedInstallsPreferences()
	else:
		plist = munkilib.munkicommon.ManagedInstallsPreferences()
	logging.debug("Writing {} to {}".format(identifier, plist))
	plist['ClientIdentifier'] = identifier


def getClientId():
	if getPreference('secure_munki_plist'):
		plist = munkilib.munkicommon.SecureManagedInstallsPreferences()
	else:
		plist = munkilib.munkicommon.ManagedInstallsPreferences()
	return plist['ClientIdentifier']


def removeLaunchAgent():
	"""Removes the launch agent that runs the EnrollGUI app at boot."""
	try:
		os.remove('/Library/LaunchAgents/com.company.munki.EnrollGUI.plist')
	except:
		pass
	

def reboot():
	"""
	Removes the EnrollGUI launch agent, configures munki to run an update check
	at the next boot, blocking login and restarts the computer immediately.
	"""
	removeLaunchAgent()
	if getPreference('munki_installatstartup'):
		f = open('/Users/Shared/.com.googlecode.munki.checkandinstallatstartup', 
					'w')
		f.close()
	time.sleep(5)
	dummy_retcode = subprocess.call(['/sbin/shutdown', '-r', 'now'])


def handleArguments():
	"""
	Parse command line arguments and execute the function defined in the 
	sub-command verb.
	"""
	parser = argparse.ArgumentParser(
		description="""Enroll a computer with a munki server or update existing 
			system information on the server.""")
	subparsers = parser.add_subparsers(help='sub-command help')
	parser.add_argument('-v', '--version',
						action='version',
						version='%(prog)s ' + version)
	
	parser_gc = subparsers.add_parser('get-client', help=sub_help['get-client'])
	for arg in ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'ext', 'path'):
		parser_gc.add_argument(*arguments[arg]['parser_flags'],
								**arguments[arg]['parser_kwargs'])
	parser_gc.set_defaults(func=getClient)
	
	parser_gr = subparsers.add_parser('get-roles', help=sub_help['get-roles'])
	for arg in ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'role_dirs'):
		parser_gr.add_argument(*arguments[arg]['parser_flags'],
								**arguments[arg]['parser_kwargs'])
	parser_gr.set_defaults(func=getRoles)
	
	parser_c = subparsers.add_parser('create', help=sub_help['create'])
	for arg in ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'ext', 'path', 
				'role', 'hostname', 'user', 'catalog', 'write_host'):
		parser_c.add_argument(*arguments[arg]['parser_flags'],
								**arguments[arg]['parser_kwargs'])
	parser_c.set_defaults(func=createClient)
	
	parser_u = subparsers.add_parser('update', help=sub_help['update'])
	for arg in ('server', 'mwa2_user', 'mwa2_pass', 'headers', 'user', 
				'hostname', 'path', 'ext'):
		parser_u.add_argument(*arguments[arg]['parser_flags'],
								**arguments[arg]['parser_kwargs'])
	parser_u.set_defaults(func=updateClient)
	
	args = parser.parse_args()
	args = vars(args)
	func = args.pop('func')
	for key, value in args.items():
		if value is None and key not in ('user'):
			args[key] = getPreference(key)
	logging.debug("about to call function {} with args: {}".format(func,args))
	func(**args)


def main():
	"""Run as a command line program"""
	handleArguments()
	

if __name__ == "__main__":
	main()