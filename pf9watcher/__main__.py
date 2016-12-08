#!/usr/bin/env python

import os, sys, time, logging, getpass, pickle, json
import crypto # This is actually crypto.py that must be in the same directory as this script.
from daemon import Daemon
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client as ksclient
from novaclient import client as nclient
def watcher():
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
			try:
				auth = v2.Password( auth_url=sessionInfo['identityApiEndpoint'], username=sessionInfo['osUsername'], password=sessionInfo['osPassword'], tenant_name=sessionInfo['osTenant'] )
				sess = session.Session( auth=auth )
				keystone = ksclient.Client(session=sess)
			except Exception,e:
				logging.error( 'error creating keystone session' )
				logging.error( str(e) )
			
			try:
				nova = nclient.Client( novaversion, session=sess, region_name=sessionInfo['osRegion'], connection_pool=True )
			except Exception,e:
				logging.error( 'error creating nova session' )
				logging.error( str(e) )

			try:
				h_list = nova.hypervisors.list( detailed=True )
			except Exception,e:
				logging.error( 'error getting hypervisor list from nova' )
				logging.error( str(e) )

			try:
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
									try:
										resp = nova.servers.evacuate( server['name'], host=None, on_shared_storage=True )
										logging.info( 'evacuating server: %s from host: %s', server['uuid'], down.hypervisor_hostname )
										print "evacuating server: %s from host: %s" %( server['uuid'], down.hypervisor_hostname )
									except Exception,e:
										logging.error( 'error evacuating server: %s from host: %s', server['uuid'], down.hypervisor_hostname )
										logging.error( str(e) )
								time.sleep(60)
								try:
									for server in down.servers:
										result = None
										timeout = 0
										while result is None:
											if timeout < 10:
												try:
													result = nova.servers.start( server['name'] )
												except Exception,e:
													timeout = timeout + 1
													logging.error( 'error restarting server: %s', server['uuid'] )
													logging.error( str(e) )
													time.sleep(5)
													pass
											else:
												result = 'break'
												logging.error( 'error could not restart server: %s', server['uuid'] )
								except:
										logging.error ( 'error looping through server list' )
										logging.error( str(e) )
							else: logging.warning( '%s: at least im not running any servers' , hypervisor.hypervisor_hostname )
					else:
						logging.info( '%s: alls good in the hood b', hypervisor.hypervisor_hostname )
			except Exception,e:
				logging.error( 'error looping through hypervisor list' )
				logging.error( str(e) )			
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
		if len(sys.argv) >= 2:
			if 'start' == sys.argv[1]:
				# If the encrypted properties file doesn't exist, build the file
				if not (os.path.isfile(propertiesFile)):
					# Build a new object to store session information
					sessionInfo = {}
					# The next block of code asks for all of the info we need to run this script
					if sys.argv[2] is not None:
						sessionInfo['identityApiEndpoint'] = sys.argv[2]
					else:
						sessionInfo['identityApiEndpoint'] = raw_input( 'Keystone API URL:  ' )
					if sys.argv[3] is not None:
						sessionInfo['osUsername'] = sys.argv[3]
					else:
						sessionInfo['osUsername'] = raw_input( 'OpenStack Username:  ' )
					if sys.argv[4] is not None:
						sessionInfo['osPassword'] = sys.argv[4]
					else:
						sessionInfo['osPassword'] = getpass.getpass( 'OpenStack Password:  ' )
					if sys.argv[5] is not None:
						sessionInfo['osTenant'] = sys.argv[5]
					else:
						sessionInfo['osTenant'] = raw_input( 'OpenStack Tenant:  ' )
					if sys.argv[6] is not None:
						sessionInfo['osRegion'] = sys.argv[6]
					else:
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

watcher()
