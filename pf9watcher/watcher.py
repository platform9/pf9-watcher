#!/usr/bin/env python

import os
import time
import logging
import pickle
import json

# This is actually crypto.py that must be in the same directory as this script.
import crypto
from keystoneauth1.identity import v2
from keystoneauth1 import session
from keystoneclient.v2_0 import client as ksclient
from novaclient import client as nclient

def watcher():
    # The location where we will store the encrypted properties
    properties_file = '/opt/pf9/pf9-watcher/pf9watcher/encryptedProperties.pkl'
    logpath = '/var/log/pf9'
    logfile = '/var/log/pf9/pf9-watcher.log'
    if not os.path.exists(logpath):
        os.makedirs(logpath)
        logging.basicConfig(
            filename=logfile,
            format='%(asctime)s %(levelname)s:%(message)s',
            level=logging.INFO)
        logging.info('starting pf9-watcher')
    else:
        logging.basicConfig(
            filename=logfile,
            format='%(asctime)s %(levelname)s:%(message)s',
            level=logging.INFO)
        logging.info('starting pf9-watcher')

    while True:
        body(properties_file)
        time.sleep(60)

def body(properties_file):
    if os.path.isfile(properties_file):
        # Open the file we stored the encrypted properties in
        with open(properties_file, 'rb') as p_file:
            # Retrieve Encrypted Properties
            encrypted_properties = pickle.load(p_file)
        # Decrypt the encrypted properties
        decrypted_properties = crypto.crypt(
            encrypted_properties['string'],
            'decrypt',
            encrypted_properties['secret'])

        # Load the decrypted properties into session_info
        session_info = json.loads(decrypted_properties['string'])

        # logging.info( 'decrypted session data: %s', session_info )
        logging.info('checking hypervisor status')

        # keystoneversion = 2
        novaversion = 2
        try:
            auth = v2.Password(
                auth_url=session_info['identityApiEndpoint'],
                username=session_info['osUsername'],
                password=session_info['osPassword'],
                tenant_name=session_info['osTenant'])
            sess = session.Session(auth=auth)
            keystone = ksclient.Client(session=sess)
        except Exception, e:
            logging.error('error creating keystone session')
            logging.error(str(e))

        try:
            nova = nclient.Client(
                novaversion,
                session=sess,
                region_name=session_info['osRegion'],
                connection_pool=True)
        except Exception, e:
            logging.error('error creating nova session')
            logging.error(str(e))

        try:
            h_list = nova.hypervisors.list(detailed=True)
        except Exception, e:
            logging.error('error getting hypervisor list from nova')
            logging.error(str(e))

        try:
            for hypervisor in h_list:
                if hypervisor.state == "down":
                    # print "here"
                    print hypervisor.hypervisor_hostname
                    # print hypervisor.state
                    down_list = nova.hypervisors.search(
                        hypervisor.hypervisor_hostname,
                        servers=True)
                    for down in down_list:
                        logging.error('%s: oh no im in trouble', hypervisor.hypervisor_hostname)
                        if hasattr(down, 'servers'):
                            # print down.servers
                            for server in down.servers:
                                # print server
                                try:
                                    resp = nova.servers.evacuate(
                                        server['name'],
                                        host=None,
                                        on_shared_storage=True
                                    )
                                    logging.info(
                                        'evacuating server: %s from host: %s',
                                        server['uuid'],
                                        down.hypervisor_hostname
                                    )
                                    print "evacuating server: %s from host: %s" \
                                          % (server['uuid'], down.hypervisor_hostname)
                                except Exception, e:
                                    logging.error(
                                        'error evacuating server: %s from host: %s',
                                        server['uuid'],
                                        down.hypervisor_hostname
                                    )
                                    logging.error(str(e))
                            time.sleep(60)
                            try:
                                for server in down.servers:
                                    result = None
                                    timeout = 0
                                    while result is None:
                                        if timeout < 10:
                                            try:
                                                result = nova.servers.start(server['name'])
                                            except Exception, e:
                                                timeout = timeout + 1
                                                logging.error('error restarting server: %s', server['uuid'])
                                                logging.error(str(e))
                                                time.sleep(5)
                                                pass
                                        else:
                                            result = 'break'
                                            logging.error(
                                                'error could not restart server: %s',
                                                server['uuid'])
                            except Exception as e:
                                logging.error(
                                    'error looping through server list')
                                logging.error(str(e))
                        else:
                            logging.warning(
                                '%s: at least im not running any servers',
                                hypervisor.hypervisor_hostname)
                else:
                    logging.info(
                        '%s: alls good in the hood b',
                        hypervisor.hypervisor_hostname
                    )
        except Exception, e:
            logging.error('error looping through hypervisor list')
            logging.error(str(e))
    else:
        logging.error('missing properties file')
    return

watcher()