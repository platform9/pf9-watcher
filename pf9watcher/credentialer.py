#!/usr/bin/env python

import sys
import getpass
import pickle
import json
import crypto

if (len(sys.argv) + 1) > 1:
    # If the encrypted properties file doesn't exist
    # build the file
    # Build a new object to store session information
    session_info = {}
    # The next block of code asks for all of the info we need
    # to run this script
    if 1 < len(sys.argv):
        session_info['identityApiEndpoint'] = sys.argv[1]
    else:
        session_info['identityApiEndpoint'] = raw_input('Keystone API URL: ')
    if 2 < len(sys.argv):
        session_info['osUsername'] = sys.argv[2]
    else:
        session_info['osUsername'] = raw_input('OpenStack Username: ')
    if 3 < len(sys.argv):
            session_info['osPassword'] = sys.argv[3]
    else:
        session_info['osPassword'] = getpass.getpass('OpenStack Password: ')
    if 4 < len(sys.argv):
        session_info['osTenant'] = sys.argv[4]
    else:
        session_info['osTenant'] = raw_input('OpenStack Tenant: ')
    if 5 < len(sys.argv):
        session_info['osRegion'] = sys.argv[5]
    else:
        session_info['osRegion'] = raw_input('OpenStack Region: ')
    # Convert the properties to a json string and encrypt them
    encrypt_properties = crypto.crypt(
        json.dumps(session_info),
        'encrypt',
        ''
    )
    # Open the file we will store the encrypted properties in
    properties_file = 'encryptedProperties.pkl'
    with open(properties_file, 'wb') as output:
        # Write the encrypted properties to the file
        pickle.dump(
            encrypt_properties,
            output,
            pickle.HIGHEST_PROTOCOL)

else:
    print 'Please provide parameters: Keystone endpoint, username, ' + \
          'password, tenant, and region.'
