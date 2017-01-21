#!/usr/bin/env python

import argparse
import ConfigParser
import datetime
import os
import time
import logging

from oslo_utils import timeutils
from keystoneauth1.identity import v2
from keystoneauth1 import session
import novaclient
from novaclient import client as nclient


class Watcher(object):
    """Ensure VM high availability across OpenStack hypervisors.

    Monitors the OpenStack Nova service on hypervisors, detects compute
    failures, and reschedules placement of affected VMs on remaining compute
    nodes.
    """

    def __init__(self, config_file):
        """Construct a new 'Watcher' object."""
        super(Watcher, self).__init__()

        self.active_migration_states = frozenset([
            'accepted',
            'migrating',
            'pre-migrating',
            'running'
        ])

        self.completed_migration_states = frozenset([
            'completed',
            'done',
            'finished'
        ])

        try:
            config = self.read_config(config_file)

            self.logfile = config['watcher']['logfile']

            if 'logdir' in config['watcher']:
                self.logdir = config['watcher']['logdir']
            else:
                self.logdir = ''

        except IOError as exp:
            logging.error(exp)
            raise exp

        # Setup logging
        self.initialize_logging()

        try:
            auth = v2.Password(
                auth_url=config['keystone']['endpoint'],
                username=config['keystone']['username'],
                password=config['keystone']['password'],
                tenant_name=config['keystone']['project_id'])
            sess = session.Session(auth=auth)
        except Exception as exp:
            logging.error('Failure creating Keystone API client.')
            logging.error(str(exp))

        # Build Nova client
        try:
            self.nova = nclient.Client(
                2,
                session=sess,
                region_name=config['keystone']['region'])
        except Exception as exp:
            logging.error('Failure creating Nova API client.')
            logging.error(str(exp))

    @staticmethod
    def read_config(config_file):
        """Read configuration file.

        :param config_file: Configuration file in INI format
        :type config_file: str
        :returns: Config file in hash format
        :rtype: dict
        """
        if not os.path.isfile(config_file):
            raise Exception(
                'Unable to read config file %s' % config_file
            )

        config = ConfigParser.SafeConfigParser()
        config.read(config_file)

        return config._sections

    def run(self):
        """Run Watcher program."""
        logging.info('Starting pf9-watcher.')

        while True:
            logging.debug('Checking hypervisor status.')

            down_hypervisors = self.get_down_hypervisors()

            for hypervisor in down_hypervisors:
                hv_info = self.get_hypervisor_servers(
                    hypervisor_id=hypervisor.id,
                    hostname=hypervisor.hypervisor_hostname
                )

                # Skip processing if hypervisor is not running any servers
                if not hasattr(hv_info, 'servers') or \
                   not hasattr(hv_info, 'service'):
                    continue

                # Evacuate VMs from hypervisor
                evacuation_time = timeutils.utcnow(with_timezone=True) \
                    .replace(microsecond=0)
                self.evacuate_hypervisor(hv_info)
                time.sleep(5)

                # List of servers to migrate from hypervisor
                migrating_servers = set([s['uuid'] for s in hv_info.servers])
                retries = 0
                max_retries = 10
                while migrating_servers and retries <= max_retries:

                    migrations = self.get_hypervisor_migrations(
                        hypervisor=hypervisor.service['host'],
                        after=evacuation_time
                    )

                    # Retain list of actively migrating VMs
                    actively_migrating = False
                    for migration in migrations:
                        if migration.status in self.active_migration_states:
                            actively_migrating = True

                        # If migration is complete
                        if (migration.instance_uuid in migrating_servers) and \
                            (migration.status in
                             self.completed_migration_states):
                            try:
                                self.nova.servers.start(
                                    migration.instance_uuid)
                            except Exception as exp:
                                logging.error(exp)
                            else:
                                migrating_servers.remove(
                                    migration.instance_uuid)

                    if actively_migrating:
                        retries += 1
                        time.sleep(10)
                    else:
                        # Break out of while loop
                        break

                if migrating_servers:
                    error_msg = 'Failed migrating instances %s from %s'
                    logging.error(
                        error_msg,
                        ', '.join(migrating_servers),
                        hypervisor.service['host']
                    )

            time.sleep(60)

    def evacuate_hypervisor(self, hypervisor):
        """Evacuate VMs on hypervisor.

        :param hypervisor: Nova hypervisor object
        :type hypervisor: novaclient.v2.hypervisors.Hypervisor
        :rtype: None
        """
        logging.error('Hypervisor %s is down', hypervisor.hypervisor_hostname)
        logging.error(
            'Evacuating %s VMs from %s',
            len(hypervisor.servers),
            hypervisor.service['host']
        )

        for server in hypervisor.servers:
            logging.info(
                'Evacuating server %s from host %s',
                server['uuid'],
                hypervisor.hypervisor_hostname
            )

            try:
                self.nova.servers.evacuate(server['uuid'])
            except Exception as exp:
                error = 'Unable to evacuate server %s from ' + \
                    'host %s.'
                logging.error(
                    error,
                    server['uuid'],
                    hypervisor.hypervisor_hostname
                )
                logging.error(str(exp))

    def initialize_logging(self):
        """Initialize logger."""
        # Create parent log directories
        if bool(self.logdir) and not os.path.exists(self.logdir):
            os.makedirs(self.logdir)

        # Create logger
        logging.basicConfig(
            filename=os.path.join(self.logdir, self.logfile),
            format='%(asctime)s %(levelname)s:%(message)s',
            level=logging.INFO)

    def get_down_hypervisors(self):
        """Retrieve list of downed hypervisors.

        :returns: List of downed hypervisors
        :rtype: list of novaclient.v2.hypervisors.Hypervisor objects
        """
        try:
            h_list = self.nova.hypervisors.list()
        except Exception as exp:
            logging.error('Unable to retrieve hypervisor list from Nova.')
            logging.error(str(exp))
            return list()

        down_hypervisors = [h for h in h_list if h.state != 'up']

        return down_hypervisors

    def get_hypervisor_migrations(self, hypervisor, after=None):
        """
        Return list of sever migration events from given hypervisor.

        :param hypervisor: OpenStack Hypervisor name
        :param after: Datetime to only select migrations created after
            this date.
        :type hypervisor: str
        :type after: datetime.datetime
        :returns: List of active migrations from hypervisor
        :rtype: list of novaclient.v2.migrations.Migration objects
        """
        migrations_list = self.nova.migrations.list(hypervisor)

        if after and isinstance(after, datetime.datetime):
            # Remove old / completed migrations
            migrations = []
            for migration in migrations_list:
                created_at = timeutils.parse_isotime(migration.created_at)
                if created_at >= after:
                    migrations.append(migration)

            return migrations
        else:
            return migrations_list

    def get_hypervisor_servers(self, hypervisor_id, hostname):
        """
        Return list of servers on hypervisor.

        :param hypervisor_id: OpenStack Hypervisor ID
        :param hostname: OpenStack Hypervisor hostname
        :type hypervisor_id: int
        :type hostname: str
        :returns: Nova Hypervisor object
        :rtype: novaclient.v2.hypervisors.Hypervisor or None
        """
        try:
            result = self.nova.hypervisors.search(
                hypervisor_match=hostname,
                servers=True)
        except novaclient.exceptions.NotFound as exp:
            return None
        except Exception as exp:
            logging.error(exp)
            return None

        for server in result:
            if server.id == hypervisor_id:
                return server


def main():
    """Main entry point."""
    # Parse CLI args
    parser = argparse.ArgumentParser(description='Watcher CLI arguments.')
    parser.add_argument(
        '--config-file',
        '-c',
        dest='config_file',
        default='/opt/pf9/etc/watcher_config.ini',
        metavar='FILE',
    )
    args = parser.parse_args()

    # Instantiate Watcher object
    watcher = Watcher(config_file=args.config_file)

    # Run service
    watcher.run()


if __name__ == '__main__':
    main()
