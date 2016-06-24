#!/usr/bin/env python

import os, sys, time, logging, getpass, pickle, json
import crypto # This is actually crypto.py that must be in the same directory as this script.
from daemon import Daemon
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client as ksclient
from novaclient import client as nclient

# The location where we will store the encrypted properties
propertiesFile = '%s/encryptedProperties.pkl' %( os.getcwd() )
logpath = 'log/'
logfile = 'log/pf9-watcher.log'
if os.path.exists( logpath ):
	logging.basicConfig( filename=logfile, format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO )
else:
	os.makedirs( logpath )
	logging.basicConfig( filename=logfile, format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO )

def body():
	if (os.path.isfile(propertiesFile)):

		# Open the file we stored teh encrypted properties in
		with open(propertiesFile, 'rb') as input:
		  # Retrieve Encrypted Properties
		  encryptedProperties = pickle.load(input)
		# Decrypt the encrypted properties
		decryptedProperties = crypto.crypt(encryptedProperties['string'], 'decrypt', encryptedProperties['secret'])
		# Load the decrypted properties into sessionInfo
		sessionInfo = json.loads(decryptedProperties['string'])

		logging.info('checking hypervisor status')
		
		keystoneversion = 2
		novaversion = 2

		auth = v2.Password( auth_url=sessionInfo['identityApiEndpoint'], username=sessionInfo['osUsername'], password=sessionInfo['osPassword'], tenant_name=sessionInfo['osTenant'] )
		sess = session.Session( auth=auth )

		keystone = ksclient.Client(session=sess)

		nova = nclient.Client( novaversion, session=sess, region_name=sessionInfo['osRegion'], connection_pool=True )

		h_list = nova.hypervisors.list( detailed=True )
		# print h_list

		for hypervisor in h_list:
			if hypervisor.state == "down":
				# print "here"
				print hypervisor.hypervisor_hostname  
				# print hypervisor.state
				down_list = nova.hypervisors.search( hypervisor.hypervisor_hostname, servers=True )
				for down in down_list:
					logging.error( '%s: oh no im in trouble' , hypervisor.hypervisor_hostname )
					if hasattr( down, 'servers' ):
						# print down.servers
						for server in down.servers:
							# print server
							resp = nova.servers.evacuate( server['name'], host=None, on_shared_storage=True )
							logging.info( 'evacuating server: %s from host: %s', server['uuid'], down.hypervisor_hostname )
							print "evacuating server: %s from host: %s" %( server['uuid'], down.hypervisor_hostname )
					else: logging.warning( '%s: at least im not running any servers' , hypervisor.hypervisor_hostname )
			else:
				logging.info( '%s: alls good in the hood b', hypervisor.hypervisor_hostname )
	else:
		logging.error('missing properties file')
	return

class PF9WatcherDaemon(Daemon):
	def run(self):
		# logging.info('starting pf9-watcher')
		while True:
			body()
			time.sleep(60)

if __name__ == "__main__":
	daemon = PF9WatcherDaemon('/tmp/pf9-watcher.pid')
	if len(sys.argv) == 2:
		if 'start' == sys.argv[1]:
			# If the encrypted properties file doesn't exist, build the file
			if not (os.path.isfile(propertiesFile)):
				# Build a new object to store session information
				sessionInfo = {}
				# The next block of code asks for all of the info we need to run this script
				sessionInfo['identityApiEndpoint'] = raw_input( 'Keystone API URL:  ' ) 
				sessionInfo['osUsername'] = raw_input( 'OpenStack Username:  ' )
				sessionInfo['osPassword'] = getpass.getpass( 'OpenStack Password:  ' )
				sessionInfo['osTenant'] = raw_input( 'OpenStack Tenant:  ' )
				sessionInfo['osRegion'] = raw_input( 'OpenStack Region:  ' )
				
				# Convert the properties to a json string and encrypt them
				encryptProperties = crypto.crypt(str(json.dumps(sessionInfo)), 'encrypt', '') 
				# Open the file we will store the encrypted properties in
				with open(propertiesFile, 'wb') as output:
					# Write the encrypted properties to the file
					pickle.dump(encryptProperties, output, pickle.HIGHEST_PROTOCOL)

			logging.info('starting pf9-watcher')
			daemon.start()
		elif 'stop' == sys.argv[1]:
			logging.info('stopping pf9-watcher')
			daemon.stop()
		elif 'restart' == sys.argv[1]:
			logging.info('re-starting pf9-watcher')
			daemon.restart()
		else:
			logging.warning('Unknown command')
			print "unknown command"
			sys.exit(2)
		sys.exit(0)
	else:
		print "usage: %s start|stop|restart" % sys.argv[0]
		sys.exit(2)

